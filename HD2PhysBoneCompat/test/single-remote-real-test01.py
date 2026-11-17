"""Current test01 Units/rigs with accepted solver + controlled engine callbacks.
These are output/call-count controls, NEVER actual multiplayer FPS measurements.
"""
from pathlib import Path
import argparse, ast, collections, copy, hashlib, importlib, json, math, os, runpy, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--variant',choices=['A','B'],required=True);args=ap.parse_args()
OUT=args.output.resolve();assert OUT.is_relative_to(ROOT);NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
os.chdir(ROOT);os.environ['LOCALAPPDATA']=str(OUT);os.environ['APPDATA']=str(OUT)
sys.path[:0]=[str(NORMAL),str(ROOT.parent.parent),str(ROOT/'tools')]
from lupa.lua51 import LuaRuntime
from anim_batch_mod.math3d import quat_rotate, quat_multiply
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.processor import _calculate_world_transforms
H=runpy.run_path(str(ROOT/'tools/audit_test06_vrd_skirt.py'),run_name='read_only_helpers');table=H['table'];py=H['py']
tree=ast.parse((ROOT/'HD2PhysBoneCompat/test/spring-dof-model-test.py').read_text('utf-8-sig'))
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='engine'],type_ignores=[]),'pure-current-unit-engine','exec'),globals())
engine0=engine
MODEL=NORMAL/'test-library/[单骨架模型]test01/sectional';models=H['units'](MODEL/'9ba626afa44a3aa3.patch_0')
assert len(models)==7
baseline=(OUT/'baseline-r2-compat.lua').read_text('utf8');candidate=(OUT/(args.variant+'-source')/'physbone_compat.lua').read_text('utf8')
checks=0

def check(value,message):
 global checks
 checks+=1
 if not value:raise AssertionError(message)

def group(code,players,variant=None):
 lua=LuaRuntime(unpack_returned_tuples=True);C=lua.execute(code)
 rig=C.parse_rig((MODEL/'physbone-rig.bin').read_bytes());rig.drivers=C.parse_driver_rig((MODEL/'physbone-driver-rig.bin').read_bytes())
 rig_before=copy.deepcopy(py(rig));instances=[];wrap=lua.eval('function(fn)return function(...)return fn(...)end end')
 for player in range(1,players+1):
  for rid,model in models.items():
   e=engine0(lua,copy.deepcopy(model),rid);S=e[0]
   lua.eval('function(U)local node=U.node;U.node=function(u,h)return node(u,h)+1 end;for _,k in ipairs({"local_pose","local_rotation","world_position","world_rotation","set_local_rotation","set_local_pose"})do local f=U[k];U[k]=function(u,n,...)return f(u,n-1,...)end end end')(S.Unit)
   counts=collections.Counter();trace=[]
   for name,fn in list(S.Unit.items()):
    if callable(fn):
     def counted(*values,_fn=fn,_name=name,_counts=counts,_trace=trace):
      _counts['Unit.'+_name]+=1
      if _name in ['set_local_pose','set_local_rotation']:_trace.append((_name,int(values[1]),py(values[-1])))
      return _fn(*values)
     S.Unit[name]=wrap(counted)
   fn=S.World.update_unit
   def flush(*values,_fn=fn,_counts=counts):_counts['World.update_unit']+=1;return _fn(*values)
   S.World.update_unit=wrap(flush)
   options=e[2];options.fastWrite=True;options.vrdSkeletonOnly=True
   session=C.attach(S,e[1],rig,options);session=session[0] if isinstance(session,tuple) else session
   session.ownerOrder=player;session.singleMainline=True
   if variant:
    remote=player>1;session.singleRemoteBaseEvaluateDrivers=True
    C.single_remote_policy_transition(session,remote and variant=='A',remote)
    session.evaluateDrivers=not remote
   check(len(session.sessions)==12,'current Unit must retain its full 12-chain rig')
   check(len(session.drivers)==6 and session.excludedWristDrivers==2,'accepted six VRD drivers/two wrist exclusions changed')
   counts.clear();trace.clear();e[5]['writes'].clear()
   instances.append(dict(player=player,resource=rid,env=e,session=session,counts=counts,trace=trace,p=copy.deepcopy(e[3]),q=copy.deepcopy(e[4])))
 # The accepted attach path annotates rig.bones with derived bind caches.
 # Freeze AFTER attach; compare these annotations against the baseline below.
 check(py(rig.drivers)==rig_before['drivers'],'VRD authored records were mutated at attach')
 return lua,C,rig,copy.deepcopy(py(rig)),instances

