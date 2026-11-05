"""Read actual Unit references and emit an explicit avatar/model name map."""
import csv,hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'tools'))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import append_unit,append_bones,load_manifest,bone_name_hash
from verify_native_v8_grip import records,read
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
def detail(fid,raw):
    u=UnitData.parse(raw)
    return {'id':f'{fid:016x}','bonesID':str(u.bones_ref),'bonesHex':f'{u.bones_ref:016x}','stateMachineID':str(u.state_machine_ref),'unitNodes':len(u.transforms),'sha256':hashlib.sha256(raw).hexdigest()}
m=load_manifest(P/'source-skeleton.json');profile=json.loads((P/'attachment-profile.json').read_text());mp=json.loads((W/'o3-mapping.json').read_text())
models=[];model_units={}
for patch in (P/'models-o3').rglob('*.patch_0'):
    f,rs=records(patch)
    try:
        for r in rs:
            if r[1]!=UNIT_TYPE_ID:continue
            raw=read(f,r);models.append(detail(r[0],raw));model_units[f'{r[0]:016x}']=UnitData.parse(raw)
    finally:f.close()
store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'));original={}
for package in (mp['armorArchive'],mp['helmetArchive']):
    arc=TocArchive.load_toc_only(store,package)
    for row in mp['mappings']:
        fid=int(row['targetUnit'],16);entry=arc.entries.get((fid,UNIT_TYPE_ID))
        if entry:original[row['targetUnit']]=detail(fid,entry.toc_data)
raw=(B/'avatar.toc').read_bytes();extended=append_unit(raw,m);eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m));eu=UnitData.parse(extended)
names=dict(zip(eb.hashes,eb.names))
for row in profile['vpk']:
    if row.get('standardName'):names[bone_name_hash(row['standardName'])]=row['standardName']
for row in m['bones']+m.get('motionLayers',[]):names[row['hash']]=row['name']
rows=[]
for row in profile['vpk']:
    if row['standardName'] not in ('attach_weapon','attach_hand_l','attach_hand_r'):continue
    node=m['bones'][row['sourceAnchorIndex']];model_positions={fid:u.name_hashes.index(node['hash']) for fid,u in model_units.items() if node['hash'] in u.name_hashes}
    rows.append({'standardName':row['standardName'],'standardAvatarIndex0':row['index'],'sourceAnchorName':node['name'],'sourceVpkName':node['sourceName'],'sourceHashDecimal':node['hash'],'sourceAvatarIndex0':eu.name_hashes.index(node['hash']),'sourceModelIndices0':model_positions,'sourceReferenceName':row['sourceReferenceName'],'sourceReferenceAvatarIndex0':row['sourceReferenceIndex'],'policy':row['policy'],'axisCorrection':row['axisCorrection']})
out=P/'bone-names';out.mkdir(exist_ok=True)
(out/'avatar-and-source-bonehash.txt').write_text(''.join(f'{h} {name}\n' for h,name in sorted(names.items())),encoding='utf-8')
with (out/'attachment-bone-map.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
sdk=Path(r'C:\Users\Administrator\AppData\Roaming\Blender Foundation\Blender\4.2\scripts\addons\HD2SDK-AQ-Edition')
evidence={}
for filename,needles in [('stingray/unit.py',('self.BonesRef != 0',"skeletonObj['BonesID']",'Global_BoneNames.get(h, str(h))','This unit does not have any animated bone data')),('__init__.py',("bones_id = int(armature['BonesID'])",))]:
    path=sdk/filename;lines=path.read_text(encoding='utf-8-sig').splitlines();evidence[str(path)]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'matches':[{'line':i+1,'text':line.strip()} for i,line in enumerate(lines) if any(n in line for n in needles)]}
avatar_id=5556372446766824087
report={'status':'PASS','gameTested':False,'blenderLiveVerified':False,'originalO3Units':list(original.values()),'modelUnits':models,'baseAvatar':detail(avatar_id,raw),'extendedAvatar':detail(avatar_id,extended),'animationBoneNames':len(eb.names),'handMappings':rows,'sdkSourceEvidence':evidence,'interpretation':'Model Unit BonesID is an external animation/name-resource reference, not a bone identifier. Keep the subordinate model reference; inspect animations on the matching shared avatar. Display names also depend on the SDK in-memory hash dictionary. Changing model BonesID alone cannot correct weapon timing or IK.'}
assert len(original)==len({r['targetUnit'] for r in mp['mappings']})
assert eu.bones_ref==avatar_id
assert all(r['bonesID']=='0' for r in models)
(W/'bones-id-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('sdkSourceEvidence','modelUnits','originalO3Units')},ensure_ascii=False,indent=2))
