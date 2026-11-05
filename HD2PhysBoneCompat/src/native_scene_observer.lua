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
