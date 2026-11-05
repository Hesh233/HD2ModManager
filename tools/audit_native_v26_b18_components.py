"""Test exact-layout discovery and linked-cache propagation with actual assets."""
import copy
import os
from package_native_v12 import ROOT, load, save_json, digest
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units, shape, plain
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime

W = ROOT / 'outputs/native-v26-b18-20261105'
P = ROOT / 'outputs/native-manual-20261103/project'

PROGRAM = r'''
local gun1=make(false,0,'39ab99895147a3bf')
local part1=make(false,0,'9c22a90da9c79de3')
local gun2=make(false,0,'e8d5f49ad7780e54')
local part2=make(false,0,'52ff81fcba0c059d')
local decoy=make(false,0,'ffffffffffffffff')
local simple={part1,part2}
local guns={gun1,gun2}
for i,part in ipairs(simple)do
 part.linkParent=guns[i];part.linkNode=guns[i].names[hash_name('attach_mag')]
 part.linkPose=copy(world(guns[i],part.linkNode))
end
local updateOrder={}
S.World.update_unit=function(_,u)
 check(u.alive,'refresh dead unit');u.refreshes=(u.refreshes or 0)+1
 updateOrder[#updateOrder+1]=u.resource
 if u==gun1 or u==gun2 then
  u.linkPose={q={0,0,0,1},p={0,0,u.shift or 0}}
 elseif u.linkParent then u.linkPose=copy(world(u.linkParent,u.linkNode))end
end
local function scan()
 strictIdStats.advanceFrame();frame=frame+1;runtime:scan(frame)
end
local function included(u)
 for _,r in ipairs(runtime.consumers)do if r.unit==u then return r end end
end
scan()
check(included(gun1)and included(gun2),'existing guns not discovered')
check(not included(decoy),'unlisted resource admitted')
local discovered={}
for _,part in ipairs(simple)do
 discovered[part.resource]=included(part)~=nil
 check(discovered[part.resource]==expectedEnabled,'wrong simple-component discovery '..part.resource..' expected='..tostring(expectedEnabled)..' actual='..tostring(discovered[part.resource]))
 if expectedEnabled then
  local row=included(part)
  check(row.kind=='weapon_magazine'and row.markers[1]==part.names[hash_name('game_mesh')],'incorrect mesh marker')
 end
end
local before={};for i,part in ipairs(simple)do before[i]=copy(world(part,part.names[hash_name('game_mesh')]))end
gun1.shift=.6;gun2.shift=.6
runtime.dirtyWorlds[1]=true;runtime:refresh_consumers()
local deltas={}
for i,part in ipairs(simple)do
 local after=world(part,part.names[hash_name('game_mesh')]);local delta=after.p[3]-before[i].p[3]
 deltas[part.resource]=delta
 check(math.abs(delta-(expectedEnabled and .6 or 0))<1e-6,'linked cache did not follow independently refreshed gun')
end
if expectedEnabled then
 local positions={};for i,id in ipairs(updateOrder)do positions[id]=i end
 check(positions[gun1.resource]<positions[part1.resource]and positions[gun2.resource]<positions[part2.resource],'component refreshed before gun')
 for _,part in ipairs(simple)do
  local originalCount=part.nodes;part.nodes=originalCount+1;scan();check(not included(part),'wrong count admitted');part.nodes=originalCount
  local key=hash_name('game_mesh');local oldIndex=part.names[key]
  part.names[key]=oldIndex+1;scan();check(not included(part),'wrong index admitted');part.names[key]=oldIndex
  key=hash_name('collision');part.missing[key]=true;scan();check(not included(part),'missing signature admitted');part.missing[key]=nil
  scan();check(included(part),'valid component did not reacquire')
  local n=part.refreshes;part.visible=false;runtime:refresh_consumers();check(part.refreshes==n,'hidden component refreshed');part.visible=true
  local id=part.resource;part.resource='eeeeeeeeeeeeeeee';runtime:refresh_consumers();check(part.refreshes==n,'changed resource refreshed');part.resource=id
  part.nodes=originalCount+1;runtime:refresh_consumers();check(part.refreshes==n,'rebuilt component refreshed');part.nodes=originalCount
  part.alive=false;runtime:refresh_consumers();check(part.refreshes==n,'dead component refreshed');part.alive=true
 end
 scan();runtime.dirtyWorlds={};local a,b=part1.refreshes,part2.refreshes
 runtime:refresh_consumers();check(part1.refreshes==a and part2.refreshes==b,'clean world refreshed')
end
for _,u in ipairs(units)do check(u.writes==0,'discovery/refresh wrote local poses')end
check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'invalid or expired ID32')
return {checks=checks,discovered=discovered,deltas=deltas,localPoseWrites=0,
        invalidIdCalls=strictIdStats.invalidArgumentCalls,expiredIdCalls=strictIdStats.expiredArgumentCalls}
'''


def main():
    avatar = next(iter(units(P / 'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    models = units(P / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    profile = load(W / 'B18-PARTS.json')
    fixture = dict(avatar=shape(avatar), models={r: shape(models[r]) for r in profile['modelLayouts']})
    for path in (W / 'assets').glob('*.toc'):
        fixture['models'][path.stem] = shape(UnitData.parse(path.read_bytes()))
    fixture['models']['ffffffffffffffff'] = copy.deepcopy(fixture['models']['9c22a90da9c79de3'])
    base = (ROOT / 'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8').split('check(armor.nodes~=A.nodes', 1)[0]
    strict = (ROOT / 'HD2PhysBoneCompat/test/strict_id32_fixture.lua').read_text(encoding='utf-8')
    base = base.replace('local runtime=adapter.new', strict + '\nlocal runtime=adapter.new')
    old = (P / 'diagnostics/B17/src/native_attachments.lua').read_text(encoding='utf-8')
    new = (ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
    cases = {}
    for label, source, enabled in (('old-runtime', old, False), ('new-disabled', new, False), ('new-enabled', new, True)):
        selected = copy.deepcopy(profile)
        if not enabled:
            selected.pop('simpleWeaponComponents')
        vm = LuaRuntime(unpack_returned_tuples=True)
        vm.globals().adapter = vm.execute(source)
        vm.globals().profile = vm.table_from(selected, recursive=True)
        vm.globals().fixture = vm.table_from(fixture, recursive=True)
        vm.globals().hash_name = bone_name_hash
        vm.globals().expectedEnabled = enabled
        cases[label] = plain(vm.execute(base + PROGRAM))
    assert cases['old-runtime'] == cases['new-disabled'], 'Opt-out path changed existing discovery/refresh behavior'
    save_json(W / 'component-refresh-audit.json', dict(status='PASS', cases=cases,
        sourceSha256=digest(ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua'),
        actualSerializedLayouts=True, existingLinkedCacheSimulated=True, rootBeforeComponentVerified=True,
        zeroLocalPoseWrites=True, negativeResourceCountSignatureAndLifecycleCases=True, optOutMatchesB17=True,
        gameTested=False, scope='Real serialized node orders with simulated existing parent links. '
                              'No live component ownership, parent link or visual identity is established.'))
    print('PASS: real component layouts, opt-out equivalence, opt-in linked-cache propagation, identity guards, lifecycle and fresh IDs.')


if __name__ == '__main__':
    main()
