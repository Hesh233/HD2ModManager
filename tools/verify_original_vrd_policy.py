"""VRD policy checks: real original units, stale records/cache, and controlled skeleton fixtures."""
from pathlib import Path
import sys,json,copy,io,contextlib,runpy,importlib.util,hashlib,math
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physical-original-vrd-guard-20261111';OLD=ROOT/'outputs/test1201-source2-accepted-20261111';sys.path[:0]=[str(ROOT/'tools'),str(ROOT.parents[1]),str(ROOT/'outputs/test1201-source-response-20261111')]
import numpy as np
import audit_test06_vrd_skirt as a
from lupa.lua51 import LuaRuntime
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_rotate,quat_multiply,quat_conjugate
spec=importlib.util.spec_from_file_location('guard_source_reference',OLD/'verify.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
new=(OUT/'formal/physbone_compat.lua').read_text('utf8');old=(OUT/'before/HD2PhysBoneCompat/src/physbone_compat.lua').read_text('utf8');cfg=json.loads((ROOT/'outputs/test1201-source2-live-rejection-20261111/source-profile.json').read_text('utf8'));model=a.INSTALL/'test-library/test1201';units=a.units(model/'Overwrite/9ba626afa44a3aa3.patch_0');records=a.container_records(model/'Overwrite/9ba626afa44a3aa3.patch_0.gpu_resources');checks=0

def check(ok,msg):
 global checks;checks+=1
 if not ok:raise AssertionError(msg)
def py(t):return a.py(t)
def parsed(vm):
 m=vm.execute(new);r=m.parse_rig(records['hd2_spring_rig.bin']);return m,r[0] if isinstance(r,tuple) else r
# Production policy itself is metadata-only and preserves current real skeleton contracts.
vm=LuaRuntime(unpack_returned_tuples=True);m=vm.execute(new);rows=[]
for p in (a.INSTALL/'test-library').iterdir():
 if not p.is_dir():continue
 for gpu in p.glob('**/*.patch_0.gpu_resources'):
  if gpu.parent.name not in ('vpk2patch','Overwrite'):continue
  r=a.container_records(gpu)
  if not r or 'hd2_spring_rig.bin' not in r or 'hd2_driver_rig.bin' not in r:continue
  rig=m.parse_rig(r['hd2_spring_rig.bin']);rig=rig[0] if isinstance(rig,tuple) else rig;dr=m.parse_driver_rig(r['hd2_driver_rig.bin']);rig.drivers=dr[0] if isinstance(dr,tuple) else dr
  allowed,reason=m.vrd_skeleton_contract(rig);check(allowed,'existing skeleton '+p.name+' '+str(reason));rows.append(dict(model=p.name,folder=gpu.parent.name,version=rig.drivers.version,contract=reason));break
# Generic native helper exercises real driver ownership/cache machinery.
fixture=ROOT/'HD2PhysBoneCompat/test/driver-update-test.py';text=fixture.read_text('utf8').replace('1.3.3','1.3.4');original=Path.read_text
def read_candidate(p,*args,**kwargs):return new if p.resolve()==ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua' else original(p,*args,**kwargs)
# Executing with a single namespace preserves module globals for Python closures.
namespace={'__name__':'guard_fixture','__file__':str(fixture)};Path.read_text=read_candidate
try:
 with contextlib.redirect_stdout(io.StringIO()):exec(compile(text,str(fixture),'exec'),namespace)
finally:Path.read_text=original
lm,compat,S,state,base=(namespace[k] for k in ['lua','compat','S','state','rig']);strict=lm.table_from(dict(world=lm.table(),fastWrite=False,vrdSkeletonOnly=True));native=compat.attach(S,lm.table(),base,strict);check(len(native.drivers)==1,'native retains helper driver');state['rot_writes'].clear();state['control_q']=[0,0,math.sqrt(.5),math.sqrt(.5)];compat.update_tip(native,1/60);check(any(r[0]==64 for r in state['rot_writes']),'native driver writes under production gate')
# Current original test1201, including accidental legacy/v3 driver records and stale cache.
originalRows=[];springBaseline={};maxSpringParity=0
for rid in cfg['units']:
 if rid in units:
  vm0=LuaRuntime(unpack_returned_tuples=True);mod0=vm0.execute(old);r0=mod0.parse_rig(records['hd2_spring_rig.bin']);r0=r0[0] if isinstance(r0,tuple) else r0;e0=v.engine(vm0,units[rid],rid,cfg['units'][rid],False);session0=mod0.attach(e0[0],e0[1],r0,e0[2])
  for f in range(1,16):e0[5]['time']=f/60;mod0.begin_frame(f);mod0.update(session0,1/60)
  springBaseline[rid]=[(t.rotation.copy(),t.position.copy()) for t in e0[3]]
for rid in cfg['units']:
 if rid not in units:continue
 profile=cfg['units'][rid]
 for case in ['no-driver','bare-v1','bare-v2','malformed-v3','scoped-v3-on-original']:
  vm=LuaRuntime(unpack_returned_tuples=True);mod,rig=parsed(vm);rig=py(rig)
  if case!='no-driver':
   dr=copy.deepcopy(cfg['rig']['drivers'])
   if case in ['bare-v1','bare-v2']:dr['version']=1 if case=='bare-v1' else 2;[b.pop('controlBindQ',None) for b in dr['bones']]
   if case=='malformed-v3':dr['bones'][0]['controlBindQ']=[0,0,0,0]
   rig['drivers']=dr
  eng=v.engine(vm,units[rid],rid,profile,False);s,u,opt,local,world,state,logs,refresh=eng;opt.vrdSkeletonOnly=True
  # Warm a legacy attach cache deliberately; strict attach may not resurrect its driver rows.
  if case in ['bare-v1','bare-v2']:
   warm=v.engine(vm,units[rid],rid,profile,False);mod.attach(warm[0],warm[1],a.table(vm,rig),warm[2])
  session=mod.attach(s,u,a.table(vm,rig),opt)
  check(session.test1201Source is None,'original not selected scoped '+rid+case);check(len(session.drivers)==0,'zero original driver rows '+rid+case)
  before=[];springNodes={n-1 for item in session.sessions.values() for n in item.nodes.values()};driverNodes={units[rid].name_hashes.index(a.bone_name_hash(r['name'])) for r in profile['records'] if r['kind']==2 and a.bone_name_hash(r['name']) in units[rid].name_hashes}
  for frame in range(1,16):state['time']=frame/60;mod.begin_frame(frame);mod.update(session,1/60);check(set(state['writes'])<=springNodes,'only spring writers '+rid+case)
  check(len(state['writes'])>0,'spring physics remains active '+rid+case)
  parity=max(float(np.max(np.abs(np.array(x)-np.array(y)))) for t,ref in zip(local,springBaseline[rid]) for x,y in zip((t.rotation,t.position),ref));maxSpringParity=max(maxSpringParity,parity);check(parity<1e-9,'original springs identical to previous no-VRD baseline '+rid+case)
  check(not (set(state['writes'])&driverNodes),'no original VRD writer '+rid+case);check(mod.update_drivers(session,1/60)==0,'direct driver call blocked '+rid+case);check(state['invalid']==0,'no invalid engine nodes')
  state['writes'].clear();mod.release(session);check(not (set(state['writes'])&driverNodes),'release owns no original driver '+rid+case)
  originalRows.append(dict(resource=rid,case=case,contract=session.vrdContract,springs=len(springNodes),driverRows=0,driverWrites=0))
# Controlled Source2 bind fixture reconstructed from the frozen profile, not claimed as a raw old UNIT.
def reconstruct(u,profile):
 unit=copy.deepcopy(u);fixed={}
 for rec in profile['records']:unit.parents[rec['node']-1]=rec['parentNode']-1 if rec['parentNode']>0 else None
 def matrix(q,p):
  out=np.eye(4);out[:3,:3]=np.column_stack([quat_rotate(q,axis) for axis in np.eye(3)]);out[:3,3]=p;return out
 def add(node,m):
  i=node-1
  if i in fixed:check(np.max(np.abs(fixed[i]-m))<3e-5,'consistent captured bind matrices')
  else:fixed[i]=m
 for r in profile['canonical']+profile['records']:add(r['node'],matrix(r['targetBindQ'],r['targetBindP']))
 for r in profile['records']:
  if r['parentNode']>0:add(r['parentNode'],matrix(r['targetBindQ'],r['targetBindP'])@np.linalg.inv(matrix(r['targetLocalQ'],r['targetLocalP'])))
 world={}
 def calc(i):
  if i in world:return world[i]
  if i in fixed:world[i]=fixed[i];return world[i]
  t=unit.transforms[i];parent=unit.parents[i];local=matrix(t.rotation,t.position);world[i]=calc(parent)@local if parent is not None else local;return world[i]
 for i in range(len(unit.transforms)):calc(i)
 for i,matrixWorld in fixed.items():
  parent=unit.parents[i];local=np.linalg.inv(world[parent])@matrixWorld if parent is not None else matrixWorld;t=unit.transforms[i];t.rotation=list(a.qm(local));t.position=local[:3,3].tolist();t.scale=[1,1,1]
 return unit
rid='34a40a5ae7a392ba';profile=cfg['units'][rid];trusted=reconstruct(units[rid],profile);tests=[]
for code,label in [(old,'accepted2.3.3'),(new,'candidate2.3.4')]:
 vm=LuaRuntime(unpack_returned_tuples=True);mod=vm.execute(code);eng=v.engine(vm,trusted,rid,profile,False);S,u,opt,local,world,state,logs,refresh=eng;opt.vrdSkeletonOnly=True;session=mod.attach(S,u,a.table(vm,cfg['rig']),opt)
 if session.test1201Source is None:print('\n'.join(logs[-6:]));raise AssertionError('trusted Source2 fixture not selected '+label)
 poses=[];initial=copy.deepcopy(local)
 for frame in range(1,61):
  for c in profile['canonical']:
   if c['targetName'] in ('hips','l_thigh','r_thigh'):
    i=c['node']-1;angle=.18*math.sin(frame*.1);q=[math.sin(angle/2),0,0,math.cos(angle/2)];local[i].rotation=quat_multiply(initial[i].rotation,q)
    if c['targetName']=='hips':local[i].position=(np.array(initial[i].position)+np.array([frame*.004,0,0])).tolist()
  refresh();state['time']=frame/60;mod.begin_frame(frame);mod.update(session,1/60);poses.append([(t.rotation.copy(),t.position.copy()) for t in local]);check((session.driverWrites or 0)>0,'scoped retains VRD '+label)
 check(session.excludedWristDrivers==2,'wrist exclusions retained '+label);check(mod.release(session)==58,'scoped restores exactly 58 '+label);tests.append(poses)
maxError=max(float(np.max(np.abs(np.array(a)-np.array(b)))) for pa,pb in zip(tests[0],tests[1]) for ta,tb in zip(pa,pb) for a,b in zip(ta,tb));check(maxError<1e-9,'scoped output parity')
result=dict(status='PASS_POLICY_OFFLINE_NOT_GAME_ACCEPTANCE',checks=checks,originalFormatCases=originalRows,existingSkeletonContracts=rows,controlledScopedFrames=60,controlledScopedMaxElementError=maxError,originalSpringMaxElementError=maxSpringParity,source2FixtureReconstructedFromCapturedBind=True,actualOriginalUnitsReadOnly=True,sourceJiggleUnchanged=True,gameDeployed=False)
(OUT/'policy-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8');print(json.dumps({k:v for k,v in result.items() if k not in ['originalFormatCases','existingSkeletonContracts']},ensure_ascii=False,indent=2));print('original cases',len(originalRows),'skeleton contracts',len(rows))
