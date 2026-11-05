"""B14 real-layout regressions and explicit frame-lifetime rejection of B13."""
import os
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units,plain
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime
W=ROOT/'outputs/native-v22-b14-20261104'
P=ROOT/'outputs/native-manual-20261103/project'
STRICT=(ROOT/'HD2PhysBoneCompat/test/strict_id32_fixture.lua').read_text(encoding='utf-8')


def regressions():
    source=Path(__file__).with_name('audit_native_v21_b13.py').read_text(encoding='utf-8')
    source=source.replace('native-v21-b13-20261104','native-v22-b14-20261104').replace('B13','B14')
    old=next(line for line in source.splitlines() if 'harness=harness.replace' in line)
    # Every apply starts another simulated frame; restore/release must also use
    # fresh IDs instead of the ones created during module initialization.
    wrapped="local originalMake=make\nmake=function(p)local instance=originalMake(p);if instance then local apply=instance.apply;instance.apply=function(self,...)strictIdStats.advanceFrame();return apply(self,...)end end;return instance end\nlocal base=copy(avatar.locals)"
    injected="    harness=harness.replace('local function make(p)',STRICT+'\\nlocal function make(p)').replace('local base=copy(avatar.locals)',"+repr(wrapped)+")\n"
    replacement="    code=code.replace(marker,"+repr(injected)+"+marker)"
    assert old in source
    source=source.replace(old,replacement)
    # The full adapter's program is a literal inside the reused B12 audit.
    marker="    # Require zero invalid name-ID calls from the full adapter"
    assert marker in source
    source=source.replace(marker,"    code=code.replace('runtime:tick(frame)','strictIdStats.advanceFrame();runtime:tick(frame)').replace('runtime:release()','strictIdStats.advanceFrame();runtime:release()')\n"+marker)
    source=source.replace("strictIdStats.invalidArgumentCalls==0,'invalid", "strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'invalid")
    # Preserve the previous strict parameter regressions and validation-only checks.
    exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))


def lifetime():
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    fixture=dict(hashes=avatar.name_hashes,parents=[0 if p is None else p+1 for p in avatar.parents])
    old=(P/'diagnostics/B13/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    current=(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    setup=r'''
local writes,reads=0,0;local logs={}
local avatar={names={},parents=fixture.parents};for i,h in ipairs(fixture.hashes)do avatar.names[h]=i end
local S={Unit={},Application={},Matrix4x4={},World={}}
S.Unit.alive=function()return true end
S.Unit.num_scene_graph_items=function()return #fixture.hashes end
S.Unit.has_node=function(u,h)return u.names[h]~=nil end
S.Unit.node=function(u,h)return u.names[h]end
S.Unit.scene_graph_parent=function(u,n)return u.parents[n]end
S.Unit.set_local_pose=function()writes=writes+1;error('validation-only write')end
S.Unit.local_pose=function()reads=reads+1;error('validation-only pose read')end
S.Unit.world_pose=S.Unit.local_pose
'''+STRICT+r'''
local actor={unit=avatar,label=1,world=1}
local function logger(fmt,...)logs[#logs+1]=string.format(fmt,...)end
local p=probe.new(S,profile,logger)
'''
    def run(module,program):
        vm=LuaRuntime(unpack_returned_tuples=True);vm.globals().probe=vm.execute(module)
        vm.globals().profile=vm.table_from(load(W/'B14-0.json'),recursive=True)
        vm.globals().fixture=vm.table_from(fixture,recursive=True);vm.globals().hash_name=bone_name_hash
        return plain(vm.execute(setup+program))
    failed=run(old,r'''
assert(strictIdStats.factoryCalls==23)
strictIdStats.advanceFrame();assert(not p:apply(actor,true,10,1210,{}))
assert(p.disabled and strictIdStats.expiredArgumentCalls==1 and writes==0 and reads==0)
return {oldB13Rejected=true,expiredIdCalls=strictIdStats.expiredArgumentCalls,writes=writes,logs=logs}
''')
    passed=run(current,r'''
assert(strictIdStats.factoryCalls==0,'constructor retained transient IDs')
for frame=1,40 do
 strictIdStats.advanceFrame();assert(not p:apply(actor,true,frame,frame,{}));p:restore_all();p:after_refresh()
end
assert(not p.disabled and writes==0 and reads==0 and strictIdStats.expiredArgumentCalls==0)
assert(strictIdStats.factoryCalls==40*23 and strictIdStats.lookupCalls==40*23*2)
p:apply(actor,false,41,41,{});strictIdStats.advanceFrame();p:apply(actor,true,42,42,{})
assert(not p.disabled)
return {freshIdPerQuery=true,frames=41,nodes=23,expiredIdCalls=strictIdStats.expiredArgumentCalls,writes=writes,logs=logs}
''')
    cases={}
    for kind in ('missing_name','index','parent'):
        cases[kind]=run(current,r'''
strictIdStats.advanceFrame()
local first=profile.attachmentProbe.nodes[1]
if CASE=='missing_name'then avatar.names[hash_name(first.name)]=nil
elseif CASE=='index'then avatar.names[hash_name(first.name)]=first.index+2
else avatar.parents[first.index+1]=first.parentIndex+2 end
assert(not p:apply(actor,true,1,1,{}));assert(p.disabled and writes==0)
local mismatch=false;for _,line in ipairs(logs)do
 if line:find('event=validation_mismatch',1,true)and line:find('reason='..CASE,1,true)then mismatch=true end
end
assert(mismatch,'missing detailed failure telemetry');return {rejected=true,writes=writes,logs=logs}
'''.replace('CASE',repr(kind)))
    save_json(W/'id32-lifetime-audit.json',dict(status='PASS',oldB13=failed,B14=passed,mismatchCases=cases,
        documentation='IdString32 is temporary for the generation frame; runtime now retains names only.',
        sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'),gameTested=False))
    print('PASS: B13 stale IDs rejected; B14 41 frames x 23 nodes validated with fresh IDs; detailed mismatch reasons covered.')


if __name__=='__main__':
    regressions()
    lifetime()
