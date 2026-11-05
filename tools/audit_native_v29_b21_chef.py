"""Exercise the standalone B21 addon with the actual Chef 1.4.1 reader/sandbox.

All engine calls and file handles are in-memory fixtures; no game is launched.
"""
import json
import sys
from package_native_v12 import ROOT, digest, save_json

W = ROOT / 'outputs/native-v29-b21-20261105'
sys.path.insert(0, str(ROOT / 'outputs/native-v11-20261104/test-runtime'))
sys.path.insert(0, str(ROOT / 'outputs/native-fix-20261103/test-runtime'))
from lupa.lua51 import LuaRuntime


def main():
    core_path = ROOT / 'outputs/native-v5-20261103/chef-loader-review/9ba626afa44a3aa3.patch_2_c27789387e64579a.lua'
    core = core_path.read_text(encoding='utf-8')
    source = (W / 'native-grip-capture.lua').read_text(encoding='utf-8')
    module_path = ROOT / 'HD2PhysBoneCompat/src/native_reference_capture.lua'
    assert module_path.read_text(encoding='utf-8') in source
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(r'''
logs={};opens={};now=0;closeCalls=0;flushCalls=0;mutationCalls=0
function memory_file(blob)
 local pos=0;local f={}
 function f:read(n)local s=blob:sub(pos+1,pos+n);pos=pos+#s;return s end
 function f:seek(whence,n)pos=whence=='set'and n or pos+(n or 0);return pos end
 function f:write(...)logs[#logs+1]=table.concat({...});return self end
 function f:flush()flushCalls=flushCalls+1;return true end
 function f:close()closeCalls=closeCalls+1;return true end
 return f
end
local function forbidden()mutationCalls=mutationCalls+1;error('mutation called')end
G={};for k,v in pairs(_G)do G[k]=v end;G._G=G
G.io={open=function(path,mode)
 opens[#opens+1]={path=path,mode=mode}
 if mode=='a'then return memory_file('')end
 return nil,'not in fixture'
end,type=function()return 'file'end}
G.os={clock=os.clock,time=os.time,date=os.date,difftime=os.difftime,
 getenv=function(k)return k=='LOCALAPPDATA'and 'C:/fixture/local'or 'C:/fixture/roaming'end}
G.stingray={
 Application={worlds=function()return {}end,time_since_launch=function()return now end,string_to_id32=function(s)return s end},
 World={units=function()return {}end,update_unit=forbidden,link_unit=forbidden,unlink_unit=forbidden},
 Unit={local_pose=function()error('no units in fixture')end,world_pose=function()error('no units in fixture')end,
  set_local_pose=forbidden,set_world_pose=forbidden,set_animation_state_machine=forbidden},
 Matrix4x4={to_elements=function(m)return unpack(m)end},IdString64={to_hex=function(v)return v end}}
G.__hd2physbone_runtime={sentinel=true}
''')
    sandbox = core.split('services.sandbox = (function()', 1)[1].split('-- @@END sandbox.lua@@', 1)[0]
    vm.globals().sandbox_module = vm.execute('return (function()' + sandbox)
    vm.execute(r'''
sb=sandbox_module.install({G=G,io=G.io,os=G.os,debug=debug,
 DIR='C:/fixture/roaming/Arrowhead/Helldivers2/',
 GAME_DIR='C:/fixture/roaming/Arrowhead/Helldivers2/',OLD_DIR='C:/fixture/local/',
 FILES='chef_loader',log=function(s)logs[#logs+1]=s end})
''')
    hooks = core.split('function starter.read_module(a, m)', 1)[1].split('-- What a mod is doing', 1)[0]
    vm.execute('starter={get=function(t,k)return t[k]end};function starter.read_module(a,m)' + hooks)
    vm.globals().new_source = source
    result = vm.execute(r'''
local owner='mods/hd2modmanager/native_grip_capture'
local api={loader='Chef Shared Loader',loader_version='1.4.1',api=1,name=owner,
 log_directory='C:/fixture/roaming/Arrowhead/Helldivers2'}
local function start(loader)
 local env=sb.env(owner)
 for k,f in pairs(starter.game_hooks)do rawset(env,k,f)end
 local chunk=assert(loadstring(new_source,'@'..owner));setfenv(chunk,env)
 local mod=chunk(loader);local a={};starter.read_module(a,mod)
 return env,mod,a
end
local env,mod,a=start(api)
assert(a.version=='1.0.0'and type(a.hooks.update)=='function'and type(a.hooks.render)=='function')
assert(type(a.hooks.shutdown)=='function'and type(mod.on_stop)=='function')
local state=assert(rawget(env,'__hd2_native_grip_capture'))
assert(not state.stopped and state.samples==0)
local path=api.log_directory..'/hd2_native_grip_capture.log'
assert(sb.check(path,'a',owner),'capture path denied')
assert(#opens==1 and opens[1].path==path and opens[1].mode=='a')
for i=1,60 do now=i/60;a.hooks.update();a.hooks.render()end
assert(state.samples==0 and not state.stopped,'empty world should await an Avatar')
mod.on_stop();assert(state.stopped and rawget(env,'__hd2_native_grip_capture')==nil)
local entries=#logs;a.hooks.shutdown();mod.on_stop();a.hooks.update();a.hooks.render()
assert(#logs==entries and closeCalls==1,'stop must be idempotent')
assert(flushCalls>=2 and mutationCalls==0 and G.__hd2physbone_runtime.sentinel)
assert(not pcall(start,nil),'missing Chef context accepted')
assert(#opens==1,'non-Chef startup opened a log')
local loaded,complete=false,false
for _,s in ipairs(logs)do
 loaded=loaded or s:find('"event":"loaded"',1,true)~=nil
 complete=complete or s:find('"event":"complete"',1,true)~=nil
 assert(not s:find('"event":"callback_error"',1,true),'callback failed')
end
assert(loaded and complete,'lifecycle log absent')
return {status='PASS',chefVersion=api.loader_version,addonVersion=a.version,
 updateCalls=60,renderCalls=60,appendLogPath=path,appendLogAllowed=true,
 shutdownAndStop=true,nonChefRejected=true,mutationCalls=mutationCalls,
 independentRuntimeStatePreserved=true,gamePoseCaptured=false,gameDeployed=false}
''')
    # Exercise the binary parser from the installed Chef source too.
    reader = core[core.index('local LUA_TYPE = {'):core.index('discover = function()', core.index('local LUA_TYPE = {'))]
    vm.execute('''scan={bad=0,huge=0,big=0,seq=0,said={},mine={},cores={},langs={}};
found_addons={};found_named={};found_options={};found_boots={};
local byte,sub,min=string.byte,string.sub,math.min
local ALLOW='^mods/[%w_%-]+/[%w_%-/]*[%w_%-]$'
local log=function(s)logs[#logs+1]=s end;local fmt=string.format
''' + reader + '\nparse_patch=read_patch')
    patch = W / 'runtime/9ba626afa44a3aa3.patch_0'
    vm.globals().patch_bytes = patch.read_bytes()
    vm.execute("""
parse_patch(memory_file(patch_bytes),'data/9ba626afa44a3aa3.patch_8')
assert(#found_addons==1 and found_addons[1].name=='mods/hd2modmanager/native_grip_capture')
assert(scan.bad==0 and scan.big==0 and found_addons[1].src==new_source,'binary source mismatch')
""")
    report = dict(result.items())
    report.update(actualChefParser=True, actualChefSandbox=True, actualChefModuleSelection=True,
                  loaderSha256=digest(core_path), assembledSha256=digest(W / 'native-grip-capture.lua'),
                  patchSha256=digest(patch), moduleSha256=digest(module_path),
                  callbackPositionRelativeToIK='unverified',
                  scope='Actual loader source with simulated empty worlds and in-memory IO.')
    save_json(W / 'chef-compatibility-audit.json', report)
    (W / 'chef-fixture.log').write_text('\n'.join(vm.globals().logs.values()), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
