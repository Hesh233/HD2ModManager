"""Actual runtime + real consumer/solver/Unit payload, controlled world, NOT FPS."""
from pathlib import Path
import argparse,ast,copy,hashlib,importlib,json,os,runpy,shutil,sys,math,collections
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--vm',choices=['lua51','luajit21'],default='luajit21');ap.add_argument('--chef-bit',type=Path);ap.add_argument('--chef-patch',type=Path);ap.add_argument('--chef-core',type=Path);a=ap.parse_args();a.source=a.source.resolve();OUT=a.output.resolve();assert OUT.is_relative_to(ROOT);OUT.mkdir(parents=True,exist_ok=True)
os.environ['APPDATA']=str(OUT);os.environ['LOCALAPPDATA']=str(OUT);os.chdir(ROOT);sys.path[:0]=[str(NORMAL),str(ROOT.parent.parent),str(ROOT/'tools')]
from anim_batch_mod.math3d import quat_rotate,quat_multiply
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.native_skeleton import bone_name_hash
helper=runpy.run_path(str(ROOT/'tools/audit_test06_vrd_skirt.py'),run_name='pure_helpers');table,py,units=helper['table'],helper['py'],helper['units']
tree=ast.parse((ROOT/'HD2PhysBoneCompat/test/spring-dof-model-test.py').read_text('utf-8-sig'));exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='engine'],type_ignores=[]),'pure-engine','exec'),globals())
L=importlib.import_module('lupa.'+a.vm).LuaRuntime;lua=L(unpack_returned_tuples=True)
if a.chef_bit:
 lua.globals().bit=lua.execute(a.chef_bit.read_text('utf-8-sig'));lua.execute('package.loaded.bit=bit')
wrap=lua.eval('function(f)return function(...)return f(...)end end')
lua.globals().arg=lua.table_from({0:str(ROOT/'HD2PhysBoneCompat/test/single-mainline-regression-test.lua'),1:str(a.source/'physbone_runtime.lua'),2:str(a.source/'physbone_compat.lua'),3:'4'})
text=(ROOT/'HD2PhysBoneCompat/test/single-mainline-regression-test.lua').read_text('utf-8-sig');text=text[:text.index('-- Positive metadata gating:')]
H=lua.execute(text+'\nreturn{fakeEngine=fakeEngine,install=install,opts=opts}\n');e=H.fakeEngine();e.levels=1;e.fp=False;e.fpCalls=0
# This helper copy is only used to parse bind/rig fixture inputs. The Chef path
# below replaces it with the actual scanned module before any simulation frames.
C=lua.execute((a.source/'physbone_compat.lua').read_text('utf-8-sig'))
if C.consumer_api.proofMode=='toc-exact-palette-v2':
 C.consumer_api.hash.update=lua.eval('function()error("RENDER_SHA_FORBIDDEN")end')
 C.consumer_api.hash.digest=lua.eval('function()error("RENDER_SHA_FORBIDDEN")end')
folder=NORMAL/'test-library/[单骨架模型]test01/sectional';models=units(folder/'9ba626afa44a3aa3.patch_0');rids=list(models);rig=C.parse_rig((folder/'physbone-rig.bin').read_bytes());rig.drivers=C.parse_driver_rig((folder/'physbone-driver-rig.bin').read_bytes())
files=[];(OUT/'data').mkdir(exist_ok=True)
for i,domain in enumerate(['sectional','Overwrite']):
 old=folder.parent/domain/'9ba626afa44a3aa3.patch_0';new=OUT/'data'/('9ba626afa44a3aa3.patch_'+str(i))
 for suffix in ['', '.gpu_resources','.stream']:
  src=Path(str(old)+suffix);dest=Path(str(new)+suffix)
  if src.is_file():shutil.copyfile(src,dest)
  else:dest.write_bytes(b'')
 files.append(dict(tocPath=str(new),index=i))
backends={};parts=[];avatars=[];attachCounts=collections.Counter();updates=collections.Counter();writes=collections.Counter();checks=0

def check(ok,msg):
 global checks
 checks+=1
 if not ok:raise AssertionError(msg)

def prepare(u,rid):
 u.realRid=rid;u.nodes=len(models[rid].transforms);u.mg=False;u.anim=False
 be=engine(lua,copy.deepcopy(models[rid]),rid)
 lua.eval('function(U)local node=U.node;U.node=function(u,h)return node(u,h)+1 end;for _,k in ipairs({"local_pose","local_rotation","world_position","world_rotation","set_local_rotation","set_local_pose"})do local f=U[k];U[k]=function(u,n,...)return f(u,n-1,...)end end end')(be[0].Unit)
 backends[int(u.id)]=be
 return u

