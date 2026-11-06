"""One-off model-only mount experiment; immutable source, no Lua/animation edits."""
import argparse, copy, hashlib, json, math, shutil, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'native-python'))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import bone_name_hash, UNIT_TYPE_ID
from anim_batch_mod.processor import WorldTransform, _calculate_world_transforms
from anim_batch_mod.attachment_skeleton import _local_under
from anim_batch_mod.motion_skeleton import matrix
from anim_batch_mod.math3d import quat_multiply, quat_rotate


def pose_from_matrix(values):
    # Reuse the production matrix/quaternion decoder rather than inventing axes.
    from anim_batch_mod.native_skeleton import row_pose
    return row_pose([values[0], values[1], values[2], 0,
                     values[3], values[4], values[5], 0,
                     values[6], values[7], values[8], 0, 0, 0, 0, 1])


def compose(a, b):
    offset=quat_rotate(a.rotation,[x*y for x,y in zip(a.scale,b.position)])
    return WorldTransform([x+y for x,y in zip(a.position,offset)],
                          quat_multiply(a.rotation,b.rotation),[x*y for x,y in zip(a.scale,b.scale)])


def descendant_set(parents, roots):
    result=set(roots)
    while True:
        added={i for i,p in enumerate(parents) if p in result}-result
        if not added:return result
        result |= added


