-- V12 reflects live logs: internal skeleton/game_mesh parents stay positive; Unit root is linked.
do (function()
local result12={};local savedCalculate=calculate
calculate=function(u,linkedRoot,linkedPose)
 if u.linkLocalOffset and linkedRoot then linkedPose=numpy_multiply(linkedPose,u.locals[linkedRoot])end
 return savedCalculate(u,linkedRoot,linkedPose)
end
local function item_scene(rid,mountName)
 repaired_start('cf8934ff6567a42d')
 if mountName=='attach_hand_r' then aim_native();native_contact(.30)end
 gun.visible=false
 local item=make(weapon_assets[rid]);item.linkOwner=A;item.linkIndex=A.names[hash_name(mountName)];item.linkRoot=1
 local c,s=math.cos(.31),math.sin(.31);item.locals[1]={c,s,0,-s,c,0,0,0,1,.08,-.06,.035};item.linkLocalOffset=true
 linkedItems={item};groups[1]={A,model,gun,item};pad_main();refresh_all()
 return item
end
for _,rid in ipairs({'005c2262f672caf4','07d605bd50c98461','503c0e01fbafa86a'})do
 local item=item_scene(rid,'attach_hand_l')
 local nl=integratedProfile.nativeLeft.index+1;local sourceRoot=A.cache[integratedProfile.leftGrip.nodes[1].index+1]
 local target=copy(A.cache[nl]);target[10]=sourceRoot[10];target[11]=sourceRoot[11];target[12]=sourceRoot[12]+.10
 A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],target);refresh_all()
 local input=copy(item.locals);local native=copy(A.cache[nl]);local mount=copy(A.cache[item.linkIndex])
 local sk=item.names[hash_name('skeleton')];check(U.scene_graph_parent(item,sk)~=nil,'TEST V12 fixture wrongly made internal skeleton external')
 step(runtime,'render',10800,1080)
 check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST V12 actual Unit-root left link not followed '..rid)
 local actual=contact_point(A.cache[integratedProfile.sourceLeft.index+1],integratedProfile.testRepairs.contacts.left.source)
 local wanted=contact_point(native,integratedProfile.testRepairs.contacts.left.native)
 for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST V12 left contact missed '..rid)end
 check(near(A.cache[item.linkIndex],mount,4e-5),'TEST V12 native magazine mount moved')
 all_same(item.locals,input,'TEST V12 magazine current local erased')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+4;refresh_all();local n=runtime.stats.leftWrites
 step(runtime,'render',10801,1080.1);check(runtime.stats.leftWrites==n,'TEST V12 released Unit-root magazine followed');runtime:stop()
end
result12.liveInternalParentsAndUnitRoot=true
-- An internally-parented aligned child is not external-link proof, even though it is near the palm.
do
 local item=item_scene('005c2262f672caf4','attach_hand_l');item.linkOwner=nil;item.linkLocalOffset=false;refresh_all()
 local inner=3;item.locals[inner]={1,0,0,0,1,0,0,0,1,0,0,0};item.cache[inner]=copy(A.cache[A.names[hash_name('attach_hand_l')]])
 step(runtime,'render',10810,1081)
 check(not runtime.disabled and runtime.stats.leftWrites==0,'TEST V12 internal child lookalike claimed');runtime:stop()
end
result12.internalChildLookalikeRejected=true
-- Exact melee assets lack IK_right; use existing native-held right-palm proxy, never relink the weapon.
for _,rid in ipairs({'792d5d2a340fd6e6','e3b6aedd07fcb464','5f3ec9bda2bd8553','b0f1b354ba1d38d8'})do
 local item=item_scene(rid,'attach_hand_r');local input=copy(item.locals);local native=copy(A.cache[integratedProfile.nativeRight.index+1]);local mount=copy(A.cache[item.linkIndex])
 check(not item.names[hash_name('IK_right')],'TEST V12 melee fixture unexpectedly has IK_right')
 step(runtime,'render',10820,1082)
 check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST V12 native melee right follower missing '..rid)
 local actual=contact_point(A.cache[integratedProfile.sourceRight.index+1],integratedProfile.testRepairs.contacts.right.source)
 local wanted=contact_point(native,integratedProfile.testRepairs.contacts.right.native)
 for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST V12 melee right contact missed '..rid)end
 check(near(A.cache[item.linkIndex],mount,4e-5),'TEST V12 native melee hand mount moved');all_same(item.locals,input,'TEST V12 melee local/link changed')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+4;refresh_all();local n=runtime.stats.rightWrites
 step(runtime,'render',10821,1082.1);check(runtime.stats.rightWrites==n,'TEST V12 dropped melee followed');runtime:stop()
