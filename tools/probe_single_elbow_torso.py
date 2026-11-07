"""Bounded offline probes for control-marker and off-axis arm regression."""
import copy,json,math,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_single_elbow_torso as a
p=a.p
index=a.ResourceIndex(a.PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')))
db=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
_,e=index.resolve(a.single.REFERENCE_UNIT,a.UNIT_TYPE_ID);n=a.UnitData.parse(e.toc_data)
_,e=index.resolve(n.bones_ref,a.BONE_TYPE_ID);b=a.BonesData.parse(e.toc_data)
m=list(a.single.model_units(a.MODEL))[0][1];bi={name:i for i,name in enumerate(b.names)};ni={h:i for i,h in enumerate(n.name_hashes)};mi={h:i for i,h in enumerate(m.name_hashes)}
c=p.ModConfig.load(a.PACK.parent/'single-config.toml');names=['weapon_aim','attach_hand_r','attach_hand_l','head_aim','aim_weapon','boss_aim','attach_weapon']
report=dict(inputAnimation=str(a.PACK),readOnly=True,helperBinds=[],variants=[])
nw=p._calculate_world_transforms(n.transforms,n.parents);mw=p._calculate_world_transforms(m.transforms,m.parents)
for name in names:
 if name not in bi:continue
 h=b.hashes[bi[name]];i,j=ni[h],mi[h];parent=m.parents[j];parent_name=b.names[b.hashes.index(m.name_hashes[parent])] if m.name_hashes[parent] in b.hashes else hex(m.name_hashes[parent])
 row=dict(name=name,parent=parent_name,nativeLocal=n.transforms[i].position,modelLocal=m.transforms[j].position,directionDegrees=a.vangle(n.transforms[i].position,m.transforms[j].position),localRotationDegrees=a.angle(n.transforms[i].rotation,m.transforms[j].rotation),nativeWorld=nw[i].position,modelWorld=mw[j].position)
 report['helperBinds'].append(row);print('helper',name,json.dumps(row),flush=True)
ids=[0x258c6e03a38bbeb2,0x4b63bdd288e12ec4,0x0004fd6ec81ff21c]
for fid in ids:
 _,e=index.resolve(fid,a.ANIMATION_TYPE_ID);source=a.AnimationData.parse(e.toc_data);ot=a.tracks(source)
 for variant in ['standard','withoutIK','bendFrame','handTarget1','withoutAimOffset','rotationComp']:
  cfg=copy.deepcopy(c)
  if variant=='handTarget1':
   for side in ['l','r']:cfg.ik_chains[side+'_hand'].target_multiplier=[1.,1.,1.]
  if variant=='withoutAimOffset':
   for name in names:
    if name in cfg.offsets:cfg.offsets[name]=[0.,0.,0.]
  out=copy.deepcopy(source)
  stats=p.modify_animation_with_world_compensation(out,b,n,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=variant=='rotationComp',apply_ik_correction=variant!='withoutIK',preserve_hand_bend_frame=variant=='bendFrame',preserve_source_key_times=True)
  # Compare serialized output, not transient solver values.
  gt=a.tracks(a.AnimationData.parse(out.to_bytes()));row=dict(id=f'{fid:016x}',variant=variant,ikEvaluations=stats.ik_evaluations,arms={})
  for side in ['l','r']:
   hh=[b.hashes[bi[side+'_'+name]] for name in ['shoulder','elbow','hand']];arm=dict(maxBendDifference=0.,maxAnatomicalPlaneDifference=0.,maxPlaneDifference=0.,maxElbowMovement=0.)
   for t in p._build_bake_times(p._last_transform_time(source)):
    nl,nworld=a.state(n,b,ot,t);ml,mworld=a.state(m,b,gt,t)
    np=[nworld[ni[h]].position for h in hh];mp=[mworld[mi[h]].position for h in hh]
    nv=[a.vec_sub(np[1],np[0]),a.vec_sub(np[2],np[1])];mv=[a.vec_sub(mp[1],mp[0]),a.vec_sub(mp[2],mp[1])]
    nb,mb=a.vangle(*nv),a.vangle(*mv);arm['maxBendDifference']=max(arm['maxBendDifference'],abs(nb-mb));arm['maxElbowMovement']=max(arm['maxElbowMovement'],math.dist(np[1],mp[1]))
    if nb>20 and mb>20:
     plane=a.vangle(a.cross(*nv),a.cross(*mv))
     rootplane=a.vangle(a.quat_inverse_rotate(nworld[ni[hh[0]]].rotation,a.cross(*nv)),a.quat_inverse_rotate(mworld[mi[hh[0]]].rotation,a.cross(*mv)))
     arm['maxPlaneDifference']=max(arm['maxPlaneDifference'],plane or 0)
     arm['maxAnatomicalPlaneDifference']=max(arm['maxAnatomicalPlaneDifference'],rootplane or 0)
   row['arms'][side]=arm
  if 'weapon_aim' in bi:
   i=bi['weapon_aim'];row['aimSourceLocal']=ot[0][i].evaluate(0.);row['aimOutputLocal']=gt[0][i].evaluate(0.);row['aimDirectionChange']=a.vangle(row['aimSourceLocal'],row['aimOutputLocal'])
  report['variants'].append(row);print('variant',json.dumps(row),flush=True)
  (a.DEST/'probes.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
index.close()
