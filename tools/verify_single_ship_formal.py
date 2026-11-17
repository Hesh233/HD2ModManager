"""Verify actual formal export contents, all source/profile hashes and installers."""
from pathlib import Path
import hashlib,importlib,json,os,struct,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-ship-vrd-formal-20261117';PROD=ROOT/'HD2PhysBoneCompat/src/production'
def sha(data):return hashlib.sha256(data).hexdigest()
manifest=json.loads((PROD/'single_remote_release_manifest.json').read_text('utf8'));base=(OUT/'before/single_remote_compat.lua').read_text('utf8');rows=[]
for v,version in [('A','2.3.13'),('B','2.3.14')]:
 e=OUT/(v+'-export');proof=json.loads((e/'physics-provenance.json').read_text('utf8'));package=e/'physics-runtime.zip'
 assert proof['runtimeVersion']==version and proof['compatVersion']=='1.3.10' and sha(package.read_bytes())==proof['zipSha256']
 assert proof['owner']=='mods/hd2modmanager/physbone' and proof['guid']=='7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01'
 with zipfile.ZipFile(package)as z:
  assert z.testzip()is None and len(z.namelist())==4 and len(set(z.namelist()))==4
  for ent in proof['entries']:
   b=z.read(ent['path']);assert len(b)==ent['bytes'] and sha(b)==ent['sha256']
  assert json.loads(z.read('manifest.json'))['Guid']==proof['guid']
  p=z.read('9ba626afa44a3aa3.patch_0');at=struct.unpack_from('<Q',p,120)[0];size=struct.unpack_from('<I',p,160)[0];s=p[at+8:at+size].decode('utf8').replace('\r\n','\n')
 assert sha(s.encode())==proof['sourceSha256'] and s==(e/'export/lua版/hd2physbone.lua').read_text('utf8')
 extracted=OUT/(v+'-extracted');extracted.mkdir(exist_ok=True)
 entry=next(x for x in manifest['sources']if x['variant']==v)
 for name,label in [('physbone_runtime.lua','PhysBoneRuntime'),('physbone_compat.lua','PhysBoneCompat')]:
  expected=(OUT/(v+'-source')/name).read_text('utf8');prefix='local '+label+' = (function()\n';offset=s.index(prefix)+len(prefix)
  assert s[offset:offset+len(expected)]==expected and s[offset+len(expected):].startswith('\nend)()')
  (extracted/name).write_text(expected,encoding='utf8',newline='\n')
  assert sha(expected.encode())==(entry['runtimeSha256']if 'runtime'in name else entry['compatSha256'])
 compat=(extracted/'physbone_compat.lua').read_text('utf8');assert compat==base.replace('M.version = "1.3.9"','M.version = "1.3.10"',1),'Accepted complete solver/bind/contacts/FK/driver source drifted'
 runtime=(extracted/'physbone_runtime.lua').read_text('utf8');assert 'Perf.'not in runtime and 'TEST01_PERF'not in runtime and 'hd2physbone_test01_'not in runtime
 assert 'SHIP_VRD_ENABLED' in runtime and 'World.num_levels' in runtime and 'single.sceneMode~="ship"' in runtime
 assert 'LOCKED_NO_MORE_ID_CHECKS'in runtime and 'if proof.owner~=nil and single.selfUnit==proof.owner then return true end'in runtime
 audit=json.loads((OUT/(v+'-core-audit.json')).read_text('utf8'));assert audit['identityUnchanged'] and not audit['changedMethods'] and not audit['changedConstants'] and not audit['changedReferences']
 assert audit['methodsBefore']==audit['methodsAfter']==19802 and audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']
 outcomes=[]
 for vm in ['lua51','luajit21']:
  L=importlib.import_module('lupa.'+vm).LuaRuntime
  for loader in [None,'Chef Shared Loader','CowboyBingusModLoader']:
   work=OUT/(v+'-installer-'+vm+'-'+(loader or 'plain').replace(' ','-'));work.mkdir(exist_ok=True);os.environ['LOCALAPPDATA']=str(work);os.environ['APPDATA']=str(work)
   lua=L(unpack_returned_tuples=True);lua.execute('clock=0;prior=0;render=function()prior=prior+1 end;stingray={Application={worlds=function()return{}end,time_since_launch=function()return clock end}}')
   ctx=lua.table_from({'loader':loader,'log_directory':str(work)}) if loader else None
   m=lua.execute(s,ctx);assert m.VERSION==version and m.FORMAL_PHYSICS_VARIANT==v
   lua.globals().module=m;lua.execute('old=render;module.install(stingray,{});assert(render==old);for i=1,10 do clock=clock+.01;render()end');assert lua.globals().prior==10
   assert m.uninstall()is True and lua.globals()['__hd2physbone_runtime']is None;lua.execute('render()');assert lua.globals().prior==11
   assert not list(work.glob('*perf.log'))
   if loader:
    lua.globals().sceneLoader=ctx;lua.globals().sceneModule=m
    lua.execute('newState=sceneModule.install(stingray,{compat={}});assert(newState.options.sceneContext==sceneLoader);sceneModule.uninstall()')
   outcomes.append({'vm':vm,'loaderMetadataShape':loader,'installDuplicateInstallUninstallPassed':True})
 row={'status':'PASS_ACTUAL_FORMAL_ZIP_OFFLINE','variant':v,'runtimeVersion':version,'compatVersion':'1.3.10','zipSha256':proof['zipSha256'],'zipBytes':package.stat().st_size,'wholeAcceptedSolverDataUnchangedExceptVersion':True,'clockGcSamplerRemoved':True,'coreChangedMethods':0,'installers':outcomes,'notNewGameplayFpsMeasurement':True}
 (OUT/(v+'-formal-verification.json')).write_text(json.dumps(row,indent=2)+'\n',encoding='utf8');rows.append(row);print('PASS '+v+' formal actual ZIP / all source hashes / entire accepted compat / both VM installers',flush=True)
(OUT/'formal-verification.json').write_text(json.dumps({'status':'PASS_TWO_FORMAL_PACKAGES','packages':rows},indent=2)+'\n',encoding='utf8')
