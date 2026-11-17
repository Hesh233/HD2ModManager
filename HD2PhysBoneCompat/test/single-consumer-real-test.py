"""Real current Unit/TOC/GPU consumer proof; no library writes or FPS inference."""
from pathlib import Path
import argparse,ast,collections,copy,hashlib,importlib,json,math,os,runpy,shutil,sys,time
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--model',choices=['test01','cow','test13','test15'],default='test01');ap.add_argument('--vm',choices=['lua51','luajit21'],default='luajit21');ap.add_argument('--mutation',choices=['none','gpu','toc','higher','missing_gpu','bind'],default='none');a=ap.parse_args();OUT=a.output.resolve();assert OUT.is_relative_to(ROOT);OUT.mkdir(parents=True,exist_ok=True)
os.environ['APPDATA']=str(OUT);os.environ['LOCALAPPDATA']=str(OUT);sys.path[:0]=[str(NORMAL),str(ROOT.parent.parent),str(ROOT/'tools')]
from anim_batch_mod.math3d import quat_rotate,quat_multiply
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.native_skeleton import bone_name_hash
H=runpy.run_path(str(ROOT/'tools/audit_test06_vrd_skirt.py'),run_name='read_only_helpers');table,py,units=H['table'],H['py'],H['units']
t=ast.parse((ROOT/'HD2PhysBoneCompat/test/spring-dof-model-test.py').read_text('utf-8-sig'));exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef)and n.name=='engine'],type_ignores=[]),'existing-unit-engine','exec'),globals())
name={'test01':'[单骨架模型]test01','cow':'[单骨架模型]Cow_QiPao_Milltina_Nick','test13':'[单骨架模型]test13','test15':'[单骨架模型]test15'}[a.model];folder=NORMAL/'test-library'/name/'sectional'
L=importlib.import_module('lupa.'+a.vm).LuaRuntime;lua=L(unpack_returned_tuples=True);C=lua.execute(a.source.read_text('utf-8-sig'));cp=C.consumer_api
rig=C.parse_rig((folder/'physbone-rig.bin').read_bytes());rig.drivers=C.parse_driver_rig((folder/'physbone-driver-rig.bin').read_bytes())
fs=OUT/'data';fs.mkdir(exist_ok=True);files=[]
for i,domain in enumerate(['sectional','Overwrite']):
 p=folder.parent/domain/'9ba626afa44a3aa3.patch_0';target=fs/('9ba626afa44a3aa3.patch_'+str(i))
 for suffix in ['', '.gpu_resources','.stream']:
  old=Path(str(p)+suffix);new=Path(str(target)+suffix)
  if old.is_file():shutil.copyfile(old,new)
  else:new.write_bytes(b'')
 files.append(dict(tocPath=str(target),index=i))
if a.mutation in ['gpu','missing_gpu']:
 p=Path(str(fs/'9ba626afa44a3aa3.patch_1')+'.gpu_resources');b=p.read_bytes();p.write_bytes(b''if a.mutation=='missing_gpu'else bytes([b[0]^1])+b[1:])
if a.mutation in ['toc','higher']:
 import struct
 p=fs/'9ba626afa44a3aa3.patch_1';b=bytearray(p.read_bytes());nt,count=struct.unpack_from('<II',b,4)
 for i in range(count):
  t=struct.unpack_from('<QQQQQQQIIIIII',b,72+32*nt+80*i)
  if t[1]==0xe0a48d0be9a7453f and f'{t[0]:016x}'==next(iter(units(folder/'9ba626afa44a3aa3.patch_0'))):b[t[2]+t[7]-1]^=1;break
 if a.mutation=='higher':
  p=fs/'9ba626afa44a3aa3.patch_2'
  for suffix in ['.gpu_resources','.stream']:shutil.copyfile(Path(str(fs/'9ba626afa44a3aa3.patch_1')+suffix),Path(str(p)+suffix))
  files.append(dict(tocPath=str(p),index=2))
 p.write_bytes(b)
