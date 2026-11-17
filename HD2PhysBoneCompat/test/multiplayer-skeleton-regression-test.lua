-- Single/dual skeleton multiplayer discovery and scheduling regression.
-- Runs against either source or a frozen pre-fix runtime; no game/Blender/IO writes.
local runtimePath = arg[1] or "HD2PhysBoneCompat/src/physbone_runtime.lua"
local compatPath = arg[2] or "HD2PhysBoneCompat/src/physbone_compat.lua"
local failures, checks = 0, 0
local function check(name, ok, detail)
    checks = checks + 1
    print(string.format("  %-4s %s%s", ok and "PASS" or "FAIL", name, detail and (" ["..tostring(detail).."]") or ""))
    if not ok then failures = failures + 1 end
end
local function vec(x,y,z) return {x=x or 0,y=y or 0,z=z or 0} end
local Fake = {}; Fake.__index = Fake
local function fakeEngine(nameOnly)
    local e=setmetatable({units={},world={},clock=0,camera=0,nameOnly=nameOnly,deadCalls=0,
        staleWorldCalls=0,factoryCalls=0,nextId=0},Fake)
    e.worlds={e.world}
    for i=1,40 do e:add({nodes=10}) end
    return e
end
function Fake:add(spec)
    self.nextId=self.nextId+1
    local u={id=self.nextId,nodes=spec.nodes or 120,alive=true,avatar=spec.avatar==true,
        anim=spec.anim~=false,mg=spec.mg~=false,position=vec(spec.x or 0),eligible=spec.eligible~=false,
        chains=spec.chains or 26,name=spec.name or ("unit"..self.nextId)}
    self.units[#self.units+1]=u;return u
end
function Fake:player(name,x,pieces)
    local av=self:add({avatar=true,name=name.."-avatar",x=x})
    local armor={}
    for i=1,pieces do armor[i]=self:add({anim=false,name=name.."-part"..i,x=x+0.01*i}) end
    return av,armor
end
function Fake:remove(unit)
    for i=#self.units,1,-1 do if self.units[i]==unit then table.remove(self.units,i) end end
    unit.alive=false
end
function Fake:api()
    local e=self
    local function valid(u)
        if not u or not u.alive then e.deadCalls=e.deadCalls+1;error("native-deref-of-dead-unit") end
        return u
    end
    local S={Unit={},World={},Application={},Vector3={},Matrix4x4={}}
    S.Application.worlds=function()return e.worlds end
    S.Application.time_since_launch=function()return e.clock end
    S.Application.string_to_id32=function(name)
        e.factoryCalls=e.factoryCalls+1
        if e.nameOnly then error("expired-id32-factory") end
        return name
    end
    S.Unit.alive=function(u)valid(u);return true end
    S.Unit.num_scene_graph_items=function(u)return valid(u).nodes end
    S.Unit.has_animation_state_machine=function(u)return valid(u).anim end
    S.Unit.has_node=function(u,name)
        valid(u)
        return name=="support_mg" and u.mg or (name=="hair" and u.eligible)
    end
    S.Unit.world_position=function(u)return valid(u).position end
    S.Unit.debug_name=function(u)valid(u);return "#ID[same-resource]" end
    S.World.units=function(world)
        if e.unreadable then error("inventory-not-ready") end
        local present=false;for _,w in ipairs(e.worlds)do if w==world then present=true end end
        if not present then e.staleWorldCalls=e.staleWorldCalls+1;error("stale-world-deref") end
        return e.units
    end
    S.World.units_by_resource=function(world,resource)
        local out={}
        for _,u in ipairs(e.units)do if u.alive and u.avatar then out[#out+1]=u end end
        if e.ghost then out[#out+1]=e.ghost end
        return out
    end
    S.World.debug_camera_pose=function()if e.cameraMissing then return nil end;return vec(e.camera) end
    S.World.update_unit=function()end
    S.Vector3.to_elements=function(v)return v.x,v.y,v.z end
    S.Matrix4x4.translation=function(p)return p end
    return S
end
function Fake:advance(n,step,before)
    for i=1,n do
        if before then before(i) end
        self.clock=self.clock+(step or 0.01);_G.render()
    end
end
local function fakeCompat(e)
    local C={attached={},released={},updates={},scores={},scoreMax=0}
    C.unit_alive=function(S,u)return S.Unit.alive(u) end
    C.begin_frame=function()end
    C.select_rig=function(S,units,carriers)
        local u=units[1];C.scores[e.clock]=(C.scores[e.clock] or 0)+1
        C.scoreMax=math.max(C.scoreMax,C.scores[e.clock])
        local row={rig=carriers[1].rig,path="fake",full=u.eligible,score=u.eligible and 1 or 0,total=1}
        return row,{row}
    end
    C.attach=function(S,u,rig,options)
        local row={S=S,unit=u,nodeCount=u.nodes,rig=rig,sessions={},logger=function()end}
        for i=1,u.chains do row.sessions[i]={} end
        C.attached[#C.attached+1]=u;return row
    end
    C.session_health=function(session)
        return C.unit_alive(session.S,session.unit) and "ok" or "dead"
    end
    C.update=function(session,dt)
        if not session.unit.alive then e.deadCalls=e.deadCalls+1;error("dead-unit-write") end
        local rows=C.updates[session.unit] or {};C.updates[session.unit]=rows
        rows[#rows+1]={time=e.clock,dt=dt};session.engineCalls=1;session.skippedSame=1;return 1
    end
    C.release=function(session)
        if not session.unit.alive then e.deadCalls=e.deadCalls+1;error("dead-unit-release") end
        C.released[#C.released+1]=session.unit;return #session.sessions
    end
    return C
end
local installed
local function install(e,opts,C)
    if installed then installed.uninstall() end
    rawset(_G,"__hd2physbone_runtime",nil);rawset(_G,"render",function()end)
    local R=assert(loadfile(runtimePath))();C=C or fakeCompat(e)
    local options={compat=C,log=false,carriers={{rig={bones={{index=1,name="hair"}}},path="fake"}},
        pollFrames=1,settleFrames=1,validateFrames=3,rescanFrames=6,heartbeatFrames=1000000,
        scoreUnitsPerFrame=2,minNodes=90}
    for k,v in pairs(opts or {})do options[k]=v end
    local state=R.install(e:api(),options);installed=R;return state,C,R
end
local function countOwners(state)
    local out={}
    for _,s in ipairs(state.sessions or {})do out[s.owner]=(out[s.owner] or 0)+1 end
    return out
end
local function allPrimary(state,av)
    local n=0
    for _,s in ipairs(state.sessions or {})do
        if s.owner==av then n=n+1;if s.ownerOrder~=1 then return false end end
    end
    return n==8
end

for _,route in ipairs({"single-v3","dual-native-v2"})do
    local e=fakeEngine();local av={}
    for i=1,4 do av[i]=e:player(route.."-p"..i,(i-1)*20,8) end
    local state,C=install(e);e:advance(240)
    local owners=countOwners(state)
    check(route..": all 32 parts attach (not only the first 16)",#(state.sessions or {})==32,#(state.sessions or {}))
    for i=1,4 do check(route..": player "..i.." owns all 8 parts",owners[av[i]]==8,owners[av[i]]) end
    check(route..": bounded scoring quota is respected",C.scoreMax<=2,C.scoreMax)
    check(route..": aggregate primary-chain budget counts every local part",state.lastPrimaryChains==208,state.lastPrimaryChains)
end

do
    local e=fakeEngine()
    for i=1,200 do e:add({x=1000+i,anim=false,name="far-display-"..i}) end
    local av={};for i=1,4 do av[i]=e:player("p"..i,(i-1)*20,8) end
    local state=install(e);e:advance(240)
    check("enumeration order: 200 distant display units do not hide the live 32 parts",#(state.sessions or {})==32,#(state.sessions or {}))
end

do
    local e=fakeEngine();local av=e:player("p1",0,8)
    local noise;local state=install(e)
    e:advance(160,0.01,function(i)
        if i%2==1 then noise=e:add({nodes=10}) else e:remove(noise) end
    end)
    check("mission background churn does not prevent initial attachment",#(state.sessions or {})==8,#(state.sessions or {}))
end

do
    local e=fakeEngine();e:player("p1",0,8)
    local late=e:add({anim=false,name="late-graph",x=0.15,eligible=false})
    local state=install(e);e:advance(80);late.eligible=true;e:advance(80)
    local found=false;for _,s in ipairs(state.sessions or {})do if s.unit==late then found=true end end
    check("late skeleton readiness is retried without an avatar/Unit-count change",found)
end

do
    local e=fakeEngine();local av1,parts1=e:player("p1",0,8)
    local state=install(e);e:advance(80);local before={}
    for _,s in ipairs(state.sessions or {})do before[s.unit]=s end
    local av2=e:player("p2",20,8);e:advance(80)
    local retained=true
    for _,s in ipairs(state.sessions or {})do if before[s.unit] and before[s.unit]~=s then retained=false end end
    check("late join attaches all 16 parts",#(state.sessions or {})==16,#(state.sessions or {}))
    check("late join keeps existing session objects",retained)
    e.camera=20;e:advance(20)
    check("camera priority change updates all parts of the new primary player",allPrimary(state,av2))
    e.camera=0;e:advance(20)
    check("camera priority returns to all parts of the original player",allPrimary(state,av1))
end

do
    local e=fakeEngine();local av,parts=e:player("p1",0,8)
    local state=install(e);e:advance(80)
    local before=e.deadCalls;e:remove(parts[1]);e:advance(1)
    check("removed armor is rejected before any Unit API dereference",e.deadCalls==before,e.deadCalls-before)
    check("default death policy drops the complete handle group",state.sessions==nil or #state.sessions==0)
    e:advance(80)
    check("surviving parts are reattached after death instead of freezing forever",#(state.sessions or {})==7,#(state.sessions or {}))
end

do
    local e=fakeEngine();e:player("p1",0,8)
    local state=install(e);e:advance(80)
    e.worlds={};e:advance(1)
    check("world disappearance releases all cached sessions and avatars",state.sessions==nil and state.avatars==nil)
    check("world disappearance never calls World.units on the removed world",e.staleWorldCalls==0,e.staleWorldCalls)
    e.worlds={e.world};e:advance(80)
    check("world recovery reattaches physics",#(state.sessions or {})==8,#(state.sessions or {}))
end

do
    local e=fakeEngine();e:player("p1",0,8)
    local state=install(e);e:advance(80)
    for _,u in ipairs(e.units)do if u.nodes>=90 then e:remove(u) end end
    -- Use a fresh list after a loading gap; old handles must never be inspected.
    local remaining={};for _,u in ipairs(e.units)do if u.alive then remaining[#remaining+1]=u end end;e.units=remaining
    local before=e.deadCalls;e:advance(1,2.0)
    check("loading-gap recovery does not query dead handles",e.deadCalls==before,e.deadCalls-before)
    check("loading gap clears avatars as well as sessions",state.sessions==nil and state.avatars==nil)
end

do
    local e=fakeEngine(true);e:player("p1",0,8)
    local state=install(e);e:advance(80)
    check("named-node discovery does not depend on a working IdString32 factory",#(state.sessions or {})==8,#(state.sessions or {}))
    check("named-node discovery allocates no IdString32 handles",e.factoryCalls==0,e.factoryCalls)
end

do
    local e=fakeEngine();local av1=e:player("single-local",0,8)
    local av2=e:player("dual-peer",20,8);av2.nodes=300;e.cameraMissing=true
    local state,C=install(e);e:advance(80)
    check("unknown camera cannot throttle the smaller local single-skeleton avatar",state.driveStride==1,state.driveStride)
    e.cameraMissing=false;e:advance(80)
    check("a temporarily unavailable camera is retried in the same world",state.cache.cameraUsable==true)
    check("camera recovery assigns primary priority to every local part",allPrimary(state,av1))
end

do
    local e=fakeEngine();local corpse=e:player("old-player",0,8)
    local state=install(e);e:advance(80)
    corpse.anim=false;corpse.eligible=false
    local newAvatar,loading=e:player("respawn",20,8)
    for _,part in ipairs(loading)do part.eligible=false end
    e:advance(50)
    check("respawn with unready models returns to waiting, not an empty active array",state.sessions==nil)
    for _,part in ipairs(loading)do part.eligible=true end
    e:advance(80)
    local owned=0;for _,session in ipairs(state.sessions or {})do if session.owner==newAvatar then owned=owned+1 end end
    check("delayed respawn model graphs recover all eight parts",owned==8,owned)
end

for _,mode in ipairs({"world-list-nil","inventory-unreadable"})do
    local e=fakeEngine();e:player("p1",0,8)
    local state=install(e);e:advance(80)
    for _,u in ipairs(e.units)do u.alive=false end
    if mode=="world-list-nil"then e.worlds=nil else e.unreadable=true end
    e:advance(1)
    check(mode..": fail closed without dereferencing prior Unit handles",e.deadCalls==0,e.deadCalls)
    check(mode..": clear every cached owner/session handle",state.sessions==nil and state.avatars==nil)
end

do
    local e=fakeEngine();e:player("p1",0,8)
    local ghost=e:add({avatar=true,name="gone-avatar"});e:remove(ghost);e.ghost=ghost
    local state=install(e);e:advance(80)
    check("ghost in units_by_resource is filtered by current inventory before Unit APIs",e.deadCalls==0,e.deadCalls)
    check("ghost avatar cannot steal or prevent live-player physics",#(state.sessions or {})==8,#(state.sessions or {}))
end

if installed then installed.uninstall();installed=nil end
-- Exercise the real accepted solver, not only a scheduler stub.
local C=assert(loadfile(compatPath))()
local e=fakeEngine(true);local av,parts=e:player("real-solver",0,8);local S=e:api()
local function q(x,y,z,w)return{x=x,y=y,z=z,w=w}end
local names={head=2,hair1=10,hair2=11};local writes=0;local badNodes=0
S.Unit.has_node=function(u,name)
    if not u.alive then e.deadCalls=e.deadCalls+1;error("dead-unit") end
    if name=="support_mg" then return u.mg end
    return not u.avatar and names[name]~=nil
end
S.Unit.node=function(u,name)return names[name] or 1 end
S.Unit.name_hash=function(u)return u.avatar and "avatar-resource" or "same-model-resource" end
S.Unit.local_pose=function(u,node)
    if type(node)~="number" or node<1 or node>u.nodes then badNodes=badNodes+1;error("bad-index") end
    return {kind="pose"}
end
S.Unit.local_rotation=function()return q(0,0,0,1)end
S.Unit.world_rotation=function()return q(0,0,0,1)end
S.Unit.world_position=function(u,node)return vec(u.position.x,(node or 1)*0.02,1)end
S.Unit.set_local_pose=function(u,node)if not u.alive then error("dead-write")end;writes=writes+1 end
S.Unit.set_local_rotation=S.Unit.set_local_pose
S.Quaternion={to_elements=function(v)return v.x,v.y,v.z,v.w end,
    from_elements=q,axis_angle=function(axis,angle)return q(0,0,math.sin(angle/2),math.cos(angle/2))end}
S.Matrix4x4.to_elements=function()return 1,0,0,0,1,0,0,0,1,0,0,0 end
S.Matrix4x4.from_quaternion_position=function()return{kind="pose"}end
S.Matrix4x4.is_valid=function()return true end
setmetatable(S.Vector3,{__call=function()return vec()end})
local params={tipMass=200,yawStiffness=50,yawDamping=7,pitchStiffness=50,pitchDamping=7,angleLimit=0.611,length=30}
local rig={bones={{index=1,name="hair1",parent=0,parentName="head",pos={0,0,0},flags=0x31,params=params},
    {index=2,name="hair2",parent=1,parentName="hair1",pos={0,0.1,0},flags=0x31,params=params}}}
local best=C.select_rig(S,{parts[1]},{{rig=rig,path="real"}})
check("real solver matches the complete rig by stable bone names",best and best.full)
local session=C.attach(S,parts[1],rig,{world=e.world,fastWrite=true})
check("real solver attaches the full chain when IdString32 is unavailable",#(session.sessions or {})==1,#(session.sessions or {}))
check("session identity stores a stable string, not an expiring token",session.identityNode=="hair1",type(session.identityNode))
for i=1,60 do C.begin_frame(i);C.update(session,0.01)end
check("real named-node solver writes physical poses",writes>0,writes)
check("real named-node path performs no out-of-range pose reads",badNodes==0,badNodes)
local factoryBefore=e.factoryCalls
local shared=C.shared_physics_nodes(S,av,rig)
check("shared-node guard correctly rejects physics ownership in the avatar",shared==0,shared)
check("real named-node matching/attach/identity does not allocate expiring IDs",factoryBefore==0,factoryBefore)
-- Token-only legacy binding remains supported without storing factory results.
if C.has_named_node then
    local tokenFrame=0;local tokenCalls=0
    local T={Application={string_to_id32=function(name)tokenCalls=tokenCalls+1;return{name=name,frame=tokenFrame}end},Unit={}}
    T.Unit.has_node=function(u,ref)if type(ref)~="table"then return false end;assert(ref.frame==tokenFrame);return ref.name=="hair1" end
    T.Unit.node=function(u,ref)assert(ref.frame==tokenFrame);return 10 end
    check("fresh-token fallback resolves legacy name bindings",C.resolve_named_node(T,{},"hair1",120)==10)
    tokenFrame=tokenFrame+1
    check("fresh-token fallback does not reuse an earlier frame's ID",C.resolve_named_node(T,{},"hair1",120)==10 and tokenCalls==2,tokenCalls)
end
print(string.format("multiplayer-skeleton-regression: %d checks, %d failures",checks,failures))
if failures>0 then os.exit(1)end
