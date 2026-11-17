"""Actual production consumer hand-back/solver vs frozen solver, real bind FK.
Proof-completion cache in this test is filled with Python SHA256 of ACTUAL payload
ranges; real streaming verifier is independently exercised by real/runtime tests.
No game/FPS claim, library writes, or fixture IDs in production profiles.
"""
from pathlib import Path
import argparse,ast,copy,hashlib,json,math,os,sys,types,collections,shutil
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2];LAB=ROOT/'outputs/physics-single-consumers-formal-20261117'
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--quick',action='store_true');ap.add_argument('--source',type=Path,default=LAB/'A-source/physbone_compat.lua');ap.add_argument('--evidence-root',type=Path,default=LAB);ap.add_argument('--baseline',type=Path,default=LAB/'before/single_remote_compat.lua');a=ap.parse_args();LAB=a.evidence_root.resolve();OUT=a.output.resolve();assert OUT.is_relative_to(LAB);OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'outputs/fp-physics-consumer-analysis-20261117'))
from analysis_common import make,units,table,py,chain_entries,driver_entries,quat_rotate,quat_multiply,bone_name_hash,parent,_calculate_world_transforms
NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
assert OUT.is_relative_to(LAB) and not OUT.is_relative_to(NORMAL)
os.environ['APPDATA']=str(OUT/'isolated-roaming');os.environ['LOCALAPPDATA']=str(OUT/'isolated-local')
# Only reuse pure replay helpers, not the older script's top-level execution.
t=ast.parse((ROOT/'outputs/fp-physics-consumer-analysis-20261117/replay_consumers.py').read_text('utf-8-sig'))
exec(compile(ast.Module(body=[n for n in t.body if isinstance(n,ast.FunctionDef)and n.name in ['enable_fk','animate','compare_consumers']],type_ignores=[]),'existing-fk-fixture','exec'),globals())
checks=0

def check(ok,message):
 global checks
 checks+=1
 if not ok:raise AssertionError(message)

catalog=json.loads((LAB/'consumer-catalog.json').read_text('utf-8-sig'));source=a.source.read_text('utf-8-sig');old=a.baseline.read_text('utf-8-sig')
nameByModel={x['modelName']:x for x in catalog['models']};entries={};digestCache={}

def ranges(folder,domain,rid):
 import struct
 p=folder.parent/domain/'9ba626afa44a3aa3.patch_0';b=p.read_bytes();nt,count=struct.unpack_from('<II',b,4)
 for i in range(count):
  r=struct.unpack_from('<QQQQQQQIIIIII',b,72+nt*32+i*80)
  if f'{r[0]:016x}'==rid and r[1]==0xe0a48d0be9a7453f:
   return dict(index=0,tocPath=str(p),tocOffset=r[2],tocSize=r[7],gpuPath=str(p)+'.gpu_resources',gpuOffset=r[4],gpuSize=r[9],streamPath=str(p)+'.stream',streamOffset=r[3],streamSize=r[8])
 raise KeyError(rid)

def hash_range(path,offset,size):
 key=(path,int(offset),int(size))
 if key not in digestCache:
  if not size:data=b''
  else:
   with Path(path).open('rb')as f:f.seek(int(offset));data=f.read(int(size))
   assert len(data)==size
  digestCache[key]=hashlib.sha256(data).hexdigest()
 return digestCache[key]

def verified_apply(x,p,folder):
 C=x['C'];cp=C.consumer_api;lua=x['lua'];s=x['session'];ctx=cp.new(lua.table(),None)
 desc=ranges(folder,p['domain'],p['resource']);stem=OUT/'payload-cache'/hashlib.sha256(desc['tocPath'].encode()).hexdigest()[:12]/'9ba626afa44a3aa3.patch_0'
 if not stem.exists():
  stem.parent.mkdir(parents=True,exist_ok=True)
  for suffix in ['', '.gpu_resources','.stream']:
   src=Path(desc['tocPath']+suffix);dest=Path(str(stem)+suffix)
   if src.is_file():shutil.copyfile(src,dest)
   else:dest.write_bytes(b'')
 desc['tocPath']=str(stem);desc['gpuPath']=str(stem)+'.gpu_resources';desc['streamPath']=str(stem)+'.stream'
 ctx.descriptors[p['resource']]=table(lua,desc)
 cp.bind(ctx,s);req=s.consumerRequest;check(req is not None,'registered profile missing')
 if cp.proofMode=="toc-exact-palette-v2":
  for i in range(64):
   cp.tick(ctx,8192);cp.bind(ctx,s)
   if not s.consumerPending:break
 else:
  req.pair.r.digest=hashlib.sha256((folder/'physbone-rig.bin').read_bytes()).hexdigest();req.pair.d.digest=hashlib.sha256((folder/'physbone-driver-rig.bin').read_bytes()).hexdigest()
  for i in range(8):
   cp.tick(ctx,64)
   for j in ctx.jobs.values():
    if j.kind=='file'and j.digest is None:
     j.digest=hash_range(j.path,j.start,j.length)
     if j.handle is not None:lua.eval('function(j)j.handle:close();j.handle=nil end')(j)
   cp.bind(ctx,s)
   if not s.consumerPending:break
 check(s.consumerMode is not None,('validated actual payload/full-bind did not activate',p['resource'],s.consumerReason))
 return ctx

