"""Pending proof world/option invalidation on real sessions, not game/FPS."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, sys
ROOT=Path(__file__).resolve().parents[2]
NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--vm',choices=['lua51','luajit21'],required=True);a=ap.parse_args()
source=a.source.resolve();OUT=a.output.resolve();assert OUT.is_relative_to(ROOT) and not OUT.is_relative_to(NORMAL);OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'outputs/fp-physics-consumer-analysis-20261117'))
from analysis_common import make,units,table
os.environ['APPDATA']=str(OUT);os.environ['LOCALAPPDATA']=str(OUT)
folder=NORMAL/'test-library/[单骨架模型]test01/sectional';models=units(folder/'9ba626afa44a3aa3.patch_0');rid=next(iter(models))
x=make(a.vm,models[rid],rid,folder,(source/'physbone_compat.lua').read_text('utf-8-sig'));lua,C,s=x['lua'],x['C'],x['session']
rt=(source/'physbone_runtime.lua').read_text('utf-8-sig');start=rt.index('local ConsumerRuntime={}');stop=rt.index('local function loadCarriers(',start)
lua.globals().Compat=C;CR=lua.execute(rt[start:stop]+'\nreturn ConsumerRuntime')
files=[]
for i,domain in enumerate(['sectional','Overwrite']):
 old=folder.parent/domain/'9ba626afa44a3aa3.patch_0';new=OUT/('9ba626afa44a3aa3.patch_'+str(i))
 for suffix in ['', '.gpu_resources','.stream']:
  src,dest=Path(str(old)+suffix),Path(str(new)+suffix)
  if src.is_file():shutil.copyfile(src,dest)
  else:dest.write_bytes(b'')
 files.append(dict(tocPath=str(new),index=i))
runtime=table(lua,dict(world={},cache={},options=dict(consumerFiles=files),sessions=[s]));runtime.logger=lua.eval('function()end')
checks=0
def check(ok,msg):
 global checks
 checks+=1
 if not ok:raise AssertionError(msg)
same=lua.eval('function(a,b)return a==b end')
full=(len(s.sessions),len(s.drivers));CR.reset(runtime);CR.bind(runtime,s);old=runtime.consumerContext
for frame in range(1,5001):
 C.begin_frame(frame);CR.tick(runtime)
 if any(j.handle is not None for j in old.jobs.values()):break
else:raise AssertionError('Actual bounded proof never opened a real payload range')
check(s.consumerPending and s.consumerMode is None,'Pending proof masked the full solver')
check((len(s.sessions),len(s.drivers))==full,'Pending proof changed full arrays')
newWorld=lua.table();runtime.world=newWorld;CR.watch(runtime)
check(old.closed is True and all(j.handle is None for j in old.jobs.values()),'World change leaked a pending payload handle')
check(runtime.consumerContext is None,'Old proof context survived world change')
CR.tick(runtime);fresh=runtime.consumerContext
check(fresh is not None and not same(fresh,old) and same(fresh.world,newWorld),'World rearm reused the old proof context')
check(same(s.consumerContext,fresh) and s.consumerPending,'New world did not restart the full proof request')
check((len(s.sessions),len(s.drivers))==full,'World rearm changed full arrays before proof')
runtime.options.consumerPlans=False;CR.tick(runtime)
check(runtime.consumerContext is None and fresh.closed is True,'Option disable did not close the proof')
check(s.consumerMode is None and not s.consumerPending and (len(s.sessions),len(s.drivers))==full,'Option disable did not retain full original state')
runtime.options.consumerPlans=True;CR.tick(runtime)
check(runtime.consumerContext is not None and not same(runtime.consumerContext,fresh) and s.consumerPending,'Re-enable did not require a new proof')
CR.close(runtime)
check(runtime.consumerContext is None,'Explicit close retained proof context')
check(sum(x['engine'][5]['writes'].values())==0,'Pending/world-invalid proof wrote a pose')
result=dict(status='PASS_PENDING_PROOF_WORLD_OPTION_EPOCH_NOT_FPS',vm=a.vm,checks=checks,harnessSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runtimeSha256=hashlib.sha256((source/'physbone_runtime.lua').read_bytes()).hexdigest(),compatSha256=hashlib.sha256((source/'physbone_compat.lua').read_bytes()).hexdigest(),worldInvalidationClosedPendingHandles=True,newWorldRestartsProof=True,pendingPoseWrites=0,actualGameFps=False)
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result),flush=True)
