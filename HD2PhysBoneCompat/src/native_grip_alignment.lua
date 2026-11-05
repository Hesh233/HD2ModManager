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
