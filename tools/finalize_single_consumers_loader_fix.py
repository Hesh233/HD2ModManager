"""Deliver validated loader-size CANDIDATES, never claim real game/FPS accepted."""
from pathlib import Path
import argparse,base64,hashlib,json,shutil,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];LAB=ROOT/'outputs/physics-single-loader-size-fix-20261117';OUT=LAB/'release-candidate';PROD=ROOT/'HD2PhysBoneCompat/src/production';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
ap=argparse.ArgumentParser();ap.add_argument('--deliver',action='store_true');a=ap.parse_args()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
protected=read(LAB/'protected-before.json');changed=[];after={}
for name,old in protected.items():
 p=Path(name);now=dict(exists=p.is_file(),bytes=p.stat().st_size if p.is_file()else None,sha256=sha(p)if p.is_file()else None);after[name]=now
 if now!=old:changed.append(name)
require(not changed,'Protected user inputs changed; no rollback is attempted: '+str(changed));(LAB/'protected-after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
config=[]
for args in [['--source-config',str(ROOT.parent/'config.toml'),'--bundle-root',str(ROOT/'tools/native-python/anim_batch_mod')],['--manager-root',str(NORMAL)]]:
 r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/check_animation_config.py')]+args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8');require(r.returncode==0,r.stdout+r.stderr);config.append(json.loads(r.stdout))
(LAB/'configuration-gates.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'--loader-size-fix','--evidence-root',str(LAB)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8');(LAB/'verify-final.log').write_text(r.stdout+r.stderr,encoding='utf-8');require(r.returncode==0,r.stdout+r.stderr)
m=read(PROD/'single_remote_release_manifest.json');c=read(PROD/'single_consumer_catalog.json');run=read(OUT/'gate-run.json')
require(m['realGameAcceptanceStatus']=='loader-size-candidate-pending-physics-and-FPS'and m['renderGpuHashing']is False,'Do not relabel candidates as game accepted')
require(run['status']=='PASS_49_CORRECTION_CANDIDATE_GATES_NOT_GAME_FPS'and len(run['tests'])==49,'49 actual candidate gates missing')
require(run['inputs']['catalog']==sha(PROD/'single_consumer_catalog.json')and run['inputs']['actualChefBit']==sha(LAB/'actual-chef-bit-shim.lua'),'Gate inputs changed')
for t in run['tests']:require(t['returncode']==0 and sha(t['command'][3])==t['scriptSha256']and sha(t['log'])==t['logSha256'],'Gate script/log changed: '+t['label'])
fk=read(LAB/'fk-release/result.json');require(fk['status']=='PASS_PRODUCTION_CONSUMER_FK_AND_HANDBACK_NOT_FPS'and len(fk['cases'])==290 and fk['profiles']==61 and fk['nonMeshConsumersCompared'],'Full FK proof incomplete')
require(fk['harnessSha256']==sha(ROOT/'HD2PhysBoneCompat/test/single-consumer-fk-test.py')and fk['catalogSha256']==sha(PROD/'single_consumer_catalog.json'),'FK inputs changed')
require(all(x['retainedStateAndWorldPose']=='bit-identical'and x['oneTimeHandback']and x['wholeRigUnchanged']for x in fk['cases']),'FK/handback drift')
producer=read(LAB/'producer-finish-verification.json');require(producer['status']=='PASS_FRESH_PRODUCER_AND_STALE_CERTIFICATE_REJECTION'and producer['sourceSha256']==m['templateSha256']['consumerProducer']and len(producer['negativeCases'])==3,'Fresh source/certificate gate missing')
probe=read(LAB/'palette-probe.json')
for p in c['units']:
 z=next(x for x in probe if x['model']==p['model']and x['resource']==p['resource']and'error'not in x)
 require(set(p['skinPaletteNodes'])==set(z['allRealPalette'])and set(p['weightedNodes'])<=set(p['skinPaletteNodes']),'Complete actual TOC palette does not cover consumers')
 require(hashlib.sha256(base64.b64decode(p['tocExactBase64'],validate=True)).hexdigest()==p['tocSha256'],'Exact TOC certificate drift')
