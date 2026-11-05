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
