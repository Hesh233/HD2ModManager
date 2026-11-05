-- Appended after the affine fixture helpers, before their existing test cases.
-- The fake weapon/foregrip consume native-right position via cached links.
-- This tests numeric telemetry and read-only behavior, not real game ownership.
local p=copy(profile);p.nativeGripAlignment.logFrames=1
local obs=p.nativeGripAlignment.consumerObservation
local function identity(x,y,z)return {1,0,0,0,1,0,0,0,1,x or 0,y or 0,z or 0}end
local function makeConsumer(resource,names,locals,link)
 local u={alive=true,count=#names,resource=resource,locals=locals,parents={},names={},link=link,cached={}}
 for i,name in ipairs(names)do u.parents[i]=i==1 and 0 or 1;u.names[hash_name(name)]=i end
 return u
end
local gun=makeConsumer('fixture_gun',{'skeleton','IK_left','IK_right'},
 {identity(),identity(0,.25,0),identity()},{unit=avatar,node=85})
local grip=makeConsumer('fixture_foregrip',{'skeleton','game_mesh','IK_left'},
 {identity(0,.18,0),identity(),identity(0,0,-.05)},{unit=gun,node=1})
local far=makeConsumer('fixture_far',{'skeleton','IK_left','IK_right'},
 {identity(50,0,0),identity(),identity()},{unit=avatar,node=85})
local function refresh(u)
 local anchor=u.link.unit==avatar and world(avatar,u.link.node)or copy(u.link.unit.cached[u.link.node])
 for i,m in ipairs(u.locals)do u.cached[i]=compose(u.parents[i]==0 and anchor or u.cached[u.parents[i]],m)end
end
local function refreshAll()refresh(gun);refresh(grip);refresh(far)end
local function item(u,kind,w)return {unit=u,resource=u.resource,kind=kind,world=w or 1,count=u.count}end
local consumers={item(gun,'weapon'),item(grip,'weapon_grip'),item(far,'weapon'),item(gun,'weapon',2),item(grip,'intelpad')}
local originalWorld=U.world_pose
U.world_pose=function(u,n)
 if u==avatar then return originalWorld(u,n)end
 assert(not u.readFault,'injected consumer read failure')
 return recycled(u.cached[n])
end
local function has(part,start)
 for i=start or 1,#logs do if logs[i]:find(part,1,true)then return true end end
 return false
end
local function metrics(resource,name,start)
 for i=start,#logs do
  local row=logs[i]
  if row:find('event=consumer ',1,true)and row:find('resource='..resource..' ',1,true)
    and row:find('name='..name..' ',1,true)then
   local values={};for k,v in row:gmatch('([%w_]+)=([^ ]+)')do values[k]=tonumber(v)or v end;return values
  end
 end
end
local function dist(a,b)local d=0;for j=10,12 do d=d+(a[j]-b[j])^2 end;return math.sqrt(d)end
local instance=make(p)
for frame=1,4 do
 strictIdStats.advanceFrame();instance:restore_all(frame)
 avatar.locals[139][10]=base[139][10]+frame*.04
 refreshAll();local gunBefore=copy(gun.cached);local gripBefore=copy(grip.cached)
 local before=snapshot();local localsBefore=copy(avatar.locals);local start=#logs+1
 check(instance:apply(actor,true,frame,consumers),'consumer-enabled alignment failed');aligned(before,localsBefore)
 check(#instance.samples[1].nearby==2,'distance/world/kind consumer filter failed')
 refreshAll();strictIdStats.advanceFrame();instance:after_refresh()
 check(not instance.disabled,'observation disabled valid alignment')
 for _,r in ipairs({{gun,gunBefore,'IK_left',2},{gun,gunBefore,'IK_right',3},{grip,gripBefore,'IK_left',3}})do
  local row=metrics(r[1].resource,r[3],start);check(row~=nil,'consumer marker not logged')
  local actual=r[1].cached[r[4]];local beforePose=r[2][r[4]]
  for j,key in ipairs({'dx','dy','dz'})do check(math.abs(row[key]-(actual[9+j]-beforePose[9+j]))<6e-7,'incorrect telemetry '..key)end
  check(math.abs(row.source_l_before_m-dist(beforePose,world(avatar,obs.leftSourceIndex+1)))<6e-7,'incorrect previous left gap')
  check(math.abs(row.source_l_m-dist(actual,world(avatar,obs.leftSourceIndex+1)))<6e-7,'incorrect left gap')
  check(math.abs(row.source_r_m-dist(actual,world(avatar,obs.rightSourceIndex+1)))<6e-7,'incorrect right gap')
  check(math.abs(row.wrist_l_m-dist(actual,world(avatar,obs.leftWristIndex+1)))<6e-7,'incorrect wrist gap')
  check(row.owner=='unverified'and row.phase=='post_refresh','observation claims ownership or wrong phase')
 end
 check(not has('resource=fixture_far',start),'distant consumer included')
end
instance:restore_all(5)
-- Bounds and missing candidates are explicit diagnostics, never pose writes.
reset();refreshAll();local limited=copy(p);limited.nativeGripAlignment.consumerObservation.maxUnits=1
instance=make(limited);check(instance:apply(actor,true,1,consumers),'bounded observation failed')
check(#instance.samples[1].nearby==1,'consumer bound ignored');instance:restore_all(2)
reset();refreshAll();instance=make(p);local start=#logs+1
check(instance:apply(actor,true,1,{}),'empty observation disabled alignment');instance:after_refresh()
check(has('nearby=0',start)and not has('event=consumer ',start),'empty candidate state missing');instance:restore_all(2)
-- Failure in optional diagnostics must leave a valid native transaction active.
for _,fault in ipairs({'read','api','renamed','rebuilt','dead'})do
 reset();refreshAll();instance=make(p);start=#logs+1
 local countApi=U.num_scene_graph_items;local name=hash_name('IK_left');local savedName=gun.names[name]
 if fault=='read'then gun.readFault=true
 elseif fault=='api'then U.num_scene_graph_items=function(u)if u==gun then error('consumer API unavailable')end;return countApi(u)end end
 strictIdStats.advanceFrame();check(instance:apply(actor,true,1,consumers),'optional pre-read failure stopped alignment: '..fault)
 if fault=='renamed'then gun.names[name]=nil
 elseif fault=='rebuilt'then gun.count=gun.count+1
 elseif fault=='dead'then gun.alive=false end
 refreshAll();strictIdStats.advanceFrame();instance:after_refresh()
 check(not instance.disabled,'optional consumer failure stopped alignment: '..fault)
 if fault=='read'or fault=='api'or fault=='renamed'then check(has('event=consumer_unavailable',start),'missing diagnostic read failure')end
 gun.readFault=nil;gun.names[name]=savedName;gun.count=3;gun.alive=true;U.num_scene_graph_items=countApi
 instance:restore_all(2)
end
-- Configuration mistakes fail closed before writing a native node.
for _,fault in ipairs({'rotation','parent','source_range','anchor','limit','distance'})do
 reset();local bad=copy(p)
 if fault=='rotation'then bad.nativeGripAlignment.pairs[1].rotationMode='guess-90'
 elseif fault=='parent'then bad.nativeGripAlignment.pairs[1].target.parentIndex=0
 elseif fault=='source_range'then bad.nativeGripAlignment.pairs[1].source.index=219
 elseif fault=='anchor'then bad.nativeGripAlignment.consumerObservation.leftWristIndex=47
 elseif fault=='limit'then bad.nativeGripAlignment.consumerObservation.maxUnits=0
 else bad.nativeGripAlignment.consumerObservation.maxDistance=-1 end
 instance=make(bad);check(instance.disabled and not instance:apply(actor,true,1,consumers)and writes==0,'invalid config wrote: '..fault)
end
check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'consumer retained invalid ID')
return {checks=checks,logs=logs,consumerWrites=0,numericTelemetryVerified=true,gunAndForegripObserved=true,
 recycledMatrices=true,freshIdsBetweenPhases=true,optionalFailureCases=5,invalidConfigCases=6,
 sourceUnchanged=true,scope='Simulated existing consumer links; real game ownership remains unverified.'}
