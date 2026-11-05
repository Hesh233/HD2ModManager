-- Experimental per-avatar attachment adapter. Original shadow nodes are never
-- written. Ownership is inferred from unique multi-node pose correspondence,
-- not a native equipment-owner query. Ambiguous matches restore native output.
-- BEGIN READ ONLY SCENE OBSERVER
local SceneObserver=(function()
-- Read-only scene graph telemetry. Every engine temporary is copied to numbers
-- before another engine call. This module never sets, links or refreshes Units.
local M={VERSION='1.0.0'}
local function finite(x)return type(x)=='number' and x==x and math.abs(x)<1e12 end
local function quote(s)
 return '"'..tostring(s):gsub('[%z\1-\31\\"]',function(c)
  if c=='\\' then return '\\\\' elseif c=='"' then return '\\"' end
  return string.format('\\u%04x',string.byte(c))
 end)..'"'
end
local function json(v)
 if v==nil then return 'null' end
 if type(v)=='boolean' then return tostring(v) end
 if type(v)=='number' then assert(finite(v),'nonfinite_json');return string.format('%.17g',v) end
 if type(v)=='string' then return quote(v) end
 assert(type(v)=='table','unsupported_json')
 local out={}
 if #v>0 then for i=1,#v do out[i]=json(v[i])end;return '['..table.concat(out,',')..']' end
 local keys={};for k in pairs(v)do keys[#keys+1]=k end;table.sort(keys)
 for _,k in ipairs(keys)do out[#out+1]=quote(k)..':'..json(v[k])end
 return '{'..table.concat(out,',')..'}'
end
function M.new(S,profile,logger)
 local cfg=profile.sceneObservation
 if not cfg or cfg.enabled~=true then return nil end
 assert(not profile.modelArmLocalSync,'observation requires B7 without model local copying')
 local self={samples=0,records=0,sequence=0,pending=nil,lastTime=nil}
 local interval=math.max(1,tonumber(cfg.intervalSeconds) or 3)
 local limit=math.min(90,math.max(1,tonumber(cfg.maxSamples) or 90))
 local maxRecords=18000
 local function emit(event)
  if self.records>=maxRecords then return end
  self.records=self.records+1
  logger('[scene_probe] %s',json(event))
 end
 local function matrix(unit,index,world)
  local fn=S.Unit.local_pose;if world then fn=S.Unit.world_pose end
  assert(type(fn)=='function' and S.Matrix4x4 and S.Matrix4x4.to_elements,'matrix_api_missing')
  local v={S.Matrix4x4.to_elements(fn(unit,index))}
  assert(#v==12,'matrix_element_count')
  for _,n in ipairs(v)do assert(finite(n),'matrix_nonfinite')end
  return v
 end
 local function parent(unit,index,count)
  if type(S.Unit.scene_graph_parent)~='function' then return 'unavailable','api_missing' end
  local ok,n=pcall(S.Unit.scene_graph_parent,unit,index)
  if not ok then return 'unavailable','api_error' end
  if n==nil then return 'nil','external_or_root' end
  if n==-1 or n==0 then return n,'external_or_root' end
  if finite(n) and n%1==0 and n>=1 and n<=count and n~=index then return n,'internal_candidate' end
  return tostring(n),'invalid'
 end
 local function scale(unit,index)
  if type(S.Unit.local_scale)~='function' then return 'unavailable' end
  local ok,v=pcall(function()return {S.Vector3.to_elements(S.Unit.local_scale(unit,index))}end)
  if not ok or #v~=3 then return 'unavailable' end
  for _,n in ipairs(v)do if not finite(n) then return 'invalid' end end
  return v
 end
 local function verify(unit,name,index,count)
  assert(type(index)=='number' and index%1==0 and index>=1 and index<=count,'node_index_range')
  local hash=S.Application.string_to_id32(name)
  assert(S.Unit.has_node(unit,hash)==true and S.Unit.node(unit,hash)==index,'node_identity:'..name)
 end
 local function snapshot(unit,index,count)
  local p,state=parent(unit,index,count)
  local row={localMatrix=matrix(unit,index,false),worldMatrix=matrix(unit,index,true),
   localScale=scale(unit,index),runtimeParent=p,parentState=state}
  if state=='internal_candidate' then row.runtimeParentWorld=matrix(unit,p,true)end
  return row
 end
 function self:capture(frame,now,phase,avatars,armor,owners,alive,visible,resource)
  if phase=='pre_apply' then
   self.pending=nil
   if self.samples>=limit or self.records>=maxRecords then return end
   if self.lastTime and now-self.lastTime<interval then return end
   local found=false
   for _,item in ipairs(armor)do if owners[item.unit] and cfg.layouts[item.resource] then found=true;break end end
   if not found then return end
   self.samples=self.samples+1;self.lastTime=now;self.pending=frame
  elseif phase~='post_refresh' or self.pending~=frame then return end
  local common={event='phase_begin',sample=self.samples,frame=frame,time=now,phase=phase,
   revision=profile.revision,observerVersion=M.VERSION,indexBase=1,readOnly=true}
  emit(common)
  local rows,errors=0,0
  for _,item in ipairs(armor)do
   local owner=owners[item.unit];local a=owner and avatars[owner]
   local layout=cfg.layouts[item.resource]
   if a and layout then
    if not item.sceneLabel then self.sequence=self.sequence+1;item.sceneLabel=self.sequence end
    local ok,err=pcall(function()
     assert(item.world==a.world and alive(item.unit) and alive(a.unit),'unit_unavailable')
     assert(S.Unit.num_scene_graph_items(item.unit)==item.count and
      S.Unit.num_scene_graph_items(a.unit)==profile.expectedAvatarNodes,'node_count_changed')
     assert(resource(item.unit)==item.resource and visible(item.unit)~=false,'model_changed_or_hidden')
     -- Buffer the whole model so a failed identity read cannot leave half a model.
     local captured={}
     assert(#layout==8,'observer_layout_count')
     for _,row in ipairs(layout)do
      local mi,ai,mp,ap=row.index+1,row.avatarIndex+1,row.parentIndex+1,row.avatarParentIndex+1
      verify(item.unit,row.name,mi,item.count);verify(a.unit,row.name,ai,profile.expectedAvatarNodes)
      verify(item.unit,row.parentName,mp,item.count);verify(a.unit,row.parentName,ap,profile.expectedAvatarNodes)
      captured[#captured+1]={event='node',sample=self.samples,frame=frame,time=now,phase=phase,
       avatar=a.label,resource=item.resource,slot=item.slot,name=row.name,
       hash=row.hash,modelIndex=mi,avatarIndex=ai,serializedModelParent=mp,serializedAvatarParent=ap,
       avatarActive=a.active==true,model=snapshot(item.unit,mi,item.count),
       avatarPose=snapshot(a.unit,ai,profile.expectedAvatarNodes),
       serializedModelParentWorld=matrix(item.unit,mp,true),serializedAvatarParentWorld=matrix(a.unit,ap,true)}
      -- Keep instance identity separate from the model pose object.
      captured[#captured].modelId=item.sceneLabel
     end
     assert(alive(item.unit) and alive(a.unit) and resource(item.unit)==item.resource and
      S.Unit.num_scene_graph_items(item.unit)==item.count and visible(item.unit)~=false,'model_changed_during_capture')
     for _,row in ipairs(captured)do emit(row);rows=rows+1 end
    end)
    if not ok then
     errors=errors+1
     emit({event='unavailable',sample=self.samples,frame=frame,phase=phase,avatar=a.label,
      modelId=item.sceneLabel,resource=item.resource,reason=tostring(err):sub(1,240)})
    end
   end
  end
  emit({event='phase_end',sample=self.samples,frame=frame,time=now,phase=phase,rows=rows,errors=errors})
  if phase=='post_refresh' then
   self.pending=nil
   if self.samples>=limit then emit({event='complete',samples=self.samples,readOnly=true})end
  end
 end
 return self
end
return M

end)()
-- END READ ONLY SCENE OBSERVER
-- BEGIN SAME MODEL LOCAL ROUNDTRIP
local SceneRoundtrip=(function()
-- Same-model local roundtrip only. No target construction or Avatar writes.
-- Captured numeric matrices live for one callback; rollback uses the captured
-- instance identity, never a pose-based owner match corrupted by a failed write.
local M={VERSION='1.0.0'}
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<1e12 end
local function maximum(a,b,first,last)
 local d=0;for i=first,last do d=math.max(d,math.abs(a[i]-b[i]))end;return d
end
local function axes(m)
 local s={};for i=1,3 do local k=(i-1)*3;s[i]=math.sqrt(m[k+1]^2+m[k+2]^2+m[k+3]^2)end;return s
end
local function error_metrics(a,b)
 local d=0;for i=10,12 do d=d+(a[i]-b[i])^2 end
 return math.sqrt(d),maximum(a,b,1,9),maximum(axes(a),axes(b),1,3)
end
local function csv(m)local t={};for i,v in ipairs(m)do t[i]=string.format('%.17g',v)end;return table.concat(t,',')end
function M.new(S,profile,logger)
 local cfg=profile.sceneRoundtrip
 if not cfg or cfg.enabled~=true then return nil end
 assert(not profile.modelArmLocalSync and cfg.mode=='same_model_local','invalid_roundtrip_mode')
 local U,X=S.Unit,S.Matrix4x4
 local self={trials=0,disabled=false,lastTime=nil}
 local function log(fmt,...)pcall(logger,'[scene_roundtrip] '..fmt,...)end
 local function mat(unit,index,world)
  local fn=U.local_pose;if world then fn=U.world_pose end
  assert(type(fn)=='function' and X and type(X.to_elements)=='function','matrix_api_missing')
  local v={X.to_elements(fn(unit,index))};assert(#v==12,'matrix_size')
  for _,n in ipairs(v)do assert(finite(n),'matrix_nonfinite')end
  return v
 end
 local function local_scale(unit,index)
  assert(type(U.local_scale)=='function','scale_api_missing')
  local v={S.Vector3.to_elements(U.local_scale(unit,index))};assert(#v==3,'scale_size')
  for _,n in ipairs(v)do assert(finite(n),'scale_nonfinite')end;return v
 end
 local function verify(unit,name,index,count)
  assert(type(index)=='number'and index%1==0 and index>=1 and index<=count,'index_range')
  local h=S.Application.string_to_id32(name)
  assert(U.has_node(unit,h)==true and U.node(unit,h)==index,'node_identity')
 end
 local function unchanged(a,b)
  local p,r,s=error_metrics(a,b)
  return p<=.001 and r<=.0002 and s<=.00002,p,r,s
 end
 function self:tick(frame,now,avatars,armor,owners,alive,visible,resource,settle)
  if self.disabled or self.trials>=90 then return end
  if self.lastTime and now-self.lastTime<3 then return end
  local batches={}
  for _,item in ipairs(armor)do
   local owner=owners[item.unit];local a=owner and avatars[owner]
   if a and a.active and a.stable[item.slot]>=(settle or 10) and cfg.layouts[item.resource] then
    batches[#batches+1]={item=item,avatar=a,rows={},written=0}
   end
  end
  if #batches==0 then return end
  self.trials=self.trials+1;self.lastTime=now
  local function identity(batch,rollback)
   local item,a=batch.item,batch.avatar
   assert(alive(item.unit) and alive(a.unit),'unit_dead')
   assert(item.world==a.world and U.num_scene_graph_items(item.unit)==item.count and
    U.num_scene_graph_items(a.unit)==profile.expectedAvatarNodes,'layout_or_world_changed')
   assert(resource(item.unit)==item.resource,'resource_changed')
   if not rollback then assert(visible(item.unit)~=false,'model_hidden')end
   local layout=cfg.layouts[item.resource];assert(#layout==8,'layout_count')
   for _,row in ipairs(layout)do
    verify(item.unit,row.name,row.index+1,item.count)
    verify(a.unit,row.name,row.avatarIndex+1,profile.expectedAvatarNodes)
    assert(type(U.scene_graph_parent)=='function' and U.scene_graph_parent(item.unit,row.index+1)==nil,'runtime_parent_changed')
   end
  end
  local function capture()
   assert(type(U.set_local_pose)=='function' and X and type(X.from_elements)=='function' and
    S.World and type(S.World.update_unit)=='function','roundtrip_api_missing')
   -- All model snapshots and constructor roundtrips precede every setter.
   for _,b in ipairs(batches)do
    identity(b,false)
    for _,row in ipairs(cfg.layouts[b.item.resource])do
     local index,ai=row.index+1,row.avatarIndex+1
     local l,w,av=mat(b.item.unit,index,false),mat(b.item.unit,index,true),mat(b.avatar.unit,ai,true)
     assert(unchanged(w,av),'model_avatar_world_mismatch')
     local rebuilt={X.to_elements(X.from_elements(unpack(l)))}
     for _,n in ipairs(rebuilt)do assert(finite(n),'constructor_nonfinite')end
     assert(#rebuilt==12 and maximum(l,rebuilt,1,12)<=.000001,'constructor_roundtrip_mismatch')
     local saved={index=index,avatarIndex=ai,name=row.name,localBefore=l,worldBefore=w,
      avatarBefore=av,scaleBefore=local_scale(b.item.unit,index)}
     b.rows[#b.rows+1]=saved
    end
   end
  end
  local function validate()
   for _,b in ipairs(batches)do
    identity(b,false)
    for _,row in ipairs(b.rows)do
     row.localAfter=mat(b.item.unit,row.index,false);row.worldAfter=mat(b.item.unit,row.index,true)
     row.scaleAfter=local_scale(b.item.unit,row.index)
     assert(maximum(row.localBefore,row.localAfter,1,12)<=.000001,'local_readback_mismatch')
     assert(maximum(row.scaleBefore,row.scaleAfter,1,3)<=.00002,'local_scale_changed')
     assert(unchanged(row.worldBefore,row.worldAfter),'world_readback_mismatch')
     assert(unchanged(row.avatarBefore,mat(b.avatar.unit,row.avatarIndex,true)),'avatar_changed')
    end
   end
  end
  local captured,why=pcall(capture)
  if not captured then
   self.disabled=true
   log('event=rejected trial=%d frame=%d writes=0 reason=%s',self.trials,frame,tostring(why):gsub('%s','_'))
   return
  end
  local writes=0
  local ok,err=pcall(function()
   for _,b in ipairs(batches)do
    identity(b,false)
    for i,row in ipairs(b.rows)do
     identity(b,false)
     b.written=i;writes=writes+1 -- Setter can mutate then throw; include it in rollback.
     U.set_local_pose(b.item.unit,row.index,X.from_elements(unpack(row.localBefore)))
    end
   end
   for _,b in ipairs(batches)do identity(b,false);S.World.update_unit(b.item.world,b.item.unit)end
   validate() -- Final check AFTER every shared model refresh.
  end)
  local rollback='not_needed'
  if not ok then
   self.disabled=true;local safe={};local restored=true
   for _,b in ipairs(batches)do if b.written>0 then
    local valid=pcall(identity,b,true)
    if valid then
     safe[#safe+1]=b
     for i=1,b.written do
      local row=b.rows[i]
      local done=pcall(function()identity(b,true);U.set_local_pose(b.item.unit,row.index,X.from_elements(unpack(row.localBefore)))end)
      if not done then restored=false end
     end
    else restored=false end
   end end
   for _,b in ipairs(safe)do
    local done=pcall(function()identity(b,true);S.World.update_unit(b.item.world,b.item.unit)end)
    if not done then restored=false end
   end
   for _,b in ipairs(safe)do for i=1,b.written do
    local row=b.rows[i]
    local checked=pcall(function()
     assert(maximum(row.localBefore,mat(b.item.unit,row.index,false),1,12)<=.000001)
     assert(maximum(row.scaleBefore,local_scale(b.item.unit,row.index),1,3)<=.00002)
     assert(unchanged(row.worldBefore,mat(b.item.unit,row.index,true)))
     assert(unchanged(row.avatarBefore,mat(b.avatar.unit,row.avatarIndex,true)))
    end)
    if not checked then restored=false end
   end end
   rollback=restored and 'verified' or 'incomplete'
  end
  for _,b in ipairs(batches)do for _,row in ipairs(b.rows)do
   if row.localAfter and row.worldAfter then
    local p,r,s=error_metrics(row.worldBefore,row.worldAfter)
    log('event=node trial=%d frame=%d avatar=%d model=%s resource=%s index=%d avatar_index=%d position_error=%.9g linear_error=%.9g scale_error=%.9g before_local=%s after_local=%s before_world=%s after_world=%s',
     self.trials,frame,b.avatar.label,tostring(b.item.sceneLabel or 'unlabeled'),b.item.resource,row.index,row.avatarIndex,
     p,r,s,csv(row.localBefore),csv(row.localAfter),csv(row.worldBefore),csv(row.worldAfter))
   end
  end end
  log('event=result trial=%d frame=%d time=%.9g status=%s models=%d writes=%d rollback=%s reason=%s',
   self.trials,frame,now,ok and 'PASS' or 'FAIL',#batches,writes,rollback,ok and 'none' or tostring(err):gsub('%s','_'))
 end
 return self
end
return M

end)()
-- END SAME MODEL LOCAL ROUNDTRIP
-- BEGIN EXPLICIT ATTACHMENT BISECTION PROBE
local AttachmentProbe=(function()
-- Explicit diagnostic displacement on a uniquely matched test01 Avatar only.
-- Matrices are copied to numbers immediately; rotation and scale are retained.
local M={VERSION='1.2.0'}
local function copy(a)local b={};for i,v in ipairs(a)do b[i]=v end;return b end
local function finite(v)return type(v)=='number'and v==v and math.abs(v)<1e10 end
local function equal(a,b,epsilon)
 for i=1,12 do if math.abs(a[i]-b[i])>(epsilon or 1e-6)then return false end end;return true
end
local function distance(a,b)local d=0;for i=1,3 do d=d+(a[i]-b[i])^2 end;return math.sqrt(d)end
local function inverse_vector(m,v)
 local a,b,c,d,e,f,g,h,i=m[1],m[4],m[7],m[2],m[5],m[8],m[3],m[6],m[9]
 local det=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
 assert(finite(det)and math.abs(det)>1e-8,'singular_parent')
 return {((e*i-f*h)*v[1]+(c*h-b*i)*v[2]+(b*f-c*e)*v[3])/det,
  ((f*g-d*i)*v[1]+(a*i-c*g)*v[2]+(c*d-a*f)*v[3])/det,
  ((d*h-e*g)*v[1]+(b*g-a*h)*v[2]+(a*e-b*d)*v[3])/det}
end
function M.new(S,profile,logger)
 local cfg=profile.attachmentProbe;if not cfg or cfg.enabled~=true then return nil end
 local U,X=S.Unit,S.Matrix4x4
 local self={pending={},epochs=setmetatable({},{__mode='k'}),phases=setmetatable({},{__mode='k'}),validated=setmetatable({},{__mode='k'}),disabled=false,telemetry={}}
 local function note(fmt,...)pcall(logger,'[attach_probe] variant='..cfg.variant..' '..fmt,...)end
 -- A serialized uint32 hash is diagnostic metadata, not an engine name ID.
 -- IdString32 is frame-temporary: keep only names, resolve immediately before
 -- each query, and never retain its userdata in self/profile/closures.
 local resolved={}
 local ready,why=pcall(function()
  assert(S.Application and type(S.Application.string_to_id32)=='function','id_factory_missing')
  local seen={}
  for _,r in ipairs(cfg.nodes)do
   assert(type(r.name)=='string'and #r.name>0 and not r.name:match('^hash_'),'unresolved_node_name')
   assert(finite(r.index)and r.index%1==0 and r.index>=0 and r.index<profile.expectedAvatarNodes,'node_index')
   assert(finite(r.parentIndex)and r.parentIndex%1==0 and r.parentIndex>=0 and r.parentIndex<profile.expectedAvatarNodes and r.parentIndex~=r.index,'parent_index')
   assert(not seen[r.index],'duplicate_node');seen[r.index]=true
   resolved[#resolved+1]=r
  end
 end)
 if not ready then self.disabled=true;note('event=disabled stage=resolve_names reason=%s',tostring(why))end
 local function matrix(unit,node,world)
  assert(type(X.from_elements)=='function','from_elements_missing')
  local fn=world and U.world_pose or U.local_pose;assert(type(fn)=='function','matrix_api_missing')
  local a={X.to_elements(fn(unit,node))};assert(#a==12,'matrix_size')
  for _,v in ipairs(a)do assert(finite(v),'invalid_matrix')end;return a
 end
 local function position(unit,node)
  local m=matrix(unit,node,true);return {m[10],m[11],m[12]}
 end
 local function valid(a)
  if U.alive(a.unit)~=true or U.num_scene_graph_items(a.unit)~=profile.expectedAvatarNodes then return false end
  assert(ready,'node_ids_unresolved')
  assert(type(U.has_node)=='function'and type(U.node)=='function'and type(U.scene_graph_parent)=='function','identity_api_missing')
  local first=not self.validated[a.unit]
  for _,r in ipairs(resolved)do
   if first then note('event=validate_node avatar=%d stage=name_query name=%s index=%d',a.label,r.name,r.index+1)end
   local id=S.Application.string_to_id32(r.name);assert(id~=nil,'id_factory_failed')
   local exists=U.has_node(a.unit,id)
   if exists~=true then
    note('event=validation_mismatch avatar=%d name=%s reason=missing_name expected_index=%d actual_exists=%s',a.label,r.name,r.index+1,tostring(exists));return false
   end
   local index=U.node(a.unit,id)
   if index~=r.index+1 then
    note('event=validation_mismatch avatar=%d name=%s reason=index expected_index=%d actual_index=%s',a.label,r.name,r.index+1,tostring(index));return false
   end
   if first then note('event=validate_node avatar=%d stage=parent_query name=%s index=%d',a.label,r.name,r.index+1)end
   local parent=U.scene_graph_parent(a.unit,r.index+1)
   if parent~=r.parentIndex+1 then
    note('event=validation_mismatch avatar=%d name=%s reason=parent expected_parent=%d actual_parent=%s',a.label,r.name,r.parentIndex+1,tostring(parent));return false
   end
  end
  if first then note('event=validated avatar=%d nodes=%d validation_only=%s',a.label,#resolved,tostring(cfg.validationOnly==true));self.validated[a.unit]=true end
  return true
 end
 local function update(a)S.World.update_unit(a.world,a.unit)end
 local function restore(record,force)
  local a=record.actor;if not valid(a)then return false,'layout_changed'end
  local restored,fresh=0,0
  for _,r in ipairs(record.rows)do
   local current=matrix(a.unit,r.node,false)
   if force or equal(current,r.written)then
    U.set_local_pose(a.unit,r.node,X.from_elements(unpack(r.before)));restored=restored+1
    assert(equal(matrix(a.unit,r.node,false),r.before,2e-5),'restore_readback')
   else fresh=fresh+1 end -- A newer animation pose must not be overwritten.
  end
  if restored>0 then update(a)end
  return true,restored,fresh
 end
 function self:restore_all()
  local dirty={};self.telemetry={}
  for unit,r in pairs(self.pending)do
   local ok,restored,detail=pcall(restore,r,false)
   if not ok then
    self.disabled=true;note('event=restore_failed avatar=%d reason=%s',r.actor.label,tostring(restored))
    -- Keep the record for a later retry/release; no further displacement.
   else
    self.pending[unit]=nil
    if restored then dirty[r.actor.world]=true
    else note('event=restore_skipped avatar=%d reason=%s',r.actor.label,tostring(detail))end
   end
  end
  return dirty
 end
 function self:apply(a,enabled,time,frame,consumers)
  if not enabled or self.disabled then self.epochs[a.unit]=nil;self.phases[a.unit]=nil;self.validated[a.unit]=nil;return false end
  local ok,err=pcall(function()
   assert(valid(a),'avatar_layout_changed')
   if cfg.validationOnly==true then return end
   if not self.epochs[a.unit]then self.epochs[a.unit]=time end
   local phase=math.floor(math.max(0,time-self.epochs[a.unit])/cfg.phaseSeconds)%2
   local transition=self.phases[a.unit]~=phase;self.phases[a.unit]=phase
   if transition then note('event=phase avatar=%d frame=%d time=%.3f state=%s shift_z=%.3f',a.label,frame,time,phase==1 and 'UP'or 'BASE',phase==1 and cfg.worldDelta[3]or 0)end
   if phase==0 then return end
   local record={actor=a,rows={},beforeWorld={}};local selected={}
   for _,r in ipairs(cfg.nodes)do selected[r.index]=true end
   -- Candidate parent/child families stay together. Move each highest selected
   -- ancestor once, so the nested aim marker moves 60 cm, never 120 cm.
   for _,r in ipairs(cfg.nodes)do
    record.beforeWorld[r.index]=position(a.unit,r.index+1)
    if not selected[r.parentIndex]then
     local before=matrix(a.unit,r.index+1,false)
     local delta=inverse_vector(matrix(a.unit,r.parentIndex+1,true),cfg.worldDelta)
     local written=copy(before);for j=1,3 do written[9+j]=written[9+j]+delta[j]end
     record.rows[#record.rows+1]={node=r.index+1,before=before,written=written}
    end
   end
   local nearby={}
   if transition then
    local anchor=position(a.unit,cfg.anchorIndex+1)
    for _,item in ipairs(consumers or {})do
     if #nearby<16 and item.world==a.world and item.kind:match('^weapon')and U.alive(item.unit)==true
       and U.num_scene_graph_items(item.unit)==item.count then
      local safe,row=pcall(function()
       local nodes={};for _,n in ipairs(item.markers or {})do nodes[#nodes+1]={node=n,before=position(item.unit,n)}end
       if #nodes>0 and distance(nodes[1].before,anchor)<3 then return {item=item,nodes=nodes}end
      end)
      if safe and row then nearby[#nearby+1]=row end
     end
    end
   end
   self.pending[a.unit]=record -- Retain before the first engine mutation.
   local applied,reason=pcall(function()
    for _,r in ipairs(record.rows)do U.set_local_pose(a.unit,r.node,X.from_elements(unpack(r.written)))end
    update(a)
    for _,r in ipairs(record.rows)do assert(equal(matrix(a.unit,r.node,false),r.written,2e-5),'write_readback')end
    for _,r in ipairs(cfg.nodes)do
     local p=position(a.unit,r.index+1);local before=record.beforeWorld[r.index];local error=0
     for j=1,3 do error=math.max(error,math.abs(p[j]-before[j]-cfg.worldDelta[j]))end
     assert(error<.002,'world_displacement_readback:'..r.name)
     if transition then note('event=node avatar=%d frame=%d name=%s hash=%u index=%d dx=%.6f dy=%.6f dz=%.6f error=%.6f',
      a.label,frame,r.name,r.hash,r.index+1,p[1]-before[1],p[2]-before[2],p[3]-before[3],error)end
    end
   end)
   if not applied then
    local rolled,result=pcall(restore,record,true)
    if rolled and result then self.pending[a.unit]=nil end
    note('event=rollback avatar=%d verified=%s',a.label,tostring(rolled and result==true))
    error(reason)
   end
   if transition then
    self.telemetry[#self.telemetry+1]={actor=a,frame=frame,nearby=nearby}
    note('event=applied avatar=%d frame=%d nodes=%d roots=%d',a.label,frame,#cfg.nodes,#record.rows)
   end
  end)
  if not ok then self.disabled=true;note('event=disabled avatar=%d reason=%s',a.label,tostring(err));return false end
  return self.pending[a.unit]~=nil
 end
 function self:after_refresh()
  for _,t in ipairs(self.telemetry)do
   for _,c in ipairs(t.nearby)do local item=c.item
    if U.alive(item.unit)==true and U.num_scene_graph_items(item.unit)==item.count then
     for _,n in ipairs(c.nodes)do
      local ok,p=pcall(position,item.unit,n.node)
      if ok then note('event=consumer avatar=%d frame=%d resource=%s kind=%s node=%d dx=%.6f dy=%.6f dz=%.6f owner=unverified',
       t.actor.label,t.frame,tostring(item.resource),item.kind,n.node,p[1]-n.before[1],p[2]-n.before[2],p[3]-n.before[3])end
     end
    end
   end
  end
  self.telemetry={}
 end
 note('event=loaded version=%s nodes=%d phase_seconds=%d shift_z=%.3f validation_only=%s scope=matched_test01_body',M.VERSION,#cfg.nodes,cfg.phaseSeconds,cfg.worldDelta[3],tostring(cfg.validationOnly==true))
 return self
end
return M

end)()
-- END EXPLICIT ATTACHMENT BISECTION PROBE
-- BEGIN NATIVE GRIP ALIGNMENT
local NativeGripAlignment=(function()
-- One-way, opt-in experiment: native grips/wrists follow existing Source bones.
-- Source/model bones are read-only; the legacy adapter must be bypassed.
-- Engine matrices and IdString32 values are frame-temporary. Retain numbers only.
local M={VERSION='1.1.0'}
local function finite(x)return type(x)=='number'and x==x and math.abs(x)<1e10 end
local function copy(a)local b={};for i,v in ipairs(a)do b[i]=v end;return b end
local function difference(a,b)
 local d=0;for i=1,12 do d=math.max(d,math.abs(a[i]-b[i]))end;return d
end
local function distance(a,b)
 local d=0;for i=10,12 do d=d+(a[i]-b[i])^2 end;return math.sqrt(d)
end
local function inverse_vector(m,v)
 local a,b,c,d,e,f,g,h,i=m[1],m[4],m[7],m[2],m[5],m[8],m[3],m[6],m[9]
 local det=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
 assert(finite(det)and math.abs(det)>1e-8,'singular_parent')
 return {((e*i-f*h)*v[1]+(c*h-b*i)*v[2]+(b*f-c*e)*v[3])/det,
  ((f*g-d*i)*v[1]+(a*i-c*g)*v[2]+(c*d-a*f)*v[3])/det,
  ((d*h-e*g)*v[1]+(b*g-a*h)*v[2]+(a*e-b*d)*v[3])/det}
end
local function relative(parent,world)
 local result={}
 for c=0,2 do
  local v=inverse_vector(parent,{world[3*c+1],world[3*c+2],world[3*c+3]})
  for j=1,3 do result[3*c+j]=v[j]end
 end
 local v=inverse_vector(parent,{world[10]-parent[10],world[11]-parent[11],world[12]-parent[12]})
 for j=1,3 do result[9+j]=v[j]end;return result
end
local function desired(source,q,native)
 local n=0;for i=1,4 do assert(finite(q[i]),'invalid_source_rotation');n=n+q[i]^2 end
 assert(n>1e-8,'zero_source_rotation');n=math.sqrt(n)
 local x,y,z,w=q[1]/n,q[2]/n,q[3]/n,q[4]/n
 local m={1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,
  2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,
  2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y,source[10],source[11],source[12]}
 -- Match position/orientation, retaining native world axis lengths so a
 -- Source character scale does not also resize the gun.
 for c=0,2 do
  local s=0;for j=1,3 do s=s+native[3*c+j]^2 end;s=math.sqrt(s)
  assert(finite(s)and s>1e-5 and s<100,'invalid_native_scale')
  for j=1,3 do m[3*c+j]=m[3*c+j]*s end
 end
 return m
end
function M.new(S,profile,logger)
 local cfg=profile.nativeGripAlignment;if not cfg or cfg.enabled~=true then return nil end
 local U,X=S.Unit,S.Matrix4x4
 local self={pending={},samples={},validated={},disabled=false,stats={writes=0,readbacks=0}}
 local function note(fmt,...)pcall(logger,'[grip_align] variant='..tostring(cfg.variant)..' '..fmt,...)end
 local writeChecks={}
 local ready,reason=pcall(function()
  assert(cfg.exclusive==true,'legacy_writes_must_be_excluded')
  assert(profile.armSync~=true and profile.armGripSync~=true,'reverse_arm_solver_enabled')
  assert(not(profile.attachmentProbe and profile.attachmentProbe.enabled),'displacement_probe_enabled')
  assert(not(profile.sceneRoundtrip and profile.sceneRoundtrip.enabled),'roundtrip_writer_enabled')
  assert(cfg.scalePolicy=='preserve-native-world','unsupported_scale_policy')
  assert(type(cfg.pairs)=='table'and #cfg.pairs>0,'missing_pairs')
  local seen={};local checks={}
  for _,r in ipairs(cfg.checks)do
   assert(type(r.name)=='string'and #r.name>0 and not r.name:match('^hash_'),'unresolved_name')
   assert(finite(r.index)and r.index%1==0 and r.index>=0 and r.index<profile.expectedAvatarNodes,'invalid_index')
   assert(finite(r.parentIndex)and r.parentIndex%1==0 and r.parentIndex>=0 and r.parentIndex<profile.expectedAvatarNodes,'invalid_parent')
   assert(not checks[r.index],'duplicate_check');checks[r.index]=r
  end
  for _,p in ipairs(cfg.pairs)do
   assert(p.target.name=='attach_hand_r'or p.target.name=='attach_hand_l'
     or p.target.name=='l_hand'or p.target.name=='l_hand_twist','target_not_native_grip')
   assert(p.rotationMode==nil or p.rotationMode=='source-world' or p.rotationMode=='native-world','invalid_rotation_mode')
   assert(p.target.index<profile.nativeSkeletonNodes and p.source.index>=profile.nativeSkeletonNodes
     and p.source.index<profile.nativeSkeletonNodes+profile.sourceSkeletonNodes,'wrong_direction')
   assert(checks[p.target.index]and checks[p.source.index],'unchecked_pair')
   assert(checks[p.target.index].name==p.target.name and checks[p.source.index].name==p.source.name,'pair_name_mismatch')
   assert(checks[p.target.index].parentIndex==p.target.parentIndex
     and checks[p.source.index].parentIndex==p.source.parentIndex,'pair_parent_mismatch')
   assert(not seen[p.target.index],'duplicate_target');seen[p.target.index]=true
   writeChecks[#writeChecks+1]=checks[p.target.index]
   writeChecks[#writeChecks+1]=assert(checks[checks[p.target.index].parentIndex],'unchecked_target_parent')
  end
  local obs=cfg.consumerObservation
  if obs and obs.enabled==true then
   for _,key in ipairs({'rightSourceIndex','leftSourceIndex','leftWristIndex'})do
    assert(checks[obs[key]] and obs[key]>=profile.nativeSkeletonNodes
      and obs[key]<profile.nativeSkeletonNodes+profile.sourceSkeletonNodes,'unchecked_consumer_anchor')
   end
   assert(finite(obs.maxDistance)and obs.maxDistance>0 and obs.maxDistance<=10,'invalid_consumer_distance')
   assert(finite(obs.maxUnits)and obs.maxUnits%1==0 and obs.maxUnits>0 and obs.maxUnits<=32,'invalid_consumer_limit')
  end
 end)
 if not ready then self.disabled=true;note('event=disabled stage=config reason=%s',tostring(reason))end
 local function matrix(a,index,world)
  local fn=world and U.world_pose or U.local_pose
  local m={X.to_elements(fn(a.unit,index+1))};assert(#m==12,'invalid_matrix_size')
  for _,v in ipairs(m)do assert(finite(v),'invalid_matrix')end;return m
 end
 local function validate(a,checks)
  if a.layoutInvalid or U.alive(a.unit)~=true or U.num_scene_graph_items(a.unit)~=profile.expectedAvatarNodes then return false end
  for _,r in ipairs(checks)do
   local id=S.Application.string_to_id32(r.name)
   if U.has_node(a.unit,id)~=true or U.node(a.unit,id)~=r.index+1
     or U.scene_graph_parent(a.unit,r.index+1)~=r.parentIndex+1 then
    note('event=validation_mismatch avatar=%d name=%s index=%d parent=%d',a.label,r.name,r.index+1,r.parentIndex+1);return false
   end
  end
  return true
 end
 local function consumer_snapshot(a,consumers)
  local obs=cfg.consumerObservation
  if not obs or obs.enabled~=true then return {}end
  local anchor=matrix(a,obs.rightSourceIndex,true);local result={}
  for _,item in ipairs(consumers or {})do
   if #result<(obs.maxUnits or 12) and item.world==a.world and item.kind:match('^weapon')
     and U.alive(item.unit)==true and U.num_scene_graph_items(item.unit)==item.count then
    local ok,value=pcall(function()
     local nodes={};local temp={unit=item.unit}
     for _,name in ipairs({'IK_left','IK_right'})do
      local id=S.Application.string_to_id32(name)
      if U.has_node(item.unit,id)==true then
       local index=U.node(item.unit,id)
       assert(type(index)=='number'and index%1==0 and index>=1 and index<=item.count,'invalid_consumer_index')
       nodes[#nodes+1]={name=name,index=index,worldPose=matrix(temp,index-1,true)}
      end
     end
     if #nodes>0 and distance(nodes[1].worldPose,anchor)<(obs.maxDistance or 3)then return {item=item,nodes=nodes}end
    end)
    if ok and value then result[#result+1]=value
    elseif not ok then note('event=consumer_unavailable resource=%s stage=pre_write reason=%s',tostring(item.resource),tostring(value))end
   end
  end
  return result
 end
 local function observe_consumers(record)
  if not record.nearby or #record.nearby==0 then return end
  local obs=cfg.consumerObservation;local a=record.actor
  local left=matrix(a,obs.leftSourceIndex,true);local right=matrix(a,obs.rightSourceIndex,true)
  local wrist=matrix(a,obs.leftWristIndex,true)
  for candidateIndex,candidate in ipairs(record.nearby)do local item=candidate.item
   if U.alive(item.unit)==true and U.num_scene_graph_items(item.unit)==item.count then
    for _,node in ipairs(candidate.nodes)do
     local ok,err=pcall(function()
      local id=S.Application.string_to_id32(node.name)
      assert(U.has_node(item.unit,id)==true and U.node(item.unit,id)==node.index,'consumer_identity_changed')
      local actual=matrix({unit=item.unit},node.index-1,true)
      note('event=consumer avatar=%d frame=%d candidate=%d resource=%s kind=%s name=%s index=%d dx=%.6f dy=%.6f dz=%.6f source_l_before_m=%.6f source_l_m=%.6f source_r_m=%.6f wrist_l_m=%.6f owner=unverified phase=post_refresh',
       a.label,record.frame,candidateIndex,tostring(item.resource),item.kind,node.name,node.index,
       actual[10]-node.worldPose[10],actual[11]-node.worldPose[11],actual[12]-node.worldPose[12],
       distance(node.worldPose,left),distance(actual,left),distance(actual,right),distance(actual,wrist))
     end)
     if not ok then note('event=consumer_unavailable resource=%s reason=%s',tostring(item.resource),tostring(err))end
    end
   end
  end
 end
 local function restore(record,force)
  local a=record.actor
  if not validate(a,writeChecks)then return false,'layout_changed'end
  local count,fresh=0,0
  for _,r in ipairs(record.rows)do
   local current=matrix(a,r.index,false)
   if force or difference(current,r.written)<2e-5 then
    U.set_local_pose(a.unit,r.index+1,X.from_elements(unpack(r.before)));count=count+1
    assert(difference(matrix(a,r.index,false),r.before)<2e-5,'restore_readback')
   else fresh=fresh+1 end
  end
  if count>0 then S.World.update_unit(a.world,a.unit)end
  return true,count,fresh
 end
 function self:restore_all(frame)
  local dirty={};self.samples={}
  for unit,record in pairs(self.pending)do
   local ok,valid,count,fresh=pcall(restore,record,false)
   if not ok then
    self.disabled=true;note('event=restore_failed avatar=%d reason=%s',record.actor.label,tostring(valid))
   else
    self.pending[unit]=nil
    if valid then
     if count>0 then dirty[record.actor.world]=true end
     if record.diagnostic then note('event=next_callback avatar=%d frame=%d retained=%d replaced=%d replacement_origin=unknown',record.actor.label,frame or -1,count,fresh)end
    else note('event=restore_skipped avatar=%d reason=%s',record.actor.label,tostring(count))end
   end
  end
  return dirty
 end
 function self:apply(a,enabled,frame,consumers)
  if not enabled or self.disabled then self.validated[a.unit]=nil;return false end
  local ok,err=pcall(function()
   assert(ready and validate(a,cfg.checks),'avatar_layout_changed')
   assert(self.pending[a.unit]==nil,'previous_write_pending')
   local first=not self.validated[a.unit]
   local diagnostic=first or frame-self.validated[a.unit]>=(cfg.logFrames or 120)
   if diagnostic then self.validated[a.unit]=frame end
   local record={actor=a,frame=frame,rows={},sources={},children={},diagnostic=diagnostic}
   -- Snapshot Source anchors and every native input before writing.
   for _,r in ipairs(cfg.watchSources)do
    record.sources[#record.sources+1]={spec=r,localPose=matrix(a,r.index,false),worldPose=matrix(a,r.index,true)}
   end
   for _,r in ipairs(cfg.preserveChildren or {})do record.children[#record.children+1]={spec=r,localPose=matrix(a,r.index,false)}end
   for _,p in ipairs(cfg.pairs)do
    local before=matrix(a,p.target.index,false)
    local native=matrix(a,p.target.index,true)
    local src=matrix(a,p.source.index,true)
    local world
    if p.rotationMode=='native-world'then
     -- Restore the preceding override before this read. Preserve the game's
     -- current aiming basis exactly; only the position follows the Source bone.
     world=copy(native);for j=10,12 do world[j]=src[j]end
    else
     local q={S.Quaternion.to_elements(U.world_rotation(a.unit,p.source.index+1))}
     world=desired(src,q,native)
    end
    local target=relative(matrix(a,p.target.parentIndex,true),world)
    for _,v in ipairs(target)do assert(finite(v),'invalid_output')end
    record.rows[#record.rows+1]={index=p.target.index,name=p.target.name,source=p.source.name,before=before,written=target,desired=world,beforeError=distance(native,src),rotationMode=p.rotationMode or 'source-world'}
   end
   if diagnostic and cfg.consumerObservation and cfg.consumerObservation.enabled then
    -- Read-only diagnostics are optional. A disappearing consumer must not
    -- prevent an otherwise valid native alignment transaction.
    local observed,value=pcall(consumer_snapshot,a,consumers)
    if observed then
     record.nearby=value;note('event=consumer_scan avatar=%d frame=%d nearby=%d owner=unverified',a.label,frame,#value)
    else note('event=consumer_unavailable avatar=%d stage=pre_write reason=%s',a.label,tostring(value))end
   end
   self.pending[a.unit]=record
   local applied,why=pcall(function()
    for _,r in ipairs(record.rows)do
     U.set_local_pose(a.unit,r.index+1,X.from_elements(unpack(r.written)));self.stats.writes=self.stats.writes+1
    end
    S.World.update_unit(a.world,a.unit)
    for _,r in ipairs(record.rows)do
     local actual=matrix(a,r.index,true)
     assert(difference(matrix(a,r.index,false),r.written)<2e-5,'local_readback')
     assert(difference(actual,r.desired)<.002,'world_readback')
     if diagnostic then note('event=aligned avatar=%d frame=%d target=%s source=%s before_m=%.6f after_m=%.6f matrix_error=%.8f rotation=%s',a.label,frame,r.name,r.source,r.beforeError,distance(actual,r.desired),difference(actual,r.desired),r.rotationMode)end
    end
    for _,r in ipairs(record.sources)do
     assert(difference(matrix(a,r.spec.index,false),r.localPose)<2e-5,'source_local_changed:'..r.spec.name)
     assert(difference(matrix(a,r.spec.index,true),r.worldPose)<.002,'source_world_changed:'..r.spec.name)
    end
    for _,r in ipairs(record.children)do assert(difference(matrix(a,r.spec.index,false),r.localPose)<2e-5,'aim_child_local_changed')end
   end)
   if not applied then
    local rolled,valid=pcall(restore,record,true)
    if rolled and valid then self.pending[a.unit]=nil end
    note('event=rollback avatar=%d verified=%s',a.label,tostring(rolled and valid==true));error(why)
   end
   self.stats.readbacks=self.stats.readbacks+1
   self.samples[#self.samples+1]=record
   if first then note('event=validated avatar=%d pairs=%d source_read_only=true legacy_writes=false',a.label,#cfg.pairs)end
  end)
  if not ok then self.disabled=true;note('event=disabled avatar=%d reason=%s',a.label,tostring(err));return false end
  return true
 end
 function self:after_refresh()
  for _,record in ipairs(self.samples)do
   local a=record.actor
   local ok,err=pcall(function()
    assert(validate(a,cfg.checks),'post_refresh_layout_changed')
    local gap,sourceChange,aimChange=0,0,0
    for _,r in ipairs(record.rows)do gap=math.max(gap,difference(matrix(a,r.index,true),r.desired))end
    for _,r in ipairs(record.sources)do sourceChange=math.max(sourceChange,difference(matrix(a,r.spec.index,false),r.localPose),difference(matrix(a,r.spec.index,true),r.worldPose))end
    for _,r in ipairs(record.children)do aimChange=math.max(aimChange,difference(matrix(a,r.spec.index,false),r.localPose))end
    if record.diagnostic or gap>.002 or sourceChange>.002 or aimChange>2e-5 then
     note('event=post_refresh avatar=%d frame=%d target_matrix_error=%.8f source_matrix_change=%.8f aim_local_change=%.8f',a.label,record.frame,gap,sourceChange,aimChange)
    end
    assert(sourceChange<.002,'post_refresh_source_changed')
    assert(aimChange<2e-5,'post_refresh_aim_local_changed')
    assert(gap<.002,'post_refresh_target_overwritten')
   end)
   if not ok then self.disabled=true;note('event=disabled avatar=%d stage=post_refresh reason=%s',a.label,tostring(err))end
   if ok and record.diagnostic then
    local observed,why=pcall(observe_consumers,record)
    if not observed then note('event=consumer_unavailable reason=%s',tostring(why))end
   end
  end
  self.samples={}
 end
 note('event=loaded version=%s mode=source_to_native pairs=%d exclusive=true scale=preserve_native_world',M.VERSION,#(cfg.pairs or {}))
 return self
end
return M

end)()
-- END NATIVE GRIP ALIGNMENT
local M={VERSION='0.12.1'}
local function mul(a,b)
 local x,y,z,w=unpack(a);local X,Y,Z,W=unpack(b)
 return {w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z}
end
local function inv(a)return {-a[1],-a[2],-a[3],a[4]} end
local function rot(q,p)local r=mul(mul(q,{p[1],p[2],p[3],0}),inv(q));return {r[1],r[2],r[3]} end
local function relative(a,b)
 local p={};for i=1,3 do p[i]=b.p[i]-a.p[i] end
 return {p=rot(inv(a.q),p),q=mul(inv(a.q),b.q)}
end
local function compose(a,b)
 local p=rot(a.q,b.p);for i=1,3 do p[i]=p[i]+a.p[i] end
 return {p=p,q=mul(a.q,b.q)}
end
local function finite(v)return type(v)=='number' and v==v and math.abs(v)<1e12 end
local function valid(p)
 if not p then return false end
 for _,v in ipairs(p.p) do if not finite(v) then return false end end
 local n=0;for _,v in ipairs(p.q) do if not finite(v) then return false end;n=n+v*v end
 return math.abs(n-1)<.002
end
local function close(a,b)
 if not valid(a) or not valid(b) then return false end
 local d=0;for i=1,3 do d=d+(a.p[i]-b.p[i])^2 end
 local q=0;for i=1,4 do q=q+a.q[i]*b.q[i] end
 return d<.000025 and math.abs(q)>.9999 -- 5 mm and about 1.6 degrees
end
M.relative=relative;M.compose=compose;M.close=close

local function add(a,b)return {a[1]+b[1],a[2]+b[2],a[3]+b[3]}end
local function sub(a,b)return {a[1]-b[1],a[2]-b[2],a[3]-b[3]}end
local function scale(a,s)return {a[1]*s,a[2]*s,a[3]*s}end
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
local function length(a)return math.sqrt(dot(a,a))end
local function normal(a,fallback)local n=length(a);if n<1e-10 then return fallback or {1,0,0}end;return scale(a,1/n)end
local function qnormal(q)local n=0;for i=1,4 do n=n+q[i]*q[i]end;n=math.sqrt(n);assert(n>1e-10,'zero arm quaternion');return {q[1]/n,q[2]/n,q[3]/n,q[4]/n}end
local function axisangle(axis,angle)local s=math.sin(angle/2);return {axis[1]*s,axis[2]*s,axis[3]*s,math.cos(angle/2)}end
local function fromto(a,b)
 a=normal(a);b=normal(b);local d=math.max(-1,math.min(1,dot(a,b)))
 if d < -1+1e-10 then
  local seed=math.abs(a[1])<.8 and {1,0,0} or {0,1,0};local axis=normal(cross(a,seed));return {axis[1],axis[2],axis[3],0}
 end
 local c=cross(a,b);return qnormal({c[1],c[2],c[3],1+d})
end
local function fitframe(q,offset,secondary,direction)
 if length(direction)<1e-8 then return q end
 local swing=fromto(rot(q,offset),direction);local axis=normal(direction)
 local finish=rot(q,secondary);local start=rot(swing,finish)
 start=sub(start,scale(axis,dot(start,axis)));finish=sub(finish,scale(axis,dot(finish,axis)))
 if math.min(length(start),length(finish))<1e-8 then return qnormal(mul(swing,q))end
 start=normal(start);finish=normal(finish)
 local roll=math.atan2(dot(cross(start,finish),axis),dot(start,finish))
 return qnormal(mul(axisangle(axis,roll),mul(swing,q)))
end

-- Drive the Source-only arm from this avatar's native, post-IK hand pose.
-- Native joints, controllers and weapon transforms are read-only inputs.
function M.grip_target(grip,chain,parentScale)
 local q=qnormal(mul(grip.q,inv(chain.sourceGripRotation)))
 return {p=sub(grip.p,rot(q,scale(chain.sourceGripOffset,parentScale or 1))),q=q}
end
function M.solve_arm(root,upper,forearm,hand,parent,chain,state,dt,parentScale,desiredHandRotation)
 parentScale=parentScale or 1;assert(finite(parentScale) and parentScale>.0001,'invalid arm parent scale')
 local uq=qnormal(mul(upper.q,chain.upperCalibration));local fq=qnormal(mul(forearm.q,chain.forearmCalibration))
 local first=scale(rot(uq,chain.upperOffset),parentScale);local second=scale(rot(fq,chain.forearmOffset),parentScale)
 local l1,l2=length(first),length(second);assert(l1>1e-5 and l2>1e-5,'zero arm length')
 local ray=sub(hand.p,root.p);local distance=length(ray);local direction=normal(ray,normal(first))
 if chain.armFrame=='reference' then
  uq=fitframe(uq,chain.upperOffset,chain.hingeAxis,sub(forearm.p,upper.p))
  fq=fitframe(fq,chain.forearmOffset,chain.forearmHingeAxis,sub(hand.referencePosition or hand.p,forearm.p))
  first=scale(rot(uq,chain.upperOffset),parentScale);second=scale(rot(fq,chain.forearmOffset),parentScale)
  -- Keep the accepted arm frame. Bend the forearm within its existing plane,
  -- then swing the whole chain toward the contact. No independent axial roll
  -- is added to force every pose onto the bind pose's hinge hemisphere.
  local reach=math.max(math.abs(l1-l2)+1e-7,math.min(l1+l2-1e-7,distance))
  local plane=cross(first,second)
  if length(plane)<l1*l2*1e-5 then plane=rot(uq,chain.hingeAxis)end
  local input=math.acos(math.max(-1,math.min(1,dot(first,second)/(l1*l2))))
  local flex=math.acos(math.max(-1,math.min(1,(reach*reach-l1*l1-l2*l2)/(2*l1*l2))))
  local elbow=axisangle(normal(plane),flex-input)
  local bent=rot(elbow,second);local swing=fromto(add(first,bent),direction)
  local firstTarget=rot(swing,first)
  local rootTarget={p=root.p,q=qnormal(mul(swing,uq))}
  local midTarget={p=add(root.p,firstTarget),q=qnormal(mul(swing,mul(elbow,fq)))}
  local handTarget={p=add(root.p,add(firstTarget,rot(swing,bent))),q=qnormal(desiredHandRotation or mul(hand.q,chain.handCalibration))}
  local result={relative(parent,rootTarget),relative(rootTarget,midTarget),relative(midTarget,handTarget)}
  for _,p in ipairs(result)do p.p=scale(p.p,1/parentScale)end
  return result,math.abs(distance-reach)
 end
 local plane=cross(first,second)
 if length(plane)<l1*l2*1e-5 then plane=rot(uq,chain.hingeAxis)end
 plane=rot(fromto(add(first,second),direction),normal(plane))
 local bend=normal(cross(direction,plane))
 if state.pole then
  local previous=rot(parent.q,state.pole);previous=sub(previous,scale(direction,dot(previous,direction)))
  if length(previous)>1e-6 then
   previous=normal(previous);local cosine=math.max(-1,math.min(1,dot(previous,bend)))
   if cosine<0 and dot(first,second)/(l1*l2)>.999 then bend=scale(bend,-1);cosine=-cosine end
   local angle=math.atan2(dot(cross(previous,bend),direction),cosine)
   local limit=math.max(0,dt)*4*math.pi;angle=math.max(-limit,math.min(limit,angle))
   bend=add(scale(previous,math.cos(angle)),scale(cross(direction,previous),math.sin(angle)))
  end
 end
 state.pole=rot(inv(parent.q),bend)
 local reach=math.max(math.abs(l1-l2)+1e-7,math.min(l1+l2-1e-7,distance))
 local projection=(reach*reach+l1*l1-l2*l2)/(2*reach)
 local height=math.sqrt(math.max(0,l1*l1-projection*projection))
 local firstTarget=add(scale(direction,projection),scale(bend,height))
 local secondTarget=sub(scale(direction,reach),firstTarget)
 local swing=fromto(first,firstTarget);local axis=normal(firstTarget)
 local start=rot(swing,rot(uq,chain.hingeAxis));start=normal(sub(start,scale(axis,dot(start,axis))))
 local finish=normal(cross(firstTarget,secondTarget))
 local roll=math.atan2(dot(cross(start,finish),axis),dot(start,finish))
 local delta=qnormal(mul(axisangle(axis,roll),swing))
 local rootTarget={p=root.p,q=qnormal(mul(delta,uq))}
 local midTarget={p=add(root.p,firstTarget),q=qnormal(mul(fromto(rot(delta,second),secondTarget),mul(delta,fq)))}
 local handTarget={p=add(root.p,scale(direction,reach)),q=qnormal(mul(hand.q,chain.handCalibration))}
 local result={relative(parent,rootTarget),relative(rootTarget,midTarget),relative(midTarget,handTarget)}
 for _,p in ipairs(result)do p.p=scale(p.p,1/parentScale)end
 return result,math.abs(distance-reach)
end

-- Source mstudioquatinterpbone_t: angular trigger weights, hemisphere-aligned
-- quaternion blending. Inputs/outputs use the unchanged Source local axes.
function M.quatinterp(control,procedure)
 local weights={};local total=0;local reference=nil
 for i,t in ipairs(procedure.triggers) do
  local dot=0;for j=1,4 do dot=dot+control[j]*t.trigger[j] end
  local w=math.max(0,1-2*math.acos(math.min(1,math.abs(dot)))*t.invTolerance)
  weights[i]=w;total=total+w
  if w>0 and not reference then reference=t.rotation end
 end
 -- Uncovered orientations keep this helper's bind, never a zero quaternion.
 if total<1e-8 then return procedure.bind end
 local p={0,0,0};local q={0,0,0,0}
 for i,t in ipairs(procedure.triggers) do
  local w=weights[i]/total;local dot=0
  for j=1,4 do dot=dot+reference[j]*t.rotation[j] end
  local sign=dot<0 and -1 or 1
  for j=1,3 do p[j]=p[j]+w*t.position[j] end
  for j=1,4 do q[j]=q[j]+w*sign*t.rotation[j] end
 end
 local n=0;for j=1,4 do n=n+q[j]*q[j] end;n=math.sqrt(n)
 assert(n>1e-8,'degenerate Source quaternion interpolation')
 for j=1,4 do q[j]=q[j]/n end
 return {p=p,q=q}
end

function M.new(S,profile,logger,options)
 assert(type(profile.modelLayouts)=='table','attachment profile lacks final modelLayouts; regenerate it from the exported model patches')
 options=options or {};local self={S=S,profile=profile,avatars={},armor={},models={},lastScan=-1000,mode=profile.diagnosticMode or options.mode or 'apply',
  logger=logger or function()end,stats={writes=0,ambiguous=0,active=0,readbacks=0,consumerRefreshes=0},lastTime=nil,consumers={},dirtyWorlds={}}
 local gripAlignment=NativeGripAlignment.new(S,profile,self.logger)
 local slots={};local selectors={};local minimumCount=nil;local avatarChecks={};local checked={};local handRows={}
 -- Leaving a controller's local pose untouched does not preserve its world
 -- pose when we move its parent. Keep every adapter-owned ancestor native.
 -- This also avoids compensating an unanimated child repeatedly each frame.
 local byIndex,protectedParents={},{}
 for _,row in ipairs(profile.vpk) do byIndex[row.index]=row end
 if profile.protectControllerParents~=false then
  for _,row in ipairs(profile.vpk) do if row.policy=='original-world' then
   local cursor=byIndex[row.parentIndex];local seen={}
   while cursor and not seen[cursor.index] do
    seen[cursor.index]=true;protectedParents[cursor.index]=true
    cursor=byIndex[cursor.parentIndex]
   end
  end end
 end
 self.protectedParents=protectedParents
 local function addModels(groups,selectsSlot)
 for kind,ids in pairs(groups) do for _,id in ipairs(ids) do
  assert(not slots[id],'duplicate attachment model resource: '..id)
  local layout=profile.modelLayouts[id]
  assert(layout and type(layout.nodeCount)=='number' and type(layout.signature)=='table','target model layout missing: '..id)
  assert(#layout.signature==#profile.signature,'model/avatar signature length mismatch: '..id)
  for i,row in ipairs(layout.signature) do
   assert(row.name==profile.signature[i].name and type(row.index)=='number' and row.index>=0 and row.index<layout.nodeCount,'invalid final model signature: '..id)
  end
  slots[id]=kind;selectors[id]=selectsSlot;minimumCount=math.min(minimumCount or layout.nodeCount,layout.nodeCount)
 end end
 end
 addModels(profile.targets,true)
 -- Split arm/hip/leg Units consume the same avatar, but must not select the
 -- entire body profile on their own. Keep the existing torso/head selectors.
 addModels(profile.consumerTargets or {},false)
 local function avatarCheck(name,index)
  if name and not checked[name] then checked[name]=true;avatarChecks[#avatarChecks+1]={name=name,index=index} end
 end
 for _,row in ipairs(profile.signature) do avatarCheck(row.name,row.index) end
 for _,row in ipairs(profile.jointProcedures or {}) do
  avatarCheck(row.name,row.index);avatarCheck(row.controlName,row.controlIndex);avatarCheck(row.parentName,row.parentIndex)
 end
 for _,chain in ipairs(profile.armChains or {}) do
  for _,node in ipairs(chain.nodes) do avatarCheck(node.name,node.index)end
 end
 for _,row in ipairs(profile.vpk) do
  avatarCheck(row.referenceName,row.referenceIndex);avatarCheck(row.standardName,row.index)
  if row.policy=='source-reference' or row.policy=='source-blended-reference' then
   avatarCheck(row.sourceReferenceName,row.sourceReferenceIndex)
  end
  if row.policy=='source-blended-reference' then
   assert(type(row.configuredAnchorIndex)=='number' and row.configuredAnchorName,'configured attachment anchor missing')
   avatarCheck(row.configuredAnchorName,row.configuredAnchorIndex)
   avatarCheck(row.sourceAnchorName,row.sourceAnchorIndex+row.sourceIndexOffset)
  end
  if row.standardName=='attach_hand_l' then handRows.l=row elseif row.standardName=='attach_hand_r' then handRows.r=row end
 end
 local function alive(unit)return unit~=nil and S.Unit.alive(unit)==true end
 local function visible(unit)
  -- Mesh visibility is an explicit engine flag, not camera distance. Hidden
  -- wardrobe/old equipment must not keep the body profile selected. Read mesh
  -- handles only in this call; they are not safe to retain across frames.
  if not (S.Mesh and S.Mesh.visibility and S.Unit.mesh and S.Unit.num_meshes) then return nil end
  local count=S.Unit.num_meshes(unit)
  if type(count)~='number' or count<1 or count>128 then return nil end
  local unknown=false
  for i=1,count do
   local mesh=S.Unit.mesh(unit,i)
   local v=mesh and S.Mesh.visibility(mesh)
   if v==true then return true end
   if v~=false then unknown=true end
  end
  if unknown then return nil end;return false
 end
 local function verify(unit,count,rows,prior)
  local missing=nil
  for _,row in ipairs(rows) do
   local id=S.Application.string_to_id32(row.name)
   if S.Unit.has_node(unit,id)==true then
    local i=S.Unit.node(unit,id)
    -- Unit.node may return an arbitrary index for an absent name; only use it
    -- after has_node and require the exact index exported for this resource.
    if type(i)~='number' or i%1~=0 or i<1 or i>count or i~=row.index+1 then return false,'index_mismatch:'..row.name end
   else missing=missing or row.name end
  end
  if missing then
   -- Existing instances may briefly fail has_node without rebuilding. A
   -- bounded grace uses only previously verified indices, and ownership is
   -- still checked from all six live poses every frame. Never admit a new
   -- instance this way or keep a changed count/resource/world alive.
   local misses=prior and (prior.missingScans or 0)+1 or 0
   if prior and misses<=(options.nameMissGraceScans or 2) then prior.missingScans=misses;return true,'cached_name_miss:'..missing end
   return false,'missing_name:'..missing
  end
  if prior then prior.missingScans=0 end
  return true
 end
 local function pose(unit,index)
  local p={S.Vector3.to_elements(S.Unit.world_position(unit,index))}
  local q={S.Quaternion.to_elements(S.Unit.world_rotation(unit,index))}
  local result={p=p,q=q};assert(#p==3 and #q==4 and valid(result),'invalid attachment pose')
  return result
 end
 local function resource(unit)
  local ok,id=pcall(S.Unit.resource_name,unit);if not ok then return nil end
  local ids=S.IdString64;local formatter=ids and (ids.to_hex or ids.to_string)
  local formatted,text=false,nil
  if formatter then formatted,text=pcall(formatter,id) end
  if not formatted then text=tostring(id) end
  text=tostring(text):lower()
  return text:match('^([0-9a-f]+)$') or text:match('^0x([0-9a-f]+)$') or text:match('#id%[([0-9a-f]+)%]')
 end
 local function signature(rows)
  local result={};for i,row in ipairs(rows) do result[i]=row.index+1 end;return result
 end
 local function emit(key,message,...)
  if self[key]~=message then self[key]=message;self.logger('[attachments] '..message,...) end
 end
 function self:scan(frame)
  local found,armor,models,consumers={},{},{},{};local rejected={};local cached=0;local lastReason='none'
  local function reject(reason,detail)
   rejected[reason]=(rejected[reason] or 0)+1;lastReason=reason..(detail and ':'..detail or '')
  end
  for _,world in ipairs(S.Application.worlds() or {}) do
   local units=S.World.units(world) or {};local avatars=S.World.units_by_resource(world,'content/fac_helldivers/cha_avatar/avatar_helldiver') or {}
   for _,unit in ipairs(avatars) do
    if alive(unit) and S.Unit.has_animation_state_machine(unit)==true then
     local count=S.Unit.num_scene_graph_items(unit)
     if count~=profile.expectedAvatarNodes then
      if self.avatars[unit] then self.avatars[unit].layoutInvalid=true end
      reject('avatar_nodes',tostring(count))
     else
      local prior=self.avatars[unit];if prior and prior.world~=world then prior=nil end
      local good,reason=verify(unit,count,avatarChecks,prior)
      if good then
       if reason then cached=cached+1 end
       if not prior then self.avatarSequence=(self.avatarSequence or 0)+1 end
       found[unit]=prior or {unit=unit,world=world,signature=signature(profile.signature),stable={body=0,head=0},active=false}
       found[unit].label=found[unit].label or self.avatarSequence
      else
       if prior then prior.layoutInvalid=true end
       reject('avatar_signature',reason)

      end
     end
    end
   end
   local hasAvatar=false;for _,a in pairs(found) do if a.world==world then hasAvatar=true;break end end
   if hasAvatar then
    for _,unit in ipairs(units) do
     if alive(unit) and not found[unit] then
      local count=S.Unit.num_scene_graph_items(unit)
      -- Ordinary world props have only a handful of nodes. Avoid their
      -- resource-name conversion, while retaining diagnostics for changed rigs.
      local id=(type(count)=='number' and count>=math.min(16,minimumCount or 16)) and resource(unit) or nil
      local slot=id and slots[id]
      if slot then
       local layout=profile.modelLayouts[id]
       if count~=layout.nodeCount then reject('model_nodes',id..' expected='..layout.nodeCount..' actual='..tostring(count))
       else
        local prior=self.models[unit]
        if prior and (prior.world~=world or prior.count~=count or prior.resource~=id) then prior=nil end
        local good,reason=verify(unit,count,layout.signature,prior)
        if good then
         if reason then cached=cached+1 end
         local item=prior or {unit=unit,world=world,slot=slot,signature=signature(layout.signature),count=count,resource=id,missingScans=0,
          selectsSlot=selectors[id]}
         armor[#armor+1]=item;models[unit]=item
        else reject('model_signature',id..' '..reason) end
       end
      elseif type(count)=='number' and count>=3 and count<=192 then
       -- Two serialized weapon IK markers identify a refresh candidate. This
       -- does not establish ownership and never authorizes pose writes/relink.
       local kind=(id=='a9936cbe561e8180' and 'sample_pouch') or (id=='1c8764d62e12925a' and 'intelpad')
       local markers={}
       -- Opt-in, exact-resource layouts for simple components without a skeleton.
       -- This only refreshes their existing links; it establishes no ownership.
       local componentId=id
       if profile.simpleWeaponComponents and not componentId then
        -- The normal discovery fast path skips resource names below 16 nodes.
        -- Resolve only counts explicitly present in the opt-in layouts.
        for _,spec in pairs(profile.simpleWeaponComponents)do
         if count==spec.count then componentId=resource(unit);break end
        end
       end
       local component=profile.simpleWeaponComponents and componentId and profile.simpleWeaponComponents[componentId]
       if not kind and component and count==component.count then
        local matched=true;local markerVerified=false
        for _,spec in ipairs(component.signature)do
         local hash=S.Application.string_to_id32(spec.name)
         if S.Unit.has_node(unit,hash)~=true or S.Unit.node(unit,hash)~=spec.index+1 then matched=false;break end
         if spec.name=='game_mesh'and spec.index==component.markerIndex then markerVerified=true end
        end
        if matched and markerVerified then id=componentId;kind='weapon_magazine';markers={component.markerIndex+1}end
       end
       if not kind then
        for _,name in ipairs({'IK_left','IK_right'}) do
         local hash=S.Application.string_to_id32(name)
         if S.Unit.has_node(unit,hash)==true then
          local n=S.Unit.node(unit,hash)
          if type(n)=='number' and n>=1 and n<=count then markers[#markers+1]=n end
         end
        end
        if #markers==2 then kind='weapon'
        elseif S.Unit.has_node(unit,S.Application.string_to_id32('skeleton'))==true
           and S.Unit.has_node(unit,S.Application.string_to_id32('game_mesh'))==true then
         -- Serialized weapon components are separate Units without hand IK:
         -- muzzle (12 nodes), optic (12), magazine (17/18), underbarrel (14).
         -- A root weapon refresh does not update their cached linked graphs.
         -- Markers classify graph-refresh candidates only, never ownership.
         markers={}
         for _,spec in ipairs({{'IK_left','weapon_grip'},{'muzzle','weapon_muzzle'},{'attach_offset','weapon_optic'},
                               {'bullet_01','weapon_magazine'},{'laser','weapon_underbarrel'}}) do
          local hash=S.Application.string_to_id32(spec[1])
          if S.Unit.has_node(unit,hash)==true then
           local n=S.Unit.node(unit,hash)
           if type(n)=='number' and n>=1 and n<=count then
            kind=spec[2];markers={n};break
           end
          end
         end
        end
       end
       if kind then consumers[#consumers+1]={unit=unit,world=world,count=count,resource=id or resource(unit),kind=kind,markers=markers} end
      end
     end
    end
   end
  end
  -- Live old avatars can leave the scanned world during transitions. Restore
  -- them before releasing references; destroyed/rebuilt graphs are never written.
  for unit,a in pairs(self.avatars) do if not found[unit] and a.active then self:restore(a) end end
  self.avatars=found;self.armor=armor;self.models=models;self.consumers=consumers;self.lastScan=frame
  -- World enumeration need not put a gun before its components. All roots
  -- must finish before refreshing their existing linked child graphs.
  table.sort(self.consumers,function(a,b)
   local ar=a.kind:match('^weapon_') and 2 or 1
   local br=b.kind:match('^weapon_') and 2 or 1
   return ar<br
  end)
  local n=0;for _ in pairs(found) do n=n+1 end
  emit('discovery','avatars='..n..' matching armor='..#armor..' mode='..self.mode..' variant='..tostring(profile.revision or 'unspecified'))
  local keys={};for key in pairs(rejected) do keys[#keys+1]=key end;table.sort(keys)
  local parts={};for _,key in ipairs(keys) do parts[#parts+1]=key..'='..rejected[key] end
  emit('diagnosis','scan phase=render cached_name_miss='..cached..' rejected='..(#parts==0 and 'none' or table.concat(parts,','))..' detail='..lastReason)
 end
 function self:refresh_consumers()
  local updated=0;local diagnostic=(self.frame or 0)-(self.lastConsumerDiagnostic or -600)>=600
  for _,item in ipairs(self.consumers) do
   if self.dirtyWorlds[item.world] and alive(item.unit) and S.Unit.num_scene_graph_items(item.unit)==item.count
      and resource(item.unit)==item.resource and visible(item.unit)~=false then
    local before={};if diagnostic then for i,n in ipairs(item.markers) do before[i]=pose(item.unit,n) end end
    -- Re-evaluate the EXISTING cross-Unit scene graph link after its avatar
    -- changed. No guessed link node, owner, or local transform is written.
    S.World.update_unit(item.world,item.unit);updated=updated+1
    if diagnostic then
     local movement=0;local after={}
     for i,n in ipairs(item.markers) do
      after[i]=pose(item.unit,n);local d=0
      for j=1,3 do d=d+(before[i].p[j]-after[i].p[j])^2 end
      movement=math.max(movement,math.sqrt(d))
     end
     self.logger('[attachments] consumer_refresh phase=render frame=%d kind=%s resource=%s marker_motion=%.6f owner=unverified',self.frame or 0,item.kind,tostring(item.resource),movement)
     -- Distances are diagnostics only. Ambiguous nearby avatars cannot drive
     -- equipment or hands. Actual IK marker orientation needs game validation.
     if #after==2 then
      for _,a in pairs(self.avatars) do if a.active and a.world==item.world and alive(a.unit) then
       local distances={}
       for i,side in ipairs({'l','r'}) do local row=handRows[side]
        if row then
         local src=pose(a.unit,row.sourceAnchorIndex+row.sourceIndexOffset+1)
         local native=pose(a.unit,row.driverAnchorIndex+1);local ds,dn=0,0
         for j=1,3 do ds=ds+(src.p[j]-after[i].p[j])^2;dn=dn+(native.p[j]-after[i].p[j])^2 end
         distances[#distances+1]=string.format('%s_source=%.6f/%s_native=%.6f',side,math.sqrt(ds),side,math.sqrt(dn))
        end
       end
       self.logger('[attachments] weapon_ik_observation frame=%d avatar=%d resource=%s %s owner=unverified',self.frame or 0,a.label,tostring(item.resource),table.concat(distances,' '))
      end end
     end
    end
   end
  end
  if diagnostic then self.lastConsumerDiagnostic=self.frame or 0 end
  self.stats.consumerRefreshes=self.stats.consumerRefreshes+updated
  self.dirtyWorlds={}
 end
 function self:snapshot(a,rows)
  assert(alive(a.unit) and S.Unit.num_scene_graph_items(a.unit)==profile.expectedAvatarNodes,'avatar changed')
  local cache={};local function get(i)
   if not cache[i] then cache[i]=pose(a.unit,i+1) end;return cache[i]
  end
  -- Capture every input before outputs change. Configured target/anchor pairs
  -- share an unmodified native ancestor; its procedural/world motion cancels
  -- in their relative pose. Never subtract a live native hand from baked data.
  for _,row in ipairs(rows or {}) do
   get(row.index);get(row.parentIndex);get(row.referenceIndex);get(row.sourceReferenceIndex)
   if row.policy=='source-blended-reference' then
    get(row.configuredAnchorIndex);get(row.sourceAnchorIndex+row.sourceIndexOffset)
   end
   if row.driverAnchorIndex and row.sourceAnchorIndex and row.sourceIndexOffset then
    get(row.driverAnchorIndex);get(row.sourceAnchorIndex+row.sourceIndexOffset)
   end
  end
  return get
 end
 function self:write(a,target,get,rows)
  -- Prepare all local poses before mutating any node. Parent outputs use the
  -- same frame's desired world pose, so cape/weapon child chains do not double-transform.
  local locals={};local verifyWrite=not a.writeVerified or (self.frame or 0)-(a.lastReadbackFrame or 0)>=(options.readbackFrames or 600)
  local beforePosition=0;local beforeByName={}
  for _,row in ipairs(rows) do
   local parent=target[row.parentIndex] or get(row.parentIndex)
   local p=relative(parent,target[row.index]);assert(valid(p),'invalid local attachment pose')
   -- All generated reference locals are rigid. Preserve unsupported scaled clips
   -- by refusing the batch instead of silently dropping a scale component.
   local raw={S.Matrix4x4.to_elements(S.Unit.local_pose(a.unit,row.referenceIndex+1))}
   for c=0,2 do local l=0;for j=1,3 do l=l+raw[c*3+j]^2 end;assert(math.abs(l-1)<.003,'scaled attachment unsupported') end
   locals[#locals+1]={index=row.index+1,p=p}
   if verifyWrite then
    local current=get(row.index);local desired=target[row.index];local d=0
    for i=1,3 do d=d+(current.p[i]-desired.p[i])^2 end
    beforePosition=math.max(beforePosition,math.sqrt(d))
    if row.standardName=='attach_weapon' or row.standardName=='attach_hand_l' or row.standardName=='attach_hand_r' then beforeByName[row.standardName]=math.sqrt(d) end
   end
  end
  for _,r in ipairs(locals) do
   local q=S.Quaternion.from_elements(unpack(r.p.q));local p=S.Vector3(unpack(r.p.p))
   S.Unit.set_local_pose(a.unit,r.index,S.Matrix4x4.from_quaternion_position(q,p))
  end
  S.World.update_unit(a.world,a.unit);self.stats.writes=self.stats.writes+#locals
  self.dirtyWorlds[a.world]=true
  if verifyWrite then
   local maxPosition,maxRotation=0,0;local details={}
   for _,row in ipairs(rows) do
    local actual=pose(a.unit,row.index+1);local desired=target[row.index];local d,q=0,0
    for i=1,3 do d=d+(actual.p[i]-desired.p[i])^2 end
    for i=1,4 do q=q+actual.q[i]*desired.q[i] end
    maxPosition=math.max(maxPosition,math.sqrt(d));maxRotation=math.max(maxRotation,1-math.abs(q))
    if beforeByName[row.standardName] then details[#details+1]=string.format('%s:before=%.6f/after=%.6f',row.standardName,beforeByName[row.standardName],math.sqrt(d)) end
   end
   self.logger('[attachments] attachment_readback phase=render frame=%d rows=%d before_position_error=%.6f position_error=%.6f rotation_error=%.6f consumer=unobserved',
    self.frame or 0,#rows,beforePosition,maxPosition,maxRotation)
   if #details>0 then self.logger('[attachments] grip_reference_error phase=render frame=%d %s',self.frame or 0,table.concat(details,' ')) end
   local selectedHands={}
   for side,row in pairs(handRows) do if beforeByName[row.standardName] and row.sourceAnchorIndex and row.sourceIndexOffset and row.driverAnchorIndex then
    selectedHands[side]={native=get(row.driverAnchorIndex),source=get(row.sourceIndexOffset+row.sourceAnchorIndex)}
   end end
   if selectedHands.l and selectedHands.r then
    local function distance(a,b)local d=0;for i=1,3 do d=d+(a.p[i]-b.p[i])^2 end;return math.sqrt(d)end
    self.logger('[attachments] geometry_diagnostic phase=render frame=%d native_source_l=%.6f native_source_r=%.6f native_hand_span=%.6f source_hand_span=%.6f consumer=unobserved',
     self.frame or 0,distance(selectedHands.l.native,selectedHands.l.source),distance(selectedHands.r.native,selectedHands.r.source),
     distance(selectedHands.l.native,selectedHands.r.native),distance(selectedHands.l.source,selectedHands.r.source))
   end
   assert(maxPosition<.005 and maxRotation<.0001,'attachment write/readback mismatch')
   a.writeVerified=true;a.lastReadbackFrame=self.frame or 0;self.stats.readbacks=self.stats.readbacks+1
  end
 end
 function self:restore(a)
  -- The exclusive experiment owns no legacy rows, arms or wrist helpers.
  -- Its conditional restoration runs before discovery and on release.
  if gripAlignment then a.active=false;return end
  if a.layoutInvalid or not alive(a.unit) or S.Unit.num_scene_graph_items(a.unit)~=profile.expectedAvatarNodes then a.active=false;return end
  -- The shadow hierarchy mirrors the native selected hierarchy exactly.
  -- Copy locals directly so rollback also preserves non-unit scales and does
  -- not depend on the transform path that may just have failed verification.
  for _,row in ipairs(a.activeRows or {}) do
   S.Unit.set_local_pose(a.unit,row.index+1,S.Unit.local_pose(a.unit,row.referenceIndex+1))
  end
  self:update_procedures(a,false)
  self:restore_arms(a)
  S.World.update_unit(a.world,a.unit);a.active=false;a.writeVerified=false;a.activeRows=nil
  self.dirtyWorlds[a.world]=true
 end
 function self:restore_arms(a)
  if not a.armOriginal then return end
  for index,p in pairs(a.armOriginal)do
   S.Unit.set_local_pose(a.unit,index,S.Matrix4x4.from_quaternion_position(S.Quaternion.from_elements(unpack(p.q)),S.Vector3(unpack(p.p))))
  end
  a.armOriginal=nil;a.armLastWritten=nil;a.armStates=nil;a.armsActive=false
  S.World.update_unit(a.world,a.unit);self.dirtyWorlds[a.world]=true
 end
 function self:sync_arms(a)
  local pending={};local residuals={};local readbacks={};a.armStates=a.armStates or {};a.armOriginal=a.armOriginal or {};a.armLastWritten=a.armLastWritten or {}
  for _,chain in ipairs(profile.armChains or {})do
   local function get(index)return pose(a.unit,index+1)end
   local parentScale=1
   -- Refuse non-rigid arm inputs before applying either arm.
   for _,index in ipairs(chain.scaleChecks or {chain.root,chain.mid,chain.hand})do
    local raw={S.Matrix4x4.to_elements(S.Unit.local_pose(a.unit,index+1))}
    local lengths={}
    for c=0,2 do
     local n=0;for j=1,3 do n=n+raw[c*3+j]^2 end;lengths[c+1]=math.sqrt(n)
    end
    local s=lengths[1];assert(finite(s) and s>.0001,'scaled Source arm unsupported')
    for c=0,2 do
     assert(math.abs(lengths[c+1]/s-1)<.0001,'scaled Source arm unsupported')
     for d=c+1,2 do local v=0;for j=1,3 do v=v+raw[c*3+j]*raw[d*3+j]end;assert(math.abs(v/(s*s))<.0001,'sheared Source arm unsupported')end
    end
    local determinant=raw[1]*(raw[5]*raw[9]-raw[6]*raw[8])-raw[2]*(raw[4]*raw[9]-raw[6]*raw[7])+raw[3]*(raw[4]*raw[8]-raw[5]*raw[7])
    assert(determinant>0,'reflected Source arm unsupported')
    if index==chain.root or index==chain.mid or index==chain.hand then assert(math.abs(s-1)<.0001,'scaled Source arm unsupported')
    else parentScale=parentScale*s end
   end
   local parent=get(chain.parent);local root=get(chain.root)
   a.armStates[chain.side]=a.armStates[chain.side] or {}
   local hand=get(chain.nativeHand);local desiredHandRotation=nil;local grip=nil
   if profile.armGripSync then
    grip=get(chain.nativeGrip)
    local target=M.grip_target(grip,chain,parentScale);desiredHandRotation=target.q
    hand={p=target.p,q=hand.q,referencePosition=hand.p}
   end
   local targets,residual=M.solve_arm(root,get(chain.nativeUpper),get(chain.nativeForearm),hand,
    parent,chain,a.armStates[chain.side],self.deltaTime or 1/60,parentScale,desiredHandRotation)
   local indices={chain.root,chain.mid,chain.hand};local parents={chain.parent,chain.root,chain.mid}
   for i,index in ipairs(indices)do
    assert(valid(targets[i]),'invalid arm output')
    local current=relative(get(parents[i]),get(index));current.p=scale(current.p,1/parentScale);local previous=a.armLastWritten[index+1]
    -- Retain the latest animation input, not the pose at first activation.
    -- Repeated render callbacks without a fresh animation pose keep the saved input.
    if not previous or not close(current,previous)then a.armOriginal[index+1]=current end
    pending[#pending+1]={index=index+1,p=targets[i]}
   end
   residuals[#residuals+1]=string.format('%s=%.6f',chain.side,residual)
   local function scaledCompose(parent,local_)return compose(parent,{p=scale(local_.p,parentScale),q=local_.q})end
   local upperWorld=scaledCompose(parent,targets[1]);local midWorld=scaledCompose(upperWorld,targets[2])
   readbacks[#readbacks+1]={index=chain.hand+1,desired=scaledCompose(midWorld,targets[3]),
    grip=grip,sourceGripOffset=chain.sourceGripOffset,parentScale=parentScale,side=chain.side}
  end
  -- Mark before the first engine write so release can undo a partial failure.
  if #pending>0 then a.active=true;a.armsActive=true end
  for _,r in ipairs(pending)do
   S.Unit.set_local_pose(a.unit,r.index,S.Matrix4x4.from_quaternion_position(S.Quaternion.from_elements(unpack(r.p.q)),S.Vector3(unpack(r.p.p))))
   a.armLastWritten[r.index]=r.p
  end
  a.armsActive=#pending>0
  if a.armsActive then
   S.World.update_unit(a.world,a.unit);self.dirtyWorlds[a.world]=true
   local error=0;local contactErrors={}
   for _,row in ipairs(readbacks)do
    local actual=pose(a.unit,row.index);error=math.max(error,length(sub(actual.p,row.desired.p)))
    assert(close(actual,row.desired),'native hand sync write/readback mismatch')
    if row.grip then
     local contact=add(actual.p,rot(actual.q,scale(row.sourceGripOffset,row.parentScale)))
     contactErrors[#contactErrors+1]=string.format('%s=%.6f',row.side,length(sub(contact,row.grip.p)))
    end
   end
   if not a.armDiagnostic or self.frame-a.armDiagnostic>=600 then
    self.logger('[attachments] native_hand_sync frame=%d avatar=%d reach_residual %s readback_error=%.6f',self.frame,a.label,table.concat(residuals,' '),error);a.armDiagnostic=self.frame
    if #contactErrors>0 then self.logger('[attachments] palm_contact_error frame=%d avatar=%d %s target=same_avatar_native_grip',self.frame,a.label,table.concat(contactErrors,' '))end
   end
  end
 end
 function self:procedure_targets(a,enabled)
  local pending={}
  for _,row in ipairs(profile.jointProcedures or {}) do
   local target=row.bind
   if enabled then
    local parent=pose(a.unit,row.parentIndex+1)
    local control=pose(a.unit,row.controlIndex+1)
    target=M.quatinterp(relative(parent,control).q,row)
   end
   assert(valid(target),'invalid Source joint helper pose')
   pending[#pending+1]={index=row.index+1,pose=target}
  end
  return pending
 end
 function self:update_procedures(a,enabled,pending)
  if not enabled and not a.proceduresActive then return end
  pending=pending or self:procedure_targets(a,enabled)
  for _,row in ipairs(pending) do
   S.Unit.set_local_pose(a.unit,row.index,S.Matrix4x4.from_quaternion_position(
    S.Quaternion.from_elements(unpack(row.pose.q)),S.Vector3(unpack(row.pose.p))))
  end
  a.proceduresActive=enabled and #pending>0
  if #pending>0 then S.World.update_unit(a.world,a.unit);self.dirtyWorlds[a.world]=true end
 end
 -- Read the matched armor's own node indices. Avatar readback alone does not
 -- show that a separate model graph received the pose, or that skinning used it.
 function self:arm_consumer_readback(a,item,phase)
  local count,missing,maxPosition,maxRotation=0,0,0,0
  for _,chain in ipairs(profile.armChains or {})do
   for _,index in ipairs({chain.root,chain.mid,chain.hand})do
    local name=nil;for _,node in ipairs(chain.nodes)do if node.index==index then name=node.name;break end end
    local hash=name and S.Application.string_to_id32(name)
    if hash and S.Unit.has_node(item.unit,hash)==true then
     local modelIndex=S.Unit.node(item.unit,hash)
     assert(type(modelIndex)=='number' and modelIndex%1==0 and modelIndex>=1 and modelIndex<=item.count,'invalid model arm node')
     local avatarPose=pose(a.unit,index+1);local modelPose=pose(item.unit,modelIndex)
     maxPosition=math.max(maxPosition,length(sub(avatarPose.p,modelPose.p)))
     local dot=0;for i=1,4 do dot=dot+avatarPose.q[i]*modelPose.q[i]end
     maxRotation=math.max(maxRotation,2*math.acos(math.min(1,math.abs(dot)))*180/math.pi)
     count=count+1
    else missing=missing+1 end
   end
  end
  self.logger('[attachments] arm_consumer_readback phase=%s frame=%d avatar=%d resource=%s nodes=%d missing=%d position_error=%.6f rotation_error_degrees=%.6f skinning=unobserved',
   phase,self.frame or 0,a.label,tostring(item.resource),count,missing,maxPosition,maxRotation)
  return {nodes=count,missing=missing,positionError=maxPosition,rotationErrorDegrees=maxRotation}
 end
 local sceneObserver=nil
 do
  local ok,value=pcall(SceneObserver.new,S,profile,self.logger)
  if ok then sceneObserver=value else pcall(self.logger,'[scene_probe] init_unavailable: %s',tostring(value))end
 end
 function self:observe_scene(phase,owners)
  if not sceneObserver then return end
  local ok,err=pcall(sceneObserver.capture,sceneObserver,self.frame,self.lastTime,phase,
   self.avatars,self.armor,owners,alive,visible,resource)
  if not ok and (self.sceneErrors or 0)<3 then
   self.sceneErrors=(self.sceneErrors or 0)+1
   pcall(self.logger,'[scene_probe] capture_unavailable: %s',tostring(err))
  end
 end
 local sceneRoundtrip=nil
 do
  local ok,value=pcall(SceneRoundtrip.new,S,profile,self.logger)
  if ok then sceneRoundtrip=value else pcall(self.logger,'[scene_roundtrip] init_unavailable: %s',tostring(value))end
 end
 function self:roundtrip_scene(owners)
  if not sceneRoundtrip then return end
  local ok,err=pcall(sceneRoundtrip.tick,sceneRoundtrip,self.frame,self.lastTime,
   self.avatars,self.armor,owners,alive,visible,resource,options.settleFrames or 10)
  if not ok then
   sceneRoundtrip.disabled=true
   pcall(self.logger,'[scene_roundtrip] unexpected_error_disabled: %s',tostring(err))
  end
 end
 local attachmentProbe=not gripAlignment and AttachmentProbe.new(S,profile,self.logger)
 function self:restore_attachment_probe()
  if attachmentProbe then
   for world in pairs(attachmentProbe:restore_all())do self.dirtyWorlds[world]=true end
  end
 end
 function self:restore_grip_alignment(frame)
  if gripAlignment then
   for world in pairs(gripAlignment:restore_all(frame))do self.dirtyWorlds[world]=true end
  end
 end
 function self:tick(frame)
  local now=S.Application.time_since_launch()
  if now==self.lastTime then return end
  self.deltaTime=self.lastTime and math.max(0,math.min(.1,now-self.lastTime)) or 1/60;self.lastTime=now
  self.frame=frame
  self:restore_grip_alignment(frame)
  self:restore_attachment_probe()
  if frame-self.lastScan>=(options.scanFrames or 30) then self:scan(frame) end
  local poses={}
  local matches={};local blocked={};local ambiguous=0;local modelOwners={}
  for unit,a in pairs(self.avatars) do
   if alive(unit) and S.Unit.num_scene_graph_items(unit)==profile.expectedAvatarNodes then
    local p={};for i,index in ipairs(a.signature) do p[i]=pose(unit,index) end;poses[unit]=p;matches[unit]={}
   end
  end
  for _,item in ipairs(self.armor) do
   if alive(item.unit) and S.Unit.num_scene_graph_items(item.unit)==item.count and resource(item.unit)==item.resource and visible(item.unit)~=false then
    local p={};for i,index in ipairs(item.signature) do p[i]=pose(item.unit,index) end
    local owner=nil;local count=0;local owners={}
    for unit,a in pairs(self.avatars) do
     if poses[unit] and a.world==item.world then
      local same=true;for i=1,#p do if not close(p[i],poses[unit][i]) then same=false;break end end
      if same then owner=unit;count=count+1;owners[#owners+1]=unit end
     end
    end
    if count==1 then
     if item.selectsSlot then matches[owner][item.slot]=true end
     modelOwners[item.unit]=owner
    elseif count>1 and item.selectsSlot then
     ambiguous=ambiguous+1
     for _,unit in ipairs(owners) do blocked[unit]=blocked[unit] or {};blocked[unit][item.slot]=true end
    end
   end
  end
  self:observe_scene('pre_apply',modelOwners)
  local active=0
  for unit,a in pairs(self.avatars) do
   local selected={};local any=false
   for _,slot in ipairs({'body','head'}) do
    a.stable[slot]=matches[unit] and matches[unit][slot] and not (blocked[unit] and blocked[unit][slot]) and a.stable[slot]+1 or 0
    selected[slot]=a.stable[slot]>=(options.settleFrames or 10);any=any or selected[slot]
   end
   local selection='avatar='..a.label..' body='..tostring(selected.body)..' head='..tostring(selected.head)
   if a.selection~=selection then a.selection=selection;a.writeVerified=false;self.logger('[attachments] slot_selection frame=%d %s',frame,selection) end
   if attachmentProbe and not selected.body then attachmentProbe:apply(a,false,now,frame,self.consumers)end
   if gripAlignment then
    -- One direction only. No old arm IK, attachment mapping, or Source wrist
    -- procedure may move the source of this experiment in the same callback.
    a.active=gripAlignment:apply(a,selected.body and self.mode=='apply',frame,self.consumers)
    if a.active then active=active+1;self.dirtyWorlds[a.world]=true end
    self.stats.writes=gripAlignment.stats.writes;self.stats.readbacks=gripAlignment.stats.readbacks
   elseif any and self.mode=='apply' then
    if selected.body and profile.armSync then self:sync_arms(a)else self:restore_arms(a)end
    -- Restore only rows that this adapter previously owned. Native controller
    -- inputs and unequipped slots must never be reset to baked shadow poses.
    local rows={};local chosen={}
    for _,row in ipairs(profile.vpk) do
     if selected[row.ownerSlot] and not protectedParents[row.index]
      and not (profile.armSync and row.standardName=='attach_hand_l')
      and not (profile.armGripSync and row.standardName=='attach_hand_r')
      and not (profile.preserveHeadAttachments and row.ownerSlot=='head')
      and (row.policy=='source-reference' or row.policy=='source-blended-reference') then
      rows[#rows+1]=row;chosen[row.index]=true
     end
    end
    local prior=a.activeRows or {}
    if #prior~=#rows then a.writeVerified=false else
     for _,row in ipairs(prior) do if not chosen[row.index] then a.writeVerified=false;break end end
    end
    local restored=false
    for _,row in ipairs(a.activeRows or {}) do if not chosen[row.index] then
     S.Unit.set_local_pose(a.unit,row.index+1,S.Unit.local_pose(a.unit,row.referenceIndex+1));restored=true
    end end
    if restored then S.World.update_unit(a.world,a.unit) end
    local get=self:snapshot(a,rows);local target={}
    for _,row in ipairs(rows) do
     if row.policy=='source-blended-reference' then
      local offset=relative(get(row.configuredAnchorIndex),get(row.sourceReferenceIndex))
      target[row.index]=compose(get(row.sourceAnchorIndex+row.sourceIndexOffset),
       {p=rot(row.axisCorrection,offset.p),q=mul(row.axisCorrection,offset.q)})
     else target[row.index]=get(row.sourceReferenceIndex) end
    end
    local joints=self:procedure_targets(a,selected.body)
    a.activeRows=rows;a.active=#rows>0 or a.proceduresActive or a.armsActive
    if #rows>0 then self:write(a,target,get,rows) end
    self:update_procedures(a,selected.body,joints)
    if attachmentProbe and attachmentProbe:apply(a,selected.body,now,frame,self.consumers)then self.dirtyWorlds[a.world]=true end
    a.active=#rows>0 or a.proceduresActive or a.armsActive
    if a.active then active=active+1 end
   elseif a.active then self:restore(a) end
  end
  self.stats.active=active;self.stats.ambiguous=ambiguous
  -- Hash-bound model graphs and independent equipment graphs can retain a
  -- pre-write pose even after update_unit(avatar). Refresh them in this order.
  for _,item in ipairs(self.armor) do
   local owner=modelOwners[item.unit];local a=owner and self.avatars[owner]
   if self.dirtyWorlds[item.world] and alive(item.unit) and S.Unit.num_scene_graph_items(item.unit)==item.count
    and (item.selectsSlot or (a and a.active and a.stable[item.slot]>=(options.settleFrames or 10)
     and resource(item.unit)==item.resource and visible(item.unit)~=false)) then
    local diagnostic=profile.armGripSync and item.slot=='body' and a and a.armsActive
     and (not item.armConsumerFrame or frame-item.armConsumerFrame>=600)
    local function observe(phase)
     local ok,err=pcall(self.arm_consumer_readback,self,a,item,phase)
     if not ok then self.logger('[attachments] arm_consumer_readback unavailable: %s',tostring(err))end
    end
    if diagnostic then observe('before_model_refresh')end
    S.World.update_unit(item.world,item.unit)
    if diagnostic then observe('after_model_refresh');item.armConsumerFrame=frame end
   end
  end
  self:refresh_consumers()
  if not gripAlignment then self:roundtrip_scene(modelOwners)end
  self:observe_scene('post_refresh',modelOwners)
  if attachmentProbe then attachmentProbe:after_refresh()end
  if gripAlignment then gripAlignment:after_refresh()end
  emit('selection','active='..active..' ambiguous='..ambiguous..' mode='..self.mode)
 end
 function self:release()
  self:restore_grip_alignment(self.frame)
  self:restore_attachment_probe()
  for _,a in pairs(self.avatars) do if a.active then pcall(self.restore,self,a) end end
  if attachmentProbe or gripAlignment then
   for _,item in ipairs(self.armor)do
    if self.dirtyWorlds[item.world]and alive(item.unit)and S.Unit.num_scene_graph_items(item.unit)==item.count and resource(item.unit)==item.resource then pcall(S.World.update_unit,item.world,item.unit)end
   end
  end
  self:refresh_consumers()
 end
 return self
end
return M