def player(name,x):
 av,us=e.player(e,name,x,7);avatars.append(av);out=[]
 for i in range(1,8):out.append(prepare(us[i],rids[i-1]))
 parts.append(out);return av,out
av,us=player('local',0);e.fpOwner=av
fp=e.add(e,table(lua,dict(nodes=63,anim=True,mg=False,eligible=False,name='native-fp')));fp.fp=True;e.fpGraph=fp
oldApi=e.api
known={bone_name_hash(n):n for n in ['support_mg','hair','root','camera','EntityRoot','r_hand','l_hand','hips']}

def api(self):
 S=oldApi(self);orig={k:v for k,v in S.Unit.items()};by=S.World.units_by_resource
 probe=next(iter(backends.values()))[0]
 for group in ['Quaternion','Matrix4x4']:
  if S[group]is None:S[group]=table(lua,{})
  for k,fn in probe[group].items():
   if k!='translation':S[group][k]=fn
 lua.eval('function(v)setmetatable(v,{__call=function(_,x,y,z)return{x,y,z}end})end')(S.Vector3)
 S.Vector3.to_elements=lua.eval('function(v)return v[1]or v.x,v[2]or v.y,v[3]or v.z end')
 S.Quaternion.to_elements=lua.eval('function(v)return v[1]or v.x,v[2]or v.y,v[3]or v.z,v[4]or v.w end')
 S.Application.string_to_id32=wrap(bone_name_hash)
 S.IdString64=table(lua,{});S.IdString64.to_hex=lua.eval('function(v)return v end')
 S.Unit.resource_name=wrap(lambda u:'d0cf4d493ca08bed'if u.fp else(str(u.realRid)if u.realRid else'4d1c334d294dfa97'))
 def hasharg(n):return bone_name_hash(n)if isinstance(n,str)else n
 def has(u,n):
  if u.fp:return known.get(hasharg(n))in ['root','camera']
  if u.realRid:return backends[int(u.id)][0].Unit.has_node(u,hasharg(n))
  return orig['has_node'](u,known.get(hasharg(n),n))
 def node(u,n):
  if u.fp:return 5 if known.get(hasharg(n))=='root'else 51
  if u.realRid:return backends[int(u.id)][0].Unit.node(u,hasharg(n))
  return 1
 S.Unit.has_node=wrap(has);S.Unit.node=wrap(node)
 for name in ['local_pose','local_rotation','world_rotation','set_local_pose','set_local_rotation']:
  def dispatch(u,*v,_name=name):
   if not u.alive:raise AssertionError('dead Unit '+_name)
   result=backends[int(u.id)][0].Unit[_name](u,*v)
   # Count completed engine writes, never a setter attempt that raised.
   if _name.startswith('set_'):writes[int(u.id)]+=1
   return result
  S.Unit[name]=wrap(dispatch)
 def position(u,n=1):
  if u.realRid:
   p=backends[int(u.id)][0].Unit.world_position(u,n)
   return table(lua,[p[1]+u.position.x,p[2],p[3]])
  return orig['world_position'](u,n)
 S.Unit.world_position=wrap(position)
 S.World.num_levels=wrap(lambda w:e.levels)
 def byresource(w,res):
  if res=='content/fac_helldivers/fp_cha_avatar/fp_cha_avatar':e.fpCalls=(e.fpCalls or 0)+1;return lua.table_from([fp])
  return by(w,res)
 S.World.units_by_resource=wrap(byresource)
 S.World.debug_camera_pose=wrap(lambda w:table(lua,dict(x=e.camera,y=0,z=1.7 if e.fp else 4.5)))
 S.Unit.world_pose=wrap(lambda u,n:table(lua,dict(x=e.fpOwner.position.x,y=0,z=1.7)))
 oldElements=S.Matrix4x4.to_elements
 S.Matrix4x4.to_elements=lua.eval('function(old)return function(p)if p.q then return old(p)end;return 1,0,0,0,1,0,0,0,1,p.x,p.y,p.z end end')(oldElements)
 return S

