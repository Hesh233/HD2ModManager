"""Verify real A/B exports and exact production consumers before delivery."""
from pathlib import Path
import argparse,base64,hashlib,importlib,json,os,struct,zipfile,subprocess
ROOT=Path(__file__).resolve().parents[1];LAB=ROOT/'outputs/physics-single-consumers-ship-11fps-20261117';PROD=ROOT/'HD2PhysBoneCompat/src/production'
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);ap.add_argument('--evidence-root',type=Path,default=LAB);ap.add_argument('--loader-size-fix',action='store_true');a=ap.parse_args();LAB=a.evidence_root.resolve();OUT=a.output.resolve()if a.output else LAB/'release-candidate';assert OUT.is_relative_to(ROOT) and not OUT.is_relative_to(ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7')
def sha(b):return hashlib.sha256(b).hexdigest()
manifest=json.loads((PROD/'single_remote_release_manifest.json').read_text('utf-8-sig'));catalog=json.loads((PROD/'single_consumer_catalog.json').read_text('utf-8-sig'))
assert manifest['consumerProfiles']==len(catalog['units'])==61 and manifest['consumerDistinctResources']==39
assert sha((PROD/'single_consumer_catalog.json').read_bytes())==manifest['consumerCatalogSha256']
for field,name in [('consumerCompat','single_consumers_compat.lua.in'),('consumerRuntime','single_consumers_runtime.lua.in'),('consumerSha256','single_consumer_sha256.lua.in')]:assert sha((PROD/name).read_bytes())==manifest['templateSha256'][field]
assert sha((ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs').read_bytes())==manifest['templateSha256']['consumerProducer']
assert sha((ROOT/'tools/build_single_consumers_ship_fix.py').read_bytes())==manifest['templateSha256']['consumerFixBuilder']
cv='1.3.13'if a.loader_size_fix else'1.3.12'
assert manifest['renderGpuHashing'] is False and manifest['realGameAcceptanceStatus']==('loader-size-candidate-pending-physics-and-FPS'if a.loader_size_fix else'correction-candidate-pending-ship-FPS')
for p in catalog['units']:
 assert p['proofMode']=='toc-exact-palette-v2' and p['palettePolicy']=='all-toc-RealIndices-v1'
 assert set(p['weightedNodes']) <= set(p['skinPaletteNodes'])
 assert sha(base64.b64decode(p['tocExactBase64'],validate=True))==p['tocSha256']
for m in catalog['models']:
 assert sha(base64.b64decode(m['rigExactBase64'],validate=True))==m['rigSha256']
 assert sha(base64.b64decode(m['driverExactBase64'],validate=True))==m['driverRigSha256']
base=(LAB/('before/HD2PhysBoneCompat/src/production/single_remote_compat.lua'if a.loader_size_fix else'before-source/single_remote_compat.lua')).read_text('utf-8-sig');prefix=base.split('-- Streaming SHA-256. Bounded verification work; no shell/helper process.',1)[0].replace('M.version = "'+('1.3.12'if a.loader_size_fix else'1.3.11')+'"','M.version = "'+cv+'"',1)
reports=[]
for entry in manifest['sources']:
 v=entry['variant'];export=OUT/(v+'-export');proof=json.loads((export/'physics-provenance.json').read_text('utf-8-sig'));package=export/'physics-runtime.zip'
 assert proof['runtimeVersion']==entry['runtimeVersion'] and proof['compatVersion']==cv
 assert proof['owner']=='mods/hd2modmanager/physbone'and proof['guid']=='7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01'
 assert sha(package.read_bytes())==proof['zipSha256']
 with zipfile.ZipFile(package)as z:
  assert z.testzip()is None and len(z.namelist())==4 and len(set(z.namelist()))==4
  for p in proof['entries']:
   b=z.read(p['path']);assert len(b)==p['bytes']and sha(b)==p['sha256']
  blob=z.read('9ba626afa44a3aa3.patch_0');at=struct.unpack_from('<Q',blob,120)[0];size=struct.unpack_from('<I',blob,160)[0];s=blob[at+8:at+size].decode('utf-8').replace('\r\n','\n')
 assert size<=4*1024*1024 and len(blob[at+8:at+size])+8==size,'Actual aggregated Lua exceeds Chef limit'
 (OUT/(v+'-addon.lua')).write_bytes(blob[at+8:at+size])
 assert sha(s.encode())==proof['sourceSha256'];extracted=OUT/(v+'-extracted');extracted.mkdir(exist_ok=True)
 for name,label in [('physbone_runtime.lua','PhysBoneRuntime'),('physbone_compat.lua','PhysBoneCompat')]:
  wanted=(LAB/(v+'-source')/name).read_text('utf-8-sig');start=s.index('local '+label+' = (function()\n')+len('local '+label+' = (function()\n')
  assert s[start:start+len(wanted)]==wanted and s[start+len(wanted):].startswith('\nend)()')
  (extracted/name).write_text(wanted,encoding='utf-8',newline='\n')
  assert sha(wanted.encode())==(entry['runtimeSha256']if 'runtime'in name else entry['compatSha256'])
 c=(extracted/'physbone_compat.lua').read_text('utf-8-sig');assert c.startswith(prefix),'Original complete math/Source2/T16/profile/VRD body drifted'
 for marker in ['local T1201','local T16','function M.step_tip','function M.update_tip','function M.update_drivers']:
  assert marker in prefix
 rt=(extracted/'physbone_runtime.lua').read_text('utf-8-sig');assert 'Perf.'not in rt and 'TEST01_PERF'not in rt
 assert 'LOCKED_NO_MORE_ID_CHECKS'in rt and 'SHIP_VRD_ENABLED'in rt and 'ConsumerRuntime.legitimate'in rt
 assert 'single_scene_policy_transition'not in rt and 'pcall(Compat.single_remote_policy_transition,'in rt
 audit=json.loads((OUT/(v+'-core-audit.json')).read_text('utf-8-sig'))
 assert audit['identityUnchanged']and not audit['changedMethods']and not audit['changedConstants']and not audit['changedReferences']
 assert audit['methodsBefore']==audit['methodsAfter']==19802 and audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']
 installers=[]
 for vm in ['lua51','luajit21']:
  L=importlib.import_module('lupa.'+vm).LuaRuntime
  for loader in [None,'Chef Shared Loader','CowboyBingusModLoader']:
   work=OUT/(v+'-consumer-installer-'+vm+'-'+(loader or'plain').replace(' ','-'));work.mkdir(exist_ok=True);os.environ['APPDATA']=str(work);os.environ['LOCALAPPDATA']=str(work)
   lua=L(unpack_returned_tuples=True);lua.execute('clock=0;prior=0;render=function()prior=prior+1 end;stingray={Application={worlds=function()return{}end,time_since_launch=function()return clock end}}')
   ctx=lua.table_from({'loader':loader,'log_directory':str(work)})if loader else None
   m=lua.execute(s,ctx);assert m.VERSION==entry['runtimeVersion'] and m.FORMAL_PHYSICS_VARIANT==v
   lua.globals().module=m;lua.execute('old=render;module.install(stingray,{});assert(render==old);for i=1,10 do clock=clock+.01;render()end');assert lua.globals().prior==10
   assert m.uninstall()is True;lua.execute('render()');assert lua.globals().prior==11 and lua.globals()['__hd2physbone_runtime']is None
   if loader:
    lua.globals().ctx=ctx;lua.execute('st=module.install(stingray,{compat={}});assert(st.options.sceneContext==ctx);module.uninstall()')
   installers.append(dict(vm=vm,loader=loader,installDuplicateInstallUninstall=True))
 result=dict(status=('PASS_ACTUAL_LOADER_SIZE_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS'if a.loader_size_fix else'PASS_ACTUAL_SHIP_FIX_CANDIDATE_ZIP_NOT_GAME_FPS'),variant=v,runtimeVersion=entry['runtimeVersion'],compatVersion=cv,luaResourceBytes=size,zipBytes=package.stat().st_size,zipSha256=proof['zipSha256'],originalMathAndProfilesBodyUnchanged=True,methodsChanged=0,resourcesChanged=2,installers=installers,newGameFpsMeasurement=False)
 (OUT/(v+'-formal-verification.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');reports.append(result)
print(json.dumps(reports,ensure_ascii=False,indent=2))