profiles=[]
for p in catalog['units']:
 folder=NORMAL/'test-library'/p['model']/'sectional'
 # Determine the real input domain by exact Unit payload SHA. Shared target IDs
 # remain separate model/rig profiles, never one global per-resource numeric state.
 for domain in ['sectional','Overwrite']:
  try:desc=ranges(folder,domain,p['resource'])
  except KeyError:continue
  if hash_range(desc['tocPath'],desc['tocOffset'],desc['tocSize'])==p['tocSha256']:
   profiles.append({**p,'domain':domain});break
 else:raise AssertionError('No exact real input for '+p['resource'])
if a.quick:profiles=[p for p in profiles if p['model']=='[单骨架模型]test13'][:3]
results=[]
for vm in (['luajit21']if a.quick else['lua51','luajit21']):
 for p in profiles:
  folder=NORMAL/'test-library'/p['model']/'sectional';u=units(folder.parent/p['domain']/'9ba626afa44a3aa3.patch_0')[p['resource']]
  rates=[120]if a.quick or p['domain']!='sectional'else[30,60,120,240]
  for hz in rates:
   aa=make(vm,u,p['resource'],folder,old);bb=make(vm,u,p['resource'],folder,source)
   enable_fk(aa,u);enable_fk(bb,u);native=set(p['nativeNodes'])
   for frame in range(1,21):
    for x in [aa,bb]:animate(x,u,native,frame,hz);x['C'].begin_frame(frame);x['C'].update(x['session'],1/hz)
   before={c['root']:copy.deepcopy(py(c['item']))for c in chain_entries(bb['session'])}
   drvBefore={d['name']:copy.deepcopy(py(d['item']))for d in driver_entries(bb['session'])}
   ctx=verified_apply(bb,p,folder)
   for c in chain_entries(bb['session']):check(before[c['root']]==py(c['item']),'handback perturbed retained spring state')
   for d in driver_entries(bb['session']):check(drvBefore[d['name']]==py(d['item']),'handback perturbed retained driver')
   row={'resource':p['resource'],'nativeNodeIndices':sorted(native|set(p['nonMeshNodes'])|set(p.get('skinPaletteNodes',[]))),'weightedNodeIndices':p['weightedNodes']}
   retained=set(n for c in chain_entries(bb['session'])for n in c['nodes'])|{d['node']for d in driver_entries(bb['session'])}
   for frame in range(21,141):
    for x in [aa,bb]:x['trace'].clear();animate(x,u,native,frame,hz);x['C'].begin_frame(frame);x['C'].update(x['session'],1/hz)
    compare_consumers(aa,bb,row)
    check([t for t in aa['trace']if t[1]-1 in retained]==bb['trace'],('retained writer sequence',p['resource'],hz,frame))
   writes=sum(bb['engine'][5]['writes'].values());bb['C'].consumer_api.bind(ctx,bb['session'])
   check(writes==sum(bb['engine'][5]['writes'].values()),'same plan repeated ownership handback')
   check(py(aa['rig'])==aa['rigSnapshot']and py(bb['rig'])==bb['rigSnapshot'],'shared author rig modified')
   for x in [aa,bb]:x['C'].release(x['session']);x['refreshFK']()
   for n in native|set(p['weightedNodes'])|set(p['nonMeshNodes'])|set(p.get('skinPaletteNodes',[])):check(aa['engine'][3][n]==bb['engine'][3][n]and aa['engine'][4][n]==bb['engine'][4][n],('release consumer FK',p['resource'],n))
   bb['C'].consumer_api.close(ctx)
   results.append(dict(vm=vm,model=p['model'],resource=p['resource'],domain=p['domain'],hz=hz,frames=120,warmupFullFrames=20,mode=bb['session'].consumerMode,retainedStateAndWorldPose='bit-identical',oneTimeHandback=True,wholeRigUnchanged=True,actualFps=False))
  print(vm,p['model'],p['resource'],rates,'PASS',flush=True)
result=dict(status='PASS_PRODUCTION_CONSUMER_FK_AND_HANDBACK_NOT_FPS',checks=checks,cases=results,actualInputSha256CachedChecks=len(digestCache),profiles=len(profiles),harnessSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),nonMeshConsumersCompared=True,compatSha256=hashlib.sha256(a.source.read_bytes()).hexdigest(),catalogSha256=hashlib.sha256((LAB/'consumer-catalog.json').read_bytes()).hexdigest(),actualGameFps=False)
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('PASS checks',checks,'cases',len(results),'profiles',len(profiles),flush=True)
