"""Reuse real-layout B12 cases with strict ID provenance; prove old B12 fails."""
import os
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units, plain
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime

W=ROOT/'outputs/native-v21-b13-20261104'
P=ROOT/'outputs/native-manual-20261103/project'
STRICT=(ROOT/'HD2PhysBoneCompat/test/strict_id32_fixture.lua').read_text(encoding='utf-8')


def regression():
    code=(ROOT/'tools/audit_native_v20_b12.py').read_text(encoding='utf-8')
    code=code.replace('native-v20-b12-20261104','native-v21-b13-20261104').replace('B12','B13')
    marker="    fixture=dict(hashes=avatar.name_hashes"
    assert marker in code
    code=code.replace(marker,"    harness=harness.replace('local base=copy(avatar.locals)',STRICT+'\\nlocal base=copy(avatar.locals)')\n"+marker)
    marker="vm.globals().probe=vm.execute(module)"
    assert marker in code
    code=code.replace(marker,marker+";vm.globals().hash_name=bone_name_hash")
    marker="    tree=ast.parse("
    assert marker in code
    code=code.replace(marker,"    base=base.replace('local runtime=adapter.new',STRICT+'\\nlocal runtime=adapter.new')\n"+marker)
    # Require zero invalid name-ID calls from the full adapter, not just the probe.
    code=code.replace("return {checks=checks,history=history,logs=logs,otherAvatarWrites=B.writes}",
        "check(strictIdStats.invalidArgumentCalls==0,'invalid full-adapter name ID');return {checks=checks,history=history,logs=logs,otherAvatarWrites=B.writes,idLookupCalls=strictIdStats.lookupCalls,invalidIdCalls=strictIdStats.invalidArgumentCalls}")
    # This adds an assertion to each actual-affine standalone A/B/ALL run.
    code=code.replace("result=plain(vm.execute(harness))", "result=plain(vm.execute(harness.replace('return {checks=checks',\"check(strictIdStats.invalidArgumentCalls==0,'invalid standalone ID');return {idLookupCalls=strictIdStats.lookupCalls,invalidIdCalls=strictIdStats.invalidArgumentCalls,checks=checks\")))")
    exec(compile(code,str(Path(__file__)),'exec'),dict(__file__=__file__,__name__='__main__',STRICT=STRICT))


def contract():
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    fixture=dict(hashes=avatar.name_hashes,parents=[0 if p is None else p+1 for p in avatar.parents])
    current=(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    old=(P/'diagnostics/B12/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    setup=r'''
local writes,reads=0,0;local logs={}
local avatar={names={},parents=fixture.parents};for i,h in ipairs(fixture.hashes)do avatar.names[h]=i end
local S={Unit={},Application={},Matrix4x4={},World={}}
S.Unit.alive=function()return true end
S.Unit.num_scene_graph_items=function()return #fixture.hashes end
S.Unit.has_node=function(u,h)return u.names[h]~=nil end
S.Unit.node=function(u,h)return u.names[h]end
S.Unit.scene_graph_parent=function(u,n)return u.parents[n]end
S.Unit.set_local_pose=function()writes=writes+1;error('validation must not write')end
S.Unit.local_pose=function()reads=reads+1;error('validation must not read poses')end
S.Unit.world_pose=S.Unit.local_pose
'''+STRICT+r'''
local actor={unit=avatar,label=1,world=1}
local function logger(fmt,...)logs[#logs+1]=string.format(fmt,...)end
'''
    def run(module,profile,program):
        vm=LuaRuntime(unpack_returned_tuples=True)
        vm.globals().probe=vm.execute(module);vm.globals().profile=vm.table_from(profile,recursive=True)
        vm.globals().fixture=vm.table_from(fixture,recursive=True);vm.globals().hash_name=bone_name_hash
        return plain(vm.execute(setup+program))
    failures={}
    for variant in ('A','B','ALL'):
        profile=load(P/f'diagnostics/B12/variants/{variant}/profile.json')
        result=run(old,profile,r'''
local p=probe.new(S,profile,logger);assert(not p:apply(actor,true,0,1,{}));assert(p.disabled)
assert(strictIdStats.invalidArgumentCalls==1 and writes==0 and reads==0)
local found=false;for _,line in ipairs(logs)do if line:find('engine_name_id_required',1,true)then found=true end end;assert(found)
return {oldCodeRejected=true,invalidIdCalls=strictIdStats.invalidArgumentCalls,writes=writes,logs=logs}
''')
        failures[variant]=result
    profile=load(W/'B13-0.json')
    validation=run(current,profile,r'''
local p=probe.new(S,profile,logger)
for i=0,20 do assert(not p:apply(actor,true,i,i+1,{}));p:restore_all();p:after_refresh()end
assert(not p.disabled and writes==0 and reads==0 and strictIdStats.invalidArgumentCalls==0)
local first=#logs;assert(not p:apply(actor,true,24,25,{}));assert(#logs==first,'validation log spam')
p:apply(actor,false,25,26,{});p:apply(actor,true,26,27,{});assert(#logs>first,'reacquire did not log validation')
return {probeWrites=writes,poseReads=reads,invalidIdCalls=strictIdStats.invalidArgumentCalls,idLookupCalls=strictIdStats.lookupCalls,logs=logs}
''')
    invalid={}
    for kind in ('placeholder','factory','index','parent','duplicate','unregistered'):
        result=run(current,profile,r'''
local kind=CASE
if kind=='placeholder'then profile.attachmentProbe.nodes[1].name='hash_75275fac'
elseif kind=='factory'then S.Application.string_to_id32=nil
elseif kind=='index'then profile.attachmentProbe.nodes[1].index=-1
elseif kind=='parent'then profile.attachmentProbe.nodes[1].parentIndex=profile.expectedAvatarNodes
elseif kind=='duplicate'then profile.attachmentProbe.nodes[2]=profile.attachmentProbe.nodes[1]
else local ok=pcall(S.Unit.has_node,avatar,{});assert(not ok);return {forgedTokenRejected=true}end
local p=probe.new(S,profile,logger);assert(p.disabled);assert(not p:apply(actor,true,4,1,{}))
assert(writes==0 and reads==0 and strictIdStats.lookupCalls==0)
return {disabled=true,probeWrites=writes,lookups=strictIdStats.lookupCalls}
'''.replace('CASE',repr(kind)))
        invalid[kind]=result
    result=dict(status='PASS',oldB12=failures,validationOnly=validation,invalidConfigurations=invalid,
                factoryContract='Only tokens returned by string_to_id32; ordinary numbers and forged tokens rejected.',
                gameTested=False,sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'))
    save_json(W/'id32-contract-audit.json',result)
    print('PASS: old B12 A/B/ALL rejected by strict IDs; B13-0 zero probe writes/pose reads; malformed config rejected before queries.')


if __name__=='__main__':
    regression()
    contract()
