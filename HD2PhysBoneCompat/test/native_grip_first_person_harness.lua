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
 local context={inMission=function()return true end,world=function()return 1 end,firstPerson=guard.sample,fpWorld=guard.world,fpActor=guard.actor}
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


-- Temporary FP arm hiding: native owner signature, per-mesh default visibility,
-- original hidden meshes, TP/ship/shutdown restoration, and no pose/link setters.
do
 local baseCount,baseMesh,baseVisible=U.num_meshes,U.mesh,S.Mesh.visibility
 local baseSetter=U.set_mesh_visibility
 local visibilityWrites=0;local visibilityFail=nil
 U.num_meshes=function(u)recycled();return u.meshes and #u.meshes or baseCount(u)end
 U.mesh=function(u,i)recycled();return u.meshes and {owner=u,index=i} or baseMesh(u,i)end
 -- Lua's and/or is unsafe for false visibility; use an explicit branch.
 S.Mesh.visibility=function(m)if m.owner then recycled();return m.owner.meshes[m.index]end;return baseVisible(m)end
 local allowed={}
 U.set_mesh_visibility=function(u,i,value,context)
  check(allowed[u] and context=='default' and type(value)=='boolean','visibility touched other object/context')
  visibilityWrites=visibilityWrites+1;u.meshes[i]=value
  if visibilityFail==visibilityWrites then visibilityFail=nil;error('injected_after_visibility_set')end
 end
 local function hide_start()
  guard=fp_start();runtime:stop()
  local right=make(fixture.model);right.resource='1111111111111111'
  local other=make(fixture.model);local torso=make(fixture.model);torso.resource='2222222222222222'
  local preview=make(fixture.model)
  model.meshes={true,false,true};right.meshes={true,true};other.meshes={true};torso.meshes={true};preview.meshes={true}
  allowed={[model]=true,[right]=true}
  groups[1][#groups[1]+1]=right;groups[1][#groups[1]+1]=other;groups[1][#groups[1]+1]=torso;groups[3]={preview}
  refresh(model);refresh(right);refresh(other);refresh(torso);refresh(preview)
  local otherRefresh=S.World.update_unit
  S.World.update_unit=function(w,u)
   otherRefresh(w,u)
   if u==other then for _,m in ipairs(u.cache)do m[10]=m[10]+50 end end
  end
  for _,m in ipairs(other.cache)do m[10]=m[10]+50 end
  local p=copy(integratedProfile)
  p.models[right.resource]=copy(p.models[model.resource]);p.models[right.resource].resource=right.resource
  p.models[torso.resource]=copy(p.models[model.resource]);p.models[torso.resource].resource=torso.resource
  p.firstPersonArmHide={enabled=true,modelResources={[model.resource]='LeftArm',[right.resource]='RightArm'},matchTolerance=.01}
  local n=6
  for _,side in ipairs({'l_','r_'})do for _,joint in ipairs({'shoulder','elbow','hand'})do
   n=n+1;local name=side..joint;fp.names[hash_name(name)]=n
   fp.cache[n]=copy(model.cache[model.names[hash_name(name)]])
  end end
  runtime=module.new(S,p,function(line)logs[#logs+1]=line end,arm_math,fpContext)
  return right,other,torso,preview,otherRefresh
 end
 local function run_case(fn)
  local right,other,torso,preview,restoreUpdate=hide_start()
  local input=copy(A.locals);local poses=writes
  fn(right,other,torso,preview)
  all_same(A.locals,input,'FP hide changed native pose inputs')
  check(writes==poses,'FP hide invoked an attachment/bone setter')
  runtime:stop();S.World.update_unit=restoreUpdate;groups[3]=nil
 end
 -- No TP apply in the visibility cases: start directly in confirmed FP, so only
 -- visibility is allowed to change. Full TP write/reentry was tested above.
 run_case(function(right,other,torso,preview)
  viewCamera=transform(0,10,20,30);local poses=writes
  step(runtime,'render',8510,851)
  check(model.meshes[1]==false and model.meshes[2]==false and model.meshes[3]==false,'left arm not hidden per mesh')
  check(right.meshes[1]==false and right.meshes[2]==false,'right arm not hidden')
  check(other.meshes[1] and torso.meshes[1] and preview.meshes[1] and gun.visible,'other player/body/preview/weapon hidden')
  model.meshes[1]=true;step(runtime,'render',8511,851.1)
  check(model.meshes[1]==false,'engine re-show was not suppressed')
  viewCamera=nil;step(runtime,'render',8512,851.2)
  check(model.meshes[1]==false,'unknown view re-showed a known FP arm')
  viewCamera=transform(0,10,18,30);step(runtime,'update',8513,851.3)
  check(model.meshes[1] and not model.meshes[2] and model.meshes[3] and right.meshes[1],'TP original mesh visibility not restored')
  check(next(runtime.fpHidden)==nil and writes==poses,'TP exit left visibility transaction or pose writes')
 end)
 run_case(function(right)
  local nativeInput=copy(A.locals)
  local sourceHands={}
  for _,u in ipairs({model,right})do
   sourceHands[u]={}
   for _,node in ipairs(integratedProfile.models[model.resource].observeNodes)do
    if node.driver=='l_hand' or node.driver=='r_hand' then sourceHands[u][node.index+1]=copy(u.cache[node.index+1]) end
   end
  end
  local update=S.World.update_unit
  S.World.update_unit=function(w,u)
   update(w,u)
   for n,pose in pairs(sourceHands[u] or {})do u.cache[n]=copy(pose)end
  end
  A.locals[1][10]=A.locals[1][10]+2;calculate(A)
  for _,side in ipairs({'l_','r_'})do for _,joint in ipairs({'shoulder','elbow','hand'})do
   local name=side..joint;fp.cache[fp.names[hash_name(name)]]=copy(A.cache[A.names[hash_name(name)]])
  end end
  viewCamera=transform(0,12,20,30);fp.cache[51]=copy(viewCamera)
  step(runtime,'render',8515,851.5)
  check(model.meshes[1]==false and right.meshes[1]==false,'frozen Source hands blocked native FP owner hide')
  for u,poses in pairs(sourceHands)do for n,pose in pairs(poses)do check(near(u.cache[n],pose),'visibility workaround rewrote frozen Source world')end end
  S.World.update_unit=update;A.locals=nativeInput;calculate(A)
 end)
 run_case(function(right)
  viewCamera=transform(0,10,20,30);step(runtime,'render',8520,852)
  runtime:stop()
  check(model.meshes[1] and not model.meshes[2] and model.meshes[3] and right.meshes[1],'shutdown did not restore original per-mesh visibility')
 end)
 run_case(function(right)
  viewCamera=transform(0,10,20,30);step(runtime,'render',8530,853)
  fpContext.inMission=function()return false end;step(runtime,'render',8531,853.1)
  check(model.meshes[1] and not model.meshes[2] and right.meshes[1],'ship transition did not restore')
  local before=visibilityWrites;step(runtime,'render',8532,853.2)
  check(visibilityWrites==before,'ship performed new hides')
 end)
 run_case(function(right)
  local duplicate=make(fixture.model);duplicate.meshes={true};refresh(duplicate)
  groups[1][#groups[1]+1]=duplicate
  viewCamera=transform(0,10,20,30);step(runtime,'render',8535,853.5)
  check(model.meshes[1]==true and duplicate.meshes[1]==true,'ambiguous same-resource receiver was hidden')
 end)
 run_case(function(right)
  viewCamera=transform(0,10,20,30);visibilityFail=visibilityWrites+1
  step(runtime,'render',8540,854)
  check(not runtime.disabled and runtime.stats.fpVisibilityErrors>0,'partial visibility error disabled runtime')
  viewCamera=transform(0,10,18,30);visibilityFail=visibilityWrites+1;step(runtime,'update',8541,854.1)
  check(not runtime.disabled and next(runtime.fpHidden)~=nil,'failed restore lost retry ledger')
  step(runtime,'update',8542,854.2)
  check(model.meshes[1] and not model.meshes[2] and model.meshes[3] and right.meshes[1] and next(runtime.fpHidden)==nil,'restore did not retry safely')
 end)
 run_case(function(right)
  viewCamera=transform(0,10,20,30);model.meshes[2]='unknown'
  step(runtime,'render',8550,855)
  check(model.meshes[1]==true and model.meshes[3]==true and runtime.fpHidden[model]==nil,'unknown getter permitted partial hide')
  model.meshes[2]=false;step(runtime,'render',8551,855.1)
  check(model.meshes[1]==false,'visibility getter recovery did not retry')
  model.alive=false;local before=visibilityWrites;viewCamera=transform(0,10,18,30);step(runtime,'update',8552,855.2)
  check(runtime.fpHidden[model]==nil and visibilityWrites==before+2,'destroyed model was written or other arm not restored')
 end)
 U.num_meshes=baseCount;U.mesh=baseMesh;S.Mesh.visibility=baseVisible;U.set_mesh_visibility=baseSetter
 fixedFP.temporaryArmHide=true;fixedFP.perMeshOriginalVisibilityRestored=true
 fixedFP.ambiguousReceiverFailsClosed=true;fixedFP.otherPlayerPreviewTorsoWeaponUnaffected=true;fixedFP.visibilityFailuresRetry=true
 fixedFP.shutdownAndShipRestore=true;fixedFP.destroyedUnitNotWritten=true
 fixedFP.frozenSourceHandsDoNotBlockHide=true;fixedFP.fpBonePositionRewriteDeferred=true
end

return {status='PASS_PENDING_GAME_TEST',checks=checks,priorChecks=checksBeforeFP,firstPerson=fixedFP,gameTested=false,logs=logs}
