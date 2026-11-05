import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.native_skeleton import load_manifest,bone_name_hash
from anim_batch_mod.formats import UnitData,BonesData
W=ROOT/'outputs/native-v5-20261103';P=W/'project';OLD=ROOT/'outputs/native-v4-20261103/project'
P.mkdir(exist_ok=True)
for name in ('models','models-o3'):
    if not (P/name).exists():shutil.copytree(OLD/name,P/name)
for name in ('config.toml','source-skeleton.json'):
    if not (P/name).exists():shutil.copy2(OLD/name,P/name)
config=(P/'config.toml').read_text(encoding='utf-8-sig')
if 'align_standard_feet' not in config:config=config.replace('model_scale = 1.05','model_scale = 1.05\nalign_standard_feet = true')
(P/'config.toml').write_text(config,encoding='utf-8')
m=load_manifest(P/'models/test01/source-skeleton.json')
u=UnitData.parse((ROOT/'outputs/native-fix-20261103/avatar.toc').read_bytes());b=BonesData.parse((ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes())
profile=json.loads((OLD/'attachment-profile-research.json').read_text(encoding='utf-8'));rows=[]
hand=next(r for r in profile['vpk'] if r['standardName']=='attach_hand_r')
for row in profile['vpk']:
    if row['standardName'] in ('attach_weapon','aim_weapon'):
        for key in ('driverAnchorIndex','driverAnchorName','sourceAnchorName','sourceAnchorIndex','axisCorrection'):
            row[key]=hand[key]
        row['anchorReason']='Follow the actual VPK right hand; retain the animated original weapon-to-hand relative pose, including stow/reload motion.'
for native,vpk in zip(profile['native'],profile['vpk']):
    ui=native['index'];mask=ui
    while u.name_hashes[mask] not in b.hashes:mask=u.parents[mask]
    name=f"__hd2_attach_original__{m['boneNamespace']}_{ui:03d}"
    rows.append(dict(index=ui,name=name,hash=bone_name_hash(name),animationChannel=native['animationChannel'],maskChannel=b.hashes.index(u.name_hashes[mask])))
    vpk.update(referenceName=name,referenceIndex=107+len(m['bones'])+len(rows)-1,
        parentIndex=u.parents[ui],sourceIndexOffset=107)
m['attachmentShadows']=rows
for path in (P/'source-skeleton.json',P/'models/test01/source-skeleton.json',P/'models-o3/test01-O3/source-skeleton.json'):
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
profile.update(version=2,runtimeEnabled=True,sceneGraphModified=True,expectedAvatarNodes=107+len(m['bones'])+len(rows),
    signature=[dict(name=n['name'],index=107+i) for i,n in enumerate(m['bones']) if n['driver'] in ('hips','head','l_hand','r_hand','l_foot','r_foot')],
    nativeSkeletonNodes=107,sourceSkeletonNodes=len(m['bones']),selectionRule='Experimental unique multi-node pose correspondence; ambiguity restores original. Not a proven equipment-owner API.',
    phaseRequirement='Late render callback plus World.update_unit; original shadow channels prevent feedback. Equipment consumer timing needs game test.',
    blockers=['Equipment identity is inferred by unique pose correspondence, not queried from a verified ownership API.',
        'Render update propagation to equipped units requires game verification.',
        'Controller-space nodes keep the original pose; per-weapon calibration is pending.'])
(P/'attachment-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
def lua(v):
    if v is None:return 'nil'
    if isinstance(v,bool):return 'true' if v else 'false'
    if isinstance(v,(int,float)):return repr(v)
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
    return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'
runtime={k:profile[k] for k in ('version','boneNamespace','targets','vpk','signature','expectedAvatarNodes')}
(ROOT/'HD2PhysBoneCompat/src/native_attachment_profile.lua').write_text('-- Generated test01 profile; indices are zero-based in data.\nreturn '+lua(runtime)+'\n',encoding='utf-8')
print('Prepared 29 original reference nodes, 29 VPK pose recipes; avatar nodes',profile['expectedAvatarNodes'])
