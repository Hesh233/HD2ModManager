-- Real game equipment fixtures appended to the existing B23/test07 suites.
local result15={}
local function real_start(rid)
 new_start(rid)
 gun=make(weapon_assets[rid]);gunParent=model;gunMount=hash_name('attach_hand_r')
 weaponRoot=gun.names[hash_name('root')];under=gun.names[hash_name('attach_underbarrel')]
 linkedItems={};groups[1]={A,model,gun};pad_main();refresh_all()
 return runtime
end
local function add_component(rid,mount)
 local part=make(weapon_assets[rid]);part.linkOwner=gun
 part.linkIndex=gun.names[hash_name(mount)];part.linkRoot=part.names[hash_name('skeleton')]
 check(part.linkIndex and part.linkRoot,'actual equipment link fixture incomplete '..rid)
 linkedItems[#linkedItems+1]=part;groups[1][#groups[1]+1]=part
 return part
end
-- AR-11 magazines/optic and its separately attached shotgun are exact signatures.
real_start('a8a91eb54892b6b2')
local launcher=add_component('b9c209b4f99b5335','attach_underbarrel')
local magazine=add_component('20c03774d6e1d87f','attach_mag')
local optic=add_component('129e5fb1b13c2018','attach_optic')
refresh_all()
-- Place the post-transfer marker within the synthetic Source left arm's reach,
-- by translating only this fixture's right clavicle (not production bone lengths).
local liveGrip=launcher.cache[launcher.names[hash_name('IK_left')]]
local leftRoot=A.cache[integratedProfile.leftGrip.nodes[2].index+1]
local eq=numpy_multiply(A.cache[integratedProfile.sourceRight.index+1],integratedProfile.rightAxes)
local expectedMount=numpy_multiply(eq,A.locals[oi])
if integratedProfile.sourceRightMount then expectedMount=A.cache[integratedProfile.sourceRightMount.index+1]end
local ci=integratedProfile.rightGrip.nodes[1].index+1
local shifted=copy(A.cache[ci]);local delta={.18,.04,.23}
for j=1,3 do
 local postGrip=liveGrip[j+9]+expectedMount[j+9]-A.cache[ti][j+9]
 shifted[j+9]=shifted[j+9]+leftRoot[j+9]+delta[j]-postGrip
end
A.locals[ci]=numpy_relative(A.cache[A.parents[ci]+1],shifted);refresh_all()
local nativePose=numpy_multiply(A.cache[oi],numpy_relative(gun.cache[weaponRoot],launcher.cache[launcher.names[hash_name('IK_left')]]))
local ni=integratedProfile.nativeLeft.index+1
A.locals[ni]=numpy_relative(A.cache[A.parents[ni]+1],nativePose);refresh_all()
local input=copy(A.locals);local locals15={}
for _,part in ipairs(linkedItems)do locals15[part]=copy(part.locals)end
step(runtime,'render',8000,800)
check(not runtime.disabled and runtime.stats.underbarrelTargets==1 and runtime.stats.leftWrites==1,'AR11 actual attached shotgun was not selected')
check(separation(A.cache[integratedProfile.sourceLeft.index+1],launcher.cache[launcher.names[hash_name('IK_left')]])<2e-5,'AR11 underbarrel grip offset survived')
local discovered={};for _,item in ipairs(runtime.consumers)do discovered[item.spec.resource]=true end
for _,part in ipairs(linkedItems)do
 check(discovered[part.resource],'AR11 exact part not discovered '..part.resource)
 check(near(part.cache[part.linkRoot],gun.cache[part.linkIndex]),'AR11 part cache detached '..part.resource)
 all_same(part.locals,locals15[part],'AR11 local animation mutated')
end
-- Existing native relink during reload is respected, not reparented by Lua.
magazine.linkOwner=model;magazine.linkIndex=model.names[hash_name('attach_hand_l')]
refresh_all();step(runtime,'render',8001,800.02)
check(near(magazine.cache[magazine.linkRoot],model.cache[magazine.linkIndex]),'AR11 reload magazine relink detached')
all_same(magazine.locals,locals15[magazine],'AR11 reload local animation mutated')
runtime:stop();all_same(A.locals,input,'AR11 restore');result15.ar11ExactPartsAndUnderbarrel=true
-- P-92 reachable native path stays intact; unreachable arm contacts the LIVE IK.
real_start('cf8934ff6567a42d')
local mag92=add_component('fc1f0a3b3fc97238','attach_mag');refresh_all()
local _,goal=aim_native();native_contact(.30)
input=copy(A.locals);local gunInput=copy(gun.locals);local magInput=copy(mag92.locals)
local stableMount=copy(A.cache[ti]);step(runtime,'render',8100,810)
check(not runtime.disabled and runtime.stats.rightReachCorrections==0,'reachable P92 was shifted')
check(near(A.cache[ti],stableMount,2e-5),'reachable P92 native path changed')
step(runtime,'update',8100,810);runtime:stop();all_same(A.locals,input,'P92 reachable restore')
real_start('cf8934ff6567a42d');mag92=add_component('fc1f0a3b3fc97238','attach_mag');refresh_all()
aim_native();native_contact(.30)
local nativePose92=copy(A.cache[nativeRight]);nativePose92[12]=nativePose92[12]+.65
A.locals[nativeRight]=numpy_relative(A.cache[A.parents[nativeRight]+1],nativePose92);refresh_all()
input=copy(A.locals);gunInput=copy(gun.locals);magInput=copy(mag92.locals);local mountBefore=copy(A.cache[ti])
step(runtime,'render',8200,820)
check(not runtime.disabled and runtime.stats.rightReachCorrections==1,'unreachable P92 correction not applied')
local hand=A.cache[integratedProfile.sourceRight.index+1];local marker=gun.cache[gun.names[hash_name('IK_right')]]
check(separation(hand,marker)<2e-5,'unreachable P92 live IK contact offset survived')
for j=1,9 do check(math.abs(A.cache[ti][j]-mountBefore[j])<2e-5,'P92 native aim basis changed')end
all_same(gun.locals,gunInput,'P92 gun animation mutated');all_same(mag92.locals,magInput,'P92 magazine animation mutated')
check(near(mag92.cache[mag92.linkRoot],gun.cache[mag92.linkIndex]),'P92 magazine separated after correction')
local firstMount=copy(A.cache[ti]);step(runtime,'update',8200,820);step(runtime,'render',8201,820.02)
check(near(A.cache[ti],firstMount,2e-5),'P92 correction accumulated across frames')
runtime:stop();all_same(A.locals,input,'P92 unreachable restore');result15.p92ReachableAndUnreachableContact=true
-- Empty observations do not exhaust the budget before these weapons are held.
real_start('cf8934ff6567a42d');integratedProfile.sidearmDiagnostics.resources={};native_contact(.30)
for i=1,185 do step(runtime,'render',8300+i,830+i*1.1)end
check((runtime.probeCount.lua or 0)==0,'empty weapon observations consumed budget')
integratedProfile.sidearmDiagnostics.resources={cf8934ff6567a42d=true}
step(runtime,'render',8500,1050)
check((runtime.probeCount.lua or 0)>0,'late P92 diagnostic never emitted')
runtime:stop();result15.boundedProbeAfterEmptyFrames=true
-- 1.0.16: distinguish the animated original reference from the final Source mount.
local range16={}
local function range_members()
 local members={}
 for w,units in pairs(groups)do
  local set={};for _,u in ipairs(units)do set[u]=true end
  members[w]={units=units,set=set,label=w}
 end
 return members
end
local function mount_scene()
 real_start('a8a91eb54892b6b2');native_contact(.30)
 local index=A.count;local name='__range_fixture_source_mount'
 local spec={name=name,index=index,parent=integratedProfile.sourceRight.index,hash=hash_name(name)}
 A.count=index+1;A.locals[index+1]=transform(0);A.parents[index+1]=spec.parent;A.names[spec.hash]=index+1
 integratedProfile.avatar.count=A.count
 integratedProfile.avatar.nodes[#integratedProfile.avatar.nodes+1]=spec
 integratedProfile.sourceRightMount=spec;refresh_all()
 return index+1
end
local function logged(fragment,first)
 for i=first or 1,#logs do if logs[i]:find(fragment,1,true)then return true end end
 return false
end
local sm=mount_scene()
step(runtime,'render',8600,860)
check(not runtime.disabled and runtime.stats.writes==1,'normal Source mount fixture did not apply')
runtime:release(range_members())
A.locals[sm][10]=.80;refresh_all()
input=copy(A.locals);gunInput=copy(gun.locals);local modelCache=copy(model.cache);local gunCache=copy(gun.cache)
local bodyBefore=runtime.stats.bodyNodeWrites;local writesBefore16=runtime.stats.writes;local logFirst=#logs+1
-- This exception occurs off the periodic diagnostic tick and after log exhaustion.
integratedProfile.maxRecords=0;runtime.lastLog=860
step(runtime,'render',8601,860.01)
check(not runtime.disabled and #runtime.pending==0,'final mount excursion permanently disabled runtime')
check(runtime.stats.mountSkipped==1 and runtime.stats.mountRollbacks==1,'final range skip/rollback not counted')
check(runtime.stats.writes==writesBefore16,'out-of-range mount was written')
check(runtime.stats.bodyNodeWrites>bodyBefore,'final-range fixture bypassed body intermediate writes')
check(runtime.stats.bodyRestores==runtime.stats.bodyNodeWrites,'final-range body rollback ledger unbalanced')
all_same(A.locals,input,'final-range restored locals');all_same(gun.locals,gunInput,'range mutated gun animation')
all_same(model.cache,modelCache,'range failed to refresh model cache');all_same(gun.cache,gunCache,'range failed to refresh gun cache')
check(logged('"stage":"final_candidate"',logFirst) and logged('"rollbackVerified":true',logFirst),'exception frame evidence was suppressed')
for _,key in ipairs({'frame','time','phase','distance','limit','originalLocal','sourceWorld','desiredWorld','sourceMountLocal','sourceMountWorld','candidate'})do
 check(logged('"'..key..'":',logFirst),'range diagnostic missing '..key)
end
check(logged('"retry":"next_render"',logFirst),'range retry diagnostic missing')
A.locals[sm][10]=0;refresh_all();step(runtime,'render',8602,860.02)
check(not runtime.disabled and runtime.stats.writes==writesBefore16+1,'normal pose did not resume after final-range excursion')
runtime:stop();range16.sourceMountNormalExcursionNormal=true;range16.offTickBudgetIndependentEvidence=true
-- Original-reference preflight remains setter-free and retryable.
sm=mount_scene();A.locals[oi][10]=.8;refresh_all();input=copy(A.locals);local setterCount=writes
step(runtime,'render',8610,861)
check(not runtime.disabled and writes==setterCount and #runtime.pending==0,'preflight range excursion called setters')
check(runtime.stats.mountSkipped==1 and runtime.stats.mountRollbacks==0,'preflight excursion was not distinguished')
all_same(A.locals,input,'preflight mutated locals')
A.locals[oi]=copy(right_fixture.matrices[oi]);refresh_all();step(runtime,'render',8611,861.01)
check(not runtime.disabled and runtime.stats.writes==1,'preflight range excursion did not retry');runtime:stop()
range16.preflightNoSettersAndRetry=true
-- Actual P-92 path: final sidearm candidate fails AFTER all right-arm outputs.
real_start('cf8934ff6567a42d')
local ri=gun.names[hash_name('IK_right')];local markerBefore=copy(gun.locals[ri])
gun.locals[ri][10]=gun.locals[ri][10]+.8;refresh_all();aim_native();input=copy(A.locals);gunInput=copy(gun.locals)
logFirst=#logs+1;step(runtime,'render',8620,862)
check(not runtime.disabled and #runtime.pending==0 and runtime.stats.mountRollbacks==1,'P92 final range excursion did not recover')
check(runtime.stats.rightNodeWrites==3 and runtime.stats.rightRestores==3,'P92 right-arm partial transaction not restored')
check(runtime.stats.writes==0,'P92 invalid final mount was written')
all_same(A.locals,input,'P92 range output restore');all_same(gun.locals,gunInput,'P92 marker local mutated')
check(logged('"weaponResource":"cf8934ff6567a42d"',logFirst),'failed sidearm selection not diagnosed')
gun.locals[ri]=markerBefore;refresh_all();aim_native();step(runtime,'render',8621,862.01)
check(not runtime.disabled and runtime.stats.writes==1,'P92 did not resume after invalid final candidate');runtime:stop()
range16.sidearmRightOutputsRolledBackAndRetried=true
-- Restore setter and consumer refresh failures must NOT be treated as recovery.
sm=mount_scene();A.locals[sm][10]=.8;refresh_all();failAt=3
step(runtime,'render',8630,863)
check(runtime.disabled and runtime.stats.mountRollbacks==0,'failed range rollback did not fail closed')
check(logged('mount_range_restore_failed:'),'range restore failure missing hard-disable reason');runtime:stop()
range16.rollbackSetterFailureFailsClosed=true
sm=mount_scene();A.locals[sm][10]=.8;refresh_all()
local update16=S.World.update_unit;local fired16=false
S.World.update_unit=function(w,u)
 if u==model and runtime.stats.bodyRestores>0 and not fired16 then
  fired16=true;error('injected_range_restore_consumer_refresh')
 end
 return update16(w,u)
end
step(runtime,'render',8640,864);S.World.update_unit=update16
check(fired16 and runtime.disabled and runtime.stats.mountRollbacks==0,'range restore consumer refresh failure was swallowed')
check(logged('restore_refresh_failed'),'range restore refresh failure not diagnosed');runtime:stop()
range16.rollbackConsumerRefreshFailureFailsClosed=true
sm=mount_scene();input=copy(A.locals);failAt=1
step(runtime,'render',8650,865)
check(runtime.disabled and runtime.stats.mountRollbacks==0,'unrelated setter error was swallowed as transient range')
all_same(A.locals,input,'non-range setter failure rollback');runtime:stop()
range16.unrelatedSetterFailureFailsClosed=true
result15.rangeRecovery16=range16
-- 1.0.17: stopping a real production sink must not stop pose transactions.
real_start('a8a91eb54892b6b2');native_contact(.30)
integratedProfile.logging={compact=true};local recordTime=0;local diskLines={}
local limited,logBudget=module.newLogSink(function(line)diskLines[#diskLines+1]=line end,
 function()return recordTime end,{recordSeconds=90,maxBytes=16384,exceptionIntervalSeconds=2})
runtime=module.new(S,integratedProfile,limited,arm_math,
 {inMission=function()return true end,world=function()return 1 end,firstPerson=function()return false end})
step(runtime,'render',8700,870)
check(not runtime.disabled and runtime.stats.writes==1,'bounded logging first real pose failed')
recordTime=91;step(runtime,'render',8701,875)
check(logBudget.stopped and not runtime.disabled and runtime.stats.writes==2,'recording timeout stopped actual grip correction')
recordTime=180;step(runtime,'render',8702,880)
check(not runtime.disabled and runtime.stats.writes==3,'grip did not continue beyond recording window')
runtime:stop();check(diskLines[#diskLines]:find('"event":"complete"',1,true)~=nil,'bounded real runtime shutdown missing')
result15.boundedLogDoesNotStopPose=true
return {status='PASS_PENDING_GAME_TEST',checks=checks,rightAim=result111,weapons15=result15,gameTested=false,logs=logs}
