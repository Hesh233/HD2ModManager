"""Measure the actual standard arm IK targets before clamping, using current config."""
import copy,json,math,sqlite3,sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_single_elbow_torso as a
p=a.p
index=a.ResourceIndex(a.PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')))
db=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
_,e=index.resolve(a.single.REFERENCE_UNIT,a.UNIT_TYPE_ID);n=a.UnitData.parse(e.toc_data)
_,e=index.resolve(n.bones_ref,a.BONE_TYPE_ID);b=a.BonesData.parse(e.toc_data)
names={n.name_hashes.index(h):name for name,h in zip(b.names,b.hashes)}
c=p.ModConfig.load(a.PACK.parent/'single-config.toml');solver=p._apply_two_bone_ik
ids=[int(row['id'],16) for row in json.loads((a.OUT/'test07-单骨架-手臂文件核查.json').read_text(encoding='utf-8'))['realClipSamples']]
report=dict(readOnlyInputs=True,clips=[])
for fid in ids:
 _,e=index.resolve(fid,a.ANIMATION_TYPE_ID);source=a.AnimationData.parse(e.toc_data)
 if source.is_additive:continue
 for multiplier in [.4,1.]:
  cfg=copy.deepcopy(c)
  for side in ['l','r']:cfg.ik_chains[side+'_hand'].target_multiplier=[multiplier,multiplier,1.]
  calls=[]
  def trace(local,parents,root,mid,hand,target,*args,**kwargs):
   if names[hand] in ['l_hand','r_hand']:
    w=p._calculate_world_transforms(local,parents);length=math.dist(w[root].position,w[mid].position)+math.dist(w[mid].position,w[hand].position);distance=math.dist(w[root].position,target)
    calls.append(dict(side=names[hand][0],targetDistance=distance,armLength=length,unreachable=distance>length,excess=max(0,distance-length)))
   return solver(local,parents,root,mid,hand,target,*args,**kwargs)
  with patch.object(p,'_apply_two_bone_ik',side_effect=trace):
   stats=p.modify_animation_with_world_compensation(copy.deepcopy(source),b,n,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True)
  row=dict(id=f'{fid:016x}',multiplier=multiplier,ikMaxErrorBefore=stats.ik_max_error_before,ikMaxErrorAfter=stats.ik_max_error_after,arms={})
  for side in ['l','r']:
   cc=[v for v in calls if v['side']==side];row['arms'][side]=dict(samples=len(cc),unreachable=sum(v['unreachable'] for v in cc),maxExcess=max(v['excess'] for v in cc),maxReachRatio=max(v['targetDistance']/v['armLength'] for v in cc))
  report['clips'].append(row);print(json.dumps(row),flush=True)
index.close();(a.DEST/'ik-targets.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
