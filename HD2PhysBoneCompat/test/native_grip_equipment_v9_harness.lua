local equipmentResult={}
-- Actual reload layouts without bullet_01/skeleton remain original animations.
for _,row in ipairs({{'02eecd0b1fa49630','b98f2b3d1bde24b0'},{'88c2d09ad85a7c9f','bf7082f0287c254f'},{'43b2d7766120203b','9c22a90da9c79de3'}})do
 local part=reload_start(row[1],row[2]);local input=copy(part.locals)
 step(runtime,'render',10500,1050)
 check(not runtime.disabled,'TEST V9 reload disabled')
 local found=false;for _,c in ipairs(runtime.consumers)do if c.spec.resource==part.resource then found=true end end
 check(found,'TEST V9 exact reload module missing')
 check(near(part.cache[part.linkRoot],gun.cache[part.linkIndex],3e-5),'TEST V9 reload detached')
 all_same(part.locals,input,'TEST V9 reload local animation modified');runtime:stop()
end
equipmentResult.glAndSterilizerReloadLayouts=true
-- JAR-5 is not an aim-only sidearm and its real root is above offset skeleton.
repaired_start('80f1a156d9fa1e36');gun=make(weapon_assets['80f1a156d9fa1e36']);gunParent=model;gunMount=hash_name('attach_hand_r');weaponRoot=gun.names[hash_name('boss')]
local fg=make(weapon_assets['411c4fd07740a7dd']);fg.linkOwner=gun;fg.linkIndex=gun.names[hash_name('attach_underbarrel')];fg.linkRoot=3
linkedItems={fg};groups[1]={A,model,gun,fg};pad_main();refresh_all()
-- Translate only a synthetic clavicle to put the real marker inside arm reach;
-- never change the exported limb lengths or real equipment local transforms.
local live=fg.cache[fg.names[hash_name('IK_left')]]
local lr=A.cache[integratedProfile.leftGrip.nodes[2].index+1]
local em=numpy_multiply(numpy_multiply(A.cache[integratedProfile.sourceRight.index+1],integratedProfile.rightAxes),A.locals[oi])
if integratedProfile.sourceRightMount then em=A.cache[integratedProfile.sourceRightMount.index+1]end
local ci=integratedProfile.rightGrip.nodes[1].index+1;local shifted=copy(A.cache[ci]);local delta={.15,.02,.18}
for j=1,3 do shifted[j+9]=shifted[j+9]+lr[j+9]+delta[j]-(live[j+9]+em[j+9]-A.cache[ti][j+9])end
A.locals[ci]=numpy_relative(A.cache[A.parents[ci]+1],shifted);refresh_all()
local nl=integratedProfile.nativeLeft.index+1
local originalGrip=numpy_multiply(A.cache[oi],numpy_relative(gun.cache[weaponRoot],fg.cache[fg.names[hash_name('IK_left')]]))
A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],originalGrip);refresh_all()
local nativeBefore=copy(A.cache[nl])
-- This synthetic T-pose moves the gun >1m in one transaction, unlike gameplay.
integratedProfile.performance.refreshRadius=3
local input=copy(fg.locals);step(runtime,'render',10510,1051)
if runtime.stats.leftWrites~=1 or runtime.stats.underbarrelTargets~=1 then
 print('JAR COUNTS',runtime.disabled,runtime.stats.leftWrites,runtime.stats.underbarrelTargets)
 for i=#logs,math.max(1,#logs-30),-1 do if logs[i]:find('"event":"left_skipped"',1,true) or logs[i]:find('"event":"disabled"',1,true) or logs[i]:find('"event":"left_applied"',1,true) then print('JAR RESULT',logs[i]);break end end
