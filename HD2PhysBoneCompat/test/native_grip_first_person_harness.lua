-- First-person gate is a global write bypass, not an ADS/left-hand condition.
local checksBeforeFP=checks
local fpGuardModule=fp_guard_module
local fp=nil;local viewCamera=nil;local queryFails=false;local fpContext=nil
local baseQuery=S.World.units_by_resource
S.World.units_by_resource=function(world,path)
 if path=='content/fac_helldivers/fp_cha_avatar/fp_cha_avatar'then
  recycled();if queryFails then error('injected_fp_query_failure')end
  return world==1 and fp and fp.alive and {fp} or {}
 end
 return baseQuery(world,path)
end
S.World.debug_camera_pose=function(world)
 check(world==1,'FP guard read a non-main camera');return recycled(viewCamera)
end
local function fp_start()
 new_start('8d3d52a3b2f19402');runtime:stop()
 local hashes,parents,matrices={},{},{}
 for i=1,63 do hashes[i]=hash_name('fp_dummy_'..i);matrices[i]=transform(0)end
 hashes[5]=hash_name('root');hashes[51]=hash_name('camera')
 fp=make({resource='d0cf4d493ca08bed',hashes=hashes,parents=parents,matrices=matrices})
 calculate(fp);fp.cache[51]=transform(0,10,20,30)
 groups[1][#groups[1]+1]=fp
 viewCamera=transform(0,10,18,30)
 local guard=fpGuardModule.new(S,{world=function()return 1 end})
 local context={inMission=function()return true end,world=function()return 1 end,firstPerson=guard.sample,fpWorld=guard.world}
 runtime=module.new(S,integratedProfile,function(line)logs[#logs+1]=line end,arm_math,
  context)
 fpContext=context
 return guard
end
local fixedFP={}
local guard=fp_start();aim_native();local input=copy(A.locals)
-- Retained FP graph and a zoomed TP view must not suppress existing gripping.
step(runtime,'render',8000,800)
check(not runtime.disabled and runtime.stats.rightWrites==1,'retained FP graph disabled TP grip')
local nativeCount=runtime.stats.writes
viewCamera=transform(0,10,20,30)
-- Enter during UPDATE, while the prior render's outputs are still held.
step(runtime,'update',8001,800.02)
check(not runtime.disabled and #runtime.pending==0,'FP entry did not restore pending transaction')
all_same(A.locals,input,'FP entry restoration')
local setterCount=writes
for i=1,8 do step(runtime,'render',8001+i,800+i*.02);step(runtime,'update',8001+i,800+i*.02)end
check(writes==setterCount and runtime.stats.writes==nativeCount,'first person still has setters')
check(runtime.stats.rightWrites==1 and runtime.stats.leftWrites<=1,'FP bypass still solves arms')
viewCamera=transform(0,10,18,30);native_contact()
step(runtime,'render',8020,801)
check(not runtime.disabled and runtime.stats.rightWrites==2,'third-person reentry did not restore normal grip')
runtime:stop();fixedFP.updateEntryAllWritesBypassed=true;fixedFP.thirdPersonReentry=true
-- A view switch occurring before RENDER is handled too; repeats have no setters.
guard=fp_start();aim_native();input=copy(A.locals);step(runtime,'render',8100,810)
viewCamera=transform(0,10,20,30);step(runtime,'render',8101,810.02)
all_same(A.locals,input,'render FP entry restoration');setterCount=writes
step(runtime,'render',8102,810.04);check(writes==setterCount,'FP render repeats cleanup setters')
runtime:stop();fixedFP.renderEntryRestoresOnce=true
-- Missing camera / resource errors are a temporary conservative bypass, not disable.
guard=fp_start();aim_native();input=copy(A.locals);step(runtime,'render',8200,820)
viewCamera=nil;check(guard.sample()==nil and guard.world()==nil,'unknown view retained stale FP world');step(runtime,'update',8201,820.02)
check(not runtime.disabled and #runtime.pending==0,'missing view camera disabled addon')
all_same(A.locals,input,'unknown camera restoration');setterCount=writes
local unknownRefresh=runtime.stats.fpPresentationRefreshes
step(runtime,'render',8202,820.04);check(writes==setterCount,'unknown camera still writes')
check(runtime.stats.fpPresentationRefreshes==unknownRefresh,'unknown view performed FP maintenance')
viewCamera=transform(0,10,18,30);step(runtime,'render',8203,820.06)
check(runtime.stats.rightWrites==2,'camera recovery did not resume TP')
queryFails=true;step(runtime,'render',8204,820.08)
check(not runtime.disabled and #runtime.pending==0,'FP query error failed bypass')
queryFails=false;runtime:stop();fixedFP.unknownViewFailsClosedAndRecovers=true
-- The graph may live in a mirrored FP World, not the main mission World.
guard=fp_start();local base=S.World.units_by_resource
S.World.units_by_resource=function(world,path)
 if path=='content/fac_helldivers/fp_cha_avatar/fp_cha_avatar' then return world==2 and {fp} or {}end
 return base(world,path)
end
viewCamera=transform(0,10,20,30);step(runtime,'render',8300,830)
check(runtime.stats.writes==0 and not runtime.disabled,'mirrored FP world not detected')
check(guard.world()==2,'FP guard did not expose actual mirrored world')
do
 local mirror=make(fixture.model);local preview=make(fixture.model)
 refresh(mirror);refresh(preview)
 groups[2][#groups[2]+1]=mirror;groups[3]={preview}
 A.locals[1][10]=A.locals[1][10]+.5;calculate(A)
 local mirrorHand=mirror.names[hash_name('r_hand')]
 local previewBefore=copy(preview.cache[mirrorHand]);local observed={}
 local baseUpdate=S.World.update_unit
 S.World.update_unit=function(w,u)observed[u]=true;return baseUpdate(w,u)end
 setterCount=writes;step(runtime,'render',8301,831)
 check(observed[mirror]==true and not observed[preview],'FP mirror scope includes preview or excludes actual FP world')
 check(near(mirror.cache[mirrorHand],A.cache[A.names[hash_name('r_hand')]]),'mirrored FP body cache not maintained')
 check(near(preview.cache[mirrorHand],previewBefore) and writes==setterCount,'preview touched during FP')
 S.World.update_unit=baseUpdate;groups[3]=nil
end
S.World.units_by_resource=base;runtime:stop();fixedFP.mirroredWorldDetected=true;fixedFP.mirroredBodyRefreshedAndPreviewExcluded=true

-- Reproduce the missing lifecycle: native Avatar moves, body palette/cache stays
-- frozen until its own update_unit. This is independent of any pose/IK setters.
do
 guard=fp_start();aim_native();step(runtime,'render',8400,840)
 viewCamera=transform(0,10,20,30);step(runtime,'update',8401,840.02)
 local forbiddenCalls=0
 local saved={}
 local function forbid(t,k)
  saved[#saved+1]={t=t,k=k,v=t[k]}
  t[k]=function()forbiddenCalls=forbiddenCalls+1;error('FP presentation used '..k)end
 end
 for _,k in ipairs({'set_local_pose','set_world_pose','set_local_position','set_world_position','set_local_rotation','set_visibility','set_mesh_visibility','set_animation_state_machine'})do forbid(U,k)end
 for _,k in ipairs({'link_unit','unlink_unit'})do forbid(S.World,k)end
 forbid(S.Mesh,'set_visibility')
 local hand=model.names[hash_name('r_hand')]
 check(hand~=nil,'missing model hand in cache fixture')
 local initial=copy(model.cache[hand])
 local far=make(fixture.weapon)
 for n,m in ipairs(far.locals)do if far.parents[n]==nil or far.parents[n]<0 then m[10]=m[10]+100 end end
 calculate(far);groups[1][#groups[1]+1]=far
 local orderedUpdate=S.World.update_unit;local order={}
 S.World.update_unit=function(w,u)order[#order+1]=u;return orderedUpdate(w,u)end
 for i=1,6 do
  -- Native movement can update its own graph without updating the body receiver.
  A.locals[1][10]=A.locals[1][10]+.3;calculate(A)
  local target=copy(A.cache[A.names[hash_name('r_hand')]])
  check(not near(model.cache[hand],target),'fixture did not reproduce stale receiver cache')
  local beforeLocals=copy(A.locals);local beforeModel=copy(model.locals)
  model.visible=(i>3) -- hidden on entry: native renderer may later show this again
  order={};setterCount=writes
  step(runtime,'render',8401+i,840.02+i*.1)
  check(not runtime.disabled and #runtime.pending==0,'FP presentation disabled runtime')
  check(near(model.cache[hand],target),'FP body receiver frozen in world space')
  check(writes==setterCount and forbiddenCalls==0,'FP refresh used a pose/visibility/link setter')
  all_same(A.locals,beforeLocals,'FP movement native inputs changed')
  all_same(model.locals,beforeModel,'FP refresh changed model local poses')
  local avatarOrder,modelOrder
  for j,u in ipairs(order)do
   check(u~=far,'FP refreshed distant battlefield equipment')
   if u==A then avatarOrder=j elseif u==model then modelOrder=j end
  end
  check(avatarOrder and modelOrder and avatarOrder<modelOrder,'FP cache refresh dependency order wrong')
  check(model.visible==(i>3),'FP maintenance changed visibility')
  step(runtime,'update',8401+i,840.02+i*.1)
 end
 check(not near(model.cache[hand],initial),'model stayed at its original world position')
 check(runtime.stats.fpPresentationRefreshes>0 and runtime.stats.fpPresentationErrors==0,'FP presentation did not refresh')
 S.World.update_unit=orderedUpdate
 for _,r in ipairs(saved)do r.t[r.k]=r.v end
 fixedFP.movingAvatarRefreshesBodyCache=true;fixedFP.hiddenBodyRefreshed=true
 fixedFP.noPoseVisibilityOrLinkSetters=true;fixedFP.avatarBeforeBodyRefresh=true;fixedFP.distantEquipmentExcluded=true
 -- A lost model/refresh error must not permanently disable TP recovery.
 local baseUpdate=S.World.update_unit
 S.World.update_unit=function(w,u)if u==model then error('injected_fp_model_refresh_failure')end;return baseUpdate(w,u)end
 step(runtime,'render',8410,841)
 check(not runtime.disabled and runtime.stats.fpPresentationErrors>0,'FP refresh failure permanently disabled addon')
 S.World.update_unit=baseUpdate
 step(runtime,'render',8411,841.1)
 check(near(model.cache[hand],A.cache[A.names[hash_name('r_hand')]]),'FP refresh did not retry after failure')
 fixedFP.refreshFailureRetries=true
 -- No presentation maintenance during an unverified/ship scene, even with FP.
 fpContext.inMission=function()return false end
 local beforeRefresh=runtime.stats.fpPresentationRefreshes;setterCount=writes
 step(runtime,'render',8412,841.2)
 check(runtime.stats.fpPresentationRefreshes==beforeRefresh and writes==setterCount,'ship FP performed maintenance')
 fpContext.inMission=function()return true end
 viewCamera=transform(0,10,18,30);native_contact()
 step(runtime,'render',8420,842)
 check(not runtime.disabled and runtime.stats.rightWrites==2,'TP failed after FP movement/cache scans')
 runtime:stop();fixedFP.thirdPersonReentryAfterMoving=true;fixedFP.shipMaintenanceBypassed=true
end

return {status='PASS_PENDING_GAME_TEST',checks=checks,priorChecks=checksBeforeFP,firstPerson=fixedFP,gameTested=false,logs=logs}
