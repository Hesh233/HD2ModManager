"""Actual Chef 1.4.1 parser/sandbox/starter on exported patch bytes (not naked Lua).
Only host game/state services are fixtures; parser, sandbox, start/watchdog and hook
selection are extracted unchanged from the captured production Chef core.
"""
from pathlib import Path
import hashlib

OWNER = 'mods/hd2modmanager/physbone'
CORE_SHA = '9a3bebdc2338cacb457eba25b52e5d8a731e1c01a8e4e0b89c0d9fd126be8b85'

def sha(b): return hashlib.sha256(b).hexdigest()

def scan_patch(lua, core_path, blob):
    core = Path(core_path).read_text('utf-8-sig')
    # Snapshot was normalized to UTF-8/LF; also record the physical file hash.
    assert sha(core.encode()) == CORE_SHA, 'Not the captured game Chef 1.4.1 parser'
    lua.execute(r'''
logs={}
function memory_file(blob)
 local pos=0;local f={}
 function f:read(n)local s=blob:sub(pos+1,pos+n);pos=pos+#s;return s end
 function f:seek(w,n)
  if w=='end'then pos=#blob+(n or 0)elseif w=='set'then pos=n or 0 else pos=pos+(n or 0)end
  return pos
 end
 function f:close()return true end
 return f
end
''')
    reader = core[core.index('local LUA_TYPE = {'):core.index('discover = function()', core.index('local LUA_TYPE = {'))]
    lua.execute("scan={bad=0,huge=0,big=0,seq=0,said={},mine={},cores={},langs={}};found_addons={};found_named={};found_options={};found_boots={};local byte,sub,min=string.byte,string.sub,math.min;local ALLOW='^mods/[%w_%-]+/[%w_%-/]*[%w_%-]$';local log=function(s)logs[#logs+1]=s end;local fmt=string.format\n" + reader + '\nparse_patch=read_patch')
    lua.globals().patch_bytes = blob
    lua.execute("parse_patch(memory_file(patch_bytes),'data/9ba626afa44a3aa3.patch_7')")
    g = lua.globals()
    receipt = dict(patchSha256=sha(blob), chefCoreSha256=sha(Path(core_path).read_bytes()),
                   chefNormalizedSha256=CORE_SHA, bad=g.scan.bad, big=g.scan.big,
                   huge=g.scan.huge, found=len(g.found_addons))
    if receipt['found']:
        assert receipt['found'] == 1 and g.found_addons[1].name == OWNER
        receipt['sourceSha256'] = sha(g.found_addons[1].src.encode())
    return core, receipt

def start_scanned(lua, core, output):
    lua.globals().test_output = str(Path(output).resolve()).replace('\\', '/') + '/'
    lua.execute(r'''
G={};for k,v in pairs(_G)do G[k]=v end;G._G=G
G.os={clock=os.clock,time=os.time,date=os.date,difftime=os.difftime,
 getenv=function(k)return test_output end}
local host_io=io
G.io={open=function(path,mode)
 local relative=path:gsub('\\','/')
 if relative:sub(1,5)=='data/'then path=test_output..relative end
 local f,why=host_io.open(path,mode)
 if f and mode=='rb'and(relative:match('%.gpu_resources$')or relative:match('%.stream$'))then
  return{close=function()return f:close()end,seek=function(_,...)return f:seek(...)end,
   read=function()error('GPU_CONTENT_READ_FORBIDDEN')end}
 end
 return f,why
end,type=host_io.type}
''')
    sandbox = core.split('services.sandbox = (function()', 1)[1].split('-- @@END sandbox.lua@@', 1)[0]
    lua.globals().sandbox_module = lua.execute('return (function()' + sandbox)
    lua.execute(r'''
local log=function(s)logs[#logs+1]=s end
sb=sandbox_module.install({G=G,io=G.io,os=G.os,debug=debug,DIR=test_output,
 GAME_DIR=test_output,OLD_DIR=test_output,FILES='chef_loader',log=log})
svc={sandbox=sb,ctx={},mod_switch=function()return true end,mod_title=function(n)return n end}
services={requirements=function()return{}end};v1={off=function()end}
tr={strikes={},why=tostring};off={};skip={};notices={};addons={};starter={get=function(t,k)return t[k]end}
function fingerprint(s)return 'fixture-'..#s end
function crumb()end
function options_for()return{}end
function make_api(a)return{loader='Chef Shared Loader',loader_version='1.4.1',api=1,
 name=a.name,log_directory=test_output}end
function save_state()end
''')
    # Wrap the unchanged starter functions in the production lexical names.
    parts = [core[core.index('starter.dog = {'):core.index('-- Started by another loader that handed off to me', core.index('starter.dog = {'))],
             core[core.index('function starter.heap_kb('):core.index('-- The game\'s callbacks as an addon finds', core.index('function starter.heap_kb('))],
             core[core.index('function starter.env_for('):core.index('-- "-- HD2-Requires:', core.index('function starter.env_for('))],
             core[core.index('function starter.addon(r)'):core.index('-- A mod\'s on/off row', core.index('function starter.addon(r)'))]]
    lua.execute("local clock,fmt,log=os.clock,string.format,function(s)logs[#logs+1]=s end;local FILES='chef_loader';\n" + '\n'.join(parts))
    lua.execute(r'''
starter.game_hooks={update=function()end,render=function()end,shutdown=function()end}
starter.state=function(a,s,why)a.state=s;a.why=why end
starter.changed_since_crash=function()end;starter.stays=function()end
starter.requires_ok=function()return true end
starter.data_only=function()return false end
starter.env_original=starter.env_for
starter.env_for=function(n)local env=starter.env_original(n);chef_env=env;return env end
starter.dog.arm(true)
chef_addon=starter.addon(assert(found_addons[1],'Chef did not discover physics addon'))
starter.dog.sethook();starter.dog.armed=false
assert(chef_addon.on and chef_addon.state=='running',chef_addon.why)
assert(type(chef_addon.hooks.render)=='function'and type(chef_addon.hooks.shutdown)=='function')
assert(chef_env.__hd2physbone_runtime,'physics runtime did not install in Chef sandbox')
''')
    g = lua.globals()
    receipt = dict(state=g.chef_addon.state, version=g.chef_addon.version,
                   startMs=g.chef_addon.start_ms, actualChefStarter=True,
                   actualChefSandbox=True, actualChefWatchdog=True)
    assert receipt['startMs'] < 10000, 'Chef startup budget exceeded'
    return g.chef_addon, g.chef_env, receipt

