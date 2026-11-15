"""Regression suite for TEST-only test09 physics sources and actual Chef parser."""
from __future__ import annotations
import contextlib,hashlib,io,json,subprocess,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
from build_test09_axis_test import OUT,INSTALL,COMPAT_VERSION,RUNTIME_VERSION,sha,save
from lupa.lua51 import LuaRuntime
COMPAT=OUT/'physbone_compat-test09.lua';RUNTIME=OUT/'physbone_runtime-test09.lua'

def python_test(name,source_text,filename,report):
    # Redirect ONLY the candidate source load in an existing harness. All its
    # real rigs, golden fixture references and assertions remain unchanged.
    env={'__file__':str(filename),'__name__':'__main__'};old=sys.argv;sys.argv=[str(filename),'--report',str(report)]
    output=io.StringIO()
    original_read=Path.read_text
    def read_candidate(path,*args,**kwargs):
        if path.resolve()==ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua':return original_read(COMPAT,*args,**kwargs)
        return original_read(path,*args,**kwargs)
    Path.read_text=read_candidate
    import runpy
    original_run=runpy.run_path
    def run_candidate(path,*args,**kwargs):
        if Path(path).resolve()==ROOT/'HD2PhysBoneCompat/test/driver-update-test.py':
            child={'__file__':str(path),'__name__':'test09_driver_fixture'}
            text=original_read(Path(path),'utf8').replace('1.3.1',COMPAT_VERSION)
            exec(compile(text,str(path),'exec'),child);return child
        return original_run(path,*args,**kwargs)
    runpy.run_path=run_candidate
    try:
        with contextlib.redirect_stdout(output):exec(compile(source_text,str(filename),'exec'),env)
    finally:sys.argv=old;Path.read_text=original_read;runpy.run_path=original_run
    (OUT/(name+'.log')).write_text(output.getvalue(),'utf8')
    return dict(name=name,status='PASS',report=str(report) if report.exists() else None)

def lua_test(name):
    if name=='mp_harness.lua':
        from lupa.luajit21 import LuaRuntime as Runtime
    else:Runtime=LuaRuntime
    vm=Runtime(unpack_returned_tuples=True);log=[]
    def source(path):
        resolved=Path(path).resolve()
        if resolved==ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua':return COMPAT.read_text('utf8')
        if resolved==ROOT/'HD2PhysBoneCompat/src/physbone_runtime.lua':return RUNTIME.read_text('utf8')
        return None
    vm.globals().__read=source;vm.globals().__log=lambda *v:log.append(' '.join(str(x) for x in v))
    io_dir=OUT/'harness-io';io_dir.mkdir(exist_ok=True);vm.globals().__harness_dir=str(io_dir)
    vm.execute('local getenv=os.getenv;os.getenv=function(k)if k=="LOCALAPPDATA"or k=="APPDATA"then return __harness_dir end;return getenv(k)end')
    vm.execute('''local old=loadfile
function loadfile(path) local s=__read(path);if s then return loadstring(s,'@'..path)end;return old(path)end
function dofile(path)local f,e=loadfile(path);assert(f,e);return f()end
os.exit=function(code)assert(code==nil or code==0,'harness failed exit='..tostring(code))end
print=__log
''')
    path=ROOT/'HD2PhysBoneCompat/test'/name
    args={0:str(path),1:str(RUNTIME if name=='runtime-harness-test.lua' else COMPAT),2:str(COMPAT)}
    vm.globals().arg=vm.table_from(args)
    try:vm.execute(path.read_text('utf8'))
    finally:(OUT/('lua-'+name+'.log')).write_text('\n'.join(log),'utf8')
    return dict(name=name,status='PASS',vm='LuaJIT2.1' if name=='mp_harness.lua' else 'Lua5.1')

