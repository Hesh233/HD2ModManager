"""Trace actual source-relative IK correction and short-step plane changes."""
import copy,sys,json,sqlite3,math
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
import lz4;sys.modules['utils.lz4_311']=lz4
from anim_batch_mod import processor as p,single_skeleton as s
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.math3d import quat_multiply as qm,quat_inverse as qi
from audit_single_against_normal import records,angle,OUT as INSTALL
OUT=ROOT/'outputs/test01-single-jitter-20261107'
MODEL=INSTALL/'test-library/[单骨架模型]test01/vpk2patch';PACK=INSTALL/'test-library/[单骨架动画](test01)/9ba626afa44a3aa3.patch_0'
idx=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));db=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';idx.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
_,e=idx.resolve(s.REFERENCE_UNIT,UNIT_TYPE_ID);u=UnitData.parse(e.toc_data);_,e=idx.resolve(u.bones_ref,BONE_TYPE_ID);b=BonesData.parse(e.toc_data)
cfg=p.ModConfig.load(PACK.parent/'single-config.toml');bi={name:i for i,name in enumerate(b.names)};ni={h:i for i,h in enumerate(u.name_hashes)};m=list(s.model_units(MODEL))[0][1]
rows={r[0]:r for r in records(PACK)}
excess=json.loads((OUT/'excess.json').read_text(encoding='utf-8'));ids=list(dict.fromkeys(int(c['id'],16) for c in excess[:18] if 'shoulder_twist' not in c['bone']))
ids+=list(dict.fromkeys(int(c['id'],16) for c in excess[:12]))
ids+= [0x0004fd6ec81ff21c,0x258c6e03a38bbeb2,0x932294c9532ed089,0xd999a338adf26fed]
ids=list(dict.fromkeys(ids));report={'samples':[]};real_solver=p._apply_two_bone_ik
with PACK.open('rb') as f:
 for fid in ids:
  _,e=idx.resolve(fid,ANIMATION_TYPE_ID);src=AnimationData.parse(e.toc_data);r=rows[fid];f.seek(r[2]);raw=f.read(r[7]);current=AnimationData.parse(raw)
  times=sorted(set(p._build_bake_times(p._last_transform_time(src))+[e.time for e in src.entries if (e.is_position or e.is_rotation or e.is_scale) and 0<=e.time<=p._last_transform_time(src)]))
  count=0;calls=[]
  def traced(local,parents,root,mid,hand,target,*args,**kw):
   global count
   time=times[count//len(cfg.ik_chains)];count+=1
   if b.names[[ni[h] for h in b.hashes].index(hand)] not in ['l_hand','r_hand']:return real_solver(local,parents,root,mid,hand,target,*args,**kw)
   w=p._calculate_world_transforms(local,parents,{root,mid,hand});before=list(w[root].rotation)
   la=math.dist(w[root].position,w[mid].position);lb=math.dist(w[mid].position,w[hand].position);reach=math.dist(w[root].position,target)
   bend=math.degrees(math.acos(max(-1,min(1,(reach*reach-la*la-lb*lb)/(2*la*lb)))))
   result=real_solver(local,parents,root,mid,hand,target,*args,**kw)
   w2=p._calculate_world_transforms(local,parents,{root,mid,hand});correction=qm(w2[root].rotation,qi(before))
   calls.append(dict(side='l' if hand==ni[b.hashes[bi['l_hand']]] else 'r',time=time,bend=bend,hinge=kw.get('hinge_axis'),correction=correction,deltaAngle=angle(correction,[0,0,0,1])))
   return result
  replay=copy.deepcopy(src)
  with patch.object(p,'_apply_two_bone_ik',side_effect=traced):st=p.modify_animation_with_world_compensation(replay,b,u,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True,preserve_unmodified_channels=True,source_arm_constraints=True)
  sample=dict(id=f'{fid:016x}',replayExact=replay.to_bytes()==raw,sides={},worldSteps={})
  for side in ['l','r']:
   cc=[x for x in calls if x['side']==side];pairs=[dict(fromMs=a['time'],toMs=z['time'],degrees=angle(a['correction'],z['correction']),before=a,after=z) for a,z in zip(cc,cc[1:])]
   pairs.sort(key=lambda r:r['degrees'],reverse=True);sample['sides'][side]=dict(maxCorrectionStep=pairs[0] if pairs else None,nearStraightSamples=sum(x['bend']<1 for x in cc),missingPlaneSamples=sum(x['hinge'] is None for x in cc))
  # Actual FK world rotation samples at 60Hz (not just local quaternion steps).
  tr_src=p._build_tracks(src);tr_cur=p._build_tracks(current);watched=['l_shoulder','r_shoulder','l_elbow','r_elbow','l_hand','r_hand','r_shoulder_twist','l_shoulder_twist','r_hand_twist','l_hand_twist']
  prev_src=prev_cur=None
  for time in [i*1000/60 for i in range(int(src.animation_length*60)+1)]:
   def world(tr):
    local=list(u.transforms)
    for i,h in enumerate(b.hashes):local[ni[h]]=p.WorldTransform(*(t[i].evaluate(time) for t in tr))
    return p._calculate_world_transforms(local,u.parents)
   ow,cw=world(tr_src),world(tr_cur)
   if prev_src:
    for name in watched:
     j=ni[b.hashes[bi[name]]];os,cs=angle(prev_src[j].rotation,ow[j].rotation),angle(prev_cur[j].rotation,cw[j].rotation)
     entry=sample['worldSteps'].setdefault(name,dict(maxSource=0,maxCurrent=0,maxExcess=0))
     entry['maxSource']=max(entry['maxSource'],os);entry['maxCurrent']=max(entry['maxCurrent'],cs)
     if cs-os>entry['maxExcess']:entry.update(maxExcess=cs-os,worstMs=time)
   prev_src,prev_cur=ow,cw
  report['samples'].append(sample);(OUT/'trace.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
  print(fid,'replay',sample['replayExact'],'correction',[(side,round(sample['sides'][side]['maxCorrectionStep']['degrees'],3)) for side in ['l','r']],'world',max(v['maxExcess'] for v in sample['worldSteps'].values()),flush=True)
idx.close()