reports=[]
for players in [1,2,4]:
 a=group(baseline,players);b=group(candidate,players,args.variant)
 check(py(a[2])==py(b[2]),'new policy changed accepted attach-derived rig caches')
 for frame in range(1,121):
  for lua,C,rig,rig_before,items in [a,b]:
   C.begin_frame(frame)
   for row in items:
    e=row['env'];s=row['session'];row['trace'].clear()
    # Same deterministic animated world input for each engine, with actual binds.
    for node in range(len(e[3])):
     e[3][node][:]=[row['p'][node][0]+.003*math.sin(frame*.04),row['p'][node][1]+.002*math.cos(frame*.03),row['p'][node][2]]
     e[4][node][:]=quat_multiply([math.sin(.04*math.sin(frame*.05)),0,0,math.cos(.04*math.sin(frame*.05))],row['q'][node])
    if not s.singleRemotePhysicsExcluded:s.singleRemoteHadUpdate=True
    C.update(s,1/120)
  for aa,bb in zip(a[4][:7],b[4][:7]):
   check(aa['trace']==bb['trace'],'LOCAL output pose trace changed')
   check(py(aa['session'].sessions)==py(bb['session'].sessions),'LOCAL spring numeric state changed')
   check(py(aa['session'].drivers)==py(bb['session'].drivers),'LOCAL VRD numeric state changed')
 for aa,bb in zip(a[4][:7],b[4][:7]):check(aa['counts']==bb['counts'],'LOCAL engine calls/cadence changed')
 check(py(b[2])==b[3],'shared rig mutated by a remote per-session flag')
 remote=b[4][7:]
 if args.variant=='A':
  check(all(not r['counts'] for r in remote),'A performed engine calls during excluded remote updates')
  check(all((r['session'].tipApplied or 0)==0 and (r['session'].driverWrites or 0)==0 for r in remote),'A performed remote springs/VRD')
 else:
  check(all(r['session'].tipApplied==120 for r in remote),'B did not preserve remote physical solver cadence')
  check(all((r['session'].driverWrites or 0)==0 for r in remote),'B wrote a remote VRD driver')
  nodes=lambda r:{int(row.node)-1 for row in r['session'].drivers.values()}
  check(all(not (set(r['env'][5]['writes']) & nodes(r)) for r in remote),'B wrote a remote driver node through a spring path')
  baseline_remote=sum(r['counts']['Unit.world_rotation'] for r in a[4][7:]);candidate_remote=sum(r['counts']['Unit.world_rotation'] for r in remote)
  if remote:check(candidate_remote<baseline_remote,'B did not eliminate remote VRD control reads')
 total=collections.Counter();local_calls=collections.Counter()
 for r in b[4]:total.update(r['counts'])
 for r in b[4][:7]:local_calls.update(r['counts'])
 report=dict(players=players,units=players*7,fullChains=players*84,variant=args.variant,measuredControlledFrames=120,actualGameFps=False,
             remoteTipUpdates=sum((r['session'].tipApplied or 0) for r in remote),remoteDriverWrites=sum((r['session'].driverWrites or 0) for r in remote),
             totalEngineCallbackCounts=dict(total),localEngineCallbackCounts=dict(local_calls))
 reports.append(report);print(json.dumps(report),flush=True)

# Once-only hand-back from previously active UNKNOWN -> known remote is tested
# separately. It must not leave a stale driven helper or re-run disabled time.
_,C,rig,rig_before,items=group(candidate,2,None)
r=items[7];s=r['session'];s.singleMainline=True;s.singleRemoteBaseEvaluateDrivers=True
for frame in range(1,31):C.begin_frame(frame);s.singleRemoteHadUpdate=True;C.update(s,1/120)
driver_history=s.driverWrites or 0
r['counts'].clear();C.single_remote_policy_transition(s,args.variant=='A',True);s.evaluateDrivers=False
returned=r['counts'].copy();r['counts'].clear();r['env'][5]['writes'].clear()
for frame in range(31,61):C.begin_frame(frame);C.update(s,1/120)
if args.variant=='A':check(not r['counts'],'A repeated engine work after one-time release')
else:check(driver_history>0 and (s.driverWrites or 0)==driver_history and (s.driverWrittenFrame or 0)==0,'B must retain earlier VRD history but write zero new drivers')
check(py(rig)==rig_before,'transition modified the shared rig')
C.single_remote_policy_transition(s,False,False);s.evaluateDrivers=True;s.pendingDt=0;C.begin_frame(61);C.update(s,1/120)
check(s.tipApplied>0 and s.singleRemotePhysicsExcluded is False and s.singleRemoteVrdExcluded is False,'solver/VRD failed to resume')
report={'status':'PASS_CURRENT_REAL_TEST01_CONTROLLED_ENGINE_NOT_FPS','variant':args.variant,'checks':checks,'results':reports,
        'transitionOneTimeCallbackCounts':dict(returned),'currentModelUnits':7,'chainCountPerUnit':12,'rigSharedAndUnmodifiedByRemotePolicy':True,
        'localOutputAndStateExactlyPreserved':True,'gameNotRun':True,'modelsNotWritten':True}
(OUT/(args.variant+'-real-test01-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('PASS real test01 '+args.variant+': '+str(checks)+' exact/state/gate checks',flush=True)