def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def rewrite_unit(raw, profile, manifest, weighted_indices):
    unit=UnitData.parse(raw);n=len(unit.parents);before=_calculate_world_transforms(unit.transforms,unit.parents)
    lookup={h:i for i,h in enumerate(unit.name_hashes)}
    if len(lookup)!=n:raise ValueError('Duplicate model node hash')
    def index(name):return lookup[bone_name_hash(name)]
    names={bone_name_hash(x['name']):x['name'] for x in manifest['bones']}
    names.update({x['hash']:x['name'] for x in profile['avatar']['nodes']})
    for x in profile['attachments']:
        for key in ('node','native','source'):names[x[key]['hash']]=x[key]['name']
    def label(i):return names.get(unit.name_hashes[i],f'hash_{unit.name_hashes[i]:08x}')
    protected=descendant_set(unit.parents,{index('head'),index(next(b['name'] for b in manifest['bones'] if b.get('driver')=='head'))})
    rows={x['node']['name']:x for x in profile['attachments']}
    rows['attach_hand_r']={'node':profile['target'],'source':profile['sourceRight'],'native':profile['nativeRight']}
    mounts={index(name):name for name in rows}
    if set(mounts)&protected:raise ValueError('Head descendants in mount allowlist')
    local=copy.deepcopy(unit.transforms);parents=list(unit.parents);desired={};edits=[]
    source_mounts={side:next(b['name'] for b in manifest['bones'] if b.get('sourceName','').lower()==name.lower())
                   for side,name in [('right','ValveBiped.weapon_bone'),('left','ValveBiped.L_weapon_bone')]}
    for i,name in mounts.items():
        row=rows[name];old_parent=parents[i]
        if old_parent in mounts and rows[mounts[old_parent]]['source']['name']==row['source']['name']:
            # Retain cape chains; only their root changes carrier.
            edits.append(dict(name=name,index=i,oldParent=label(old_parent),newParent=label(old_parent),chainPreserved=True));continue
        if name in ('attach_hand_r','attach_weapon','attach_hand_l'):
            parent=index(source_mounts['left' if name=='attach_hand_l' else 'right'])
            target=copy.deepcopy(before[parent])
        else:
            parent=index(row['source']['name'])
            anchor=compose(before[parent],pose_from_matrix(row['axes']))
            target=compose(anchor,_local_under(before[index(row['native']['name'])],before[i]))
        parents[i]=parent;desired[i]=target;local[i]=_local_under(before[parent],target)
        edits.append(dict(name=name,index=i,oldParent=label(old_parent),newParent=label(parent),
                          parentIndex=parent,chainPreserved=False))
    affected=descendant_set(parents,set(desired))
    if affected & protected:raise ValueError('Move would affect head descendants')
    if affected & set(weighted_indices):raise ValueError('Move would affect weighted mesh nodes: '+str(sorted(affected & set(weighted_indices))))
    after=_calculate_world_transforms(local,parents)
    for i in range(n):
        if i not in affected and (distance(before[i].position,after[i].position)>1e-7 or parents[i]!=unit.parents[i]):
            raise ValueError('Unexpected non-mount change')
    at=struct.unpack_from('<I',raw,52)[0];block=bytearray(raw[at:at+16+136*n])
    for i in desired:block[16+64*i:16+64*(i+1)]=struct.pack('<16f',*matrix(local[i]))
    for i in affected:
        start=16+64*n+64*i;block[start:start+64]=struct.pack('<16f',*matrix(after[i],True))
    for i in desired:struct.pack_into('<H',block,16+128*n+4*i+2,parents[i] if parents[i] is not None else 65535)
    output=bytearray(raw);output.extend(bytes(-len(output)%16));struct.pack_into('<I',output,52,len(output));output.extend(block)
    checked=UnitData.parse(output);final=_calculate_world_transforms(checked.transforms,checked.parents)
    assert checked.name_hashes==unit.name_hashes and checked.parents==parents
    for i in desired:
        if distance(final[i].position,desired[i].position)>1e-5:raise ValueError('Float32 bind mismatch')
    for i in protected:
        if checked.parents[i]!=unit.parents[i] or distance(final[i].position,before[i].position)>1e-5:
            raise ValueError('Head changed')
    # No Lua: independently move the Source wrist and the native wrist.
    right=index('attach_hand_r');src=index(profile['sourceRight']['name']);native=index('r_hand')
    def move(i):
        poses=copy.deepcopy(checked.transforms);poses[i].position[0]+=.02
        return _calculate_world_transforms(poses,checked.parents)[right].position
    source_move=distance(move(src),final[right].position);native_move=distance(move(native),final[right].position)
    if source_move<.019 or native_move>1e-6:raise ValueError('Static mount does not follow Source wrist independently')
    return bytes(output),dict(nodes=n,mounts=len(edits),roots=len(desired),edits=edits,
        weightedNodesUntouched=len(weighted_indices),headDescendantsUntouched=len(protected),
        sourceWristMovesMount=source_move,nativeWristMovesMount=native_move,noLuaUsed=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--profile',required=True)
    p.add_argument('--skin-audit',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();source=Path(a.source).resolve();output=Path(a.output).resolve()
    if output.exists():raise ValueError('Choose a new output directory')
    if source==output or source in output.parents or output in source.parents:raise ValueError('Source/output overlap')
    profile=json.loads(Path(a.profile).read_text(encoding='utf-8-sig'))
    manifest=json.loads((source/'source-skeleton.json').read_text(encoding='utf-8-sig'))
    skins={r['resource']:{x['index'] for x in r['weightedNodes']} for r in json.loads(Path(a.skin_audit).read_text(encoding='utf-8-sig'))['rows']}
    sections=json.loads((source/'sections.json').read_text(encoding='utf-8-sig'))
    head_ids={int(r['fileId'],16) for r in sections['units'] if r['slot']=='Helmet'}
    output.mkdir(parents=True)
    for path in source.iterdir():
        if path.is_file():shutil.copyfile(path,output/path.name)
    patch=source/'9ba626afa44a3aa3.patch_0';raw=patch.read_bytes()
    archive=TocArchive.parse_parts(raw,load_external_data=False);result=bytearray(raw);reports=[]
    type_count,file_count=struct.unpack_from('<II',raw,4)
    for j in range(file_count):
        record=72+32*type_count+80*j;file_id,type_id=struct.unpack_from('<QQ',raw,record)
        if type_id!=UNIT_TYPE_ID:raise ValueError('Model patch contains unexpected resource type')
        entry=archive.entries[(file_id,type_id)]
        if file_id in head_ids:
            reports.append(dict(resource=f'{file_id:016x}',headUnitUnchanged=True));continue
        new,report=rewrite_unit(bytes(entry.toc_data),profile,manifest,skins[f'{file_id:016x}'])
        result.extend(bytes(-len(result)%16));offset=len(result);result.extend(new)
        struct.pack_into('<Q',result,record+16,offset);struct.pack_into('<I',result,record+56,len(new))
        reports.append(dict(resource=f'{file_id:016x}',**report))
    struct.pack_into('<Q',result,32,len(result));(output/patch.name).write_bytes(result)
    actual=TocArchive.parse_parts(result,load_external_data=False)
    for file_id in head_ids:assert actual.entries[(file_id,UNIT_TYPE_ID)].toc_data==archive.entries[(file_id,UNIT_TYPE_ID)].toc_data
    untouched=[x for x in source.iterdir() if x.is_file() and x.name!=patch.name]
    assert all(x.read_bytes()==(output/x.name).read_bytes() for x in untouched)
    report=dict(status='PASS',scope='model-only-static-parent-experiment',source=str(source),output=str(output),
        originalSourceUnmodified=True,noLuaChanges=True,noAvatarChanges=True,noAnimationChanges=True,
        wholeGpuStreamAndPhysBoneTrailerPreserved=True,headUnitsUnchanged=sorted(f'{x:016x}' for x in head_ids),units=reports)
    (output/'static-mount-model-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='units'},ensure_ascii=False))
    print('body units',len(reports)-len(head_ids),'mounts per body',next(r['mounts'] for r in reports if 'mounts' in r))

if __name__=='__main__':main()
