-- Real serialized layouts, numeric matrix recycling, and forbidden mutations.
local function copy(v)if type(v)~='table'then return v end;local r={};for k,x in pairs(v)do r[k]=copy(x)end;return r end
local checks=0;local function check(v,m)checks=checks+1;assert(v,m)end
local units={};local logs={};local mutationCalls=0;local clock=0
local function compose(a,b)
 local r={};for c=0,2 do for j=1,3 do r[c*3+j]=a[j]*b[c*3+1]+a[j+3]*b[c*3+2]+a[j+6]*b[c*3+3]end end
 for j=1,3 do r[j+9]=a[j]*b[10]+a[j+3]*b[11]+a[j+6]*b[12]+a[j+9]end;return r
end
for _,shape in ipairs(fixture)do
 local u={alive=true,resource=shape.resource,count=shape.count,kind=shape.kind,
  locals=copy(shape.locals),worlds=copy(shape.worlds),baseWorlds=copy(shape.worlds),parents=copy(shape.parents),names={},visible=shape.visible}
 for i,h in ipairs(shape.hashes)do u.names[h]=i end
 units[#units+1]=u
end
local A=units[1];local scratch={}
local function recycled(v)for k in pairs(scratch)do scratch[k]=nil end;for i,x in ipairs(v)do scratch[i]=x end;return scratch end
local function forbidden()mutationCalls=mutationCalls+1;error('read-only collector called a mutation')end
local S={Unit={},World={},Application={},Matrix4x4={},IdString64={},Mesh={}}
local U=S.Unit
U.alive=function(u)return u.alive end
U.num_scene_graph_items=function(u)return u.count end
U.resource_name=function(u)return u.resource end
U.has_node=function(u,h)return u.names[h]~=nil end
U.node=function(u,h)return u.names[h]end
U.scene_graph_parent=function(u,n)return u.parents[n]end
U.local_pose=function(u,n)check(u.alive and n<=u.count,'read dead/rebuilt unit');return recycled(u.locals[n])end
U.world_pose=function(u,n)check(u.alive and n<=u.count,'read dead/rebuilt unit');return recycled(u.worlds[n])end
U.num_meshes=function()return 1 end
U.mesh=function(u)return u end
S.Mesh.visibility=function(u)return u.visible~=false end
S.IdString64.to_hex=function(id)return id end
S.Matrix4x4.to_elements=function(m)return unpack(m)end
S.Application.worlds=function()return {1}end
S.Application.time_since_launch=function()return clock end
S.World.units=function()return units end
U.set_local_pose=forbidden;U.set_local_position=forbidden;U.set_local_rotation=forbidden
U.set_world_pose=forbidden;U.link=forbidden;U.unlink=forbidden;U.set_animation_state_machine=forbidden
S.World.update_unit=forbidden;S.World.link_unit=forbidden;S.World.unlink_unit=forbidden
-- STRICT_ID_FIXTURE
local function make(p)return module.new(S,p or profile,function(s)logs[#logs+1]=s end)end
local function has(part,start)for i=start or 1,#logs do if logs[i]:find(part,1,true)then return true end end;return false end
local function same(a,b)
 if type(a)~='table'then return a==b end
 for k,v in pairs(a)do if not same(v,b[k])then return false end end;return true
end
local instance=make();local left=A.names[hash_name('l_hand')];local firstModel
for _,u in ipairs(units)do if u.kind=='native_armor'and u.visible~=false then firstModel=firstModel or u end end
check(firstModel~=nil,'missing native model fixture')
-- Move all fixture graphs as a native engine animation would. Between update
-- and render, only the Avatar changes: no observer-induced model refresh is allowed.
for frame=1,14 do
 local a=frame*.07;local motion={math.cos(a),math.sin(a),0,-math.sin(a),math.cos(a),0,0,0,1,100+frame*.03,20,30}
 for _,u in ipairs(units)do for n,m in ipairs(u.baseWorlds)do u.worlds[n]=compose(motion,m)end end
 local before=copy(units);clock=frame*.25;strictIdStats.advanceFrame()
 check(instance:tick('update',frame,clock),'update sample missing')
 check(same(units,before),'update changed graph data')
 A.worlds[left][10]=A.worlds[left][10]+.01
 before=copy(units);strictIdStats.advanceFrame()
 check(instance:tick('render',frame,clock+.001),'render sample missing')
 check(same(units,before),'render refreshed/changed graph data')
end
check(instance.samples==14 and not instance.stopped,'normal sample limit wrong')
check(has('"layout":"native_107"')and has('"kind":"foregrip"')and has('"kind":"weapon"'),'native reference groups absent')
check(not has('"kind":"test01_model"'),'hidden test01 fixture captured')
check(has('"phase":"update"')and has('"phase":"render"'),'paired phases missing')
instance:stop('fixture_complete');local sampleLogs=copy(logs)
local stoppedCount=#logs;check(not instance:tick('update',99,99),'stopped collector ran');instance:stop();check(#logs==stoppedCount,'duplicate stop')
-- Identity/lifecycle changes between callbacks only remove the affected row.
for _,kind in ipairs({'dead','rebuilt','resource','renamed','hidden'})do
 instance=make();strictIdStats.advanceFrame();clock=clock+3;instance:tick('update',100,clock)
 local saved={count=firstModel.count,resource=firstModel.resource,names=copy(firstModel.names),visible=firstModel.visible}
 if kind=='dead'then firstModel.alive=false
 elseif kind=='rebuilt'then firstModel.count=firstModel.count-1
 elseif kind=='resource'then firstModel.resource='ffffffffffffffff'
 elseif kind=='renamed'then
  local spec=profile.resources[firstModel.resource].layouts[tostring(firstModel.count)].nodes[1]
  firstModel.names[hash_name(spec.name)]=nil
 else firstModel.visible=false end
 local start=#logs+1;strictIdStats.advanceFrame();instance:tick('render',100,clock+.001)
 check(has('"event":"unavailable"',start),'changed consumer not reported: '..kind)
 check(not instance.stopped,'one changed unit stopped collection')
 firstModel.alive=true;firstModel.count=saved.count;firstModel.resource=saved.resource
 firstModel.names=saved.names;firstModel.visible=saved.visible;instance:stop('fixture_lifecycle')
end
local limited=copy(profile);limited.maxSamples=2;instance=make(limited)
for i=1,3 do strictIdStats.advanceFrame();instance:tick('update',i,100+i);strictIdStats.advanceFrame();instance:tick('render',i,100+i+.001)end
check(instance.samples==2 and instance.stopped,'sample limit exceeded')
instance=make(limited);instance:tick('update',1,200);instance:tick('update',2,201);instance:tick('update',3,202)
check(instance.samples==2 and instance.stopped and has('"event":"incomplete_pair"'),'unpaired callbacks exceeded limit')
-- Hybrid layout is recorded honestly, never labeled as a native baseline.
local hybrid=copy(fixtureHybrid);A.count=hybrid.count;A.locals=hybrid.locals;A.worlds=hybrid.worlds
A.parents=hybrid.parents;A.names={};for i,h in ipairs(hybrid.hashes)do A.names[h]=i end
for _,u in ipairs(units)do if u.kind=='test01_model'then u.visible=true end end
instance=make();local start=#logs+1;strictIdStats.advanceFrame();instance:tick('update',1,300)
strictIdStats.advanceFrame();instance:tick('render',1,300.001)
check(has('"layout":"test01_255"',start)and not has('"layout":"native_107"',start),'hybrid mislabeled native')
check(mutationCalls==0,'mutator called')
check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'expired ID used')
return {checks=checks,sampleLogs=sampleLogs,mutationCalls=mutationCalls,pairedFrames=14,
 optionalLifecycleCases=5,hybridDistinguished=true,limitsEnforced=true,recycledMatrices=true,
 expiredIdCalls=strictIdStats.expiredArgumentCalls,allLogs=logs}
