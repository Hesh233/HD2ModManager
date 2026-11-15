-- Only the two native-matched local FP arm meshes are hidden. No Source solver/pose/refresh.
local M={VERSION='1.0.0'}
function M.new(S,p,guard,context,log)
 local U,W,A,X=S.Unit,S.World,S.Application,S.Matrix4x4
 local self={records={},lastStatus=nil,lastLog=0,stats={ticks=0,meshHides=0,meshRestores=0,fullScans=0,scopedQueries=0,ambiguities=0,poseWrites=0,updateUnitCalls=0,failures=0}}
 local cached={}
 local function read(u,i)local m={X.to_elements(U.world_pose(u,i+1))};assert(#m==12,'hidden_matrix_layout');return m end
 local function rid(u)return S.IdString64.to_hex(U.resource_name(u)):lower():gsub('^0x','')end
 local function identity(u,spec)
  assert(U.alive(u)and rid(u)==spec.resource and U.num_scene_graph_items(u)==spec.count,'hidden_model_identity')
  for _,n in ipairs(spec.nativeMatches)do local id=A.string_to_id32(n.name);assert(U.has_node(u,id)and U.node(u,A.string_to_id32(n.name))==n.index+1,'hidden_native_model_node')end
 end
 local function delta(a,b)local d=0;for i=1,12 do d=math.max(d,math.abs(a[i]-b[i]))end;return d end
 function self:restore(reason)
  for u,row in pairs(self.records)do
   local ok,why=pcall(function()
    if not U.alive(u)then return end
    identity(u,row.spec)
    local present=false;for _,other in ipairs(W.units(row.world)or{})do if other==u then present=true;break end end
    if not present then return end
    assert(U.num_meshes(u)==#row.mask,'hidden_restore_mesh_count')
    for i,v in ipairs(row.mask)do U.set_mesh_visibility(u,i,v,'default');self.stats.meshRestores=self.stats.meshRestores+1 end
   end)
   if ok then self.records[u]=nil
   else self.stats.failures=self.stats.failures+1;log({event='fp_hidden_only_restore_failed',reason=tostring(why),scope='only_saved_native_matched_fp_model'})end
  end
 end
 function self:tick(phase,frame,now)
  self.stats.ticks=self.stats.ticks+1
  if guard.reset then guard.reset()end
  local ok,mission=pcall(context.inMission)
  local view=false
  if ok and mission==true then view=guard.sample()end
  if view==false or not ok or mission~=true then self:restore('tp_or_non_mission');cached={};return end
  if view~=true then return end -- Unknown view: retain prior safe hide, no new owner/setters.
  if phase~='render'then return end
  local actor=guard.actor();if not actor then return end
  local full;local selected={};local bySide={r={},l={}};local invalidSides={}
  for _,spec in ipairs(p.models)do
   local found={};local list;local old=cached[spec.resource]
   if old and U.alive(old)and type(W.units_by_resource)=='function'then
    local queried,value=pcall(function()return W.units_by_resource(actor.world,U.resource_name(old))end)
    if queried and type(value)=='table'and #value>0 then list=value;self.stats.scopedQueries=self.stats.scopedQueries+1 end
   end
   if not list then full=full or W.units(actor.world)or{};list=full;self.stats.fullScans=self.stats.fullScans+1 end
   for _,u in ipairs(list)do
    if U.alive(u)and rid(u)==spec.resource then
     local matched=pcall(function()
      identity(u,spec)
      for _,n in ipairs(spec.nativeMatches)do assert(delta(read(u,n.index),read(actor.unit,n.fpIndex))<=(p.modelMatchTolerance or .01),'hidden_native_owner_mismatch')end
     end)
     if matched then found[#found+1]=u end
    end
   end
   if #found==1 then local side=spec.sourceRole or spec.nativeMatches[1].name:sub(1,1);assert(bySide[side],'hidden_side');bySide[side][#bySide[side]+1]={unit=found[1],spec=spec};cached[spec.resource]=found[1]
   else self.stats.ambiguities=self.stats.ambiguities+1;cached[spec.resource]=nil;if #found>1 then local side=spec.sourceRole or spec.nativeMatches[1].name:sub(1,1);invalidSides[side]=true end end
  end
  for _,side in ipairs({'r','l'})do if #bySide[side]==1 and not invalidSides[side] then selected[#selected+1]=bySide[side][1] elseif #bySide[side]>1 then self.stats.ambiguities=self.stats.ambiguities+1 end end
  local touched={}
  for _,item in ipairs(selected)do
   local u=item.unit;touched[u]=true
   local ok,why=pcall(function()
    local count=U.num_meshes(u);assert(type(count)=='number'and count>=1 and count<=128 and count%1==0,'hidden_mesh_count')
    local row=self.records[u]
    if not row then
     row={world=actor.world,spec=item.spec,mask={}}
     for i=1,count do local v=S.Mesh.visibility(U.mesh(u,i));assert(type(v)=='boolean','hidden_unknown_mask');row.mask[i]=v end
     self.records[u]=row
    end
    assert(#row.mask==count,'hidden_mesh_layout_changed')
    for i=1,count do if S.Mesh.visibility(U.mesh(u,i))~=false then U.set_mesh_visibility(u,i,false,'default');self.stats.meshHides=self.stats.meshHides+1 end end
   end)
   if not ok then self.stats.failures=self.stats.failures+1;log({event='fp_hidden_only_unavailable',frame=frame,reason=tostring(why)})end
  end
  if now-self.lastLog>=5 then self.lastLog=now;log({event='fp_arms_disabled',frame=frame,time=now,hiddenReceivers=#selected,fpSolverConstructed=false,sourcePoseWrites=0,updateUnitCalls=0})end
 end
 function self:stop()self:restore('stop');log({event='fp_hidden_only_complete',stats=self.stats})end
 return self
end
return M