def chef_test():
    # Actual deployed Chef1.4.1 sandbox and module discovery routines, empty
    # simulated worlds / memory-only IO. No CUA/real game access.
    import re,struct
    core_path=ROOT/'outputs/native-v5-20261103/chef-loader-review/9ba626afa44a3aa3.patch_2_c27789387e64579a.lua'
    core=core_path.read_text('utf8');vm=LuaRuntime(unpack_returned_tuples=True)
    vm.execute(r'''
logs={};opens={};now=0;mutationCalls=0
function memory_file(blob)
 local pos=0;local f={}
 function f:read(n)local s=blob:sub(pos+1,pos+n);pos=pos+#s;return s end
 function f:seek(w,n)pos=w=='set'and n or pos+(n or 0);return pos end
 function f:write(...)logs[#logs+1]=table.concat({...});return self end
 function f:flush()return true end;function f:close()return true end
 return f
end
local function forbidden()mutationCalls=mutationCalls+1;error('empty-world mutation')end
G={};for k,v in pairs(_G)do G[k]=v end;G._G=G
G.io={open=function(path,mode)opens[#opens+1]={path=path,mode=mode};if mode=='a'or mode=='w'then return memory_file('')end;return nil,'not in fixture'end,type=function()return 'file'end}
G.os={clock=os.clock,time=os.time,date=os.date,difftime=os.difftime,getenv=function(k)return k=='LOCALAPPDATA'and 'C:/fixture/local'or 'C:/fixture/roaming'end}
G.stingray={Application={worlds=function()return {}end,time_since_launch=function()return now end,string_to_id32=function(s)return s end},
 World={units=function()return {}end,update_unit=forbidden,link_unit=forbidden,unlink_unit=forbidden},
 Unit={alive=function()return false end,set_local_pose=forbidden,set_local_rotation=forbidden},
 IdString64={to_hex=function(v)return v end}}
''')
    sandbox=core.split('services.sandbox = (function()',1)[1].split('-- @@END sandbox.lua@@',1)[0]
    vm.globals().sandbox_module=vm.execute('return (function()'+sandbox)
    vm.execute("sb=sandbox_module.install({G=G,io=G.io,os=G.os,debug=debug,DIR='C:/fixture/roaming/Arrowhead/Helldivers2/',GAME_DIR='C:/fixture/roaming/Arrowhead/Helldivers2/',OLD_DIR='C:/fixture/local/',FILES='chef_loader',log=function(s)logs[#logs+1]=s end})")
    hooks=core.split('function starter.read_module(a, m)',1)[1].split('-- What a mod is doing',1)[0]
    vm.execute('starter={get=function(t,k)return t[k]end};function starter.read_module(a,m)'+hooks)
    vm.globals().new_source=(OUT/'hd2physbone-test09.lua').read_text('utf8');vm.globals().expected=RUNTIME_VERSION
    result=vm.execute(r'''
local owner='mods/hd2modmanager/physbone'
local env=sb.env(owner);for k,f in pairs(starter.game_hooks)do rawset(env,k,f)end
local chunk=assert(loadstring(new_source,'@'..owner));setfenv(chunk,env)
local api={loader='Chef Shared Loader',loader_version='1.4.1',api=1,name=owner,log_directory='C:/fixture/roaming/Arrowhead/Helldivers2'}
local mod=chunk(api);local a={};starter.read_module(a,mod)
assert(a.version==expected and type(a.hooks.render)=='function')
assert(type(a.hooks.shutdown)=='function' and type(mod.on_stop)=='function')
for i=1,60 do now=i/60;if a.hooks.update then a.hooks.update()end;a.hooks.render()end
assert(mutationCalls==0,'empty world mutation')
mod.on_stop();a.hooks.shutdown();mod.on_stop()
return {status='PASS',renderCalls=60,emptyWorldWrites=mutationCalls,version=a.version}
''')
    reader=core[core.index('local LUA_TYPE = {'):core.index('discover = function()',core.index('local LUA_TYPE = {'))]
    vm.execute("scan={bad=0,huge=0,big=0,seq=0,said={},mine={},cores={},langs={}};found_addons={};found_named={};found_options={};found_boots={};local byte,sub,min=string.byte,string.sub,math.min;local ALLOW='^mods/[%w_%-]+/[%w_%-/]*[%w_%-]$';local log=function(s)logs[#logs+1]=s end;local fmt=string.format\n"+reader+'\nparse_patch=read_patch')
    vm.globals().patch_bytes=(OUT/'patch/9ba626afa44a3aa3.patch_0').read_bytes()
    vm.execute("parse_patch(memory_file(patch_bytes),'data/9ba626afa44a3aa3.patch_5');assert(#found_addons==1 and found_addons[1].name=='mods/hd2modmanager/physbone');assert(found_addons[1].src==new_source and scan.bad==0 and scan.big==0,'embedded source mismatch')")
    report=dict(result.items());report.update(actualChefParser=True,actualChefSandbox=True,actualChefModuleSelection=True,
        sourceFromEmbeddedPatchExact=True,loaderSha256=sha(core_path),gameDeployed=False,gameTested=False)
    save(OUT/'chef-test09-axis.json',report)
    (OUT/'chef-test09-axis.log').write_text('\n'.join(str(x) for x in vm.globals().logs.values()),'utf8')
    return dict(name='actual-Chef1.4.1',status='PASS',report=str(OUT/'chef-test09-axis.json'))