for model in c['models']:
 folder=NORMAL/'test-library'/model['modelName']/'sectional'
 for key,file in [('bindSha256','single-hd2-bind.json'),('configSha256','single-config.toml'),('rigSha256','physbone-rig.bin'),('driverRigSha256','physbone-driver-rig.bin')]:require(sha(folder/file)==model[key],'Actual model certificate changed')
encoding=read(OUT/'catalog-and-chef-size-tests.json')
require(encoding['status']=='PASS_BYTE_EXACT_ENCODING_AND_ACTUAL_CHEF_SIZE_NEGATIVES'and encoding['catalogSha256']==sha(PROD/'single_consumer_catalog.json')and len(encoding['roundtrips'])==2,'Byte-exact catalog/boundary gate missing')
require(all(x['big']==1 and x['found']==0 for x in encoding['oldPackagesSkipped']),'Old oversized package negative failed')
exportGuard=read(LAB/'actual-export-guard-tests.json');require(exportGuard['status']=='PASS_ACTUAL_EXPORTER_RAW_RESOURCE_GUARD'and exportGuard['oldOversizedRejected']==2,'Actual exporter guard missing')

packages=[];runtimeChecks=0;means=[];maxima=[]
for entry in m['sources']:
 v=entry['variant'];require(run['inputs'][v+'Runtime']==entry['runtimeSha256']and run['inputs'][v+'Compat']==entry['compatSha256']==fk['compatSha256'],'Source SHA mismatch')
 for profile in ['jit','plain','chef','chef-patch']:
  r=read(OUT/('runtime-'+v+'-'+profile)/'result.json');require(r['status']=='PASS_ACTUAL_RUNTIME_REAL_CONSUMER_DATA_NOT_FPS'and r['checks']>=78 and r['renderShaForbidden']and r['runtimeSha256']==entry['runtimeSha256']and r['compatSha256']==entry['compatSha256'],'Runtime/transition/no-SHA proof missing');runtimeChecks+=r['checks']
  if profile in ['chef','chef-patch']:require(r['chefLuaBit']and max(r['proofWaitCallbacks'].values())<=120,'Actual game VM proof stalled')
  if profile=='chef-patch':
   require(r['actualChefScannedAddon']and r['shipSolverAndWriterActive']and r['adsLocalSolverAndWriterActive']and r['gpuContentReadForbidden'],'Actual patch callbacks/solver/writer missing')
   require(r.get('boneWriteCountMode')=='successful-setter-return','Setter attempts are not successful bone writes')
   for scene in ['shipWriteEvidence','adsWriteEvidence']:
    rows=r.get(scene,[]);require(rows and all(x['solverCallbacks']>0 and x['successfulBoneWrites']>0 for x in rows),'Missing completed engine writes: '+scene)
   require(all(x['solverCallbacks']==100 for x in r['adsWriteEvidence']),'ADS local solver cadence changed')
   require(r['chefScan']['bad']==r['chefScan']['big']==r['chefScan']['huge']==0 and r['chefScan']['found']==1,'Chef skipped actual patch')
   require(r['chefStart']['state']=='running'and r['chefStart']['version']==entry['runtimeVersion']and r['chefStart']['actualChefStarter']and r['chefStart']['actualChefSandbox']and r['chefStart']['actualChefWatchdog'],'Actual Chef sandbox/start/watchdog failed')
   require(r['chefScan']['chefCoreSha256']==sha(LAB/'actual-chef-core-1.lua'),'Chef fixture drift')
   require(r['chefScan']['sourceSha256']==sha(OUT/(v+'-addon.lua')),'Scanned source changed')
   with zipfile.ZipFile(OUT/(v+'-export/physics-runtime.zip'))as z:require(hashlib.sha256(z.read('9ba626afa44a3aa3.patch_0')).hexdigest()==r['chefScan']['patchSha256'],'Scanned patch changed')
 for vmname in ['lua51','luajit21']:
  for kind in ['inventory','epoch']:
   r=read(OUT/(kind+'-'+v+'-'+vmname)/'result.json');require(r['runtimeSha256']==entry['runtimeSha256']and r['compatSha256']==entry['compatSha256']and r['status'].startswith('PASS'),'Inventory/epoch gate missing')
 verify=read(OUT/(v+'-formal-verification.json'));require(verify['status']=='PASS_ACTUAL_LOADER_SIZE_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS'and verify['methodsChanged']==0 and len(verify['installers'])==6,'Actual ZIP/IL/loader verification missing')
 z=OUT/(v+'-export/physics-runtime.zip');require(sha(z)==verify['zipSha256'],'Candidate ZIP changed')
 with zipfile.ZipFile(z)as f:require(f.testzip()is None and len(f.infolist())==4,'Candidate CRC/member mismatch')
 name='物理运行时-单骨架-'+v+'-Chef加载上限修复-'+entry['runtimeVersion']+'-候选版-待实机验收.zip';dest=(NORMAL/'运行时配套'/name).resolve();require(dest.parent==(NORMAL/'运行时配套').resolve(),'Unsafe candidate path');require(not dest.exists()or sha(dest)==sha(z),'Refusing to overwrite different existing candidate')
 packages.append(dict(variant=v,runtimeVersion=entry['runtimeVersion'],compatVersion='1.3.13',path=str(dest),exportPath=str(z),sha256=sha(z),bytes=z.stat().st_size))
