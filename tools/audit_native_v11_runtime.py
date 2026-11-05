"""Verify Source wrist procedures, untouched head nodes and native sling offsets."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v11-20261104';P=W/'project'
os.environ['HD2_LUA_TEST_RUNTIME']=str(W/'test-runtime')
sys.path.insert(0,str(ROOT/'tools'))
from audit_native_attachment_layouts import units,shape,run
profile=json.loads((P/'attachment-profile.json').read_text())
base=ROOT/'outputs/native-manual-20261103/project/animations/runtime/9ba626afa44a3aa3.patch_2'
avatar=next(iter(units(base).values()))
models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
fixture=dict(avatar=shape(avatar),models={r:shape(models[r]) for r in profile['modelLayouts']})
source=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
harness=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8').split("check(armor.nodes~=A.nodes",1)[0]
checks=r'''
tick(3)
check(runtime.stats.active==1,'body not selected')
for _,row in ipairs(profile.jointProcedures)do
 local saved=copy(A.locals[row.controlIndex+1])
 local initial=copy(A.locals[row.index+1]);local changed=false
 for _,trigger in ipairs(row.triggers)do
  A.locals[row.controlIndex+1].q=copy(trigger.trigger);tick(1)
  local result=A.locals[row.index+1]
  check(adapter.close(result,{p=trigger.position,q=trigger.rotation}),'Source trigger pose mismatch')
  if not adapter.close(initial,result)then changed=true end
  local opposite={};for j=1,4 do opposite[j]=-trigger.trigger[j] end
  A.locals[row.controlIndex+1].q=opposite;tick(1)
  check(adapter.close(result,A.locals[row.index+1]),'quaternion sign changed helper pose')
 end
 check(changed,'weighted wrist helper stayed frozen')
 A.locals[row.controlIndex+1]=saved;tick(1)
end
-- A stowed primary must read its original animated socket, not the configured
-- clone that already contains the character-size translation adjustment.
local sling;for _,row in ipairs(profile.vpk)do if row.standardName=='sling'then sling=row end end
check(sling.sourceReferenceIndex==sling.referenceIndex,'sling still reads configured shape offset')
local old=world(A,sling.index+1)
local configuredIndex
for i,h in ipairs(A.hashes)do if h==hash_name('__hd2_attach_vpk__'..profile.boneNamespace..'_027')then configuredIndex=i end end
check(configuredIndex~=nil,'missing sling regression clone')
local saved=copy(A.locals[configuredIndex]);A.locals[configuredIndex].p[1]=saved.p[1]+.2
tick(1);check(adapter.close(old,world(A,sling.index+1)),'duplicate sling offset leaked back')
A.locals[configuredIndex]=saved
local original=copy(A.locals[sling.referenceIndex+1]);A.locals[sling.referenceIndex+1].p[2]=original.p[2]+.03
tick(1);check(not adapter.close(old,world(A,sling.index+1)),'native stow animation ignored')
A.locals[sling.referenceIndex+1]=original
-- Head-only equipment must perform zero writes, including the aim/camera nodes.
local helmet=make(false,B.x,profile.targets.head[1],B);tick(3)
check(B.writes==0,'head-only equipment mutated the avatar')
for _,row in ipairs(profile.vpk)do if row.ownerSlot=='head'then
 check(not A.written[row.index+1] and not B.written[row.index+1],'head child written')
end end
armor.visible=false;tick(1)
for _,row in ipairs(profile.jointProcedures)do check(adapter.close(A.locals[row.index+1],row.bind),'wrist helper not restored after unequip')end
check(runtime.stats.active==0,'head-only equipment left active writer')
return {status='PASS',checks=checks,wristHelpers=#profile.jointProcedures,headUntouched=true,slingDoubleOffsetRegression=true,unequipRestores=true,gameTested=false}
'''
result=run(profile,fixture,source,harness+checks)
(W/'wrist-head-sling-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
