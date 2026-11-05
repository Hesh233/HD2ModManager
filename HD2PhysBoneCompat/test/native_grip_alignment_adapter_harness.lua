-- Appended to the common fixture setup. All 11 split model Units have separate
-- name-bound cached graphs, as in the established model-refresh regression.
local cfg=profile.nativeGripAlignment
local parts={armor}
for resource in pairs(profile.modelLayouts)do if resource~=armor.resource then parts[#parts+1]=make(false,A.x,resource,A)end end
for _,u in ipairs(parts)do for i,h in ipairs(u.hashes)do if A.names[h]then u.locals[i]={p={0,0,0},q={0,0,0,1}}end end end
world=function(u,n)
 if u.fixtureLink and u.cached and u.cached[n]then return copy(u.cached[n])end
 if u.owner and u.cached and u.cached[n]then return copy(u.cached[n])end
 local p=copy(u.locals[n]);local parent=u.parents[n]
 if parent~=0 then return adapter.compose(world(u,parent),p)end;p.p[1]=p.p[1]+u.x;return p
end
local function refresh(u)
 if u.fixtureLink then
  u.cached={}
  local anchor=world(u.fixtureLink.unit,u.fixtureLink.node)
  for i,p in ipairs(u.locals)do
   u.cached[i]=adapter.compose(u.parents[i]==0 and anchor or u.cached[u.parents[i]],p)
  end
  return
 end
 if not u.owner then return end
 u.cached={};for i,h in ipairs(u.hashes)do local n=u.owner.names[h]
  if n then u.cached[i]=adapter.compose(world(u.owner,n),u.locals[i])end
 end
end
S.World.update_unit=function(_,u)refresh(u)end
S.Unit.world_pose=function(u,n)return world(u,n)end
S.Unit.scene_graph_parent=function(u,n)return u.parents[n]end
S.Matrix4x4.from_elements=function(...)
 local m={...};local q=quat_from_matrix(m);return {q={q[1],q[2],q[3],q[4]},p={m[10],m[11],m[12]}}
end
-- Simulate separate, already-linked gun and foregrip graphs. These fixtures
-- exercise discovery/refresh/observation; they do not assert a real game link.
local consumerFixtures={}
local function makeConsumer(resource,names,poses,link)
 local u={alive=true,avatar=false,x=0,resource=resource,nodes=#names,locals=poses,
  parents={},hashes={},names={},writes=0,written={},missing={},fixtureLink=link}
 for i,name in ipairs(names)do u.parents[i]=i==1 and 0 or 1;u.hashes[i]=hash_name(name);u.names[u.hashes[i]]=i end
 units[#units+1]=u;consumerFixtures[#consumerFixtures+1]=u;refresh(u);return u
end
if cfg and cfg.consumerObservation and cfg.consumerObservation.enabled then
 local gun=makeConsumer('f100000000000001',{'skeleton','IK_left','IK_right'},
  {{p={0,0,0},q={0,0,0,1}},{p={0,.25,0},q={0,0,0,1}},{p={0,0,0},q={0,0,0,1}}},{unit=A,node=85})
 makeConsumer('f100000000000002',{'skeleton','game_mesh','IK_left'},
  {{p={0,.18,0},q={0,0,0,1}},{p={0,0,0},q={0,0,0,1}},{p={0,0,-.05},q={0,0,0,1}}},{unit=gun,node=1})
end
local allowed={};if cfg then for _,p in ipairs(cfg.pairs)do allowed[p.target.index+1]=true end end
local setter=S.Unit.set_local_pose
S.Unit.set_local_pose=function(u,n,p)
 if cfg then check(u==A and allowed[n],'Source, other Avatar or model written')end
 return setter(u,n,p)
end
local animationA=copy(A.locals);local animationB=copy(B.locals)
local function runTick()
 strictIdStats.advanceFrame();frame=frame+1;clock=clock+1/60
 for _,u in ipairs(parts)do refresh(u)end
 runtime:tick(frame)
end
local function checkSource()
 for i=108,196 do check(adapter.close(A.locals[i],animationA[i]),'Source local changed '..i)end
 check(B.writes==0,'other Avatar written')
 for _,u in ipairs(parts)do check(u.writes==0,'model offset written')end
 for _,u in ipairs(consumerFixtures)do check(u.writes==0,'external consumer written')end
end
local enabled=cfg and profile.diagnosticMode=='apply'
local history={}
for k=1,20 do
 A.locals=copy(animationA);B.locals=copy(animationB)
 local before={};if cfg then for _,p in ipairs(cfg.pairs)do before[p.target.index]=world(A,p.target.index+1)end end
 runTick()
 if cfg then
  checkSource()
  if k>=2 then
   check(runtime.stats.active==(enabled and 1 or 0),'wrong active selection')
   if enabled then for _,p in ipairs(cfg.pairs)do
    local expected=copy(world(A,p.source.index+1))
    if p.rotationMode=='native-world'then expected.q=copy(before[p.target.index].q)end
    check(adapter.close(world(A,p.target.index+1),expected),'full adapter missed target')
   end end
  end
 end
 history[k]=copy(A.locals)
end
if not cfg then return {checks=checks,history=history,logs=logs,writes=A.writes,protectedRight=runtime.protectedParents[84]==true}end
check(not hasLog('native_hand_sync')and not hasLog('palm_contact_error')and not hasLog('attachment_readback'),'legacy writer ran')
check(not hasLog('[scene_probe]'),'bulk legacy observation still enabled')
check(not hasLog('event=disabled'),'alignment disabled during valid frames')
if enabled and #consumerFixtures>0 then
 check(#runtime.consumers==2,'gun/foregrip discovery failed')
 check(hasLog('event=consumer')and hasLog('resource=f100000000000001 kind=weapon name=IK_left')
  and hasLog('resource=f100000000000002 kind=weapon_grip name=IK_left'),'consumer list not observed by alignment')
 for _,u in ipairs(consumerFixtures)do
  local expected=adapter.compose(world(u.fixtureLink.unit,u.fixtureLink.node),u.locals[1])
  check(adapter.close(world(u,1),expected),'consumer refresh order incorrect')
 end
end
-- Hide body selectors but leave a head visible: body alignment must stop.
for _,u in ipairs(parts)do if profile.modelLayouts[u.resource].ownerSlot=='body'then u.visible=false end end
runTick();check(runtime.stats.active==0,'head-only selected body alignment');checkSource()
for _,p in ipairs(cfg.pairs)do check(adapter.close(A.locals[p.target.index+1],animationA[p.target.index+1]),'switch-away failed restoration')end
for _,u in ipairs(parts)do u.visible=true end
runTick();runTick();check(runtime.stats.active==(enabled and 1 or 0),'reacquisition failed')
-- Identical avatar signatures are ambiguous; never choose by proximity.
B.x=0;runTick();check(runtime.stats.active==0 and runtime.stats.ambiguous>0,'ambiguous body accepted')
checkSource();B.x=4;runTick();runTick()
strictIdStats.advanceFrame();runtime:release();checkSource()
for _,p in ipairs(cfg.pairs)do check(adapter.close(A.locals[p.target.index+1],animationA[p.target.index+1]),'release retained native override')end
check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'ID lifetime contract failed')
return {checks=checks,logs=logs,history=history,writes=A.writes,modelCount=#parts,otherAvatarWrites=B.writes,
 sourceWrites=0,consumerCount=#consumerFixtures,consumerWrites=0,headOnlyIgnored=true,
 ambiguousOwnershipRejected=true,switchAndReleaseRestored=true}
