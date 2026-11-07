"""Validate control-safe single policy on real clips; writes only new audit artifacts."""
import copy,json,math,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_single_elbow_torso as a
p=a.p;s=a.single
index=a.ResourceIndex(a.PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')))
db=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
_,e=index.resolve(s.REFERENCE_UNIT,a.UNIT_TYPE_ID);n=a.UnitData.parse(e.toc_data)
_,e=index.resolve(n.bones_ref,a.BONE_TYPE_ID);b=a.BonesData.parse(e.toc_data)
folder=a.DEST/'model-fixed-final/test07';units=list(s.model_units(folder));m=units[0][1]
standard=s._read_standard_config(a.OUT/'config.toml');cert=s._validate_bind(folder,units)
c,deltas=s._compose_config(s._derive_calibration(units,n,b),standard,n,b)
digest=s._write_effective_config(folder/'single-config.toml',c,deltas)
marker=s._standard_manifest(folder,cert,units,b,c,standard,digest)
(folder/'single-skeleton.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding='utf-8')
bi={name:i for i,name in enumerate(b.names)};ni={h:i for i,h in enumerate(n.name_hashes)};mi={h:i for i,h in enumerate(m.name_hashes)}
report=dict(status='RUNNING',version=s.PIPELINE_VERSION,model=str(folder),config=str(folder/'single-config.toml'),helpers={},clips=[],gameTested=False)
for name in s.CONTROL_MARKERS:
 if name not in bi:continue
 h=b.hashes[bi[name]];x,y=n.transforms[ni[h]],m.transforms[mi[h]]
 report['helpers'][name]=dict(positionError=math.dist(x.position,y.position),rotationError=a.angle(x.rotation,y.rotation),offset=c.offsets.get(name))
 assert report['helpers'][name]['positionError']<2e-5
 assert report['helpers'][name]['rotationError']<.01
 assert max(abs(v) for v in c.offsets.get(name,[0,0,0]))==0
ids=[int(row['id'],16) for row in json.loads((a.OUT/'test07-单骨架-手臂文件核查.json').read_text(encoding='utf-8'))['realClipSamples']]
ids += [0x4bc9a2411115d455,0x13f9d73ad1b76729,0x3b314d1755fda426]
for fid in dict.fromkeys(ids):
 _,e=index.resolve(fid,a.ANIMATION_TYPE_ID);raw=e.toc_data;source=a.AnimationData.parse(raw);out=copy.deepcopy(source)
 stats=p.modify_animation_with_world_compensation(out,b,n,c,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True,preserve_unmodified_channels=True,source_arm_constraints=True)
 gt=a.tracks(a.AnimationData.parse(out.to_bytes()));ot=a.tracks(source)
 times=sorted(set([0.,source.animation_length*1000,*p._build_bake_times(p._last_transform_time(source)),*(float(e.time) for e in source.entries if e.is_rotation)]))
 row=dict(id=f'{fid:016x}',additive=source.is_additive,unchangedBytes=out.to_bytes()==raw,ikEvaluations=stats.ik_evaluations,armTargetProjections=stats.arm_target_projections,armRequestedTargetMaxDistance=stats.arm_requested_target_max_distance,torsoMax=0.,arms={})
 for name in a.TORSO:
  if name not in bi:continue
  i=bi[name];maximum=max(a.angle(ot[1][i].evaluate(t),gt[1][i].evaluate(t)) for t in times)
  row['torsoMax']=max(row['torsoMax'],maximum)
 assert row['torsoMax']<.05,(row['id'],row['torsoMax'])
 if not source.is_additive:
  for side in ['l','r']:
   hh=[b.hashes[bi[side+'_'+name]] for name in ['shoulder','elbow','hand']]
   arm=dict(maxBendError=0.,maxAnatomicalPlaneError=0.)
   for t in times:
    nl,nworld=a.state(n,b,ot,t);ml,mworld=a.state(m,b,gt,t)
    np=[nworld[ni[h]].position for h in hh];mp=[mworld[mi[h]].position for h in hh]
    nv=[a.vec_sub(np[1],np[0]),a.vec_sub(np[2],np[1])];mv=[a.vec_sub(mp[1],mp[0]),a.vec_sub(mp[2],mp[1])]
    nb,mb=a.vangle(*nv),a.vangle(*mv);arm['maxBendError']=max(arm['maxBendError'],abs(nb-mb))
    if nb>20 and mb>20:
     plane=a.vangle(a.quat_inverse_rotate(nworld[ni[hh[0]]].rotation,a.cross(*nv)),a.quat_inverse_rotate(mworld[mi[hh[0]]].rotation,a.cross(*mv)))
     arm['maxAnatomicalPlaneError']=max(arm['maxAnatomicalPlaneError'],plane or 0.)
   row['arms'][side]=arm
 report['clips'].append(row);print(json.dumps(row),flush=True)
 (a.DEST/'fix-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
index.close();report['status']='OFFLINE_VERIFIED_GAME_PENDING';(a.DEST/'fix-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