e.api=wrap(api)
if a.chef_patch:
 for row in files:row['tocPath']='data/'+Path(row['tocPath']).name
 import zipfile
 from chef_physics_patch_harness import scan_patch,start_scanned
 lua.globals().stingray=e.api(e)
 with zipfile.ZipFile(a.chef_patch)as z:blob=z.read('9ba626afa44a3aa3.patch_0')
 core,scanReceipt=scan_patch(lua,a.chef_core,blob)
 assert scanReceipt['found']==1 and scanReceipt['big']==scanReceipt['bad']==scanReceipt['huge']==0
 chefRow,chefEnv,startReceipt=start_scanned(lua,core,OUT)
 R=chefRow.module;state=chefEnv.__hd2physbone_runtime;C=state.options.compat
 assert C.version=='1.3.13'
 rig=C.parse_rig((folder/'physbone-rig.bin').read_bytes());rig.drivers=C.parse_driver_rig((folder/'physbone-driver-rig.bin').read_bytes())
 C.consumer_api.hash.update=lua.eval('function()error("RENDER_SHA_FORBIDDEN")end')
 C.consumer_api.hash.digest=lua.eval('function()error("RENDER_SHA_FORBIDDEN")end')
oldAttach=C.attach;oldUpdate=C.update
C.attach=wrap(lambda S,u,r,o:(attachCounts.update([int(u.id)])or oldAttach(S,u,r,o)))
def update(s,dt,*v):updates[int(s.unit.id)]+=1;return oldUpdate(s,dt,*v)
C.update=wrap(update)
opts=H.opts(table(lua,dict(consumerFiles=files,carriers=[dict(rig=rig,path=str(OUT/'data/9ba626afa44a3aa3.patch_0.gpu_resources'))],identityWatch=False,rescanFrames=300,mode='external')))
if a.chef_patch:
 # Supply controlled game discovery inputs through the production hot-options
 # API. Never uninstall/reinstall: Chef's hook captures the original driver.
 for k,v in dict(pollFrames=1,settleFrames=1,minNodes=90,heartbeatFrames=0).items():opts[k]=v
 assert R.setOptions(opts)is True
 lua.globals().render=chefRow.hooks.render
else:
 state,_,R=H.install(e,opts,C)
proofWaitCallbacks={}
def wait_for_proof(label):
 # Hash work stays bounded by the REAL production VM path. Do not change its
 # cap or inject precomputed hashes to make a Lua 5.1 test look like LuaJIT.
 for callbacks in range(60,200001,60):
  e.advance(e,60)
  ctx=state.consumerContext
  if ctx is not None and ctx.done and state.sessions and all(not s.consumerPending for s in state.sessions.values()):
   proofWaitCallbacks[label]=callbacks
   return
 raise AssertionError('Production streaming proof never completed: '+label)
wait_for_proof('initial')
if not state.sessions:raise AssertionError('runtime never attached')
rows=[s for s in state.sessions.values()]
print('initial',len(rows),[(s.unit.realRid,s.consumerMode,s.consumerReason)for s in rows],flush=True)
check(len(rows)==7,'all seven source instances remain registered')
check(sum(len(s.sessions)for s in rows)==12,'actual runtime did not apply 84->12 chains')
check(sum(len(s.drivers)for s in rows)==6,'actual runtime did not apply 42->6 drivers')
check(sum(s.consumerMode=='empty'for s in rows)==4,'legal empty states missing')
before=dict(attachCounts);e.advance(e,650);check(dict(attachCounts)==before,'legal empty caused periodic reattach')
for i in [5,6]:prepare(e.add(e,table(lua,dict(anim=False,x=0,name='extra-fp-arm'))),rids[i])
e.advance(e,420);check(len(state.sessions)==9,'duplicate resource instances were incorrectly deduplicated')
check(sum(len(s.sessions)for s in state.sessions.values())==12,'extra FP arm instances ran unnecessary chains')
for i in range(1,4):player('remote'+str(i),i*20)
e.advance(e,600);check(len(state.avatars)==4 and len(state.sessions)==30,'four players/30 instances were not retained')
check(sum(len(s.sessions)for s in state.sessions.values())==48,'four-player consumer chain closure wrong')
shipActive=[s for s in state.sessions.values()if s.consumerMode!='empty']
check(all(s.evaluateDrivers and s.singleStride==1 for s in shipActive),'ship springs/VRD/full-rate policy inactive')
check(all(not s.firstFailReason and not s.deadLogged for s in shipActive),'ship writer/health errors were suppressed')
check(all(updates[int(s.unit.id)]>0 and writes[int(s.unit.id)]>0 for s in shipActive),'ship callbacks made no solver/writer calls')
shipWriteEvidence=[dict(unitId=int(s.unit.id),resource=s.unit.realRid,solverCallbacks=updates[int(s.unit.id)],successfulBoneWrites=writes[int(s.unit.id)])for s in shipActive]
e.levels=900;e.advance(e,40);check(state.singleState.sceneMode=='mission','mission transition wrong')
check(state.singleState.selfUnit is None,'mission falsely reused ship identity')
e.fp=True;e.advance(e,100);print('ads',e.fpCalls,py(state.singleState.adsIdentity), 'avatars',[(u.id,u.position.x)for u in avatars],flush=True);check(lua.eval('function(a,b)return a==b end')(state.singleState.selfUnit,av) and state.singleState.adsIdentity.checks==3,'mission ADS identity not confirmed once')
fpCalls=e.fpCalls;updates.clear();writes.clear()
def ads_motion(frame):
 for u in us:u.position.x=0.03*math.sin(frame/7)
