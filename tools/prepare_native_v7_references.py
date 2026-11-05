"""Preserve configured attachment hierarchies until the runtime blend is complete."""
import copy,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import bone_name_hash,load_manifest,append_unit,append_bones
W=ROOT/'outputs/native-v7-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'

def prepare():
    m=load_manifest(P/'source-skeleton.json');profile=json.loads((P/'attachment-profile.json').read_text(encoding='utf-8-sig'))
    raw=(B/'avatar.toc').read_bytes();u=UnitData.parse(raw);b=BonesData.parse((B/'bones.toc').read_bytes())
    by_index={u.name_hashes.index(h):i for i,h in enumerate(b.hashes)}
    selected=[r for r in profile['vpk'] if r['policy'] in ('source-reference','source-blended-reference')]
    needed={r['index'] for r in selected}
    # Copy both paths to their lowest common ancestor. Shared live ancestors
    # cancel exactly, including procedural motion, without mixing live and baked poses.
    for row in selected:
        paths=[]
        for node in (row['index'],row['driverAnchorIndex']):
            path=[]
            while node is not None:path.append(node);node=u.parents[node]
            paths.append(path)
        common=next(i for i in paths[0] if i in paths[1])
        for path in paths:
            for i in path:
                if i==common:break
                needed.add(i)
    indices=sorted(needed);start=len(u.transforms)+len(m['bones'])+len(m.get('motionLayers',[]))+len(m['attachmentShadows'])
    lookup={i:start+j for j,i in enumerate(indices)}
    names={i:f"__hd2_attach_vpk__{m['boneNamespace']}_{i:03d}" for i in indices}
    offset=struct.unpack_from('<I',raw,52)[0];n=len(u.transforms)
    rows=[]
    for i in indices:
        channel=by_index.get(i);owner=channel;parent=u.parents[i]
        while owner is None:
            if parent is None:raise ValueError('No mask owner for configured attachment')
            owner=by_index.get(parent);parent=u.parents[parent]
        rows.append(dict(index=i,name=names[i],hash=bone_name_hash(names[i]),
            sourceParent=lookup.get(u.parents[i],u.parents[i]),animationChannel=channel,maskChannel=owner,
            localMatrix=list(struct.unpack_from('<16f',raw,offset+16+64*i)),
            worldMatrix=list(struct.unpack_from('<16f',raw,offset+16+64*n+64*i)),
            referenceRole='configured-local-chain'))
    m['sourceAttachmentShadows']=rows;m['attachmentReferenceMode']='blended-configured-chain'
    eu=UnitData.parse(append_unit(raw,m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
    for row in profile['vpk']:
        row['referenceIndex']=eu.name_hashes.index(bone_name_hash(row['referenceName']))
        if row not in selected:continue
        i=row['index'];anchor=row['driverAnchorIndex']
        row.update(policy='source-blended-reference',sourceReferenceName=names[i],sourceReferenceIndex=lookup[i],
            configuredAnchorIndex=lookup.get(anchor,anchor),
            configuredAnchorName=names.get(anchor,row['driverAnchorName']))
        assert u.name_hashes[anchor]==bone_name_hash(row['driverAnchorName'])
        assert eu.name_hashes[row['configuredAnchorIndex']]==bone_name_hash(row['configuredAnchorName'])
    profile.update(version=5,expectedAvatarNodes=len(eu.transforms),
        phaseRequirement='Compute relative offsets from one configured pose snapshot after blending; render weapon consumption remains unverified.')
    for path in (P/'source-skeleton.json',P/'models/test01/source-skeleton.json',P/'models-o3/test01-O3/source-skeleton.json'):
        path.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    (P/'attachment-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(status='PASS',configuredReferenceNodes=len(rows),additionalChainDrivers=[i for i in indices if i not in {r['index'] for r in selected}],
        sourceMappedAttachments=len(selected),avatarNodes=len(eu.transforms),animationChannels=len(eb.names),modelNodesUnchanged=True)
    (W/'configured-reference-layout.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':prepare()
