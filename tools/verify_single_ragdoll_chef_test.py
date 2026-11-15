"""Actual Chef parser/sandbox for additive SINGLE observer; empty worlds and stub IO."""
from pathlib import Path
import inspect,json,sys,zipfile
import build_detailed_grip_test as b
import audit_native_v31_b23_chef as chef
import build_single_ragdoll_probe_test as builder
OUT,VERSION,ROOT=builder.OUT,builder.VERSION,builder.ROOT

def main():
 global OUT,VERSION
 OUT,VERSION=builder.OUT,builder.VERSION
 row=b.load(OUT/'build-report.json')
 with zipfile.ZipFile(row['package'])as z:(OUT/'chef-observer.patch').write_bytes(z.read('9ba626afa44a3aa3.patch_0'))
 mapping={
  'hd2attachmentfix-B23.lua':OUT/'observer-entry.lua',
  'runtime/9ba626afa44a3aa3.patch_4':OUT/'chef-observer.patch',
  'native-parenting/9ba626afa44a3aa3.patch_5':ROOT/'outputs/grip-equipment-perf-test-20261108-v9/test01/9ba626afa44a3aa3.patch_1',
  'physics-companion/9ba626afa44a3aa3.patch_3':ROOT/'outputs/native-v34-b23-integrated-20261105/physics-companion/9ba626afa44a3aa3.patch_3',
  'chef-audit.json':OUT/'chef-observer-validation.json','chef-fixture.log':OUT/'chef-observer-validation.log'}
 class Alias:
  def __init__(self,k=''):self.k=k
  def __truediv__(self,k):key=(self.k+'/'+str(k)).lstrip('/');return mapping.get(key,Alias(key))
 fn=inspect.getsource(chef.main)
 start=fn.index("    result=vm.execute(r'''");end=fn.index("    reader = core",start)
 test="""    result=vm.execute(r'''
local owner='mods/hd2modmanager/single_ragdoll_probe_test01'
local api={loader='Chef Shared Loader',loader_version='1.4.1',api=1,name=owner,log_directory='C:/fixture/roaming/Arrowhead/Helldivers2'}
local function start(loader)
 local env=sb.env(owner)
 for k,f in pairs(starter.game_hooks)do rawset(env,k,f)end
 local chunk=assert(loadstring(new_source,'@'..owner));setfenv(chunk,env)
 local mod=chunk(loader);local a={};starter.read_module(a,mod);return env,mod,a
end
local env,mod,a=start(api)
assert(a.version==expected_version and type(a.hooks.update)=='function' and type(a.hooks.render)=='function')
local path=opens[1].path;assert(path:find('hd2_single_TEST_DETAILED_test01_RAGDOLL_S1_',1,true),'single test path missing')
assert(#opens==1 and opens[1].mode=='w' and sb.check(path,'a',owner),'single log sandbox denied')
for i=1,60 do now=i/60;a.hooks.update();a.hooks.render()end
mod.on_stop();local entries=#logs;a.hooks.shutdown();mod.on_stop();a.hooks.update();a.hooks.render()
assert(#logs==entries and closeCalls==1 and mutationCalls==0,'observer stop/write regression')
assert(not pcall(start,nil) and #opens==1,'non-Chef observer accepted')
assert(G.__hd2physbone_runtime.sentinel,'observer changed independent physics')
return {status='PASS',addonVersion=a.version,poseWrites=mutationCalls,updateCalls=60,renderCalls=60,logPath=path,shutdownIdempotent=true,gameDeployed=false,gameTested=false}
''')
"""
 fn=fn[:start]+test+fn[end:];fn=fn.replace('mods/hd2modmanager/attachment_fix','mods/hd2modmanager/single_ragdoll_probe_test01')
 if builder.REVISION!='s1':fn=fn.replace('_RAGDOLL_S1_',f'_RAGDOLL_{builder.REVISION.upper()}_')
 env=dict(chef.__dict__);env['W']=Alias();exec(compile(fn,'<single-observer-chef>','exec'),env);env['main'](VERSION)
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',choices=('s1','s2','s3'),default='s1');builder.configure_revision(parser.parse_args().revision)
 sys.stdout.reconfigure(encoding='utf-8');main()
