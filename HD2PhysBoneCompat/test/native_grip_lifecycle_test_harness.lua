-- V7: native reverse removed; source forward baseline, read-only whole-body
-- probes, no-FSM cleanup, and no assumption that ignore mode == ragdoll.
local lifecycleResult={}
local oldHasFSM=U.has_animation_state_machine;local oldBoneMode=U.animation_bone_mode
local hasFSM=true;local mode='transform';local stateCalls=0
U.has_animation_state_machine=function(u)check(u==A,'TEST lifecycle queried foreign actor');stateCalls=stateCalls+1;return hasFSM end
U.animation_bone_mode=function(u)check(u==A,'TEST lifecycle bone mode queried foreign actor');return mode end
repaired_start('dbb6c961c59fadc1');aim_native();native_contact(.30)
-- An obsolete V6 option must no longer grant native joint writer access.
integratedProfile.testRepairs.nativeReverse={enabled=true,resources={dbb6c961c59fadc1=true}}
for _,spec in pairs(integratedProfile.models)do
 local node=integratedProfile.testRepairs.gripTracking.actorNodes.sourceHand
 local i=node and model.names[node.hash];spec.testSkinProbes={}
 if i then spec.testSkinProbes[1]={name=node.name,hash=node.hash,index=i-1,parent=model.parents[i],weightedVertices=10,avatarSameHashAvailable=true,kind='weighted_skeleton_node'}end
end
local input=copy(A.locals);local nativeInput=copy(A.locals[integratedProfile.nativeRight.index+1])
step(runtime,'render',10100,1010)
check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST rollback did not restore forward follower')
check(near(A.locals[integratedProfile.nativeRight.index+1],nativeInput),'TEST rollback wrote native r_hand')
local seen=false
for _,line in ipairs(logs)do
 if line:find('"event":"test_body_lifecycle_probe"',1,true) and line:find('"weightedBonePoses"',1,true)
  and line:find('"worldScale"',1,true) and line:find('"stateMachinePresent":true',1,true)then seen=true end
end
check(seen,'TEST lifecycle weighted body telemetry missing')
step(runtime,'update',10100,1010.02)
local updateSeen=false
for _,line in ipairs(logs)do if line:find('"event":"test_body_lifecycle_probe"',1,true) and line:find('"stage":"update_input"',1,true)then updateSeen=true end end
check(updateSeen,'TEST lifecycle update-stage evidence missing')
hasFSM=false;mode='ignore'
step(runtime,'render',10101,1010.30)
check(not runtime.disabled and runtime.stats.rightWrites==1 and runtime.stats.lifecycleBypasses==1,'TEST lifecycle continued driving no-FSM actor')
all_same(A.locals,input,'TEST lifecycle no-FSM cleanup failed')
local writesBefore=writes
step(runtime,'render',10102,1010.60)
check(writes==writesBefore and runtime.stats.lifecycleBypasses==2,'TEST lifecycle repeated no-FSM pose writes')
check(near(A.locals[integratedProfile.nativeRight.index+1],nativeInput),'TEST lifecycle no-FSM native hand changed')
hasFSM=true;mode='ignore'
step(runtime,'render',10103,1010.90)
check(not runtime.disabled and runtime.stats.rightWrites==2,'TEST lifecycle treated bone mode as unverified ragdoll flag')
-- Missing API cannot silently disable ordinary actors; unknown keeps baseline.
U.has_animation_state_machine=nil;step(runtime,'render',10104,1011.20)
check(not runtime.disabled and runtime.stats.rightWrites==3,'TEST lifecycle unknown API disabled baseline')
-- Remove the actor before update/render; no state/pose readers may touch it.
U.has_animation_state_machine=function(u)stateCalls=stateCalls+1;error('TEST lifecycle dead actor read')end
local callsBefore=stateCalls;groups[1]={model,gun}
step(runtime,'update',10105,1011.50);step(runtime,'render',10105,1011.50)
check(stateCalls==callsBefore and not runtime.disabled,'TEST lifecycle read removed actor')
runtime:stop()
-- A fresh actor whose API initially reports false is not automatically a corpse.
hasFSM=false
U.has_animation_state_machine=function(u)check(u==A,'TEST initial-FSM queried foreign actor');return hasFSM end
repaired_start('dbb6c961c59fadc1');aim_native();native_contact(.30)
step(runtime,'render',10106,1011.80)
check(not runtime.disabled and runtime.stats.rightWrites==1 and runtime.stats.lifecycleBypasses==0,'TEST lifecycle treated initial no-FSM actor as corpse')
runtime:stop()
-- After a rig is reduced to native-only, remain a reader and include nearby
-- orphan skin bones without granting writer ownership or reading Source slots.
repaired_start('dbb6c961c59fadc1');local orphanCache=copy(model.cache);A.count=107;refresh_all();model.cache=orphanCache
integratedProfile.testRepairs.bodyDiagnostics.unownedProbeRadius=100
for _,spec in pairs(integratedProfile.models)do
 local node=integratedProfile.testRepairs.gripTracking.actorNodes.sourceHand
 local i=node and model.names[node.hash];spec.testSkinProbes={}
 if i then spec.testSkinProbes[1]={name=node.name,hash=node.hash,index=i-1,parent=model.parents[i],weightedVertices=10,avatarSameHashAvailable=true,kind='weighted_skeleton_node'}end
end
local oldWorldPose=U.world_pose
U.world_pose=function(u,n)if u==A then check(n<=107,'TEST native-only observer read Source slot')end;return oldWorldPose(u,n)end
step(runtime,'render',10107,1012.10)
check(not runtime.disabled and runtime.stats.writes==0 and runtime.stats.rightWrites==0 and runtime.stats.bodyNodeWrites==0,'TEST native-only observer gained writer access')
local orphanSeen=false
for _,line in ipairs(logs)do
 if line:find('"event":"test_body_lifecycle_probe"',1,true) and line:find('"nativeOnlyObserver":true',1,true)
  and line:find('unverified_near_native_observer_read_only',1,true)then orphanSeen=true end
end
check(orphanSeen,'TEST native-only orphan weighted evidence missing')
runtime:stop();U.world_pose=oldWorldPose
U.has_animation_state_machine=oldHasFSM;U.animation_bone_mode=oldBoneMode
lifecycleResult.nativeReverseRemoved=true;lifecycleResult.forwardBaselineRestored=true
lifecycleResult.weightedBodyAndUpdateEvidence=true;lifecycleResult.noFsmCleanedWithoutRepeatedWrites=true
lifecycleResult.unknownOrIgnoreNotAssumedRagdoll=true;lifecycleResult.removedActorNoReads=true;lifecycleResult.initialNoFsmNotAssumedCorpse=true;lifecycleResult.nativeOnlyOrphanReadOnly=true
result15.bodyLifecycle=lifecycleResult
