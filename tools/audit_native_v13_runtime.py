"""Test v12 protection and real SMG-203/foregrip layouts in a Lua 5.1 VM."""
import copy,json,os,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v13-20261104';P=ROOT/'outputs/native-v12-20261104/project'
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
sys.path.insert(0,str(ROOT/'tools'))
from audit_native_attachment_layouts import units,shape,run
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.formats import UnitData
from anim_batch_mod.constants import UNIT_TYPE_ID
profile=json.loads((P/'attachment-profile.json').read_text(encoding='utf-8'))
avatar=next(iter(units(ROOT/'outputs/native-v11-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2').values()))
models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
fixture=dict(avatar=shape(avatar),models={r:shape(models[r]) for r in profile['modelLayouts']},consumers={})
idx=ResourceIndex(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')))
idx.connection=sqlite3.connect('file:'+str(ROOT/'outputs/native-v9-20261104/project/animations/resource-index.sqlite3')+'?mode=ro',uri=True)
for h in ('186ea95de7306b1a','411c4fd07740a7dd','3ae1f60c5efd2b43','f9df21c8e52cac95','9549ff64ba3fd5a1'):
    _,entry=idx.resolve(int(h,16),UNIT_TYPE_ID)
    fixture['consumers'][h]=shape(UnitData.parse(entry.toc_data))
idx.close()
source=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
harness=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
# Existing ownership, scale, hidden-item and lifecycle tests still apply to
# the deliberately retained B1 mapping, independent of the new guard.
legacy=copy.deepcopy(profile);legacy['protectControllerParents']=False
regression=run(legacy,fixture,source,harness.replace('if fixture.consumers then','if false then'))
prefix=harness.split("check(armor.nodes~=A.nodes",1)[0]
checks=r'''
local function row(name)for _,r in ipairs(profile.vpk)do if r.standardName==name then return r end end end
local weapon=row('attach_weapon');local right=row('attach_hand_r');local sling=row('sling')
local aims={row('aim_weapon'),row('weapon_aim')}
local before={};for _,r in ipairs(aims)do before[r.index]=world(A,r.index+1)end
tick(3)
check(runtime.stats.active==1,'body selection failed')
for _,r in ipairs({weapon,right})do
 check(not A.written[r.index+1],'controller ancestor was written')
 check(runtime.protectedParents[r.index],'controller protection plan missing')
end
for _,r in ipairs(aims)do check(adapter.close(before[r.index],world(A,r.index+1)),'aim world changed at activation')end
-- Change actual native controller input and Source hand independently.
local sourceHand=weapon.sourceAnchorIndex+weapon.sourceIndexOffset+1
for i=1,100 do
 A.locals[sourceHand].q={math.sin(i*.005),0,0,math.cos(i*.005)}
 A.locals[right.parentIndex+1].q={0,0,math.sin(i*.003),math.cos(i*.003)}
 for _,r in ipairs(aims)do
  A.locals[r.index+1].p[1]=i*.001
  before[r.index]=world(A,r.index+1)
 end
 tick(1)
 for _,r in ipairs(aims)do
  check(adapter.close(before[r.index],world(A,r.index+1)),'aim parent protection drift')
  check(not A.written[r.index+1],'controller local was overwritten')
 end
end
-- Both Source QuatInterp helpers must retain the v11 trigger behavior.
for _,r in ipairs(profile.jointProcedures)do
 local saved=copy(A.locals[r.controlIndex+1])
 for _,t in ipairs(r.triggers)do
  A.locals[r.controlIndex+1].q=copy(t.trigger);tick(1)
  check(adapter.close(A.locals[r.index+1],{p=t.position,q=t.rotation}),'wrist trigger regression')
 end
 A.locals[r.controlIndex+1]=saved
end
local helmet=make(false,B.x,profile.targets.head[1],B);tick(3)
for _,r in ipairs(profile.vpk)do if r.ownerSlot=='head'then
 check(B.written[r.index+1],'head child was not restored to mapped behavior')
end end
-- Serialized single-marker grips, including flashlight/laser variants.
local function consumer(id,owner,node)
 local f=fixture.consumers[id];local u={alive=true,avatar=false,x=0,resource=id,nodes=#f.hashes,
  locals=copy(f.localPoses),parents=f.parents,hashes=f.hashes,names={},writes=0,written={},missing={},
  linkOwner=owner,linkNode=node,linkPose=world(owner,node),refreshes=0}
 for i,h in ipairs(f.hashes)do u.names[h]=i end
 units[#units+1]=u;return u
end
local gun=consumer('186ea95de7306b1a',A,sling.index+1)
local grips={}
for _,id in ipairs({'411c4fd07740a7dd','3ae1f60c5efd2b43','f9df21c8e52cac95','9549ff64ba3fd5a1'})do
 grips[#grips+1]=consumer(id,gun,assert(gun.names[hash_name('attach_underbarrel')]))
end
for i,u in ipairs(units)do if u==gun then table.remove(units,i);break end end;units[#units+1]=gun
S.World.update_unit=function(_,u)
 check(u.alive,'refresh of dead unit')
 if u.linkOwner and u.linkNode then u.linkPose=world(u.linkOwner,u.linkNode);u.refreshes=u.refreshes+1 end
end
tick(3)
check(#runtime.consumers==5,'SMG-203 or foregrip was not discovered')
for _,c in ipairs(runtime.consumers)do
 check(c.unit==gun or c.kind=='weapon_grip','single-hand grip classified incorrectly')
end
local spine=sling.sourceAnchorIndex+sling.sourceIndexOffset+1
for i=1,5 do
 A.locals[spine].p[1]=A.locals[spine].p[1]+.02;tick(1)
 for _,g in ipairs(grips)do
  check(g.refreshes>0 and adapter.close(g.linkPose,world(gun,g.linkNode)),'grip kept pre-gun transform')
  check(g.writes==0,'grip local pose/relink was guessed')
 end
end
local g=grips[1];local detached=copy(g.linkPose);g.linkNode=nil;g.linkOwner=nil;tick(1)
check(adapter.close(detached,g.linkPose),'detached grip relinked')
g=grips[2];local refreshes=g.refreshes;g.alive=false;tick(1);check(g.refreshes==refreshes,'dead grip refreshed')
armor.visible=false;tick(1)
for _,r in ipairs(profile.jointProcedures)do check(adapter.close(A.locals[r.index+1],r.bind),'wrist unequip restore failed')end
for _,r in ipairs({weapon,right})do check(not A.written[r.index+1],'native parent overwritten during restore')end
return {status='PASS',checks=checks,aimWorldFrames=100,realForegrips=4,smg203Nodes=gun.nodes,headChildren=5,wristHelpers=2,gameTested=false}
'''
result=run(profile,fixture,source,prefix+checks)
# Prove the v11 implementation fails the newly added contract, not just that
# the v12 test fixture accepts itself.
try:run(profile,fixture,(ROOT/'outputs/native-v12-20261104/source-before/native_attachments.lua').read_text(encoding='utf-8'),prefix+checks)
except Exception as e:
    assert 'protectedParents' in str(e) or 'controller ancestor' in str(e),str(e)
    result['v11ProtectionRegressionReproduced']=True
else:raise AssertionError('v11 unexpectedly satisfied the new protection contract')
variants={}
for label,change in [('B1',{'protectControllerParents':False}),('B2',{}),('B3',{'diagnosticMode':'observe'})]:
    p=copy.deepcopy(profile);p.update(change)
    if label=='B2':next(r for r in p['vpk'] if r['standardName']=='sling')['policy']='original-world'
    extra="tick(3);return {writes=A.writes,active=runtime.stats.active,gun=A.written[33]==true,sling=A.written[28]==true}"
    values=run(p,fixture,source,prefix+extra);variants[label]=values
assert variants['B1']['gun'] and variants['B1']['sling']
assert not variants['B2']['gun'] and not variants['B2']['sling'] and variants['B2']['active']==1
assert variants['B3']['writes']==0 and variants['B3']['active']==0
result.update(legacyMappingRegression=regression,variants=variants)
current=json.loads((W/'project/attachment-profile.json').read_text(encoding='utf-8'))
assert not current['armSync']
current_check=run(current,fixture,source,prefix+"tick(3);return {active=runtime.stats.active,gun=A.written[33]==true,sling=A.written[28]==true}")
assert current_check=={'active':1,'gun':False,'sling':False},current_check
result.update(v13Baseline=current_check,armSyncExperimental=True)
(W/'attachment-runtime-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
