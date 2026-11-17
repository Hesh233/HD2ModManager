"""Rebuild the two formal variants with a ship-specific VRD branch."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-ship-vrd-formal-20261117';PROD=ROOT/'HD2PhysBoneCompat/src/production';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def once(s,a,b):assert s.count(a)==1,(a[:85],s.count(a));return s.replace(a,b,1)
previous=json.loads((OUT/'before/single_remote_release_manifest.json').read_text('utf8'))
files=set(p for p in NORMAL.iterdir()if p.is_file())
files.update([ROOT/'HD2PhysBoneCompat/src/physbone_runtime.lua',ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua',ROOT/'../config.toml',ROOT/'tools/native-python/anim_batch_mod/config.toml'])
for model in ['[单骨架模型]test01','[单骨架模型]Cow_QiPao_Milltina_Nick']:files.update(p for p in (NORMAL/'test-library'/model).rglob('*')if p.is_file())
files.update(p for p in (NORMAL/'test-library').rglob('*.json')if p.is_file())
files.update(p for p in (NORMAL/'运行时配套').glob('*2.3.1[12]*.zip'))
files.update(p for p in (NORMAL/'非运行文件/归档').glob('*AB*20261117*.zip'))
protected={str(p.resolve()):sha(p)for p in files if p.is_file()};(OUT/'protected-before.json').write_text(json.dumps(protected,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
for old in previous['sources']:assert sha(OUT/'before'/('single_remote_'+old['variant']+'_runtime.lua'))==old['runtimeSha256']
oldcompat=(OUT/'before/single_remote_compat.lua').read_text('utf8');assert sha(OUT/'before/single_remote_compat.lua')==previous['sources'][0]['compatSha256']
c=once(oldcompat,'M.version = "1.3.9"','M.version = "1.3.10"')
(PROD/'single_remote_compat.lua').write_text(c,encoding='utf8',newline='\n')
scene=(PROD/'single_ship_scene.lua.in').read_text('utf8');policy=(PROD/'single_remote_policy.lua.in').read_text('utf8').replace('@SCENE@',scene)
oldpolicy=(OUT/'before/single_remote_policy.lua.in').read_text('utf8');rows=[]
for v,version in [('A','2.3.13'),('B','2.3.14')]:
 old=next(x for x in previous['sources']if x['variant']==v);mode=old['policy'];s=(OUT/'before'/('single_remote_'+v+'_runtime.lua')).read_text('utf8')
 s=once(s,'M.VERSION = "'+old['runtimeVersion']+'"','M.VERSION = "'+version+'"')
 s=once(s,oldpolicy.replace('@POLICY@',mode).replace('@VARIANT@',v),policy.replace('@POLICY@',mode).replace('@VARIANT@',v))
 a='''\tif formal then
\t\tapi.sample_ads_once(runtime, single)
\t\tif scene=="ship" or RemotePhysics.DEFAULT == "remote-no-vrd" then refresh_avatar_distances(S, single) end'''
 b='''\tif formal then
\t\tlocal scene,changed=RemotePhysics.scene(runtime,single)
\t\tif changed then ads_note(runtime,scene=="ship" and "SHIP_VRD_ENABLED" or (scene=="mission" and "MISSION_WAIT_AIM" or "UNKNOWN_SCENE_RESTRICTED"),nil,0) end
\t\tif scene~="ship" then api.sample_ads_once(runtime, single) end
\t\tif RemotePhysics.DEFAULT == "remote-no-vrd" then refresh_avatar_distances(S, single) end'''
 s=once(s,a,b)
 s=once(s,'if formal and RemotePhysics.DEFAULT == "self-only" and view.owner ~= single.selfUnit then','if formal and single.sceneMode~="ship" and RemotePhysics.DEFAULT == "self-only" and view.owner ~= single.selfUnit then')
 s=once(s,'\toptions = options or {}\n\tlocal compat = options.compat','''\toptions = options or {}
\t-- In the actual exported addon __hd2_loader is the lexical loader argument.
\t-- Standalone source can instead inject options.sceneContext explicitly.
\tlocal context=__hd2_loader
\tif type(context)~="table" then context=rawget(_G,"__hd2_loader") end
\tif options.sceneContext==nil and type(context)=="table" then options.sceneContext=context end
\tlocal compat = options.compat''')
 p=PROD/('single_remote_'+v+'_runtime.lua');p.write_text(s,encoding='utf8',newline='\n');stage=OUT/(v+'-source');stage.mkdir();(stage/'physbone_runtime.lua').write_bytes(p.read_bytes());(stage/'physbone_compat.lua').write_bytes((PROD/'single_remote_compat.lua').read_bytes())
 rows.append({'variant':v,'runtimeVersion':version,'compatVersion':'1.3.10','policy':mode,'runtimePath':str(p),'runtimeSha256':sha(p),'compatSha256':sha(PROD/'single_remote_compat.lua')})
manifest={**previous,'identityRevision':'first-person-aim-once-v1','sceneRevision':'ship-vrd-mission-ads-v2','sources':rows,'shipPolicy':{'A':'springs and VRD; no ADS identification','B':'springs and VRD; no ADS identification'},'sceneContract':{'mainWorldFromLoader':True,'levelsShip':[1,2],'levelsMissionGreaterThan':10,'levelsZeroOrUnknownNotAutomaticallyShip':True,'chefGuardedHelper':'call (api is revision number)','sceneProbeFrames':30,'sameWorldSceneChangeResetsPolicyEpochAndAdsIdentity':True},'templateSha256':{'identity':sha(PROD/'single_ads_identity.lua.in'),'policy':sha(PROD/'single_remote_policy.lua.in'),'scene':sha(PROD/'single_ship_scene.lua.in')}}
(PROD/'single_remote_release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8');(OUT/'source-build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
assert all(Path(p).is_file() and sha(Path(p))==h for p,h in protected.items())
print(json.dumps({'status':'FORMAL_SHIP_VRD_SOURCES','sources':rows,'protectedFiles':len(protected)},ensure_ascii=False,indent=2))