e.advance(e,100,0.01,wrap(ads_motion));check(e.fpCalls==fpCalls,'consumer paths restarted FP query')
for s in state.sessions.values():
 if lua.eval('function(a,b)return a==b end')(s.owner,av):
  check(s.singleStride==1,'local physics cadence lowered')
  check(s.consumerMode=='empty'or updates[int(s.unit.id)]==100,'active local consumer not full-rate')
  check(s.consumerMode=='empty'or writes[int(s.unit.id)]>0,'ADS local solver made no bone writes')
 else:
  check(not s.evaluateDrivers,'remote VRD enabled')
  check(updates[int(s.unit.id)]==(0 if R.FORMAL_PHYSICS_VARIANT=='A'or s.consumerMode=='empty'else 100),'remote A/B consumer dispatch wrong')
adsWriteEvidence=[dict(unitId=int(s.unit.id),resource=s.unit.realRid,solverCallbacks=updates[int(s.unit.id)],successfulBoneWrites=writes[int(s.unit.id)])for s in state.sessions.values()if s.consumerMode!='empty'and lua.eval('function(a,b)return a==b end')(s.owner,av)]
old=us[5];e.remove(e,old);e.advance(e,120);check(all(not lua.eval('function(a,b)return a==b end')(s.unit,old) for s in state.sessions.values()),'dead empty instance retained')
R.setOptions(table(lua,dict(consumerPlans=False)));e.advance(e,1);check(all(s.consumerMode is None for s in state.sessions.values()),'plan disable did not restore original full arrays')
R.setOptions(table(lua,dict(consumerPlans=True)));wait_for_proof('re-enabled');check(any(s.consumerMode=='empty'for s in state.sessions.values()),'consumer re-enable failed')
ctx=state.consumerContext;R.uninstall();check(all(j.handle is None for j in ctx.jobs.values()),'uninstall left open proof handles')
if a.chef_patch:
 (OUT/'chef-loader.log').write_text('\n'.join(str(x)for x in lua.globals().logs.values()),encoding='utf-8')
logs='\n'.join(p.read_text('utf-8',errors='replace')for p in OUT.glob('*.log'))
check(all(x not in logs for x in ['transition-error=','proof-error=','bind-error=','could not start','could not compile','驱动失败','安装失败','stopped by the hang watchdog']),'suppressed runtime errors must fail release tests')
result=dict(status='PASS_ACTUAL_RUNTIME_REAL_CONSUMER_DATA_NOT_FPS',variant=R.FORMAL_PHYSICS_VARIANT,vm=a.vm,checks=checks,source7FullChains=84,source7ConsumerChains=12,instancesWithFpArms=9,fourPlayerInstances=30,fpChecks=3,chefLuaBit=bool(a.chef_bit),renderShaForbidden=C.consumer_api.proofMode=='toc-exact-palette-v2',proofWaitCallbacks=proofWaitCallbacks,runtimeSha256=hashlib.sha256((a.source/'physbone_runtime.lua').read_bytes()).hexdigest(),compatSha256=hashlib.sha256((a.source/'physbone_compat.lua').read_bytes()).hexdigest(),actualChefScannedAddon=bool(a.chef_patch),chefScan=scanReceipt if a.chef_patch else None,chefStart=startReceipt if a.chef_patch else None,scannedAddonSha256=scanReceipt['sourceSha256']if a.chef_patch else None,shipSolverAndWriterActive=True,adsLocalSolverAndWriterActive=True,boneWriteCountMode='successful-setter-return',shipWriteEvidence=shipWriteEvidence,adsWriteEvidence=adsWriteEvidence,gpuContentReadForbidden=bool(a.chef_patch),realGameFps=False)
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
