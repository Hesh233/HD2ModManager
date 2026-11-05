-- B21: read-only observations of existing Avatar, armor and weapon graphs.
-- No setters, graph links, animation commands or forced World updates.
local M={VERSION='1.0.0'}
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<1e12 end
local function quote(s)
 return '"'..tostring(s):gsub('[%z\1-\31\\"]',function(c)
  if c=='\\'then return '\\\\'elseif c=='"'then return '\\"'end
  return string.format('\\u%04x',string.byte(c))
 end)..'"'
end
local function json(v)
 if v==nil then return 'null'elseif type(v)=='boolean'then return tostring(v)
 elseif type(v)=='number'then assert(finite(v),'nonfinite_json');return string.format('%.9g',v)
 elseif type(v)=='string'then return quote(v)end
 assert(type(v)=='table','invalid_json_type');local out={}
 if #v>0 then for i=1,#v do out[i]=json(v[i])end;return '['..table.concat(out,',')..']'end
 local keys={};for k in pairs(v)do keys[#keys+1]=k end;table.sort(keys)
 for _,k in ipairs(keys)do out[#out+1]=quote(k)..':'..json(v[k])end
 return '{'..table.concat(out,',')..'}'
end
function M.new(S,cfg,logger)
 local U,X=S.Unit,S.Matrix4x4
 assert(U and X and type(U.local_pose)=='function'and type(U.world_pose)=='function','pose_api_missing')
 assert(type(S.Application.string_to_id32)=='function'and type(S.World.units)=='function','discovery_api_missing')
 local self={samples=0,records=0,sequence=0,tracked={},identities={},lastScan=nil,lastSample=nil,pending=nil,stopped=false}
 local function emit(row)
  if self.records>=cfg.maxRecords then return end
  self.records=self.records+1;logger(json(row))
 end
 local function resource(u)
  local value=S.IdString64.to_hex(U.resource_name(u))
  assert(type(value)=='string'and #value==16 and value:match('^[%da-fA-F]+$'),'invalid_resource_id')
  return value:lower()
 end
 local function visible(u)
  if not U.num_meshes or not U.mesh or not S.Mesh or not S.Mesh.visibility then return 'unknown'end
  local ok,value=pcall(function()
   local count=U.num_meshes(u);if not finite(count)or count==0 then return 'unknown'end
   local unknown=false
   for i=1,count do local v=S.Mesh.visibility(U.mesh(u,i));if v==true then return true elseif v~=false then unknown=true end end
   return unknown and 'unknown'or false
  end)
  if ok then return value end;return 'unknown'
 end
 local function matrix(u,n,isWorld)
  local values={X.to_elements((isWorld and U.world_pose or U.local_pose)(u,n))}
  assert(#values==12,'matrix_element_count')
  for _,v in ipairs(values)do assert(finite(v),'matrix_nonfinite')end
  return values
 end
 local function identity(u,layout)
  assert(U.alive(u)==true and U.num_scene_graph_items(u)==layout.count,'dead_or_rebuilt_unit')
  for _,r in ipairs(layout.nodes)do
   local id=S.Application.string_to_id32(r.name)
   assert(U.has_node(u,id)==true and U.node(u,id)==r.index+1,'node_identity:'..r.name)
  end
 end
 local function snapshot(item)
  local u,layout=item.unit,item.layout
  identity(u,layout);assert(resource(u)==item.resource,'resource_changed')
  local visibility=visible(u)
  assert(item.kind=='avatar'or visibility~=false,'model_hidden')
  local rows={}
  for _,r in ipairs(layout.nodes)do
   local n=r.index+1;local parent,state,parentWorld
   if type(U.scene_graph_parent)=='function'then
    local ok,p=pcall(U.scene_graph_parent,u,n)
    if not ok then state='api_error'
    elseif p==nil or p==0 or p==-1 or p==n then parent=p;state='external_or_root'
    elseif finite(p)and p%1==0 and p>=1 and p<=layout.count then
     parent=p;state='internal_candidate';parentWorld=matrix(u,p,true)
    else state='nonlocal_or_invalid'end
   else state='api_missing'end
   rows[#rows+1]={name=r.name,index=n,serializedParent=r.parentIndex==nil and 0 or r.parentIndex+1,
    runtimeParent=parent,parentState=state,parentWorld=parentWorld,
    localMatrix=matrix(u,n,false),worldMatrix=matrix(u,n,true),skinInput=r.skinInput==true}
  end
  assert(U.alive(u)==true and U.num_scene_graph_items(u)==layout.count and resource(u)==item.resource,'changed_during_snapshot')
  return {id=item.id,world=item.worldLabel,resource=item.resource,kind=item.kind,layout=layout.label,
   nodeCount=layout.count,visibility=visibility,nodes=rows,owner='unverified'}
 end
 local function scan(now,frame)
  local found,seen,newIdentities={},{},{}
  local counts={};for _,spec in pairs(cfg.resources)do for count in pairs(spec.layouts)do counts[tonumber(count)]=true end end
  local skipped,errors=0,0
  local worlds=S.Application.worlds()or {}
  for worldLabel,w in ipairs(worlds)do
   if worldLabel>cfg.maxWorlds then break end
   local ok,units=pcall(S.World.units,w)
   if ok then
    for i,u in ipairs(units or {})do
     if i>cfg.maxScanUnits then skipped=skipped+1;break end
     local good,value=pcall(function()
      if U.alive(u)~=true then return end
      local count=U.num_scene_graph_items(u);if not counts[count]then return end
      local id=resource(u);local spec=cfg.resources[id]
      local layout=spec and spec.layouts[tostring(count)]
      if not layout then return end
      if spec.kind~='avatar'and visible(u)==false then return end
      identity(u,layout)
      local prior=self.identities[u]
      if not prior or prior.resource~=id or prior.count~=count or prior.world~=w then
       self.sequence=self.sequence+1;prior={id=self.sequence,resource=id,count=count,world=w}
      end
      newIdentities[u]=prior
      return {unit=u,id=prior.id,world=w,worldLabel=worldLabel,resource=id,kind=spec.kind,layout=layout}
     end)
     if good and value and not seen[u]then found[#found+1]=value;seen[u]=true
     elseif not good then errors=errors+1 end
    end
   else errors=errors+1 end
  end
  table.sort(found,function(a,b)
   local aa=a.kind=='avatar'and 0 or 1;local bb=b.kind=='avatar'and 0 or 1
   if aa~=bb then return aa<bb elseif a.worldLabel~=b.worldLabel then return a.worldLabel<b.worldLabel end
   return a.id<b.id
  end)
  while #found>cfg.maxTracked do table.remove(found);skipped=skipped+1 end
  self.tracked=found;self.identities=newIdentities;self.lastScan=now
  emit({event='scan',frame=frame,time=now,tracked=#found,errors=errors,truncated=skipped})
 end
 local function near_avatar(row,avatars)
  if row.kind=='avatar'then return true end
  local gap=math.huge
  for _,a in ipairs(avatars)do if a.world==row.world then
   for _,n in ipairs(row.nodes)do for _,b in ipairs(a.nodes)do
    if b.name=='l_hand'or b.name=='r_hand'then
     local d=0;for j=10,12 do d=d+(n.worldMatrix[j]-b.worldMatrix[j])^2 end
     gap=math.min(gap,math.sqrt(d))
    end
   end end
  end end
  if gap<=cfg.radiusMetres then row.nearestAvatarHandMetres=gap;return true end
  return false
 end
 function self:stop(reason)
  if self.stopped then return end
  emit({event='complete',reason=reason or 'stopped',samples=self.samples,records=self.records,
   pendingSample=self.pending and self.pending.sample or nil,readOnly=true})
  self.stopped=true;self.pending=nil;self.tracked={};self.identities={}
 end
 function self:tick(phase,frame,now)
  if self.stopped then return false end
  if phase=='update'and self.pending then
   emit({event='incomplete_pair',sample=self.pending.sample,frame=self.pending.frame,reason='next_update_before_render'});self.pending=nil
  end
  if self.samples>=cfg.maxSamples or self.records>=cfg.maxRecords-100 then
   if not self.pending then self:stop('capture_limit');return true end
  end
  if phase=='update'then
   if self.lastSample and now-self.lastSample<cfg.intervalSeconds then return false end
   if not self.lastScan or now-self.lastScan>=cfg.scanSeconds then scan(now,frame)end
   local rows,items,avatars={},{},{}
   for _,item in ipairs(self.tracked)do
    local ok,row=pcall(snapshot,item)
    if ok then
     rows[#rows+1]=row;items[row.id]=item
     if row.kind=='avatar'then avatars[#avatars+1]=row end
    else emit({event='unavailable',phase=phase,frame=frame,id=item.id,resource=item.resource,reason=tostring(row):sub(1,180)})end
   end
   if #avatars==0 then return false end
   self.samples=self.samples+1;self.lastSample=now
   local sample=self.samples;local selected={}
   emit({event='phase_begin',phase=phase,frame=frame,time=now,sample=sample,indexBase=1,readOnly=true})
   for _,row in ipairs(rows)do if near_avatar(row,avatars)then
    selected[#selected+1]=items[row.id];row.event='unit';row.phase=phase;row.frame=frame;row.time=now;row.sample=sample;emit(row)
   end end
   self.pending={sample=sample,frame=frame,targets=selected}
   emit({event='phase_end',phase=phase,frame=frame,time=now,sample=sample,units=#selected})
   return true
  elseif phase=='render'and self.pending then
   local p=self.pending;self.pending=nil;local count,errors=0,0
   emit({event='phase_begin',phase=phase,frame=p.frame,time=now,sample=p.sample,indexBase=1,readOnly=true})
   for _,item in ipairs(p.targets)do
    local ok,row=pcall(snapshot,item)
    if ok then
     row.event='unit';row.phase=phase;row.frame=p.frame;row.time=now;row.sample=p.sample;emit(row);count=count+1
    else errors=errors+1;emit({event='unavailable',phase=phase,frame=p.frame,sample=p.sample,
      id=item.id,resource=item.resource,reason=tostring(row):sub(1,180)})end
   end
   emit({event='phase_end',phase=phase,frame=p.frame,time=now,sample=p.sample,units=count,errors=errors})
   return true
  end
  return false
 end
 local methods={}
 for name,value in pairs(type(U)=='table'and U or {})do if type(name)=='string'and type(value)=='function'and
   (name:find('scene',1,true)or name:find('parent',1,true)or name:find('link',1,true)or name:find('animation',1,true))then methods[#methods+1]=name end end
 table.sort(methods)
 emit({event='loaded',version=M.VERSION,revision=cfg.revision,intervalSeconds=cfg.intervalSeconds,
  maxSamples=cfg.maxSamples,readOnly=true,phaseMeaning='Two loader callbacks; their position relative to game IK is unverified.',unitMethods=methods})
 return self
end
return M
