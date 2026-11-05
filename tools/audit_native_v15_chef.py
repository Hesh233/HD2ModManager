"""Run Chef 1.4.1 parser/sandbox and hook selection against the final v8 export.

All engine calls and file handles in the Lua VM are in-memory fixtures. No game
code, game writes, network calls or native modules are executed.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/native-v15-20261104'
sys.path.insert(0,str(ROOT/'outputs/native-v11-20261104/test-runtime'))
from lupa.lua51 import LuaRuntime

core_path=ROOT/'outputs/native-v5-20261103/chef-loader-review/9ba626afa44a3aa3.patch_2_c27789387e64579a.lua'
core=core_path.read_text(encoding='utf-8')
source=(W/'physics-export-delivery/lua版/hd2physbone.lua').read_bytes().decode('utf-8-sig')
profile=json.loads((W/'project/ab-profiles/B6.json').read_text(encoding='utf-8-sig'))
# Verify the published assembly embeds the current adapter/profile/runtime, not
# merely a module with the expected version string. Newline style is immaterial.
source_normalized=source.replace('\r\n','\n')
embedded_sources={}
for name in ('native_attachments.lua','physbone_runtime.lua'):
    path=ROOT/'HD2PhysBoneCompat/src'/name
    content=path.read_text(encoding='utf-8-sig')
    assert content.replace('\r\n','\n') in source_normalized, f'Stale embedded source: {name}'
    embedded_sources[name]=hashlib.sha256(path.read_bytes()).hexdigest()
old=(ROOT/'outputs/native-v5-20261103/chef-loader-review/9ba626afa44a3aa3.patch_4_14950b033ceb3511.lua').read_text(encoding='utf-8')
lua=LuaRuntime(unpack_returned_tuples=True)
lua.execute(r'''
logs={}; opens={}; now=0
function memory_file(blob)
 local pos=0;local f={}
 function f:read(n) local s=blob:sub(pos+1,pos+n);pos=pos+#s;return s end
 function f:seek(whence,n) pos=whence=='set' and n or pos+(n or 0);return pos end
 function f:write(...) logs[#logs+1]=table.concat({...});return self end
 function f:flush()return true end
 function f:close()return true end
 return f
end
function fixture_open(path,mode)
 opens[#opens+1]={path=path,mode=mode}
 if mode=='a' then return memory_file('') end
 return nil,'not in fixture'
end
G={};for k,v in pairs(_G) do G[k]=v end;G._G=G
G.io={open=fixture_open,type=function()return 'file' end}
G.os={clock=os.clock,time=os.time,date=os.date,difftime=os.difftime,
 getenv=function(k)return k=='LOCALAPPDATA' and 'C:/fixture/local' or 'C:/fixture/roaming' end}
G.stingray={Application={worlds=function()return {} end,time_since_launch=function()return now end},
 World={},Unit={}}
''')
sandbox=core.split('services.sandbox = (function()',1)[1].split('-- @@END sandbox.lua@@',1)[0]
lua.globals().sandbox_module=lua.execute('return (function()'+sandbox)
lua.execute(r'''
sb=sandbox_module.install({G=G,io=G.io,os=G.os,debug=debug,
 DIR='C:/fixture/roaming/Arrowhead/Helldivers2/',
 GAME_DIR='C:/fixture/roaming/Arrowhead/Helldivers2/',OLD_DIR='C:/fixture/local/',
 FILES='chef_loader',log=function(s)logs[#logs+1]=s end})
''')
hooks=core.split('function starter.read_module(a, m)',1)[1].split('-- What a mod is doing',1)[0]
lua.execute('starter={get=function(t,k)return t[k] end};function starter.read_module(a, m)'+hooks)
lua.globals().new_source=source
lua.globals().old_source=old
lua.globals().expected_profile=lua.table_from(profile,recursive=True)
result=lua.execute(r'''
local owner='mods/hd2modmanager/physbone'
local api={loader='Chef Shared Loader',loader_version='1.4.1',api=1,name=owner,
 log_directory='C:/fixture/roaming/Arrowhead/Helldivers2'}
local function start(src,loader)
 local env=sb.env(owner)
 for k,f in pairs(starter.game_hooks)do rawset(env,k,f)end
 local chunk=assert(loadstring(src,'@'..owner));setfenv(chunk,env)
 local module=chunk(loader)
 local a={};starter.read_module(a,module)
 if next(a.hooks)==nil and not a.hooks_mt and starter.data_only(module)then a.game_env=env end
 return env,module,a
end
local oldenv,oldmod,olda=start(old_source,api)
assert(next(olda.hooks)==nil and not olda.game_env,'baseline unexpectedly has Chef callbacks')
local oldpath='C:/fixture/local/hd2physbone.log'
assert(not sb.check(oldpath,'a',owner),'baseline log unexpectedly writable')
local env,mod,a=start(new_source,api)
assert(type(a.hooks.update)=='function' and a.hooks.render==nil and type(a.hooks.shutdown)=='function')
assert(a.version=='2.1.9' and type(mod.on_stop)=='function')
local state=rawget(env,'__hd2physbone_runtime');assert(state.installed and state.attachments)
local p=state.attachments.profile
assert(p.version==5 and p.expectedAvatarNodes==255 and p.expectedModelNodes==nil)
assert(#p.vpk==29 and #p.signature==6)
local blended=0
for i,row in ipairs(p.vpk) do
 local expected=expected_profile.vpk[i]
 assert(row.policy==expected.policy and row.index==expected.index)
 if row.policy=='source-blended-reference' then
  assert(row.configuredAnchorIndex==expected.configuredAnchorIndex and row.configuredAnchorName==expected.configuredAnchorName)
  assert(row.sourceReferenceIndex==expected.sourceReferenceIndex and row.sourceReferenceName==expected.sourceReferenceName)
  blended=blended+1
 end
end
assert(blended==23 and not p.preserveHeadAttachments and p.protectControllerParents and #p.jointProcedures==2)
local count=0
for id,expected in pairs(expected_profile.modelLayouts) do
 local layout=assert(p.modelLayouts[id],'missing model layout: '..id)
 assert(layout.nodeCount==205 and layout.nodeCount==expected.nodeCount)
 assert(layout.layoutSha256==expected.layoutSha256 and layout.unitSha256==expected.unitSha256)
 assert(layout.ownerSlot==expected.ownerSlot and #layout.signature==#p.signature)
 for i,row in ipairs(expected.signature) do
  local actual=layout.signature[i]
  assert(actual.name==row.name and actual.hash==row.hash and actual.index==row.index and actual.parentIndex==row.parentIndex)
 end
 count=count+1
end
assert(count==5 and p.armSync==true and p.armGripSync==true and #p.armChains==2)
for id in pairs(p.modelLayouts) do assert(expected_profile.modelLayouts[id],'unexpected model target') end
assert(state.options.logPath==api.log_directory..'/hd2physbone.log')
assert(sb.check(state.options.logPath,'a',owner))
assert(sb.check('data/9ba626afa44a3aa3.patch_0.gpu_resources','rb',owner))
for i=1,60 do now=i/60;a.hooks.update()end
assert(state.frame==60 and state.attachments and not state.driveErrorLogged)
mod.on_stop();assert(not state.installed and rawget(env,'__hd2physbone_runtime')==nil)
a.hooks.shutdown() -- shutdown after stop must be safe
local env2,mod2,a2=start(new_source,nil)
assert(a2.hooks.render==nil,'non-Chef export must retain its previous global-hook contract')
rawget(env2,'render')();assert(rawget(env2,'__hd2physbone_runtime').frame==1)
mod2.uninstall()
return {status='PASS',chefVersion=api.loader_version,runtimeVersion=a.version,updateFrames=state.frame,
 modelTargets=count,modelNodeCount=205,avatarNodeCount=p.expectedAvatarNodes,attachmentRows=#p.vpk,
 finalModelLayoutsMatch=true,blendedReferenceRows=blended,
 oldCallbackFailureReproduced=true,oldLogPathDenied=true,newLogPathAllowed=true,
 shutdownAndStop=true,ordinaryLoaderContractPreserved=true,gameTested=false}
''')
# Run the exact installed loader's binary reader with in-memory patch bytes.
reader=core[core.index('local LUA_TYPE = {'):core.index('discover = function()',core.index('local LUA_TYPE = {'))]
lua.execute('''scan={bad=0,huge=0,big=0,seq=0,said={},mine={},cores={},langs={}};
found_addons={};found_named={};found_options={};found_boots={};
local byte,sub,min=string.byte,string.sub,math.min
local ALLOW='^mods/[%w_%-]+/[%w_%-/]*[%w_%-]$'
local log=function(s)logs[#logs+1]=s end;local fmt=string.format
'''+reader+'\nparse_patch=read_patch')
patch=W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'
lua.globals().patch_bytes=patch.read_bytes()
lua.execute("parse_patch(memory_file(patch_bytes),'data/9ba626afa44a3aa3.patch_8')")
lua.execute("assert(#found_addons==1 and found_addons[1].name=='mods/hd2modmanager/physbone','addon discovery');assert(scan.bad==0 and scan.big==0,'reader errors');assert(found_addons[1].src==new_source,'source bytes')")
report={k:v for k,v in result.items()}
report.update(actualChefParser=True,actualChefSandbox=True,actualChefModuleSelection=True,
              loaderSha256=hashlib.sha256(core_path.read_bytes()).hexdigest(),
              addonSha256=hashlib.sha256(source.encode('utf-8')).hexdigest(),
              embeddedSourceSha256=embedded_sources,
              attachmentConsumerTiming='unobserved',
              scope='deployed Chef source with simulated engine and in-memory IO; no game deployment')
(W/'chef-compatibility-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