expected={'test01':(84,12,42,6),'cow':(182,29,14,2),'test13':(98,14,35,10),'test15':(203,29,98,14)}
for profile in ['jit','plain','chef']:
 for name,numbers in expected.items():
  r=read(OUT/('palette-'+name+'-'+profile)/'result.json');require(r['status']=='PASS_TOC_EXACT_ALL_PALETTE_PROOF_NO_RENDER_SHA_NOT_FPS'and r['renderShaForbidden']and r['gpuContentReadForbidden']and r['compatSha256']==fk['compatSha256'],'Full-palette/no-SHA proof missing');require(tuple(r[k]for k in ['fullChains','closedChains','fullDrivers','closedDrivers'])==numbers,'Consumer closure changed')
  if profile=='chef':means.append(r['proofSliceMeanMs']);maxima.append(r['proofSliceMaxMs']);require(r['proofSliceMaxMs']<20 and r['proofCallbacks']<1000,'Actual VM proof frame regression')
for mutation in ['gpu','toc','higher','missing_gpu','bind']:
 r=read(OUT/('negative-'+mutation+'-chef')/'result.json');require(r['status']=='PASS_TOC_EXACT_ALL_PALETTE_PROOF_NO_RENDER_SHA_NOT_FPS'and r['mutation']==mutation and r['compatSha256']==fk['compatSha256'],'Negative proof missing')
 if mutation!='gpu':require(r['unitRows'][0]['mode']is None,'Unknown/incomplete Unit must retain full solver')
 else:require(all(x['mode']is not None for x in r['unitRows']),'Legal GPU content within full TOC palette was incorrectly treated as precise-weight proof')
require(len(packages)==2 and {x['variant']for x in packages}=={'A','B'},'Both candidates required')
if a.deliver:
 for p in packages:
  dest=Path(p['path'])
  if not dest.exists():
   with Path(p['exportPath']).open('rb')as source,dest.open('xb')as target:shutil.copyfileobj(source,target)
  require(sha(dest)==p['sha256'],'Delivered candidate byte mismatch')
result=dict(status='DELIVERED_CORRECTION_CANDIDATES_PENDING_GAME_ACCEPTANCE'if a.deliver else'CORRECTION_CANDIDATE_GATES_PASSED_NOT_GAME_FPS',packages=packages,protectedPaths=len(protected),protectedFiles=sum(x['exists']for x in protected.values()),protectedChanges=[],rootConfigSha256=sha(NORMAL/'config.toml'),normalCoreSha256=sha(NORMAL/'HD2ModCore.dll'),consumerProfiles=len(c['units']),consumerResources=len({x['resource']for x in c['units']}),fullFkCases=len(fk['cases']),fullFkChecks=fk['checks'],runtimeChecks=runtimeChecks,gateCommands=49,actualChefProofMeanMs=means,actualChefProofMaxMs=maxima,failedOldVersions=['2.3.15','2.3.16','2.3.17','2.3.18'],encodingChecks=encoding['checks'],actualChefPatchToStarterToSolver=True,actualGameFpsMeasured=False,gameOrManagerLaunched=False,libraryOrModelOrAnimationChanged=False,automaticallyImportedOrDeployed=False)
(LAB/('delivery.json'if a.deliver else'final-gates.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))

