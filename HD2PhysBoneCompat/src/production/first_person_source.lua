-- Independent FP Source-output domain. Never runs TP IK on the native FP63 graph.
local M={VERSION='1.0.1'}
local function cp(t)local r={};for k,v in pairs(t)do r[k]=type(v)=='table'and cp(v)or v end;return r end
local function delta(a,b)local d=0;for i=1,12 do d=math.max(d,math.abs(a[i]-b[i]))end;return d end
local function dist(a,b)local d=0;for i=10,12 do d=d+(a[i]-b[i])^2 end;return math.sqrt(d)end
function M.new(S,p,Math,guard,log,context)
 local U,W,A,X=S.Unit,S.World,S.Application,S.Matrix4x4
 context=context or {}
 assert(p.avatar.nativeCount==63 and p.avatar.count>63 and p.side=='both' and p.entry.index==63 and p.entry.parent==7,'fp_source_contract')
 local self={pending=nil,allowed=nil,receiver=nil,proof=0,lastLog={},lastWanted=nil,stats={writes=0,restores=0,receiverMatches=0,receiverMisses=0,failures=0,nativeWrites=0,modelPoseWrites=0,nativeInputRefreshes=0,receiverInputRefreshes=0,receiverRestoreRefreshes=0,meleeProbeRefreshes=0,sourceWorldReadbackFailures=0,nativeWorldChangedDuringOutput=0}}
 local function emit(r,force)
  r.event=r.event or 'fp_source_output';r.fpProduction=true;r.moduleVersion=M.VERSION;r.nativeWrites=0;r.modelPoseWrites=0;r.gpuPaletteObserved=false
  local now=r.time or 0
  -- A native capture must not consume the receiver/visibility proof's log slot.
  local slot=r.event
  if r.event=='fp_source_final_check'then slot=slot..':'..tostring(r.stage)end
  if r.event=='fp_source_unavailable'then slot=slot..':'..tostring(r.detail and r.detail.stage or r.reason)end
  local last=self.lastLog[slot]
  if force or not last or now<last or now-last>=(p.logSeconds or 1)then self.lastLog[slot]=now;log(r)end
 end
 local function rid(u)return S.IdString64.to_hex(U.resource_name(u)):lower():gsub('^0x','')end
 local function read(u,i,world)
  local r={X.to_elements((world and U.world_pose or U.local_pose)(u,i+1))};assert(#r==12,'fp_matrix_size')
  for _,v in ipairs(r)do assert(type(v)=='number'and v==v and math.abs(v)<1e10,'fp_matrix_nonfinite')end
  return r
 end
 local function pose(m)return {p={m[10],m[11],m[12]},q=Math.quaternion(m)}end
 local function elements(t)
  local r={};for _,axis in ipairs({{1,0,0},{0,1,0},{0,0,1}})do for _,v in ipairs(Math.rotate(t.q,axis))do r[#r+1]=v end end
  for _,v in ipairs(t.p)do r[#r+1]=v end;return r
 end
 local static={}
 for _,n in ipairs(p.sourceNodes)do
  static[n.index]={descriptor=n,bind=pose(n.bindLocal),registration=n.native and Math.relative(pose(n.native.bindWorld),pose(n.rotationReferenceWorld or n.bindWorld))or nil}
 end
 local function node(u,n,parents)
  local id=A.string_to_id32(n.name);assert(U.has_node(u,id)and U.node(u,A.string_to_id32(n.name))==n.index+1,'fp_named_index:'..n.name)
  if parents and n.parent~=nil then assert(U.scene_graph_parent(u,n.index+1)==n.parent+1,'fp_source_parent:'..n.name)end
 end
 local identityProof={}
 local function identity(a)
  local now=A.time_since_launch and A.time_since_launch()or 0
  local old=identityProof[a.unit]
  assert(U.alive(a.unit)and rid(a.unit)==p.avatar.resource and U.num_scene_graph_items(a.unit)==p.avatar.count,'fp_avatar_identity')
  if old and old.count==p.avatar.count and now>=old.time and now-old.time<.5 then
   node(a.unit,p.entry,true)
   for _,arm in pairs(p.arms)do
    for _,index in ipairs({arm.shoulder,arm.elbow,arm.hand})do node(a.unit,static[index].descriptor,true)end
    for _,twist in ipairs(arm.twistNodes)do node(a.unit,static[twist.index].descriptor,true)end
   end
   return
  end
  assert(U.alive(a.unit)and rid(a.unit)==p.avatar.resource and U.num_scene_graph_items(a.unit)==p.avatar.count,'fp_avatar_identity')
  for _,n in ipairs(p.avatar.nativeGraph)do if n.name then node(a.unit,n,false)end end
  for _,n in ipairs(p.avatar.outputs)do assert(n.index>=63,'fp_native_writer_forbidden');node(a.unit,n,true)end
  identityProof[a.unit]={count=p.avatar.count,time=now}
 end
 local inventory={};local inventorySets={}
 local function units(world)
  if not inventory[world]then inventory[world]=W.units(world)or{};local set={};for _,u in ipairs(inventory[world])do set[u]=true end;inventorySets[world]=set;self.stats.worldInventorySnapshots=(self.stats.worldInventorySnapshots or 0)+1 end
  return inventory[world]
 end
 local function present(a)
  if not U.alive(a.unit)then return false end
  units(a.world);return inventorySets[a.world][a.unit]==true
 end
 local modelProof={}
 local function source_model(a)
  local found={};local counts={};local selected={};local sideCounts={r=0,l=0}
  for _,spec in ipairs(p.models)do
   counts[spec.resource]=0
   local candidates
   local old=self.receivers and self.receivers[spec.resource]
   if old and U.alive(old)and rid(old)==spec.resource and type(W.units_by_resource)=='function'then
    local ok,value=pcall(function()return W.units_by_resource(a.world,U.resource_name(old))end)
    if ok and type(value)=='table'then
     if #value>0 or not present({unit=old,world=a.world})then candidates=value;self.stats.scopedReceiverQueries=(self.stats.scopedReceiverQueries or 0)+1
     else self.stats.scopedQueryFallbacks=(self.stats.scopedQueryFallbacks or 0)+1 end
    else self.stats.scopedQueryFallbacks=(self.stats.scopedQueryFallbacks or 0)+1 end
   end
   if not candidates then candidates=units(a.world);self.stats.fullReceiverInventories=(self.stats.fullReceiverInventories or 0)+1 end
   for _,u in ipairs(candidates)do
    if U.alive(u)and rid(u)==spec.resource and U.num_scene_graph_items(u)==spec.count then
     local ok=pcall(function()
      for _,n in ipairs(spec.nativeMatches)do node(u,n,false)end
      local now=A.time_since_launch and A.time_since_launch()or 0;local previous=modelProof[u]
      if not previous or previous.resource~=spec.resource or now<previous.time or now-previous.time>=.5 then
       for _,n in ipairs(p.sourceNodes)do node(u,{name=n.name,index=n.modelIndices[spec.resource]},false)end
       modelProof[u]={resource=spec.resource,time=now}
      end
      W.update_unit(a.world,u);self.stats.receiverInputRefreshes=self.stats.receiverInputRefreshes+1
      for _,n in ipairs(spec.nativeMatches)do assert(delta(read(u,n.index,true),read(a.unit,n.fpIndex,true))<=(p.modelMatchTolerance or .01),'fp_model_native_mismatch')end
     end)
     if ok then counts[spec.resource]=counts[spec.resource]+1;found[spec.resource]=u end
    end
   end
   if counts[spec.resource]>1 then return nil,counts[spec.resource] end
   if counts[spec.resource]==1 then
    local side=spec.sourceRole or spec.nativeMatches[1].name:sub(1,1)
    assert(side=='r' or side=='l','fp_receiver_side')
    sideCounts[side]=sideCounts[side]+1;selected[side]=spec
   end
  end
  if sideCounts.r~=1 or sideCounts.l~=1 then return nil,math.max(sideCounts.r,sideCounts.l) end
  self.receivers={ [selected.r.resource]=found[selected.r.resource],[selected.l.resource]=found[selected.l.resource] }
  self.activeModels={selected.r,selected.l}
  return found[selected.r.resource],1
 end
 function self:membership()
  local a=guard.actor();if not a then return nil end
  local snapshot={};local main=context.world and context.world()or nil
  for _,w in ipairs(main and main~=a.world and {a.world,main}or {a.world})do
   units(w);snapshot[w]={units=inventory[w],set=inventorySets[w],label=1}
  end
  return snapshot
 end
 function self:visibilityModels(profile)
  local rows={}
  for _,spec in ipairs(self.activeModels or {})do local u=self.receivers and self.receivers[spec.resource]
   if u and U.alive(u)then rows[#rows+1]={unit=u,world=self.receiverWorld,spec=profile.models[spec.resource],id=spec.resource,worldLabel='verified_fp_world'}end
  end
  return rows
 end
 function self:restore(reason)
  local r=self.pending;self.pending=nil;self.allowed=nil
  if not r then return true end
  if not present(r.actor)then return false end
  local ok,err=pcall(function()
   identity(r.actor)
   for _,n in ipairs(r.rows)do
    assert(n.index>=63 and n.index<p.avatar.count,'fp_native_restore_forbidden')
    if delta(read(r.actor.unit,n.index,false),n.written)<=1e-5 then
     U.set_local_pose(r.actor.unit,n.index+1,X.from_elements(unpack(n.before)));self.stats.restores=self.stats.restores+1
    end
   end
   W.update_unit(r.actor.world,r.actor.unit)
   if r.model and U.alive(r.model)and present({unit=r.model,world=r.actor.world})then
    assert(rid(r.model)==r.modelSpec.resource and U.num_scene_graph_items(r.model)==r.modelSpec.count,'fp_restore_model_identity')
    for _,n in ipairs(p.sourceNodes)do if n.driver=='r_hand'or n.driver=='l_hand'then node(r.model,{name=n.name,index=n.modelIndices[r.modelSpec.resource]},false)end end
    W.update_unit(r.actor.world,r.model);self.stats.receiverRestoreRefreshes=self.stats.receiverRestoreRefreshes+1
   end
   for rid,u in pairs(r.receivers or {})do if u~=r.model and U.alive(u)and present({unit=u,world=r.actor.world})then W.update_unit(r.actor.world,u);self.stats.receiverRestoreRefreshes=self.stats.receiverRestoreRefreshes+1 end end
   if self.previousOutput then self.previousOutput.restored=true end
  end)
  if not ok then self.stats.failures=self.stats.failures+1;emit({event='fp_source_restore_failed',reason=tostring(err),time=r.time},true)end
  return ok
 end
 function self:check(stage,frame,now,strict)
  if stage=='post_physics'then inventory={};inventorySets={} end
  local pending=self.pending
  if not pending then return false end
  self.stats.finalChecks=(self.stats.finalChecks or 0)+1
  if stage=='post_physics'then self.stats.postPhysicsChecks=(self.stats.postPhysicsChecks or 0)+1 end
  if stage=='post_presentation'then self.stats.postPresentationChecks=(self.stats.postPresentationChecks or 0)+1 end
  local ok,err=pcall(function()
   local mission=context.inMission and context.inMission()==true
   local state=guard.sample();local current=state==true and guard.actor()or nil
   assert(mission and current and current.unit==pending.actor.unit and current.world==pending.actor.world,'fp_final_view_or_actor_changed')
   assert(present(pending.actor)and present({unit=pending.model,world=pending.actor.world}),'fp_final_membership')
   identity(pending.actor)
   assert(rid(pending.model)==pending.modelSpec.resource and U.num_scene_graph_items(pending.model)==pending.modelSpec.count,'fp_final_model_identity')
   local full=not self.finalProbeTime or not self.finalProbeTime[stage]or now-self.finalProbeTime[stage]>=2;self.finalProbeTime=self.finalProbeTime or {};if full then self.finalProbeTime[stage]=now end
   local outputRows={};local maxReceiver,maxWrittenWorld,maxLocal=0,0,0
   for _,row in ipairs(pending.rows)do
    maxLocal=math.max(maxLocal,delta(read(pending.actor.unit,row.index,false),row.written))
   end
   for _,n in ipairs(p.sourceNodes)do
    local core=n.native~=nil
    if stage=='post_presentation'and not full then core=(n.driver and (n.driver=='r_hand'or n.driver=='l_hand'or n.driver=='r_elbow'or n.driver=='l_elbow'))or n.name:find('zhandtwist_',1,true)~=nil end
    if full or core then
    node(pending.model,{name=n.name,index=n.modelIndices[pending.modelSpec.resource]},false)
    local currentSource=read(pending.actor.unit,n.index,true);local actualModel=read(pending.model,n.modelIndices[pending.modelSpec.resource],true)
    local receiverError=delta(currentSource,actualModel);local writtenError=delta(currentSource,pending.expected[n.index])
    for rid,u in pairs(pending.receivers or {})do maxReceiver=math.max(maxReceiver,delta(read(u,n.modelIndices[rid],true),currentSource))end
    maxReceiver=math.max(maxReceiver,receiverError);maxWrittenWorld=math.max(maxWrittenWorld,writtenError)
    if full then outputRows[#outputRows+1]={index=n.index,modelIndex=n.modelIndices[pending.modelSpec.resource],name=n.name,currentSource=currentSource,actualModel=actualModel,writtenWorld=pending.expected[n.index],receiverError=receiverError,writtenWorldError=writtenError};end
    end
   end
   local skin={}
   for _,n in ipairs(full and (p.weightedSkinNodes or {})or {})do
    local owner=pending.receivers[n.resource]
    node(owner,n,false)
    skin[#skin+1]={index=n.index,name=n.name,parent=n.parent,kind=n.kind,resource=n.resource,world=read(owner,n.index,true),localPose=read(owner,n.index,false),directSourceOutput=n.directSourceOutput}
   end
   local meshes={}
   if type(U.num_meshes)=='function'and type(U.mesh)=='function'and S.Mesh and type(S.Mesh.visibility)=='function'then
    local count=U.num_meshes(pending.model);assert(count>=1 and count<=128,'fp_final_mesh_count')
    for i=1,count do local visibility=S.Mesh.visibility(U.mesh(pending.model,i));assert(type(visibility)=='boolean','fp_final_mesh_visibility');meshes[#meshes+1]={index=i,defaultVisible=visibility}end
   end
   local camera=read(pending.actor.unit,50,true)
   local accepted=not strict or (pending.frame==frame and maxReceiver<=(p.receiverTolerance or .002)and maxWrittenWorld<.0002 and maxLocal<1e-5)
   if full then emit({event='fp_source_final_check',stage=stage,frame=frame,writeFrame=pending.frame,time=now,strict=strict,accepted=accepted,held=true,maxReceiverError=maxReceiver,maxWrittenWorldError=maxWrittenWorld,maxOwnedLocalError=maxLocal,outputs=outputRows,weightedSkin=skin,meshes=meshes,cameraBoneWorld=camera,actualCameraProjectionObserved=false,postPhysics=stage=='post_physics',gpuPaletteObserved=false,permitBeforeCheck=self.allowed~=nil});end
   if strict then assert(accepted,'fp_final_output_changed')end
  end)
  if not ok then
   self.stats.failures=self.stats.failures+1;self.proof=0;self.receiver=nil;self.motionSeen=false;self.motionAnchor=nil
   local restoreOK=self:restore('final_check_failed')
   emit({event='fp_source_final_check_failed',stage=stage,frame=frame,time=now,reason=tostring(err),restoreAttemptCompleted=restoreOK==true,restored=restoreOK==true},true)
   return false
  end
  return true
 end
 function self:permit(u,world,frame)
  return self.allowed and self.allowed.units and self.allowed.units[u]==true and self.allowed.world==world and self.allowed.frame==frame and U.alive(u)==true or false
 end
 function self:tick(phase,frame,now)
  inventory={};inventorySets={};if guard.reset then guard.reset()end
  if phase~='render' then
   local mok,mission=pcall(function()return context.inMission()end)
   local state,detail=guard.sample()
   local actor=state==true and guard.actor()or nil
   if not mok or mission~=true or state~=true or (self.pending and (not actor or actor.unit~=self.pending.actor.unit or actor.world~=self.pending.actor.world))then
    local hadPending=self.pending~=nil;local restoreOK=self:restore('update_view_scene_or_actor_change')
    if hadPending then emit({event='fp_source_hold_ended',frame=frame,time=now,stage='update_gate',mission=mok and mission==true,view=detail,restoreAttemptCompleted=restoreOK==true,reason='view_scene_or_actor_changed_or_unverified'})end
    self.proof=0;self.receiver=nil;self.motionSeen=false;self.motionAnchor=nil;return
   end
   if not self.lastHeldProbe or now-self.lastHeldProbe>=2 then self.lastHeldProbe=now;self:check('update_held_pre_engine',frame,now,false)end
   return
  end
  local mission=false
  if type(context.inMission)=='function' then local ok,v=pcall(context.inMission);mission=ok and v==true end
  if not mission then self:restore('scene');self.previousOutput=nil;self.proof=0;self.receiver=nil;self.lastWanted=nil;self.motionSeen=false;return end
  local diagnostic=not self.lastReceiverProbe or now<self.lastReceiverProbe or now-self.lastReceiverProbe>=(p.diagnosticSeconds or 5)
  local previous=diagnostic and self.previousOutput or nil;local nextCheck
  if previous and present(previous.actor)and U.alive(previous.model)and present({unit=previous.model,world=previous.actor.world})then
   local ok,value=pcall(function()
    identity(previous.actor);assert(rid(previous.model)==previous.modelSpec.resource and U.num_scene_graph_items(previous.model)==previous.modelSpec.count,'fp_next_render_model_identity')
    local maximum=0;local samples={}
    for _,n in ipairs(p.sourceNodes)do
     if n.driver=='r_shoulder'or n.driver=='r_elbow'or n.driver=='r_hand'then
      node(previous.model,{name=n.name,index=n.modelIndices[previous.modelSpec.resource]},false)
      local source=read(previous.actor.unit,n.index,true);local model=read(previous.model,n.modelIndices[previous.modelSpec.resource],true)
      maximum=math.max(maximum,delta(model,source));samples[#samples+1]={name=n.name,fpCurrent=source,modelCurrent=model,previousWritten=previous.samples[n.index]}
     end
    end
    emit({event='fp_source_next_render',frame=frame,time=now,previousFrame=previous.frame,stage='next_render_before_restore_held_output',outputRestoredSinceWrite=previous.restored==true,maxCurrentReceiverError=maximum,samples=samples,previousPoseStillDrivenNotAssumed=true})
    return maximum
   end);nextCheck=ok and value or nil
  end
  self.previousOutput=nil
  local state,detail=guard.sample()
  if state~=true then self:restore('before_render_view_exit');self.proof=0;self.receiver=nil;self.lastWanted=nil;self.motionSeen=false;return end
  local a=guard.actor();if not a or not present(a)then self:restore('actor_lost');return end
  local previousTransaction=self.pending
  if previousTransaction and (previousTransaction.actor.unit~=a.unit or previousTransaction.actor.world~=a.world)then self:restore('actor_changed');previousTransaction=nil end
  self.allowed=nil

  self.failureDetail=nil
  local ok,err=pcall(function()
   local actualCount=U.num_scene_graph_items(a.unit)
   if actualCount==63 then
    assert(rid(a.unit)==p.avatar.resource,'fp_capture_native_resource')
    for _,n in ipairs(p.avatar.nativeGraph)do if n.name then node(a.unit,n,false)end end
   else identity(a)end
   local recoilBefore=read(a.unit,p.entry.parent,true)
   -- Flush only the verified FP producer's native cache BEFORE sampling inputs.
   -- This is not the Source driver: independent Source output/readback proofs below remain mandatory.
   W.update_unit(a.world,a.unit);self.stats.nativeInputRefreshes=self.stats.nativeInputRefreshes+1
   local refreshedState=guard.sample(true);local refreshedActor=guard.actor()
   assert(refreshedState==true and refreshedActor and refreshedActor.unit==a.unit and refreshedActor.world==a.world,'fp_view_changed_after_native_refresh')
   local recoilAfter=read(a.unit,p.entry.parent,true)
   local nativeRefresh={stage='native_cache_flushed_before_pose_sampling',maxRecoilWorldChange=delta(recoilBefore,recoilAfter),recoilBefore=recoilBefore,recoilAfter=recoilAfter}
   if p.diagnosticsEnabled and (not self.lastNativeProbe or now-self.lastNativeProbe>=2) then
    self.lastNativeProbe=now;local nativePoses={}
    for _,n in ipairs(p.avatar.nativeGraph)do
     if n.inAnimationChannel and n.name then nativePoses[#nativePoses+1]={name=n.name,index=n.index,world=read(a.unit,n.index,true),localPose=read(a.unit,n.index,false)}end
    end
    local worlds={a.world};if type(context.world)=='function' then local main=context.world();if main and main~=a.world then worlds[#worlds+1]=main end end
    local items={}
    for _,world in ipairs(worlds)do
     for _,u in ipairs(W.units(world)or{})do
      if U.alive(u)then local spec=p.meleeProbeSpecs and p.meleeProbeSpecs[rid(u)]
       if spec and U.num_scene_graph_items(u)==spec.count and #items<8 then
        local before={};for _,i in ipairs(spec.rootIndices)do before[i]=read(u,i,true)end
        W.update_unit(world,u);self.stats.meleeProbeRefreshes=self.stats.meleeProbeRefreshes+1
        local roots={};for _,i in ipairs(spec.rootIndices)do roots[#roots+1]={index=i,worldBeforeRefresh=before[i],world=read(u,i,true),localPose=read(u,i,false),parent=U.scene_graph_parent(u,i+1)}end
        local leftMarker;if spec.leftMarker then node(u,spec.leftMarker,false);leftMarker={name=spec.leftMarker.name,index=spec.leftMarker.index,world=read(u,spec.leftMarker.index,true),localPose=read(u,spec.leftMarker.index,false)}end
        items[#items+1]={resource=spec.resource,world=tostring(world),fpWorld=world==a.world,roots=roots,leftMarker=leftMarker,cacheRefreshedBeforeCapture=true,heldBySelectedFpActorNotProven=true}
       end
      end
     end
    end
    emit({event='fp_native_and_melee_capture',frame=frame,time=now,fpResource=p.avatar.resource,fpCount=actualCount,nativeCount=63,nativeChannelCount=47,nativePoses=nativePoses,meleeItems=items,fpWorld=tostring(a.world),readOnly=true,nativeRefresh=nativeRefresh,captureStage='after_native_and_item_cache_refresh'},true)
   end
   if actualCount==63 then self.proof=0;self.receiver=nil;self.motionSeen=false;emit({event='fp_source_graph_not_installed',frame=frame,time=now,nativeCaptureAvailable=true,actualCount=63,expectedCount=p.avatar.count});return end
   local model,matches=source_model(a)
   if not model then self:restore('no_unique_receiver');self.proof=0;self.receiver=nil;self.motionSeen=false;emit({event='fp_source_no_unique_receiver',frame=frame,time=now,candidates=matches});return end
   local shoulder
   for _,n in ipairs(p.sourceNodes)do if n.driver=='r_shoulder'then shoulder=n.native end end
   assert(shoulder,'fp_shoulder_driver_missing')
   local nativeWorldBefore={[p.entry.parent]=read(a.unit,p.entry.parent,true)}
   for _,n in ipairs(p.sourceNodes)do if n.native then nativeWorldBefore[n.native.index]=read(a.unit,n.native.index,true)end end
   local entryWorld=pose(nativeWorldBefore[shoulder.index]);local recoil=pose(nativeWorldBefore[p.entry.parent]);local entryLocal=Math.relative(recoil,entryWorld)
   local candidates={[p.entry.index]=entryWorld};local rows={{index=p.entry.index,before=read(a.unit,p.entry.index,false),written=elements(entryLocal)}}
   local nativeBefore={};for _,n in ipairs(p.avatar.nativeGraph)do nativeBefore[n.index]=read(a.unit,n.index,false)end
   for _,n in ipairs(p.sourceNodes)do
    local parent=candidates[n.parent];assert(parent,'fp_source_parent_order');local localPose=cp(static[n.index].bind)
    if n.native then
     node(a.unit,n.native,false)
     local registration=static[n.index].registration
     local rotation=Math.compose(pose(nativeWorldBefore[n.native.index]),registration)
     localPose.q=Math.relative(parent,rotation).q
    end
    candidates[n.index]=Math.compose(parent,localPose)
    rows[#rows+1]={index=n.index,before=read(a.unit,n.index,false),written=elements(localPose)}
   end

   local byIndex={};for _,n in ipairs(p.sourceNodes)do byIndex[n.index]=n end
   local function vsub(x,y)return {x[1]-y[1],x[2]-y[2],x[3]-y[3]}end
   local function length(v)return math.sqrt(v[1]^2+v[2]^2+v[3]^2)end
   local function normalized(v)local l=length(v);assert(l>1e-8,'fp_contact_zero_direction');return {v[1]/l,v[2]/l,v[3]/l}end
   local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
   local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
   local function product(a,b)return Math.compose({p={0,0,0},q=a},{p={0,0,0},q=b}).q end
   local function swing(a,b)
    a=normalized(a);b=normalized(b);local d=dot(a,b);local axis=cross(a,b)
    if d<-.999999 then local ref=math.abs(a[1])<.8 and {1,0,0}or {0,1,0};axis=normalized(cross(a,ref));return {axis[1],axis[2],axis[3],0}end
    local q={axis[1],axis[2],axis[3],1+d};local l=math.sqrt(q[1]^2+q[2]^2+q[3]^2+q[4]^2);return {q[1]/l,q[2]/l,q[3]/l,q[4]/l}
   end
   local overrides={};local contacts={}
   for side,arm in pairs(p.arms)do
    local shoulder,elbow,hand=candidates[arm.shoulder],candidates[arm.elbow],candidates[arm.hand]
    local x,y=nativeWorldBefore[arm.nativeContactIndices[1]],nativeWorldBefore[arm.nativeContactIndices[2]]
    assert(x and y,'fp_native_contact_missing')
    local target={(x[10]+y[10])*.5,(x[11]+y[11])*.5,(x[12]+y[12])*.5};local offset=Math.rotate(hand.q,arm.sourceContactLocal)
    local wrist={target[1]-offset[1],target[2]-offset[2],target[3]-offset[3]};local start=pose(nativeWorldBefore[byIndex[arm.shoulder].native.index]).p;local d=length(vsub(wrist,start));local direction=normalized(vsub(wrist,start))
    local l1,l2=arm.upperMetres,arm.forearmMetres;local maximum=l1+l2-.001;local minimum=math.abs(l1-l2)+.001;local reach=math.max(minimum,math.min(maximum,d));local shift=d-reach
    assert(math.abs(shift)<=arm.maxShoulderShift,'fp_contact_shoulder_shift_limit')
    for k=1,3 do start[k]=start[k]+direction[k]*shift end
    local ex=pose(nativeWorldBefore[byIndex[arm.elbow].native.index]).p;local pole=vsub(ex,start);local projection=dot(pole,direction)
    for k=1,3 do pole[k]=pole[k]-projection*direction[k]end
    if length(pole)<1e-5 then pole=Math.rotate(shoulder.q,{0,0,1});projection=dot(pole,direction);for k=1,3 do pole[k]=pole[k]-projection*direction[k]end end
    pole=normalized(pole);local along=(l1*l1-l2*l2+reach*reach)/(2*reach);local height=math.sqrt(math.max(0,l1*l1-along*along));local mid={}
    for k=1,3 do mid[k]=start[k]+direction[k]*along+pole[k]*height end
    local upperOffset=pose(byIndex[arm.elbow].bindLocal).p;local lowerOffset=pose(byIndex[arm.hand].bindLocal).p
    overrides[arm.shoulder]={p=start,q=product(swing(Math.rotate(shoulder.q,upperOffset),vsub(mid,start)),shoulder.q)}
    local forearmRef=product(hand.q,pose(arm.handToForearmRotation).q)
    local forearmQ=product(swing(Math.rotate(forearmRef,lowerOffset),vsub(wrist,mid)),forearmRef)
    overrides[arm.elbow]={p=mid,q=forearmQ}
    for _,twist in ipairs(arm.twistNodes)do overrides[twist.index]={q=product(hand.q,pose(twist.handToTwistRotation).q),rotationOnly=true}end
    overrides[arm.hand]={p=wrist,q=hand.q}
    contacts[side]={target=target,wrist=wrist,shoulderShift=shift,sourceContactLocal=arm.sourceContactLocal,wristContinuity='palm_registered_forearm_and_hand_relative_twist',kind='native_index_middle_knuckle_proxy_not_mesh_surface'}
   end
   rows={{index=p.entry.index,before=read(a.unit,p.entry.index,false),written=elements(entryLocal)}}
   for _,n in ipairs(p.sourceNodes)do
    local parent=candidates[n.parent];local old=candidates[n.index];local localPose=cp(static[n.index].bind);local desired=overrides[n.index]
    localPose.q=Math.relative(parent,{p=old.p,q=desired and desired.q or old.q}).q
    if desired and (n.index==p.arms.r.shoulder or n.index==p.arms.l.shoulder)then localPose.p=Math.relative(parent,desired).p end
    candidates[n.index]=Math.compose(parent,localPose)
    if desired and desired.p then assert(length(vsub(candidates[n.index].p,desired.p))<.0002,'fp_fixed_length_contact_fk')end
    rows[#rows+1]={index=n.index,before=read(a.unit,n.index,false),written=elements(localPose)}
   end
   local modelBefore={};if diagnostic then for _,n in ipairs(p.sourceNodes)do modelBefore[n.index]=read(model,n.modelIndices[self.activeModels[1].resource],true)end end

   if previousTransaction then
    local oldRows={};for _,row in ipairs(previousTransaction.rows)do oldRows[row.index]=row end
    for _,row in ipairs(rows)do
     local old=oldRows[row.index]
     if old and delta(row.before,old.written)<=1e-5 then row.before=cp(old.before)end
    end
    self.stats.heldTransactionUpdates=(self.stats.heldTransactionUpdates or 0)+1
   end
   self.pending={actor=a,model=model,modelSpec=self.activeModels[1],receivers=self.receivers,rows=rows,time=now,frame=frame,expected={}}
   for i,candidate in pairs(candidates)do self.pending.expected[i]=elements(candidate)end
   for _,n in ipairs(rows)do assert(n.index>=63,'fp_native_write_attempt');U.set_local_pose(a.unit,n.index+1,X.from_elements(unpack(n.written)));self.stats.writes=self.stats.writes+1 end
   W.update_unit(a.world,a.unit);for _,u in pairs(self.receivers)do W.update_unit(a.world,u)end
   local nativeChange=0
   for i,m in pairs(nativeWorldBefore)do nativeChange=math.max(nativeChange,delta(m,read(a.unit,i,true)))end
   if nativeChange>=.0002 then
    self.stats.nativeWorldChangedDuringOutput=self.stats.nativeWorldChangedDuringOutput+1
    self.failureDetail={stage='native_input_changed_during_source_flush',maxNativeWorldChange=nativeChange,nativeRefresh=nativeRefresh,recoilInput=nativeWorldBefore[p.entry.parent],recoilAfterOutput=read(a.unit,p.entry.parent,true)}
    error('fp_native_world_changed_during_source_output')
   end
   local maximum=0;local samples={};local outputs={};local nextSamples={};local actualHand,modelHand
   for _,n in ipairs(p.sourceNodes)do
    local expected=elements(candidates[n.index]);local actual=read(a.unit,n.index,true);local worldError=delta(expected,actual)
    if worldError>=.0002 then
     self.stats.sourceWorldReadbackFailures=self.stats.sourceWorldReadbackFailures+1
     self.failureDetail={stage='source_world_readback',index=n.index,name=n.name,parent=n.parent,expectedWorld=expected,actualWorld=actual,actualLocal=read(a.unit,n.index,false),writtenLocal=rows[n.index-p.entry.index+1].written,parentWorld=read(a.unit,n.parent,true),maxSourceWorldError=worldError,maxNativeWorldChange=nativeChange,nativeRefresh=nativeRefresh}
     error('fp_source_world_readback')
    end
    local modelWorld=read(model,n.modelIndices[self.activeModels[1].resource],true);local error=delta(modelWorld,actual);maximum=math.max(maximum,error)
    for rid,u in pairs(self.receivers)do if u~=model then maximum=math.max(maximum,delta(read(u,n.modelIndices[rid],true),actual))end end
    if n.driver=='r_hand'then actualHand=cp(actual);modelHand=cp(modelWorld)end
    if diagnostic then outputs[#outputs+1]={name=n.name,index=n.index,modelIndex=n.modelIndices[self.activeModels[1].resource],source=actual,modelBefore=modelBefore[n.index],modelAfter=modelWorld,sourceWorldReadbackError=worldError,receiverError=error};end;nextSamples[n.index]=cp(actual)
    if diagnostic and (n.driver=='r_shoulder'or n.driver=='r_elbow'or n.driver=='r_hand'or n.driver=='l_shoulder'or n.driver=='l_elbow'or n.driver=='l_hand')then samples[#samples+1]={name=n.name,native=n.native and nativeWorldBefore[n.native.index],source=actual,modelBefore=modelBefore[n.index],modelAfter=modelWorld,receiverError=error}end
   end
   for _,n in ipairs(p.avatar.nativeGraph)do assert(delta(read(a.unit,n.index,false),nativeBefore[n.index])<1e-6,'fp_native_local_changed')end
   local hand
   for _,n in ipairs(p.sourceNodes)do if n.driver=='r_hand'then hand=elements(candidates[n.index])end end
   assert(actualHand and modelHand,'fp_hand_driver_missing')
   -- A 2mm-per-render threshold starves slow motion, and matching a frozen
   -- receiver within a 2mm tolerance is not proof that the model actually moved.
   local sameReceiver=self.receiver==model and self.producer==a.unit and self.receiverWorld==a.world
    and self.lastProofFrame and (frame==self.lastProofFrame or frame==self.lastProofFrame+1)
   local movement=sameReceiver and self.lastWanted and dist(actualHand,self.lastWanted)or 0;self.lastWanted=cp(actualHand)
   local sourceSpan,modelSpan,motionAgreement=0,0,0
   if sameReceiver and self.motionAnchor then
    sourceSpan=dist(actualHand,self.motionAnchor.source);modelSpan=dist(modelHand,self.motionAnchor.model)
    for i=10,12 do local error=(actualHand[i]-self.motionAnchor.source[i])-(modelHand[i]-self.motionAnchor.model[i]);motionAgreement=motionAgreement+error*error end
    motionAgreement=math.sqrt(motionAgreement)
   end
   if maximum<=(p.receiverTolerance or .002)then
    self.stats.receiverMatches=self.stats.receiverMatches+1
    if not sameReceiver then self.motionSeen=false;self.motionAnchor={source=cp(actualHand),model=cp(modelHand)};self.proof=1
    elseif frame~=self.lastProofFrame then self.proof=self.proof+1 end
    self.receiver=model;self.producer=a.unit;self.receiverWorld=a.world;self.lastProofFrame=frame
    self.motionSeen=self.motionSeen or (sourceSpan>=(p.motionProofMetres or .002)and modelSpan>=(p.motionProofMetres or .002)and motionAgreement<=(p.motionAgreementTolerance or .0002))
    if self.proof>=(p.minProofFrames or 3)and self.motionSeen then self.allowed={units={[model]=true},world=a.world,frame=frame}end
    local arm=p.arms.l;local ln=byIndex[arm.hand];local sourceLeft=elements(candidates[arm.hand]);local leftRid=self.activeModels[2].resource;local leftModel=self.receivers[leftRid];local actualLeft=read(leftModel,ln.modelIndices[leftRid],true)
    self.leftProof=self.leftProof or {}
    if not sameReceiver or self.leftProof.unit~=leftModel then self.leftProof={unit=leftModel,source=cp(sourceLeft),model=cp(actualLeft),seen=false}end
    local leftSourceSpan=dist(sourceLeft,self.leftProof.source);local leftModelSpan=dist(actualLeft,self.leftProof.model);local leftAgreement=0
    for k=10,12 do local x=(sourceLeft[k]-self.leftProof.source[k])-(actualLeft[k]-self.leftProof.model[k]);leftAgreement=leftAgreement+x*x end
    self.leftProof.seen=self.leftProof.seen or (leftSourceSpan>=.002 and leftModelSpan>=.002 and math.sqrt(leftAgreement)<.0002)
    if self.proof>=3 and self.leftProof.seen then self.allowed=self.allowed or {units={},world=a.world,frame=frame};self.allowed.units[leftModel]=true end
   else self.stats.receiverMisses=self.stats.receiverMisses+1;self.proof=0;self.receiver=nil;self.motionSeen=false;self.motionAnchor=nil end
   self.previousOutput={actor=a,model=model,modelSpec=self.activeModels[1],frame=frame,samples=nextSamples,restored=false}
   if diagnostic then self.lastReceiverProbe=now;emit({event='fp_source_receiver',frame=frame,time=now,modelResource=self.activeModels[1].resource,matched=maximum<=(p.receiverTolerance or .002),maxReceiverError=maximum,proofFrames=self.proof,showPermit=self.allowed~=nil,nextRenderReceiverError=nextCheck,handMotion=movement,sourceHandMotionSpan=sourceSpan,modelHandMotionSpan=modelSpan,motionDisplacementError=motionAgreement,motionProofKind='source_and_actual_model_displacement_continuous_unique_frames',samples=samples,outputs=outputs,nativeRefresh=nativeRefresh,maxNativeWorldChangeDuringOutput=nativeChange,sourceWorldTolerance=.0002,palmAxisPolicy=p.palmAxisRegistration and p.palmAxisRegistration.method or 'shoulder-aligned-bind',contacts=contacts,sourceBonesStretched=false,weaponAndCameraWritten=false});end
  end)
  if not ok then self.stats.failures=self.stats.failures+1;self.proof=0;self.receiver=nil;self.motionSeen=false;self:restore('failed');emit({event='fp_source_unavailable',frame=frame,time=now,reason=tostring(err),detail=self.failureDetail,totalFailures=self.stats.failures})end
 end
 function self:stop()self:restore('stop');emit({event='fp_source_complete',stats=cp(self.stats)},true)end
 return self
end
return M
