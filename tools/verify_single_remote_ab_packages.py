"""Validate BOTH actual exported A/B ZIPs, standalone installers and long logs.
All tests are isolated/offline. No GUI/game launch, import, apply, or deployment.
"""
from pathlib import Path
import argparse, hashlib, importlib, json, os, re, struct, zipfile
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();OUT=args.output.resolve();assert OUT.is_relative_to(ROOT);os.chdir(ROOT)
def sha(data):return hashlib.sha256(data).hexdigest()
base=(OUT/'baseline-r2-compat.lua').read_text('utf8');reports=[]
for variant,version,mode in [('A','2.3.9','self-only'),('B','2.3.10','remote-no-vrd')]:
 folder=OUT/(variant+'-source');export=OUT/(variant+'-export');proof=json.loads((export/'physics-provenance.json').read_text('utf8'));package=export/'physics-runtime.zip'
 assert sha(package.read_bytes())==proof['zipSha256']
 assert proof['runtimeVersion']==version and proof['compatVersion']=='1.3.8'
 assert proof['owner']=='mods/hd2modmanager/physbone' and proof['guid']=='7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01'
 with zipfile.ZipFile(package) as z:
  assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))==4
  assert set(z.namelist())=={row['path'] for row in proof['entries']}
  for row in proof['entries']:
   data=z.read(row['path']);assert len(data)==row['bytes'] and sha(data)==row['sha256']
  manifest=json.loads(z.read('manifest.json'));assert manifest['Guid']==proof['guid']
  patch=z.read('9ba626afa44a3aa3.patch_0');offset=struct.unpack_from('<Q',patch,120)[0];size=struct.unpack_from('<I',patch,160)[0]
  source=patch[offset+8:offset+size].decode('utf8').replace('\r\n','\n')
 assert sha(source.encode())==proof['sourceSha256']
 assert source==(export/'export/lua版/hd2physbone.lua').read_text('utf8')
 assert source.startswith('-- HD2-Addon: mods/hd2modmanager/physbone\n')
 extracted=OUT/(variant+'-extracted');extracted.mkdir(exist_ok=True)
 payloads={}
 for name,label in [('physbone_compat.lua','PhysBoneCompat'),('physbone_runtime.lua','PhysBoneRuntime')]:
  expected=(folder/name).read_text('utf8');prefix='local '+label+' = (function()\n';start=source.index(prefix)+len(prefix)
  actual=source[start:start+len(expected)];assert actual==expected and source[start+len(expected):].startswith('\nend)()')
  (extracted/name).write_text(actual,encoding='utf8',newline='\n');payloads[name]=sha(actual.encode())
 compat=(extracted/'physbone_compat.lua').read_text('utf8')
 # Full production bind/profile literals stay EXACT, not just version strings.
 profile_hashes={}
 for label in ['local T1201 =','local T16 =']:
  before=next(line for line in base.splitlines() if line.startswith(label));after=next(line for line in compat.splitlines() if line.startswith(label));assert before==after
  profile_hashes[label]=sha(after.encode())
 for start,end in [('local function sJiggle(','M.test1201_jiggle=sJiggle'),('function M.step_tip(','function M.local_rotations('),('function M.quatinterp(','local function ' )]:
  if start not in base:continue
  a=base.index(start);b=base.find(end,a+len(start))
  if b<0:continue
  piece=base[a:b];assert piece in compat,'numeric solver body changed: '+start
 audit=json.loads((OUT/(variant+'-core-audit.json')).read_text('utf8'))
 assert audit['identityUnchanged'] and audit['methodsBefore']==audit['methodsAfter']==19802
 assert not audit['changedMethods'] and not audit['changedConstants'] and not audit['changedReferences']
 assert audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']
 outcomes=[]
 for vm in ['lua51','luajit21']:
  L=importlib.import_module('lupa.'+vm).LuaRuntime
  for loader in [None,'Chef Shared Loader','CowboyBingusModLoader']:
   work=OUT/(variant+'-standalone-'+vm+'-'+('plain' if loader is None else loader.replace(' ','-')));work.mkdir(exist_ok=True)
   os.environ['LOCALAPPDATA']=str(work);os.environ['APPDATA']=str(work)
   lua=L(unpack_returned_tuples=True);lines=[];lua.globals().print=lambda *x:lines.append(' '.join(map(str,x)))
   lua.execute('clock=0;priorCalls=0;render=function()priorCalls=priorCalls+1 end;stingray={Application={worlds=function()return{}end,time_since_launch=function()return clock end}}')
   module=lua.execute(source,lua.table_from({'loader':loader,'log_directory':str(work)}) if loader else None)
   assert module.VERSION==version and module.REMOTE_TEST_POLICY==mode and lua.globals()['__hd2physbone_runtime'] is not None
   lua.globals().testModule=module;lua.execute('before=render;testModule.install(stingray,{});assert(render==before);for i=1,8 do clock=clock+.01;render()end')
   assert lua.globals().priorCalls==8
   assert module.uninstall() is True and lua.globals()['__hd2physbone_runtime'] is None
   lua.execute('render()');assert lua.globals().priorCalls==9
   assert not any('安装失败' in line for line in lines)
   if loader:
    log=(work/('hd2physbone_test01_'+variant+'_perf.log')).read_text('utf8');assert 'variant='+variant in log and 'policy='+mode in log and 'NOT_FPS' in log
   outcomes.append({'vm':vm,'loader':loader,'installDuplicateInstallRenderRestorePassed':True})
  # Long fake mission crosses the OLD 90s cutoff and closes after 1200s.
  work=OUT/(variant+'-sampler-'+vm);work.mkdir(exist_ok=True);os.environ['LOCALAPPDATA']=str(work);os.environ['APPDATA']=str(work)
  lua=L(unpack_returned_tuples=True);lines=[];lua.globals().print=lambda *x:lines.append(' '.join(map(str,x)))
  lua.globals().arg=lua.table_from({0:'isolated-long-sampler',1:str(extracted/'physbone_runtime.lua'),2:str(extracted/'physbone_compat.lua'),10:str(work/'fixture-compact.log')})
  test=(ROOT/'outputs/physics-test01-multiplayer-combat-fps-20261116/diagnostic-lifetime-test.lua').read_text('utf8')
  old='local e=fakeEngine();local av,armor=e:player("probe",0,7);for _,u in ipairs(armor)do u.chains=12 end'
  new=old+'\nlocal team,remote=e:player("team",20,7);for _,u in ipairs(remote)do u.chains=12 end'
  assert test.count(old)==1;test=test.replace(old,new)
  lua.execute(test)
  log=(work/('hd2physbone_test01_'+variant+'_perf.log')).read_text('utf8')
  times=[float(x) for x in re.findall(r'TEST01_PERF t=([\d.]+)',log)]
  assert times and max(times)>100 and 'TEST01_PERF_STOP' in log and 'identity=fp-confirmed' in log and 'remoteUnits=7' in log
  assert ('physicsExcluded=84' if variant=='A' else 'physicsExcluded=0') in log
  assert len(log.encode())<=260000
  outcomes.append({'vm':vm,'bounded1200SecondSamplerPassed':True,'fakeLogBytes':len(log.encode()),'latestFakeTime':max(times),'actualGameLog':False})
 report={'variant':variant,'status':'PASS_ACTUAL_EXPORT_OFFLINE_NOT_FPS','zipSha256':proof['zipSha256'],'zipBytes':package.stat().st_size,'versions':{'runtime':version,'compat':'1.3.8'},'defaultPolicy':mode,'payloadSha256':payloads,'productionProfileLiteralSha256':profile_hashes,'coreChangedMethods':0,'coreChangedResources':audit['changedResources'],'standaloneAndSampler':outcomes,'gameNotRun':True}
 (OUT/(variant+'-package-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');reports.append(report)
 print('PASS '+variant+' actual ZIP, source identity, profile/math preservation, both-VM install/uninstall, long sampler',flush=True)
assert (OUT/'A-source/physbone_compat.lua').read_bytes()==(OUT/'B-source/physbone_compat.lua').read_bytes()
(OUT/'packages-verification.json').write_text(json.dumps({'status':'PASS_BOTH_ACTUAL_ZIPS_OFFLINE','reports':reports},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