end
result12.fourMeleeNativeHeldReleased=true
-- When a real two-hand melee marker is in native left-palm contact, follow that native palm too.
do
 local item=item_scene('5f3ec9bda2bd8553','attach_hand_r');local nl=integratedProfile.nativeLeft.index+1
 local sourceRoot=A.cache[integratedProfile.leftGrip.nodes[1].index+1];local goal=copy(A.cache[nl]);goal[10]=sourceRoot[10];goal[11]=sourceRoot[11];goal[12]=sourceRoot[12]+.10
 A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],goal);refresh_all()
 local marker=item.names[hash_name('IK_left')];item.locals[marker]=numpy_relative(item.cache[item.parents[marker]+1],A.cache[nl]);refresh_all()
 local input=copy(item.locals);local native=copy(A.cache[nl]);step(runtime,'render',10825,1082.5)
 check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST V12 two-hand melee left follower missing')
 local actual=contact_point(A.cache[integratedProfile.sourceLeft.index+1],integratedProfile.testRepairs.contacts.left.source);local wanted=contact_point(native,integratedProfile.testRepairs.contacts.left.native)
 for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST V12 two-hand melee left contact missed')end
 all_same(item.locals,input,'TEST V12 melee left marker local changed');runtime:stop()
end
result12.meleeLeftOnlyOnNativeContact=true
-- Railgun sabot has no bullet_01/g_mag and must be admitted by exact resource, not a loose name classifier.
do
 local part=reload_start('2e9d0bdc48b09e60','503c0e01fbafa86a');local input=copy(part.locals)
 local sk=part.names[hash_name('skeleton')];part.cache[sk][10]=part.cache[sk][10]+4
 step(runtime,'render',10830,1083)
 check(not runtime.disabled and near(part.cache[part.linkRoot],gun.cache[part.linkIndex],4e-5),'TEST V12 railgun magazine graph detached')
 local expected=numpy_multiply(part.cache[part.parents[sk]+1],part.locals[sk]);check(near(part.cache[sk],expected,4e-5),'TEST V12 railgun skeleton stale')
 all_same(part.locals,input,'TEST V12 railgun ammunition local changed');runtime:stop()
end
result12.exactRailgunSabotGraph=true
-- A2 adds opt-in actual matrices and current-local root association, not offsets.
local previousCapture=test_repair_configuration.meleeCapture
test_repair_configuration.meleeCapture={enabled=true,maxItems=4}
for _,rid in ipairs({'792d5d2a340fd6e6','e3b6aedd07fcb464','5f3ec9bda2bd8553','b0f1b354ba1d38d8'})do
 local item=item_scene(rid,'attach_hand_r');local input=copy(item.locals);local mount=copy(A.cache[item.linkIndex])
 step(runtime,'render',10840,1084)
 local before,final,fullRight=false,false,false
 for _,line in ipairs(logs)do
  if line:find('"event":"test_melee_native_capture"',1,true) and line:find(rid,1,true)then
   if line:find('"stage":"before_write"',1,true)then before=true end
   if line:find('"stage":"final_output"',1,true)then final=true end
   check(line:find('"worldBeforeRefresh"',1,true) and line:find('"expectedFromCurrentLocal"',1,true) and line:find('"nativeLinkHypothesisMatched":true',1,true),'TEST A2 melee capture lacks current-local link evidence')
   check(line:find('"poseWrites":false',1,true) and line:find('"sameAvatarWorld":true',1,true),'TEST A2 melee capture changed domains or writes poses')
  end
  if line:find('"event":"right_applied"',1,true) and line:find(rid,1,true)then
   fullRight=line:find('"contact"',1,true) and not line:find('"format":"positions-v1"',1,true)
  end
 end
 check(before and final and fullRight,'TEST A2 bounded full melee capture missing '..rid)
 all_same(item.locals,input,'TEST A2 melee capture changed item local poses')
 check(near(A.cache[item.linkIndex],mount,4e-5),'TEST A2 melee capture moved native mount')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+4;refresh_all();local n=runtime.stats.rightWrites
 step(runtime,'render',10841,1084.1);check(runtime.stats.rightWrites==n,'TEST A2 dropped melee recording caused follow');runtime:stop()
end
test_repair_configuration.meleeCapture=previousCapture;integratedProfile.testRepairs.meleeCapture=previousCapture
result12.a2MeleeNativeAndSourceCapture=true
result12.a2MeleeCaptureHasNoOffsetOrPoseChanges=true
calculate=savedCalculate
result15.leftItemsV12=result12
end)()end
