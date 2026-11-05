import json,shutil,sys,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.native_skeleton import load_manifest,bone_name_hash,row_pose
from anim_batch_mod.attachment_skeleton import source_attachment_pose
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_multiply,quat_rotate,vec_add
W=ROOT/'outputs/native-v6-20261104';P=W/'project';OLD=ROOT/'outputs/native-v5-20261103/project'
P.mkdir(exist_ok=True)
config=(OLD/'config.toml').read_text(encoding='utf-8-sig').replace('model_scale = 1.05','model_scale = 1.08').replace('align_standard_feet = true','align_standard_feet = false\ngrip_target = "configured"').replace('workers = 4','workers = 8')
(P/'config.toml').write_text(config,encoding='utf-8')
if not (P/'source').exists():
    (P/'source').mkdir();shutil.copy2(ROOT/'testvpk/test01.vpk',P/'source/test01.vpk')
m=load_manifest(P/'models/test01/source-skeleton.json');previous=load_manifest(OLD/'source-skeleton.json')
assert m['modelScale']==1.08 and m['scaleOrigin']=='source'
m['attachmentShadows']=previous['attachmentShadows']
u=UnitData.parse((ROOT/'outputs/native-fix-20261103/avatar.toc').read_bytes());b=BonesData.parse((ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes())
world=_calculate_world_transforms(u.transforms,u.parents)
profile=json.loads((OLD/'attachment-profile.json').read_text(encoding='utf-8'));rows=[]
def matrix(q,p,local=False):
    x,y,z,w=q
    r=[1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y]
    return r+list(p)+[1.,1.,1.,0.] if local else r[:3]+[0.]+r[3:6]+[0.]+r[6:]+[0.]+list(p)+[1.]
for row in profile['vpk']:
    row['translationPolicy']='Source origin scale 1.08; preserve equipment size in metres.'
    if row['standardName'] in ('aim_weapon','weapon_aim'):
        row['policy']='original-world';row['anchorReason']='Engine aim-controller input; never overwrite from late render.'
    if row['policy']=='original-world':continue
    row['policy']='source-reference'
    name=f"__hd2_attach_vpk__{m['boneNamespace']}_{row['index']:03d}"
    source=copy.deepcopy(row);pose=source_attachment_pose(world,source)
    anchor=row_pose(m['bones'][row['sourceAnchorIndex']]['world'])
    wp=vec_add(anchor.position,quat_rotate(anchor.rotation,pose.position));wq=quat_multiply(anchor.rotation,pose.rotation)
    native=next(r for r in m['attachmentShadows'] if r['index']==row['index'])
    source.update(name=name,hash=bone_name_hash(name),sourceParent=107+row['sourceAnchorIndex'],
        localMatrix=matrix(pose.rotation,pose.position,True),worldMatrix=matrix(wq,wp),maskChannel=native['maskChannel'])
    rows.append(source);row.update(sourceReferenceName=name,sourceReferenceIndex=224+len(rows))
m['sourceAttachmentShadows']=rows
assert len(rows)==24
for path in (P/'source-skeleton.json',P/'models/test01/source-skeleton.json'):
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
profile.update(version=3,expectedAvatarNodes=225+len(rows),expectedModelNodes=196,
    phaseRequirement='Select baked VPK attachment world poses in late render; do not write aim controllers.',
    blockers=['Equipment ownership remains inferred from unique pose correspondence.',
        'Procedural aim and equipment consumer timing require an in-game check.'])
(P/'attachment-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
def lua(v):
    if v is None:return 'nil'
    if isinstance(v,bool):return 'true' if v else 'false'
    if isinstance(v,(int,float)):return repr(v)
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
    return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'
runtime={k:profile[k] for k in ('version','boneNamespace','targets','vpk','signature','expectedAvatarNodes','expectedModelNodes')}
(ROOT/'HD2PhysBoneCompat/src/native_attachment_profile.lua').write_text('-- Generated test01 O-3 profile, source origin scale 1.08.\nreturn '+lua(runtime)+'\n',encoding='utf-8')
print('Prepared 29 native references, 24 VPK references, 5 untouched controllers, avatar 249.')
