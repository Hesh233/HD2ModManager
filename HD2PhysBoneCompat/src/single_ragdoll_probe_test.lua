-- Read-only SINGLE HD2 ragdoll evidence. No pose setters, relinks or graph refreshes.
local M={VERSION='1.0.0-test.single-ragdoll'}
local function finite(x)return type(x)=='number' and x==x and math.abs(x)<1e30 end
local function encode(x)
 if x==nil then return 'null' end
 if type(x)=='boolean' then return x and 'true' or 'false' end
 if type(x)=='number' then if not finite(x)then return 'null'end;return x==math.floor(x) and string.format('%.0f',x) or string.format('%.7g',x) end
 if type(x)=='string' then return '"'..x:gsub('\\','\\\\'):gsub('"','\\"'):gsub('\n','\\n'):gsub('\r','\\r')..'"' end
 local r={};if #x>0 then for _,v in ipairs(x)do r[#r+1]=encode(v)end;return '['..table.concat(r,',')..']' end
 local keys={};for k in pairs(x)do keys[#keys+1]=k end;table.sort(keys)
 for _,k in ipairs(keys)do r[#r+1]=encode(k)..':'..encode(x[k]) end;return '{'..table.concat(r,',')..'}'
end
M.encode=encode
local function compose(a,b)
 local r={};for c=0,2 do for i=1,3 do local v=0;for k=0,2 do v=v+a[k*3+i]*b[c*3+k+1]end;r[c*3+i]=v end end
 for i=1,3 do r[i+9]=a[i+9]+a[i]*b[10]+a[i+3]*b[11]+a[i+6]*b[12]end;return r
end
local function dist(a,b)local d=0;for i=10,12 do d=d+(a[i]-b[i])^2 end;return math.sqrt(d)end
local function scales(m)local r={};for c=0,2 do local d=0;for i=1,3 do d=d+m[c*3+i]^2 end;r[c+1]=math.sqrt(d)end;return r end
function M.new(S,p,log,context)
 local U,W,A,X=S.Unit,S.World,S.Application,S.Matrix4x4
 local self={stopped=false,frame=0,lastScan=nil,lastSample={},items={},ids={},seq=0,samples=0,errors=0,fullSamples={},motionSamples=0,firstSeen={},checkpoints={}}
 context=context or {}
 M.VERSION=p.version or M.VERSION
 local function emit(r)r.testOnly=true;r.readOnly=true;r.version=M.VERSION;r.gpuSkinObserved=false;log(encode(r))end
 local function resource(u)return S.IdString64.to_hex(U.resource_name(u)):lower():gsub('^0x','')end
 local function matrix(u,index,world)
  local m=world and U.world_pose(u,index) or U.local_pose(u,index);local v={X.to_elements(m)}
  if #v~=12 then error('pose_element_count')end;for _,n in ipairs(v)do if not finite(n)then error('pose_nonfinite')end end;return v
 end
 local function api(name,u)local f=U[name];if type(f)~='function'then return {available=false}end;local ok,v=pcall(f,u);return ok and {available=true,value=tostring(v),valueType=type(v)}or {available=false,error=tostring(v)}end
 local function scan(now)
  local items={};local ok,worlds=pcall(A.worlds)
  if not ok then emit({event='observer_scan_error',error=tostring(worlds)});return end
  for _,w in ipairs(worlds or {})do
   local good,units=pcall(W.units,w)
   if good then for _,u in ipairs(units or {})do
    local good,item=pcall(function()
     if not U.alive(u)then return end;local rid=resource(u);local spec=p.resources[rid];if not spec then return end
     if not self.ids[u]then self.seq=self.seq+1;self.ids[u]=self.seq end
     self.firstSeen[u]=self.firstSeen[u] or now
     return {unit=u,world=w,id=self.ids[u],resource=rid,spec=spec,firstSeen=self.firstSeen[u]}
    end)
    if good and item and (p.maxNativeReferences or #items<p.maxInstances) then items[#items+1]=item end
   end end
  end
  if p.maxNativeReferences then
   local models,refs={},{}
   for _,item in ipairs(items)do
    if item.spec.kind=='single_model' then models[#models+1]=item
    elseif #refs<p.maxNativeReferences then refs[#refs+1]=item end
   end
   if p.preferNearestReference then
    local allRefs={}
    for _,item in ipairs(items)do if item.spec.kind=='native_avatar_reference' then allRefs[#allRefs+1]=item end end
    local function hips(item)
     local ok,v=pcall(function()
      local id=A.string_to_id32('hips')
      if not U.has_node(item.unit,id)then return end
      local index=U.node(item.unit,A.string_to_id32('hips'))
      if not finite(index)or index<1 or index>U.num_scene_graph_items(item.unit)then return end
      return matrix(item.unit,index,true)
     end)
     return ok and v or nil
    end
    local referencePoses={}
    for _,ref in ipairs(allRefs)do referencePoses[ref.unit]=hips(ref)end
    local filtered={}
    for _,item in ipairs(models)do
     local pose=hips(item);local nearest
     for _,ref in ipairs(allRefs)do
      local v=referencePoses[ref.unit]
      if pose and v and item.world==ref.world then local d=dist(pose,v);nearest=not nearest and d or math.min(nearest,d)end
     end
     item.referenceDistance=nearest
     if nearest==nil or nearest<=(p.modelMatchRadius or 5)then filtered[#filtered+1]=item end
    end
    models=filtered
    table.sort(models,function(a,b)return (a.referenceDistance or 1e30)<(b.referenceDistance or 1e30)end)
   end
   items={}
   for _,item in ipairs(models)do if #items<p.maxInstances then items[#items+1]=item end end
   for _,item in ipairs(refs)do if #items<p.maxInstances then items[#items+1]=item end end
  end
  local inventory={};local keys={};local modelCount=0;self.primary=nil
  for _,item in ipairs(items)do
   if item.spec.kind=='single_model' then
    modelCount=modelCount+1
    if not self.primary or item.spec.fullHierarchy and not self.primary.spec.fullHierarchy then self.primary=item end
   end
  end
  if modelCount>0 then self.sawModel=true end
  if p.requireModelToSample and modelCount==0 and (not self.lastMissing or now-self.lastMissing>=5)then
   self.lastMissing=now;emit({event='observer_target_missing',time=now,frame=self.frame,expectedModelResources=p.deployedAliases,
    reason='no_exact_single_model_resource_instance',nativeReferencesNotModelEvidence=true})
  end
  for _,item in ipairs(items)do
   local good,count=pcall(U.num_scene_graph_items,item.unit)
   inventory[#inventory+1]={instance=item.id,resource=item.resource,world=tostring(item.world),kind=item.spec.kind,count=good and count or nil,sourceResource=item.spec.sourceResource,deployedAlias=item.spec.deployedAlias,referenceDistance=item.referenceDistance,ownershipProven=false}
   keys[#keys+1]=tostring(item.id)..':'..item.resource..':'..tostring(good and count or '?')
  end
  table.sort(keys);local signature=table.concat(keys,'|')
  if signature~=self.lastInventory then
   self.lastInventory=signature;emit({event='observer_scan',time=now,frame=self.frame,instances=inventory,ownership='resource_instances_only',ragdollStateDirectlyObserved=false})
  end
  self.items=items;self.lastScan=now
 end
 local function capture(item,phase,now,motion,full)
  local u=item.unit;if not U.alive(u)then return end
  if resource(u)~=item.resource then return end
  local count=U.num_scene_graph_items(u)
  if p.strictPoseLayout and count~=item.spec.count then
   emit({event='observer_layout_changed',instance=item.id,resource=item.resource,actualCount=count,expectedCount=item.spec.count,poseWrites=0});return
  end
  if p.captureCheckpoints and not self.checkpoints[item.unit] then
   self.checkpoints[item.unit]=true;emit({event='observer_capture_checkpoint',stage='named_pose_read_start',instance=item.id,resource=item.resource,kind=item.spec.kind,phase=phase,time=now,poseWrites=0})
  end
  local poses={};local worlds={}
  local function world(index)if not worlds[index]then worlds[index]=matrix(u,index,true)end;return worlds[index]end
  local nodes={}
  for _,node in ipairs(item.spec.nodes)do
   if full or (motion and p.motionNames and p.motionNames[node.name]) or (not motion and (not p.captureNames or p.captureNames[node.name])) then nodes[#nodes+1]=node end
  end
  for _,node in ipairs(nodes)do
   local ok,row=pcall(function()
    local index
    if node.name then
     local id=A.string_to_id32(node.name)
     if not U.has_node(u,id)then return {name=node.name,available=false,reason='name_missing',expectedIndex=node.index}end
     index=U.node(u,A.string_to_id32(node.name))
    else
     if count~=item.spec.count then return {rawHash=node.hash,expectedIndex=node.index,available=false,reason='unnamed_export_index_layout_changed'}end
     index=node.index+1 -- indexed pose reads only; never pass a numerical hash to node APIs.
    end
    if not finite(index)or index<1 or index>count then error('node_index_range')end
    if p.strictPoseLayout and index~=node.index+1 then return {name=node.name,available=false,reason='named_index_layout_changed',index=index-1,expectedIndex=node.index}end
    local localPose=matrix(u,index,false);local worldPose=world(index);local parent=U.scene_graph_parent(u,index)
    local out={name=node.name,rawHash=node.hash,nameAvailable=node.name~=nil,index=index-1,expectedIndex=node.index,indexMatches=index==node.index+1,localPose=localPose,worldPose=worldPose,localScale=scales(localPose),worldScale=scales(worldPose),exportBindLocal=node.bind,exportParentIndex=node.parent,parentReturned=parent,parentAvailable=parent~=nil,available=true}
    if p.compactPoseRecords and not full then out.exportBindLocal=nil end
    local pi=parent and parent>0 and parent or node.parent and node.parent+1
    if pi and pi>=1 and pi<=count then
     local parentWorld=world(pi);local expected=compose(parentWorld,localPose)
     out.parentInterpretation=parent and parent>0 and 'returned_scene_graph_parent' or 'exported_parent_fallback_not_solver_parent'
     out.worldVsLocalParentFK=dist(worldPose,expected);out.worldSegmentLength=dist(worldPose,parentWorld)
    end
    return out
   end)
   poses[#poses+1]=ok and row or {name=node.name,rawHash=node.hash,available=false,error=tostring(row)}
  end
  if motion then
   local values={}
   for _,row in ipairs(poses)do
    if row.available then
     local m=row.worldPose;local l=row.localPose
     local localLength=math.sqrt(l[10]^2+l[11]^2+l[12]^2)
     values[#values+1]={row.index,m[10],m[11],m[12],math.max(unpack(row.worldScale)),math.max(unpack(row.localScale)),
      localLength,row.worldVsLocalParentFK or -1,row.worldSegmentLength or -1,row.parentAvailable and 1 or 0}
    end
   end
   self.motionSamples=self.motionSamples+1
   emit({event='single_model_motion',time=now,frame=self.frame,phase=phase,instance=item.id,resource=item.resource,kind=item.spec.kind,
    format='index_xyz_max_worldscale_max_localscale_localsegment_parentfk_worldsegment_parent_available_v1',values=values,
    parentFallbackNotSolverParent=true,ragdollSolverStateDirectlyObserved=false})
   return
  end
  -- Model Units are externally bone-linked and have no animation object.
  -- animation_bone_mode dereferences that object natively: pcall cannot save the process.
  local animationState,boneMode
  if item.spec.kind=='native_avatar_reference' then
   animationState=api('has_animation_state_machine',u)
   boneMode=animationState.available and animationState.value=='true' and api('animation_bone_mode',u)
    or {available=false,reason='no_observed_native_animation_state_machine'}
  else
   animationState={available=false,reason='external_model_animation_api_not_queried'}
   boneMode={available=false,reason='external_model_has_no_animation_object_do_not_query'}
  end
  self.samples=self.samples+1
  emit({event='single_ragdoll_pose',phase=phase,time=now,frame=self.frame,instance=item.id,resource=item.resource,world=tostring(item.world),actualCount=count,expectedCount=item.spec.count,kind=item.spec.kind,ownership='resource_instance_only_not_player_or_ragdoll_proof',animationState=animationState,boneMode=boneMode,fullHierarchySnapshot=full==true,sourceResource=item.spec.sourceResource,poses=poses,ragdollSolverStateDirectlyObserved=false})
 end
 function self:tick(phase,now)
  if self.stopped then return end;if phase=='update'then self.frame=self.frame+1 end
  if p.renderOnly and phase~='render' then return end
  if p.missionOnly then
   local active=false
   if type(context.inMission)=='function' then local ok,v=pcall(context.inMission);active=ok and v==true
   elseif context.inMission==true then active=true end
   if not active then
    self.items={};self.primary=nil;self.firstSeen={}
    if not self.lastSceneBypass or now-self.lastSceneBypass>=5 then self.lastSceneBypass=now;emit({event='observer_scene_bypass',time=now,reason='ship_loading_or_unverified_mission',poseReads=false,poseWrites=0})end
    return
   end
  end
  if not self.lastScan or now<self.lastScan or now-self.lastScan>=p.scanSeconds then scan(now)end
  local function ready(item)
   return not p.warmupSeconds or (item and now-(item.firstSeen or now)>=p.warmupSeconds)
  end
  if p.requireModelToSample and not self.sawModel then return end
  if phase=='render' and p.motionSeconds and self.primary and ready(self.primary) and (not self.lastMotion or now<self.lastMotion or now-self.lastMotion>=p.motionSeconds)then
   self.lastMotion=now
   local ok,err=pcall(capture,self.primary,phase,now,true,false)
   if not ok then self.errors=self.errors+1;emit({event='observer_motion_error',error=tostring(err)})end
  end
  local last=self.lastSample[phase];local interval=phase=='render' and p.renderSeconds or p.updateSeconds
  if last and now>=last and now-last<interval then return end;self.lastSample[phase]=now
  for _,item in ipairs(self.items)do
   if ready(item) then
   if p.fullSnapshots and item.spec.fullHierarchy and not self.fullSamples[item.unit] then
    local ok,err=pcall(capture,item,phase,now,false,true)
    if ok then self.fullSamples[item.unit]=true else self.errors=self.errors+1;emit({event='observer_full_snapshot_error',error=tostring(err)})end
   end
   local ok,err=pcall(capture,item,phase,now,false,false)
   if not ok then self.errors=self.errors+1;emit({event='observer_item_error',instance=item.id,error=tostring(err)})end
   end
  end
 end
 function self:stop()if self.stopped then return end;self.stopped=true;emit({event='complete',samples=self.samples,motionSamples=self.motionSamples,errors=self.errors,poseWrites=0})end
 emit({event='loaded',profile=p.label,maxBytes=p.maxBytes,duration=p.duration,poseWrites=0,sourceSkeleton=false});return self
end
return M
