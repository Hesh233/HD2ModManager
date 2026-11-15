"""Actual Hips probe2 writes exactly match accepted axis1; bounded correct target."""
from pathlib import Path
import copy,json,math,sys,re
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import numpy as np
from lupa.lua51 import LuaRuntime
import audit_test06_vrd_skirt as a
from build_test09_axis_test import sha,save
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.math3d import quat_multiply
OUT=ROOT/'outputs/test09-chr654-hips-probe2-20261110';AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110'
E=ROOT/'outputs/test09-chr654-front-skirt-analysis-20261110';LIVE=ROOT/'outputs/test09-chr654-vrd-followup-20261110/live-probe1-2230'
checks=0

def check(ok,label):
 global checks
 checks+=1
 if not ok:raise AssertionError(label)

def main():
 path=E/'replay_gpu_skin.py';t=path.read_text('utf8');env={'__file__':str(path),'__name__':'hips_probe2_fixture'}
 exec(compile(t[:t.index('results={};outputs=')],str(path),'exec'),env)
 L=env['lua'];old=L.execute((AXIS/'physbone_compat-test09.lua').read_bytes());new=L.execute((OUT/'physbone_compat-test09.lua').read_bytes())
 model=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/test-library/[单骨架模型]test09_chr654/Overwrite/9ba626afa44a3aa3.patch_0'
 units=a.units(model);actual=units['34a40a5ae7a392ba'];doc=json.loads((LIVE/'gpu-active-hips-lod0.json').read_text('utf8'))
 env['unit']=actual;env['doc']=doc
 traces=[];records=[];summaries=[];readbudget=[]
 for label,mod in [('axis1',old),('hipsprobe2',new)]:
  env['M']=mod;session,local,getworld,calls,logs=env['fixture']();mod._fastWrite=True
  if label=='hipsprobe2':check(session.test09HipProbe is not None,'exact visible Hip selected')
  reads={'local':0,'world':0,'position':0};wrap=L.eval('function(f)return function(...)return f(...)end end')
  for field,key in [('local_pose','local'),('world_rotation','world'),('world_position','position')]:
   original=session.S.Unit[field]
   def counted(*args,fn=original,k=key):reads[k]+=1;return fn(*args)
   session.S.Unit[field]=wrap(counted)
  trace=[]
  for frame in range(2400):
   hips=actual.name_hashes.index(bone_name_hash('hips'));body_root=actual.parents[hips]
   tilt=math.radians(12)*math.sin(frame*.006)
   local[body_root].rotation=quat_multiply([math.sin(tilt/2),0,0,math.cos(tilt/2)],actual.transforms[body_root].rotation)
   for b in env['rig']['drivers']['bones'][:2]:
    i=actual.name_hashes.index(bone_name_hash(b['controlName']));rule=b['rules'][1]['trigger']
    local[i].rotation=list(b['controlBindQ'] if frame<180 or frame%600<90 else quat_multiply(rule,b['controlBindQ']))
   session.S.World.update_unit(session.world,session.unit)
   mod.update_tip(session,1/60)
   if frame%60==0:trace.append(dict(poses=[[t.position[:],t.rotation[:]] for t in local],calls=copy.deepcopy(calls)))
  mod.release(session)
  traces.append(dict(trace=trace,calls=calls,after=[[t.position,t.rotation] for t in local]));readbudget.append(dict(label=label,reads=reads))
  tags=[l for l in logs if '[test09-hipsprobe]' in l or '[test09-hipdriver]' in l or '[test09-hipspring]' in l]
  if label=='axis1':check(not tags,'accepted tags unchanged')
  else:
   bodies=[l for l in tags if 'phase=after_physics' in l];drivers=[l for l in tags if '[test09-hipdriver]' in l];springs=[l for l in tags if '[test09-hipspring]' in l]
   check(len(bodies)==16 and len(drivers)==32 and len(springs)==112,'complete bounded Hips bundles')
   check(sum(len(l.encode('utf8'))+1 for l in tags)<85000,'bounded extra log payload')
   check(all('resource=34a40a5ae7a392ba' in l for l in bodies),'correct resource identity logged')
   check(all('bodyDeltaDeg=0.00000,0.00000,0.00000' in l for l in bodies),'no body changes')
   check(all('afterVsWriteDeg=0.00000' in l for l in drivers+springs),'write readings agree')
   check(all('unreadable' not in l for l in springs+drivers),'full numeric snapshots')
   check(new.test09HipProbeOwner is None,'release clears probe owner')
   for sample in range(1,17):
    matching=[l for l in springs if f'sample={sample} ' in l]
    check(len(matching)==7,'seven fronts sample '+str(sample))
   records=tags
 check(traces[0]==traces[1],'all model poses/write calls/restore identical axis1')
 extra=sum(readbudget[1]['reads'].values())-sum(readbudget[0]['reads'].values())
 check(extra<3000,'extra reads bounded to 16 samples')
 # No helmet/root/other Hip proxy allowed, including previous probe1 target.
 exclusions=[]
 for rid in ['8a026ed4c1830deb','f479e48687a13b31','ce2f4949f14c7df0','d154442f2e33fdee']:
  env['unit']=units[rid];env['doc']=dict(doc,resource=rid);env['M']=new
  s,_,_,_,logs=env['fixture']();check(s.test09HipProbe is None,'reject non-target '+rid);new.release(s);exclusions.append(rid)
 # Name hash absent fallback only accepts exact known debug identifier.
 u=actual;env['unit']=u;env['doc']=doc;env['M']=new
 s1,_,_,_,_=env['fixture']();s2,_,_,_,_=env['fixture']()
 for _ in range(240):new.update_tip(s1,1/60);new.update_tip(s2,1/60)
 check(s1.test09HipProbe.samples>0 and s2.test09HipProbe.samples==0,'single foreground session')
 new.release(s1);new.update_tip(s2,1/60);check(L.eval('function(a,b)return a==b end')(new.test09HipProbeOwner,s2),'ownership release transfer');new.release(s2)
 # Guard before expensive observations if dead or graph no longer matches.
 dead,_,_,_,_=env['fixture']();dead.dead='dead';dead.test09HipProbe.elapsed=2
 dead.S.Unit.world_rotation=L.eval('function()error("dead pose read")end')
 check(new.update_tip(dead,1/60)==0,'dead pose guarded');new.release(dead)
 p=a.table(L,dict(rules=[dict(trigger=[0,0,0,1],rotation=[0,0,0,1],invTolerance=2)]))
 check(old.quatinterp(a.table(L,[1,0,0,0]),p)==new.quatinterp(a.table(L,[1,0,0,0]),p),'nil API result preserved')
 (OUT/'hips-probe-fixture.log').write_text('\n'.join(records),'utf8')
 save(OUT/'probe-regression.json',dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',checks=checks,writerTraceEqualsAcceptedAxis1=True,
 exactHipResource='34a40a5ae7a392ba',completeSamples=16,frontDriverRows=32,frontSpringRows=112,excludedResources=exclusions,
 extraFixtureLogBytes=sum(len(l.encode('utf8'))+1 for l in records),additionalPoseReads=extra,sampleSessionLimit=1,
 productionChanged=False,gameTested=False))
 print('PASS Hips probe2',checks,'checks',len(records),'records',extra,'extra pose reads')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()

