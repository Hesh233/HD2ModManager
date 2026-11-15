-- Independent FP Source-output domain. Never runs TP IK on the native FP63 graph.
local M={VERSION='1.0.1-test.fp-source.a2'}
local function cp(t)local r={};for k,v in pairs(t)do r[k]=type(v)=='table'and cp(v)or v end;return r end
local function delta(a,b)local d=0;for i=1,12 do d=math.max(d,math.abs(a[i]-b[i]))end;return d end
local function dist(a,b)local d=0;for i=10,12 do d=d+(a[i]-b[i])^2 end;return math.sqrt(d)end
function M.new(S,p,Math,guard,log,context)
 local U,W,A,X=S.Unit,S.World,S.Application,S.Matrix4x4
 context=context or {}
 assert(p.avatar.nativeCount==63 and p.avatar.count>63 and p.side=='r' and p.entry.index==63 and p.entry.parent==7,'fp_source_contract')
 local self={pending=nil,allowed=nil,receiver=nil,proof=0,lastLog={},lastWanted=nil,stats={writes=0,restores=0,receiverMatches=0,receiverMisses=0,failures=0,nativeWrites=0,modelPoseWrites=0,nativeInputRefreshes=0,receiverInputRefreshes=0,receiverRestoreRefreshes=0,meleeProbeRefreshes=0,sourceWorldReadbackFailures=0,nativeWorldChangedDuringOutput=0}}
 local function emit(r,force)
  r.event=r.event or 'fp_source_output';r.fpTestOnly=true;r.phaseA=true;r.nativeWrites=0;r.modelPoseWrites=0;r.gpuPaletteObserved=false
  local now=r.time or 0
  -- A native capture must not consume the receiver/visibility proof's log slot.
  local slot=r.event
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
 local function node(u,n,parents)
  local id=A.string_to_id32(n.name);assert(U.has_node(u,id)and U.node(u,A.string_to_id32(n.name))==n.index+1,'fp_named_index:'..n.name)
  if parents and n.parent~=nil then assert(U.scene_graph_parent(u,n.index+1)==n.parent+1,'fp_source_parent:'..n.name)end
 end
 local function identity(a)
  assert(U.alive(a.unit)and rid(a.unit)==p.avatar.resource and U.num_scene_graph_items(a.unit)==p.avatar.count,'fp_avatar_identity')
  for _,n in ipairs(p.avatar.nativeGraph)do if n.name then node(a.unit,n,false)end end
  for _,n in ipairs(p.avatar.outputs)do assert(n.index>=63,'fp_native_writer_forbidden');node(a.unit,n,true)end
 end
 local function present(a)
  if not U.alive(a.unit)then return false end
  for _,u in ipairs(W.units(a.world)or{})do if u==a.unit then return true end end;return false
 end
 local function source_model(a)
  local found={}
  for _,u in ipairs(W.units(a.world)or{})do
   if U.alive(u)and rid(u)==p.model.resource and U.num_scene_graph_items(u)==p.model.count then
    local ok=pcall(function()
     for _,n in ipairs(p.model.nativeMatches)do node(u,n,false)end
     for _,n in ipairs(p.sourceNodes)do node(u,{name=n.name,index=n.modelIndex},false)end
     -- Native/model external-link caches can still describe the preceding frame.
     W.update_unit(a.world,u);self.stats.receiverInputRefreshes=self.stats.receiverInputRefreshes+1
     for _,n in ipairs(p.model.nativeMatches)do
      assert(delta(read(u,n.index,true),read(a.unit,n.fpIndex,true))<=(p.modelMatchTolerance or .01),'fp_model_native_mismatch')
     end
    end)
    if ok then found[#found+1]=u end
   end
  end
  if #found~=1 then return nil,#found end;return found[1],1
 end
 function self:restore(reason)
  local r=self.pending;self.pending=nil;self.allowed=nil
  if not r then return end
  if not present(r.actor)then return end
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
    assert(rid(r.model)==p.model.resource and U.num_scene_graph_items(r.model)==p.model.count,'fp_restore_model_identity')
    for _,n in ipairs(p.sourceNodes)do node(r.model,{name=n.name,index=n.modelIndex},false)end
    W.update_unit(r.actor.world,r.model);self.stats.receiverRestoreRefreshes=self.stats.receiverRestoreRefreshes+1
   end
   if self.previousOutput then self.previousOutput.restored=true end
  end)
  if not ok then self.stats.failures=self.stats.failures+1;emit({event='fp_source_restore_failed',reason=tostring(err),time=r.time},true)end
 end
 function self:permit(u,world,frame)
  return self.allowed and self.allowed.unit==u and self.allowed.world==world and self.allowed.frame==frame and U.alive(u)==true or false
 end
 function self:tick(phase,frame,now)
  if phase~='render' then self:restore('update');return end
  local mission=false
  if type(context.inMission)=='function' then local ok,v=pcall(context.inMission);mission=ok and v==true end
  if not mission then self:restore('scene');self.previousOutput=nil;self.proof=0;self.receiver=nil;self.lastWanted=nil;self.motionSeen=false;return end
  local previous=self.previousOutput;local nextCheck
  if previous and present(previous.actor)and U.alive(previous.model)and present({unit=previous.model,world=previous.actor.world})then
   local ok,value=pcall(function()
    identity(previous.actor);assert(rid(previous.model)==p.model.resource and U.num_scene_graph_items(previous.model)==p.model.count,'fp_next_render_model_identity')
    local maximum=0;local samples={}
    for _,n in ipairs(p.sourceNodes)do
     if n.driver=='r_shoulder'or n.driver=='r_elbow'or n.driver=='r_hand'then
      node(previous.model,{name=n.name,index=n.modelIndex},false)
      local source=read(previous.actor.unit,n.index,true);local model=read(previous.model,n.modelIndex,true)
      maximum=math.max(maximum,delta(model,source));samples[#samples+1]={name=n.name,fpCurrent=source,modelCurrent=model,previousWritten=previous.samples[n.index]}
     end
    end
    emit({event='fp_source_next_render',frame=frame,time=now,previousFrame=previous.frame,stage='before_refresh_after_update_restore',outputRestoredSinceWrite=previous.restored==true,maxCurrentReceiverError=maximum,samples=samples,previousPoseStillDrivenNotAssumed=true})
    return maximum
   end);nextCheck=ok and value or nil
  end
  self.previousOutput=nil
  self:restore('before_render')
  local state,detail=guard.sample()
  if state~=true then self.proof=0;self.receiver=nil;self.lastWanted=nil;self.motionSeen=false;return end
  local a=guard.actor();if not a or not present(a)then return end
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
   local refreshedState=guard.sample();local refreshedActor=guard.actor()
   assert(refreshedState==true and refreshedActor and refreshedActor.unit==a.unit and refreshedActor.world==a.world,'fp_view_changed_after_native_refresh')
   local recoilAfter=read(a.unit,p.entry.parent,true)
   local nativeRefresh={stage='native_cache_flushed_before_pose_sampling',maxRecoilWorldChange=delta(recoilBefore,recoilAfter),recoilBefore=recoilBefore,recoilAfter=recoilAfter}
   if not self.lastNativeProbe or now-self.lastNativeProbe>=1 then
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
   if not model then self.proof=0;self.receiver=nil;self.motionSeen=false;emit({event='fp_source_no_unique_receiver',frame=frame,time=now,candidates=matches});return end
   local shoulder
   for _,n in ipairs(p.sourceNodes)do if n.driver=='r_shoulder'then shoulder=n.native end end
   assert(shoulder,'fp_shoulder_driver_missing')
   local nativeWorldBefore={[p.entry.parent]=read(a.unit,p.entry.parent,true)}
   for _,n in ipairs(p.sourceNodes)do if n.native then nativeWorldBefore[n.native.index]=read(a.unit,n.native.index,true)end end
   local entryWorld=pose(nativeWorldBefore[shoulder.index]);local recoil=pose(nativeWorldBefore[p.entry.parent]);local entryLocal=Math.relative(recoil,entryWorld)
   local candidates={[p.entry.index]=entryWorld};local rows={{index=p.entry.index,before=read(a.unit,p.entry.index,false),written=elements(entryLocal)}}
   local nativeBefore={};for _,n in ipairs(p.avatar.nativeGraph)do nativeBefore[n.index]=read(a.unit,n.index,false)end
   for _,n in ipairs(p.sourceNodes)do
    local parent=candidates[n.parent];assert(parent,'fp_source_parent_order');local localPose=pose(n.bindLocal)
    if n.native then
     node(a.unit,n.native,false)
     local registration=Math.relative(pose(n.native.bindWorld),pose(n.bindWorld))
     local rotation=Math.compose(pose(nativeWorldBefore[n.native.index]),registration)
     localPose.q=Math.relative(parent,rotation).q
    end
    candidates[n.index]=Math.compose(parent,localPose)
    rows[#rows+1]={index=n.index,before=read(a.unit,n.index,false),written=elements(localPose)}
   end
   local modelBefore={};for _,n in ipairs(p.sourceNodes)do modelBefore[n.index]=read(model,n.modelIndex,true)end
   self.pending={actor=a,model=model,rows=rows,time=now}
   for _,n in ipairs(rows)do assert(n.index>=63,'fp_native_write_attempt');U.set_local_pose(a.unit,n.index+1,X.from_elements(unpack(n.written)));self.stats.writes=self.stats.writes+1 end
   W.update_unit(a.world,a.unit);W.update_unit(a.world,model)
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
    local modelWorld=read(model,n.modelIndex,true);local error=delta(modelWorld,actual);maximum=math.max(maximum,error)
    if n.driver=='r_hand'then actualHand=cp(actual);modelHand=cp(modelWorld)end
    outputs[#outputs+1]={name=n.name,index=n.index,modelIndex=n.modelIndex,source=actual,modelBefore=modelBefore[n.index],modelAfter=modelWorld,sourceWorldReadbackError=worldError,receiverError=error};nextSamples[n.index]=cp(actual)
    if n.driver=='r_shoulder'or n.driver=='r_elbow'or n.driver=='r_hand'then samples[#samples+1]={name=n.name,native=n.native and nativeWorldBefore[n.native.index],source=actual,modelBefore=modelBefore[n.index],modelAfter=modelWorld,receiverError=error}end
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
    if self.proof>=(p.minProofFrames or 3)and self.motionSeen then self.allowed={unit=model,world=a.world,frame=frame}end
   else self.stats.receiverMisses=self.stats.receiverMisses+1;self.proof=0;self.receiver=nil;self.motionSeen=false;self.motionAnchor=nil end
   self.previousOutput={actor=a,model=model,frame=frame,samples=nextSamples,restored=false}
   emit({event='fp_source_receiver',frame=frame,time=now,modelResource=p.model.resource,matched=maximum<=(p.receiverTolerance or .002),maxReceiverError=maximum,proofFrames=self.proof,showPermit=self.allowed~=nil,nextRenderReceiverError=nextCheck,handMotion=movement,sourceHandMotionSpan=sourceSpan,modelHandMotionSpan=modelSpan,motionDisplacementError=motionAgreement,motionProofKind='source_and_actual_model_displacement_continuous_unique_frames',samples=samples,outputs=outputs,nativeRefresh=nativeRefresh,maxNativeWorldChangeDuringOutput=nativeChange,sourceWorldTolerance=.0002,sourceBonesStretched=false,weaponAndCameraWritten=false})
  end)
  if not ok then self.stats.failures=self.stats.failures+1;self.proof=0;self.receiver=nil;self.motionSeen=false;self:restore('failed');emit({event='fp_source_unavailable',frame=frame,time=now,reason=tostring(err),detail=self.failureDetail,totalFailures=self.stats.failures})end
 end
 function self:stop()self:restore('stop');emit({event='fp_source_complete',stats=cp(self.stats)},true)end
 return self
end
return M