def main():
    rows=[];errors=[]
    test_names=['p1-regression-test.lua','p2-solver-test.lua','spring-dof-test.lua','limit-source-test.lua','axis-limit-behaviour-test.lua',
        'axis-limit-frame-test.lua','bind-shape-test.lua','fast-write-test.lua','lifecycle-test.lua','motion-gate-test.lua',
        'attach-loop-test.lua','attach-cache-test.lua','rig-select-test.lua','driver-update-test.py','runtime-harness-test.lua','mp_harness.lua']
    for name in test_names:
        if name.endswith('.py'):continue
        try:rows.append(lua_test(name));print('PASS',name)
        except Exception as exc:errors.append(dict(name=name,error=str(exc)));print('FAIL',name,str(exc))
    # Existing source-level regression loads redirected into the separate TEST copy.
    for name in ['driver-update-test.py','spring-dof-model-test.py','test06-native-vrd-bind-test.py','driver-wrist-exclusion-test.py','single-front-skirt-test.py']:
        path=ROOT/'HD2PhysBoneCompat/test'/name;text=path.read_text('utf8')
        if name=='test06-native-vrd-bind-test.py':
            old="SOURCE_ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua'";replacement="Path("+repr(str(COMPAT))+")"
        else:old="ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua'";replacement="Path("+repr(str(COMPAT))+")"
        text=text.replace(old,replacement).replace('1.3.1',COMPAT_VERSION)
        try:rows.append(python_test(name,text,path,OUT/(name+'.json')));print('PASS',name)
        except Exception as exc:errors.append(dict(name=name,error=str(exc)));print('FAIL',name,str(exc))
    try:rows.append(chef_test());print('PASS actual Chef')
    except Exception as exc:errors.append(dict(name='Chef',error=str(exc)));print('FAIL Chef',str(exc))
    status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE' if not errors else 'FAILED'
    save(OUT/'test09-axis-suite.json',dict(status=status,tests=rows,errors=errors,candidateCompatSha256=sha(COMPAT),candidateRuntimeSha256=sha(RUNTIME),
        testsUseSeparateCandidate=True,expectedTestRevisionAdjustedInMemory=True,harnessIOIsolatedToWorkspace=True,productionSourcesNotOverwritten=True,gameTested=False))
    if errors:raise AssertionError('TEST suite not clean: '+str(errors))
    print('PASS full test09 suite',len(rows),'harnesses')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()

