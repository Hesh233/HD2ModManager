-- Read-only FP view gate. A retained FP graph or narrow FOV is NOT entry proof.
-- Compare the real main-view camera with the concrete FP graph's camera bone.
-- Engine matrices/IdStrings are callback-local; pose data is copied to numbers.
-- The matched World handle is consumed only after a fresh sample/membership check.
local M={VERSION='1.0.0'}
local RESOURCE='content/fac_helldivers/fp_cha_avatar/fp_cha_avatar'
local RESOURCE_HEX='d0cf4d493ca08bed'
local function finite(x)return type(x)=='number' and x==x and math.abs(x)<1e12 end
function M.new(S,context,contract)
 local U,W,A,X,I=S.Unit,S.World,S.Application,S.Matrix4x4,S.IdString64
 local callbackCache=nil
 local layoutProof={}
 local held=false;local currentFpWorld=nil;local currentFpActor=nil
 local function pose(fn,...)
  local values={X.to_elements(fn(...))}
  assert(#values==12,'view_matrix_size')
  for _,v in ipairs(values)do assert(finite(v),'view_matrix_nonfinite')end
  return values
 end
 local function sample()
  local worlds=A.worlds() or {};assert(type(worlds)=='table' and #worlds<=64,'view_world_inventory')
  local graphs,seen={},{ }
  for _,world in ipairs(worlds)do
   local units=W.units_by_resource(world,RESOURCE)
   assert(type(units)=='table' and #units<=8,'view_fp_inventory')
   for _,u in ipairs(units)do
    if not seen[u] and U.alive(u)==true then
     seen[u]=true
     assert(I.to_hex(U.resource_name(u)):lower()==RESOURCE_HEX,'view_fp_identity')
     local count=U.num_scene_graph_items(u)
     local now=A.time_since_launch and A.time_since_launch()or 0
     local cached=layoutProof[u]
     if count~=63 and not (cached and cached.count==count and now>=cached.time and now-cached.time<.5) then
      assert(contract and contract.resource==RESOURCE_HEX and count==contract.count and contract.nativeCount==63,'view_fp_layout')
      for _,n in ipairs(contract.nativeGraph or {})do
       if n.name then local id=A.string_to_id32(n.name);assert(U.has_node(u,id)and U.node(u,A.string_to_id32(n.name))==n.index+1,'view_fp_native_prefix')end
       if n.parent~=nil then assert(U.scene_graph_parent(u,n.index+1)==n.parent+1,'view_fp_native_parent')end
      end
      for _,n in ipairs(contract.outputs or {})do
       assert(n.index>=63,'view_fp_output_index');local id=A.string_to_id32(n.name)
       assert(U.has_node(u,id)and U.node(u,A.string_to_id32(n.name))==n.index+1,'view_fp_source_identity')
       assert(U.scene_graph_parent(u,n.index+1)==n.parent+1,'view_fp_source_parent')
      end
     end
     if not cached or cached.count~=count or now<cached.time or now-cached.time>=.5 then layoutProof[u]={count=count,time=now}end
     -- Verified serialized FP layout: root[4], camera[50] (zero-based).
     for _,row in ipairs({{'root',5},{'camera',51}})do
      local id=A.string_to_id32(row[1])
      assert(U.has_node(u,id)==true and U.node(u,id)==row[2],'view_fp_camera_identity')
     end
     graphs[#graphs+1]={unit=u,world=world,count=count,layoutVerified=true}
    end
   end
  end
  if #graphs==0 then held=false;currentFpWorld=nil;currentFpActor=nil;return false,{reason='no_fp_graph'}end
  local main=context and type(context.world)=='function' and context.world() or nil
  if not main then return nil,{reason='main_view_world_unavailable'}end
  if type(W.debug_camera_pose)~='function' then return nil,{reason='main_view_camera_api_unavailable'}end
  local camera=pose(W.debug_camera_pose,main)
  -- Small Schmitt band protects camera-blend frames without a sticky FP latch.
  local limit=held and .12 or .08
  local nearest=math.huge
  for _,row in ipairs(graphs)do
   local fp=pose(U.world_pose,row.unit,51)
   local d=math.sqrt((camera[10]-fp[10])^2+(camera[11]-fp[11])^2+(camera[12]-fp[12])^2)
   nearest=math.min(nearest,d)
   if d<=limit then
    held=true;currentFpWorld=row.world;currentFpActor={unit=row.unit,world=row.world,count=row.count,layoutVerified=row.layoutVerified}
    return true,{reason='fp_camera_matches_main_view',distance=d,limit=limit,
     camera={camera[10],camera[11],camera[12]},fpCamera={fp[10],fp[11],fp[12]},fpWorld=tostring(row.world)}
   end
  end
  held=false;currentFpWorld=nil;currentFpActor=nil
  return false,{reason='main_view_not_fp_camera',distance=nearest,limit=limit}
 end
 return {reset=function()callbackCache=nil end,actor=function()return currentFpActor end,world=function()return currentFpWorld end,sample=function(force)
  if force then callbackCache=nil end
  if contract and contract.cacheViewWithinCallback and callbackCache and not force then return callbackCache.state,callbackCache.detail end
  local ok,state,detail=pcall(sample)
  if ok then
   if state~=true then currentFpWorld=nil;currentFpActor=nil end
   if contract and contract.cacheViewWithinCallback then callbackCache={state=state,detail=detail}end
   return state,detail
  end
  currentFpWorld=nil;currentFpActor=nil
  -- Uncertain view is a write bypass, not a permanent addon disable.
  return nil,{reason='view_probe_unavailable',detail=tostring(state)}
 end}
end
return M