logs=[];wrap=lua.eval('function(f)return function(...)return f(...)end end');logger=wrap(lambda fmt,*v:logs.append(lua.eval('string.format')(fmt,*v)))
ctx=cp.new(table(lua,files),logger);models=units(folder/'9ba626afa44a3aa3.patch_0');items=[];checks=0
def check(ok,msg):
 global checks
 checks+=1
 if not ok:raise AssertionError(msg)
for rid,model in models.items():
 e=engine(lua,copy.deepcopy(model),rid);S=e[0]
 lua.eval('function(U)local node=U.node;U.node=function(u,h)return node(u,h)+1 end;for _,k in ipairs({"local_pose","local_rotation","world_position","world_rotation","set_local_rotation","set_local_pose"})do local f=U[k];U[k]=function(u,n,...)return f(u,n-1,...)end end end')(S.Unit)
 S.Unit.resource_name=lua.eval('function(r)return function()return r end end')(rid);S.IdString64=table(lua,{});S.IdString64.to_hex=lua.eval('function(v)return v end')
 e[2].vrdSkeletonOnly=True;e[2].fastWrite=True;s=C.attach(S,e[1],rig,e[2]);s=s[0]if isinstance(s,tuple)else s;s.singleMainline=True;s.ownerOrder=1
 before=(len(s.sessions),len(s.drivers));cp.bind(ctx,s);check((len(s.sessions),len(s.drivers))==before,'proof pending changed full arrays')
 if a.mutation=='bind'and rid==next(iter(models)):s.nodeCount=s.nodeCount+1
 items.append(dict(resource=rid,env=e,session=s,before=before))
start=time.perf_counter();loops=0;last=-1
while loops<500000:
 loops+=1;C.begin_frame(loops);cp.tick(ctx,8192)
 if ctx.serial!=last:
  last=ctx.serial
  for row in items:
   if row['session'].consumerPending:cp.bind(ctx,row['session'])
 if all(not r['session'].consumerPending for r in items):break
wanted_full=set()if a.mutation=='none'else(set(models)if a.mutation=='missing_gpu'else{next(iter(models))})
if not all((r['session'].consumerMode is None if r['resource']in wanted_full else r['session'].consumerMode is not None) for r in items):
 print('\n'.join(logs));print([(r['resource'],r['session'].consumerReason,r['session'].consumerPending)for r in items]);raise AssertionError('real proof/full bind failed')
rig_before=copy.deepcopy(py(rig));rows=[]
for row in items:
 s=row['session'];counts=[]
 if row['resource']in wanted_full:check(s.consumerMode is None and(len(s.sessions),len(s.drivers))==row['before'],'rejected proof did not retain original full solver')
 else:check(s.consumerApplied.tocSha256 is not None,'missing verified payload fact')
 for frame in range(1,121):C.begin_frame(loops+frame);C.update(s,1/120)
 check(py(rig)==rig_before,'solver changed shared rig')
 C.release(s)
 rows.append(dict(resource=row['resource'],fullChains=row['before'][0],fullDrivers=row['before'][1],chains=len(s.sessions),drivers=len(s.drivers),mode=s.consumerMode,reason=s.consumerReason,t16=s.test16Resource==row['resource']))
serial=ctx.serial
for i in range(20):cp.tick(ctx,8192)
check(ctx.serial==serial and ctx.done,'completed proof context continued work')
cp.close(ctx);check(all(j.handle is None for j in ctx.jobs.values()),'file handles left open')
result=dict(status='PASS_REAL_DEPLOYED_PAYLOAD_PROOF_NOT_FPS',model=a.model,vm=a.vm,mutation=a.mutation,checks=checks,proofCallbacks=loops,proofControlWallSeconds=time.perf_counter()-start,unitRows=rows,fullChains=sum(r['fullChains']for r in rows),closedChains=sum(r['chains']for r in rows),fullDrivers=sum(r['fullDrivers']for r in rows),closedDrivers=sum(r['drivers']for r in rows),compatSha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),actualGameFps=False)
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(OUT/'events.log').write_text('\n'.join(logs)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False),flush=True)
