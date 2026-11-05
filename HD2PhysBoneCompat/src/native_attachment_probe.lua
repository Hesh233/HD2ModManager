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
