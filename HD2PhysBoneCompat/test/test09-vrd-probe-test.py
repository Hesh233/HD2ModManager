"""Probe is observation only: compare accepted axis1 numeric traces and read budgets."""
from pathlib import Path
import copy,json,math,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools'))
import numpy as np
from lupa.lua51 import LuaRuntime
import audit_test06_vrd_skirt as a
from build_test09_axis_test import sha,save
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.math3d import quat_multiply
OUT=ROOT/'outputs/test09-chr654-vrd-followup-20261110';AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110'
E=ROOT/'outputs/test09-chr654-front-skirt-analysis-20261110'
checks=0

def check(ok,label):
 global checks
 checks+=1
 if not ok:raise AssertionError(label)

def main():
 path=E/'replay_gpu_skin.py';text=path.read_text('utf8');prefix=text[:text.index('results={};outputs=')]
 env={'__file__':str(path),'__name__':'test09_probe_fixture'};exec(compile(prefix,str(path),'exec'),env)
 L=env['lua'];old=L.execute((AXIS/'physbone_compat-test09.lua').read_bytes());new=L.execute((OUT/'physbone_compat-test09.lua').read_bytes())
 results=[];traces=[];row_logs=[]
 for label,mod in [('accepted-axis1',old),('read-only-probe',new)]:
  env['M']=mod;session,local,getworld,calls,logs=env['fixture']();mod._fastWrite=True;trace=[]
  # 44 seconds => cap reached; varying controls and upper-body lean are input,
  # not written by this module. One known front-rule cone is held repeatedly.
  seen_helpers=set()
  for frame in range(2640):
   hip=env['unit'].name_hashes.index(bone_name_hash('hips'))
   tilt=math.radians(15)*math.sin(frame*.004)
   body_root=env['unit'].parents[hip]
   local[body_root].rotation=quat_multiply([math.sin(tilt/2),0,0,math.cos(tilt/2)],env['unit'].transforms[body_root].rotation)
   for b in env['rig']['drivers']['bones'][:2]:
    i=env['unit'].name_hashes.index(bone_name_hash(b['controlName']))
    rule=b['rules'][1]['trigger'];q=b['controlBindQ'] if frame<120 else quat_multiply(rule,b['controlBindQ'])
    local[i].rotation=list(q)
   session.S.World.update_unit(session.world,session.unit)
   mod.update_tip(session,1/60)
   if frame%60==0:
    trace.append(dict(poses=[[t.position[:],t.rotation[:]] for t in local],calls=copy.deepcopy(calls)))
   for _,row in session.drivers.items():
    if a.angle(a.py(row.smoothedQ),a.py(row.base.bindQ))>5:seen_helpers.add(row.name)
  check(len(seen_helpers)>=2,'authored rule produces nonzero helpers '+label)
  p=env['skin'](getworld());check(np.isfinite(p).all(),'finite')
  mod.release(session)
  for i,t in enumerate(local):
   # animated base hips/thighs belong to the fake animation, helpers/springs
   # are restored by release; compare both modules in traces below.
   check(all(math.isfinite(x) for x in t.rotation),'finite release')
  traces.append(dict(trace=trace,calls=calls,end=[[t.position,t.rotation] for t in local]))
  tags=[l for l in logs if '[test09-vrdprobe]' in l or '[test09-vrdrow]' in l]
  if label=='read-only-probe':
   rows=[l for l in tags if '[test09-vrdrow]' in l];summary=[l for l in tags if 'phase=after_physics' in l]
   check(len(summary)==20 and len(rows)==120,'bounded sample and rows')
   check(all('ctrl=?' not in l for l in rows),'control labels resolved')
   check(sum(len(l.encode('utf8'))+1 for l in tags)<43000,'extra log byte cap')
   check(all('bodyPhysicsDeltaDeg=0.00000,0.00000,0.00000' in l for l in summary),'no upper body writer')
   check(any('ruleDeg=0.000' not in l and 'ruleDeg=-1.000' not in l for l in rows),'nonzero raw rule observed')
   check(new.test09ProbeOwner is None,'release clears owner')
   import re
   tilts=[float(re.search(r'leanUp=([0-9.]+)',l).group(1)) for l in summary]
   check(max(tilts)-min(tilts)>5,'animated body tilt is sampled')
   row_logs=tags
  else:check(len(tags)==0,'accepted pack logs untouched')
  results.append(dict(source=label,nonzeroHelpers=sorted(seen_helpers),writerCalls=calls,probeRecords=len(tags)))
 check(traces[0]==traces[1],'sampled control driver spring writers exact')
 # Two concurrently eligible sessions: only the first foreground session logs.
 env['M']=new
 s1,l1,w1,c1,g1=env['fixture']();s2,l2,w2,c2,g2=env['fixture']()
 for _ in range(240):new.update_tip(s1,1/60);new.update_tip(s2,1/60)
 check(s1.test09Probe.samples>0 and s2.test09Probe.samples==0,'single instance sampling')
 new.release(s1);new.update_tip(s2,1/60);check(L.eval('function(a,b)return a==b end')(new.test09ProbeOwner,s2),'ownership transfers after release')
 new.release(s2)
 env['M']=new;dead,_,_,_,_=env['fixture']();dead.dead='dead';dead.test09Probe.elapsed=2
 dead.S.Unit.world_rotation=L.eval('function()error("dead pose read")end')
 check(new.update_tip(dead,1/60)==0,'dead session guarded before probe pose reads')
 new.release(dead)
 # Underlying no-coverage API keeps original nil return, including Python arity.
 procedure=a.table(L,dict(rules=[dict(trigger=[0,0,0,1],rotation=[0,0,0,1],invTolerance=2)]))
 check(old.quatinterp(a.table(L,[1,0,0,0]),procedure)==new.quatinterp(a.table(L,[1,0,0,0]),procedure),'no-coverage return arity')
 # Unrelated current test10 rig: no added probe session/read ownership.
 install=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/test-library/[单骨架模型]test10_chr651/vpk2patch'
 r=a.py(old.parse_rig((install/'physbone-rig.bin').read_bytes()));r['drivers']=a.py(old.parse_driver_rig((install/'physbone-driver-rig.bin').read_bytes()))
 check(new.test09_axis_profile(a.table(L,r)) is None,'test10 excluded')
 (OUT/'probe-fixture.log').write_text('\n'.join(row_logs),'utf8')
 save(OUT/'probe-regression.json',dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',checks=checks,
 writerTraceEqualsAcceptedAxis1=True,upperBodyWrites=0,sampleCount=20,maxSessions=1,extraFixtureLogBytes=sum(len(l.encode('utf8'))+1 for l in row_logs),
 knownAuthoredRuleHasNonzeroOutput=True,bodyInputTiltVaried=True,deadUnitPoseReadsAvoided=True,results=results,noncoverageApiArityUnchanged=True,gameTested=False))
 print('PASS probe exact trace',checks,'checks',len(row_logs),'records')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()