end
check(not runtime.disabled and runtime.stats.leftWrites==1 and runtime.stats.underbarrelTargets==1,'TEST V9 JAR actual foregrip not selected')
local rebased=numpy_multiply(fg.cache[fg.names[hash_name('IK_left')]],numpy_relative(originalGrip,nativeBefore))
local hand=A.cache[integratedProfile.sourceLeft.index+1]
local actual=contact_point(hand,integratedProfile.testRepairs.contacts.left.source)
local wanted=contact_point(rebased,integratedProfile.testRepairs.contacts.left.native)
for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST V9 JAR final contact missed')end
all_same(fg.locals,input,'TEST V9 JAR foregrip locals modified');runtime:stop()
equipmentResult.jarPolicyAndRealLinkRoot=true
-- C4 detonator and marker use accepted pistol wrist orientation policy.
for _,rid in ipairs({'51f50d6321f52f3d','64cdb52aca152be1'})do
 repaired_start('cf8934ff6567a42d');gun=make(weapon_assets[rid]);gunParent=model;gunMount=hash_name('attach_hand_r');weaponRoot=gun.names[hash_name('boss')];linkedItems={};groups[1]={A,model,gun};pad_main();refresh_all()
 local input=copy(gun.locals);local native=copy(A.locals[integratedProfile.nativeRight.index+1])
 step(runtime,'render',10520,1052)
 check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST V9 tool pistol follower missing')
 check(near(A.locals[integratedProfile.nativeRight.index+1],native),'TEST V9 tool wrote native wrist')
 all_same(gun.locals,input,'TEST V9 tool animation modified');runtime:stop()
end
equipmentResult.detonatorAndDesignator=true
-- Only a held rigid item may drive a hand; released explosives remain untouched.
for _,rid in ipairs({'9b75217d8312dd67','14368dc8784220b0'})do
 repaired_start('cf8934ff6567a42d');gun.visible=false
 local item=make(weapon_assets[rid]);item.linkOwner=A;item.linkIndex=ti;item.linkRoot=3
 linkedItems={item};groups[1]={A,model,gun,item};pad_main();refresh_all();local input=copy(item.locals)
 step(runtime,'render',10530,1053)
 check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST V9 rigid held item not followed')
 all_same(item.locals,input,'TEST V9 held explosive locals modified')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+3;refresh_all();local released=copy(item.locals);local count=runtime.stats.rightWrites
 step(runtime,'render',10531,1053.1)
 check(runtime.stats.rightWrites==count,'TEST V9 released explosive still drove hand')
 all_same(item.locals,released,'TEST V9 released explosive modified');runtime:stop()
end
equipmentResult.heldAndReleasedExplosives=true
-- Production-like low-volume test mode disables heavy observers, not grip/FK.
repaired_start('cf8934ff6567a42d');aim_native();native_contact(.30)
integratedProfile.logging={compact=true,detailed=false};integratedProfile.testRepairs.bodyDiagnostics.enabled=false
integratedProfile.testRepairs.aimDiagnostics.enabled=false;integratedProfile.testRepairs.gripTracking.enabled=false;integratedProfile.sidearmDiagnostics.enabled=false
local offset=#logs;step(runtime,'render',10540,1054)
check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST V9 performance mode disabled grip')
for i=offset+1,#logs do
 check(not logs[i]:find('"event":"test_body_lifecycle_probe"',1,true) and not logs[i]:find('"event":"test_pose_trace"',1,true),'TEST V9 performance emitted heavy poses')
end
-- V9 restores the dual-skeleton lifecycle baseline, rather than applying
-- the single-skeleton ragdoll investigation gate to this character.
integratedProfile.testRepairs.bodyDiagnostics.bypassNoAnimationStateMachine=false
local oldFSM=U.has_animation_state_machine;local fsm=true
U.has_animation_state_machine=function()return fsm end
step(runtime,'render',10541,1054.1);local count=runtime.stats.rightWrites;fsm=false
step(runtime,'render',10542,1054.2)
check(not runtime.disabled and runtime.stats.rightWrites==count+1 and runtime.stats.lifecycleBypasses==0,'TEST V9 dual ragdoll gate was not restored')
U.has_animation_state_machine=oldFSM
runtime:stop();equipmentResult.performanceObserversDisabled=true;equipmentResult.dualLifecycleOriginal=true
result15.equipmentV9=equipmentResult
