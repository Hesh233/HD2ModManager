"""Build the two formal single-skeleton variants from the frozen accepted A/B inputs.
No manager/default-policy replacement, model/config/profile edit or game deployment.
"""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-ads-once-release-20261117';OLD=ROOT/'outputs/physics-test01-remote-ab-20261116';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';PROD=ROOT/'HD2PhysBoneCompat/src/production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s,a,b):assert s.count(a)==1,(a[:70],s.count(a));return s.replace(a,b,1)
proof=json.loads((OLD/'source-build.json').read_text('utf8'))
protected=set(p for p in NORMAL.iterdir() if p.is_file())
protected.update([ROOT/'HD2PhysBoneCompat/src/physbone_runtime.lua',ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua',ROOT/'../config.toml',ROOT/'tools/native-python/anim_batch_mod/config.toml'])
for model in ['[单骨架模型]test01','[单骨架模型]Cow_QiPao_Milltina_Nick']:
 protected.update(p for p in (NORMAL/'test-library'/model).rglob('*') if p.is_file())
protected.update(p for p in (NORMAL/'test-library').rglob('*.json') if p.is_file())
original={str(p.resolve()):sha(p) for p in protected if p.is_file()}
(OUT/'protected-before.json').write_text(json.dumps(original,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(OUT/'before-AGENTS.md').write_bytes((ROOT/'AGENTS.md').read_bytes())
(OUT/'before-TODO.md').write_bytes((ROOT/'docs/TODO.md').read_bytes())
inputs=OUT/'accepted-inputs';inputs.mkdir()
for variant in ['A','B']:
 p=OLD/(variant+'-source');v=next(x for x in proof['variants'] if x['variant']==variant)
 assert sha(p/'physbone_runtime.lua')==v['runtimeSha256'] and sha(p/'physbone_compat.lua')==v['compatSha256']
 shutil.copytree(p,inputs/(variant+'-source'))
 (inputs/(variant+'-test-package.zip')).write_bytes((OLD/(variant+'-export/physics-runtime.zip')).read_bytes())
(inputs/'test-delivery.json').write_bytes((OLD/'delivery.json').read_bytes())
# The current A library payload is still present; preserve and verify it too.
active=NORMAL/'test-library/物理运行时-A-单骨架仅自己物理-2.3.9-r1-待实测'
active_patch=next(active.rglob('9ba626afa44a3aa3.patch_0'))
a_proof=json.loads((OLD/'A-export/physics-provenance.json').read_text('utf8'))
assert sha(active_patch)==next(e['sha256'] for e in a_proof['entries'] if e['path'].endswith('.patch_0'))
(inputs/'actual-tested-A.patch_0').write_bytes(active_patch.read_bytes())
(inputs/'actual-tested-A-integrity.json').write_text(json.dumps({'currentLibraryPath':str(active_patch),'sha256':sha(active_patch),'matchesDeliveredA':True,'BRemovedFromCurrentLibrary':True,'BIdentityEstablishedByVersionAndRecordedModeNotCurrentPatchReadback':True},indent=2)+'\n',encoding='utf8')
common=(inputs/'A-source/physbone_compat.lua').read_text('utf8');common=once(common,'M.version = "1.3.8"','M.version = "1.3.9"')
assert common==(inputs/'B-source/physbone_compat.lua').read_text('utf8').replace('M.version = "1.3.8"','M.version = "1.3.9"',1)
common_path=PROD/'single_remote_compat.lua';assert not common_path.exists();common_path.write_text(common,encoding='utf8',newline='\n')
ads=(PROD/'single_ads_identity.lua.in').read_text('utf8');policy=(PROD/'single_remote_policy.lua.in').read_text('utf8')
old_policy=(ROOT/'HD2PhysBoneCompat/src/experimental/single_remote_ab_policy.lua.in').read_text('utf8');rows=[]
for variant,version,mode in [('A','2.3.11','self-only'),('B','2.3.12','remote-no-vrd')]:
 s=(inputs/(variant+'-source/physbone_runtime.lua')).read_text('utf8')
 old_version='2.3.9' if variant=='A' else '2.3.10'
 s=once(s,'M.VERSION = "'+old_version+'"','M.VERSION = "'+version+'"')
 old=old_policy.replace('@POLICY@',mode).replace('@VARIANT@',variant)
 s=once(s,old,policy.replace('@POLICY@',mode).replace('@VARIANT@',variant))
 s=once(s,'local Single = (function()','local RemotePhysics\nlocal Single = (function()')
 s=once(s,'function api.tick(runtime)\n',ads.replace('@VARIANT@',variant)+'\nfunction api.tick(runtime)\n')
 a='''\tsingle.cache.frame = runtime.frame
\trefresh_avatar_distances(S, single)
\tlocal ok, err = pcall(identity_watch, S, single)'''
 b='''\tsingle.cache.frame = runtime.frame
\tlocal formal = runtime.options.singleFormalPolicy ~= false
\tif formal then
\t\tapi.sample_ads_once(runtime, single)
\t\tif RemotePhysics.DEFAULT == "remote-no-vrd" then refresh_avatar_distances(S, single) end
\telse refresh_avatar_distances(S, single) end
\t-- Existing preview/follower cleanup is NOT a local-player identity check.
\t-- Preserve the accepted motion-based removal of stationary ship previews.
\tlocal ok, err = pcall(identity_watch, S, single)'''
 s=once(s,a,b)
 s=once(s,'\tfp_lock_watch(S, single)\n\tscheduler_watch(S, single, runtime.dt)',
        '\tif not formal then fp_lock_watch(S, single); scheduler_watch(S, single, runtime.dt) end')
 a='\t\tif (view.ownerOrder or 99) <= 1 or runtime.cache.cameraUsable ~= true then primaryChains = primaryChains + chains'
 b='\t\tif formal and RemotePhysics.DEFAULT == "self-only" and view.owner ~= single.selfUnit then\n\t\t\t-- Excluded remote/unknown chains are retained for lifecycle, not budget.\n\t\telseif (view.ownerOrder or 99) <= 1 or runtime.cache.cameraUsable ~= true then primaryChains = primaryChains + chains'
 s=once(s,a,b)
 a='\t\tsource.owner, source.ownerTag, source.singleOwnerOrder = view.owner, view.ownerTag, view.ownerOrder'
 s=once(s,a,a+'\n\t\tif formal then source.ownerOrder = view.ownerOrder; RemotePhysics.bind(single, source) end')
 a='\t\tif single.driveHoldUntil ~= nil and runtime.frame < single.driveHoldUntil then source.singleDue = false end'
 s=once(s,a,a+'\n\t\tif source.singleRemotePhysicsExcluded == true then source.singleDue, source.pendingDt = false, 0 end')
 s=once(s,'\tRemoteTest.apply(runtime)','\tRemotePhysics.frame(runtime)')
 # Formal runtime contains no sampled clock/GC profiler or test-log filenames.
 start=s.index('-- Test01 multiplayer performance audit only.')
 end=s.index('local function readVector(S_, vector)',start)
 s=s[:start]+s[end:]
 import re
 s='\n'.join(line for line in s.split('\n') if not re.match(r'^\s*Perf\.(mark|install|begin|finish|close)\(',line) and not re.match(r'^\s*if runtime\.perf then runtime\.perf\.(scans|inventoryLists)=',line) and not re.match(r'^\s*(runtime|driver)\.perfFrameWritten,\s*(runtime|driver)\.perfFrameCalls\s*=',line))
 assert 'Perf.' not in s
 # Close only the new transition-only log, never modify the sealed test logs.
 s=once(s,'\tif runtime.attachments then pcall(runtime.attachments.release, runtime.attachments) end','\tif runtime.adsLog then pcall(function() runtime.adsLog:flush(); runtime.adsLog:close() end); runtime.adsLog=nil end\n\tif runtime.attachments then pcall(runtime.attachments.release, runtime.attachments) end')
 production=PROD/('single_remote_'+variant+'_runtime.lua');assert not production.exists();production.write_text(s,encoding='utf8',newline='\n')
 target=OUT/(variant+'-source');target.mkdir();(target/'physbone_runtime.lua').write_bytes(production.read_bytes());(target/'physbone_compat.lua').write_bytes(common_path.read_bytes())
 rows.append({'variant':variant,'runtimeVersion':version,'compatVersion':'1.3.9','policy':mode,'runtimePath':str(production),'runtimeSha256':sha(production),'compatSha256':sha(common_path)})
manifest={'schema':'hd2-single-physics-formal-family-v1','releaseDate':'2026-11-17','identityRevision':'first-person-aim-once-v1','acceptedFeedback':{'A':'large performance improvement, still behind mainline','B':'small improvement, still behind mainline'},'sources':rows,'compatPath':str(common_path),'templateSha256':{'identity':sha(PROD/'single_ads_identity.lua.in'),'policy':sha(PROD/'single_remote_policy.lua.in')},'fpReadOnlyContract':{'resource':'d0cf4d493ca08bed','nativePrefixMinimum':63,'rootNode':5,'cameraNode':51,'cameraPositionToleranceMetres':.08,'uniqueTpHorizontalToleranceMetres':.35,'consecutiveFpProofs':3,'pollFramesUntilConfirmed':20},'performanceAuditDefault':False,'performanceAuditRemovedFromFormal':True,'managerEmbeddedDefaultNotChanged':True,'modelsAndConfigNotWritten':True}
(PROD/'single_remote_release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8');(OUT/'source-build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert all(Path(p).is_file() and sha(Path(p))==h for p,h in original.items())
print(json.dumps({'status':'FORMAL_VARIANT_SOURCES_CREATED','protectedInputs':len(original),'variants':rows},ensure_ascii=False,indent=2))
