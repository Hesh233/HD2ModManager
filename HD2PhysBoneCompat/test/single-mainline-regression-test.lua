-- Single-only master policy regression. Fake engine/call counts are NOT actual FPS.
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
    for i=1,(tonumber(arg[3]) or 128) do e:add({nodes=10}) end
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
    local options={compat=C,log=false,carriers={{rig={bones={{index=1,name="hair"}},drivers={version=3,bones={}}},path="fake"}},
        pollFrames=1,settleFrames=1,validateFrames=3,rescanFrames=6,heartbeatFrames=1000000,
        scoreUnitsPerFrame=2,minNodes=90}
    for k,v in pairs(opts or {})do options[k]=v end
    local engine=e:api();e.nativeCounts={}
    for _,group in ipairs({"Application","Unit","World","Vector3","Matrix4x4"})do
        for name,fn in pairs(engine[group])do if type(fn)=="function"then
            local key=group.."."..name;local original=fn
            engine[group][name]=function(...)e.nativeCounts[key]=(e.nativeCounts[key]or 0)+1;return original(...)end
        end end
    end
    local state=R.install(engine,options);installed=R;return state,C,R
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


local function opts(values)
 local result={scoreUnitsPerFrame=100,validateFrames=60,rescanFrames=0,maxChainsPerFrame=100000,heartbeatFrames=0,maxAvatars=4}
 for k,v in pairs(values or {})do result[k]=v end
 return result
end
local function setup(players,pieces,values)
 local e=fakeEngine();local avatars,parts={},{}
 for p=1,players do local av,armor=e:player("p"..p,(p-1)*20,pieces);avatars[p],parts[p]=av,armor end
 local state,C,R=install(e,opts(values));e:advance(120)
 return e,state,C,R,avatars,parts
end
local function nUpdates(C,units)
 local total=0;for _,u in ipairs(units)do total=total+#(C.updates[u]or{})end;return total
end
local function allStride(state,owner,stride)
 local found=false
 for _,s in ipairs(state.sessions or{})do
  if s.owner==owner then found=true;if s.singleStride~=stride then return false end end
 end
 return found
end
local function sessions(state)return #(state.sessions or{})end
local function singleRig(name)return{bones={{index=1,name=name or"hair"}},drivers={version=3,bones={}}}end

-- Positive metadata gating: native/untagged rigs do not acquire the new policy.
do
 local R=assert(loadfile(runtimePath))();local P=R.single_policy
 check("single policy provenance pins the verified master",P and P.UPSTREAM_COMMIT=="b78e63ebc77017aa6c70d52e0bf9e06e46360b92")
 check("legacy/dual policy explicitly remains 2.3.6",R.LEGACY_SKELETON_VERSION=="2.3.6")
 check("v3 single rig is positively recognized",P.is_rig(singleRig()))
 check("untagged rig is not guessed as single",not P.is_rig({bones={{name="hair"}}}))
 check("v2 rig retains the legacy path",not P.is_rig({bones={{name="hair"}},drivers={version=2}}))
 check("native namespace defeats even a forged v3 marker",not P.is_rig(singleRig("hd2n_aabbccdd_phys_1_skirt")))
 local a,b=P.schedule_budget(208,208,416,600)
 check("mainline pure budget returns the near/far tier",a==2 and b==4,a.."/"..b)
 local x,y=P.schedule_budget(832,0,0,160)
 check("no near chains restores the near tier even when primary is over-budget",x==1 and y==16,x.."/"..y)
end

-- Same-owner activity is the only evidence used to remove previews.
for _,players in ipairs({1,4})do
 local e,state,C,R,avatars,parts=setup(players,17,{maxUnits=4})
 local real,preview={},{}
 for p=1,players do
  for i,u in ipairs(parts[p])do if i<=8 then real[#real+1]=u else preview[#preview+1]=u end end
 end
 check(players.."p standing/unknown retains all 17 per player",sessions(state)==17*players,sessions(state))
 check(players.."p all units use the single-only policy",R.single_policy.active_only(state))
 check(players.."p player limit is not a four-armor-unit cap",sessions(state)>4)
 e:advance(120,0.01,function()
  for _,av in ipairs(avatars)do av.position.x=av.position.x+0.01 end
  for _,u in ipairs(real)do u.position.x=u.position.x+0.01 end
 end)
 check(players.."p movement converges to eight actual followers per owner",sessions(state)==8*players,sessions(state))
 local counts=countOwners(state)
 for p=1,players do check(players.."p owner "..p.." keeps eight independent sessions",counts[avatars[p]]==8)end
 check(players.."p each stationary preview is released once",#C.released==9*players,#C.released)
 C.updates={};e:advance(60)
 check(players.."p every genuine follower updates every measured frame",nUpdates(C,real)==8*players*60,nUpdates(C,real))
 check(players.."p previews receive no writes after classification",nUpdates(C,preview)==0,nUpdates(C,preview))
 check(players.."p filtering does not dereference dead units",e.deadCalls==0,e.deadCalls)
end

-- Preserve unknown identity, full chain count and primary cadence, even over budget.
do
 local e,state,C,R,avatars,parts=setup(1,17,{maxChainsPerFrame=160})
 C.updates={};e:advance(300)
 local chainTotal=0;for _,s in ipairs(state.sessions)do chainTotal=chainTotal+#s.sessions end
 check("standing primary retains all 442 complete chains",sessions(state)==17 and chainTotal==442,chainTotal)
 check("primary cannot be throttled to hide a frame-rate regression",allStride(state,avatars[1],1))
 check("primary 17 instances keep all 5100 updates in 300 frames",nUpdates(C,parts[1])==5100,nUpdates(C,parts[1]))
 check("unknown motion never releases a legitimate stationary part",#C.released==0)
end

-- No periodic full discovery at every roster validation; positive matches stay cached.
do
 local e,state,C,R,avatars,parts=setup(1,17)
 e.nativeCounts={};C.scores={};C.scoreMax=0;e:advance(180)
 check("stable roster does only cheap avatar-node checks",(e.nativeCounts["Unit.num_scene_graph_items"]or 0)<=6,e.nativeCounts["Unit.num_scene_graph_items"]or 0)
 check("positive single matches are not repeatedly rescored",C.scoreMax==0,C.scoreMax)
 check("stable single discovery has no pending fill",state.reconcile==nil and not state.fillPending)
 -- Check every carrier identity, not only count/first path as the old upstream key did.
 local a,b=singleRig(),singleRig();local carriers={{rig=a,path="a"},{rig=b,path="b"}}
 local s=R.single_policy.prepare(state,state.avatars,{},carriers)
 s.matches[parts[1][1]]={rig=a,nodes=120}
 local replacement={{rig=a,path="a"},{rig=singleRig(),path="b"}}
 local again=R.single_policy.prepare(state,state.avatars,{},replacement)
 check("changing the second carrier invalidates positive and retry caches",again.matches[parts[1][1]]==nil and next(again.attemptAt)==nil)
end

do
 local e,state,C,R,avatars,parts=setup(1,8)
 local victim=parts[1][1];local slot=state.singleLiveIndex and state.singleLiveIndex[victim]
 check("single fresh membership index contains every active part",slot and R.single_policy.member(state,victim))
 local calls=e.deadCalls;e:remove(victim)
 check("stale index cannot accept a shifted fresh inventory slot",not R.single_policy.member(state,victim))
 check("single index membership test performs no dead native dereference",e.deadCalls==calls)
 e:advance(1)
 check("single index is reconstructed after inventory mutation",state.singleLiveIndex[victim]==nil)
end

do
 local e,state,C,R,avatars,parts=setup(1,8)
 local watched=0;for _ in pairs(state.singleLiveIndex)do watched=watched+1 end
 check("single index stores only eight active parts plus one avatar",watched==9,watched)
 local original=state.sessions[1];local u=parts[1][1]
 local added=e:add({nodes=10});table.remove(e.units,#e.units);table.insert(e.units,1,added)
 check("shifted same-frame slot is rejected before any pointer dereference",not R.single_policy.member(state,u))
 e:advance(1)
 check("next fresh inventory pass resolves shifted active slots",R.single_policy.member(state,u))
 local same=false;for _,row in ipairs(state.sessions)do if row==original then same=true end end
 check("inventory reordering does not rebuild healthy single sessions",same and e.deadCalls==0)
end

do
 local e,state,C,R,avatars,parts=setup(1,8)
 local mt={__eq=function(a,b)local x,y=rawget(a,"backing")or a,rawget(b,"backing")or b;return x.id==y.id end,
  __index=function(a,k)local original=rawget(a,"backing");return original and original[k]end}
 local fresh={e:add({nodes=10})}
 for i=1,#state.liveUnits-1 do local u=state.liveUnits[i];setmetatable(u,mt);fresh[#fresh+1]=setmetatable({backing=u},mt)end
 state.liveUnits=fresh;R.single_policy.refresh_inventory(state)
 check("native-equal fresh wrapper keys are not mistaken for missing single Units",R.single_policy.member(state,parts[1][1]))
 check("native-equal wrapper fallback resolves all watched active slots",R.single_policy.member(state,parts[1][8])and R.single_policy.member(state,avatars[1]))
 check("native-equal wrapper fallback makes no Unit API dereferences",e.deadCalls==0)
end

-- Partial matching is single-only; complete present chains still belong to Compat.attach.
do
 local e=fakeEngine();local av,armor=e:player("partial",0,1);armor[1].chains=2
 local C=fakeCompat(e)
 C.select_rig=function(S,units,carriers)local row={rig=carriers[1].rig,path="partial",score=1,total=64,full=false};return row,{row}end
 local state=install(e,opts(),C);e:advance(40)
 check("single partial hit is attached rather than rejected as a whole-rig mismatch",sessions(state)==1)
 check("single partial attachment keeps every complete present chain",sessions(state)==1 and #state.sessions[1].sessions==2)
 local state2=install(e,opts({carriers={{rig={bones={{name="hd2n_aabbccdd_phys_1_skirt"}},drivers={version=2}},path="native"}}}),C)
 e:advance(40)
 check("same partial hit does not change the dual full-match contract",sessions(state2)==0)
end

-- Zero hits and a positive match with zero usable chains are retried, not cached forever.
for _,mode in ipairs({"zero-hit","zero-chain"})do
 local e=fakeEngine();local av,armor=e:player(mode,0,8);local ready=false;local C=fakeCompat(e);local scored=0
 C.select_rig=function(S,units,carriers)
  scored=scored+1
  local row={rig=carriers[1].rig,path=mode,score=(ready or mode=="zero-chain")and 1 or 0,total=1,full=(ready or mode=="zero-chain")}
  return row,{row}
 end
 if mode=="zero-chain"then for _,u in ipairs(armor)do u.chains=0 end end
 local state=install(e,opts({negativeRetryFrames=30,scoreUnitsPerFrame=2}),C);e:advance(40)
 check(mode.." keeps an empty rig in waiting rather than a false active state",sessions(state)==0)
 local before=scored;ready=true;for _,u in ipairs(armor)do u.chains=26 end;e:advance(90)
 check(mode.." recovers all eight parts without roster/count change",sessions(state)==8,sessions(state))
 check(mode.." genuine readiness can overturn a negative cached result",scored>before)
end

-- New, late-born layouts get the sparse single safety pass, not permanent omission.
do
 local e,state,C,R,avatars,parts=setup(1,8,{rescanFrames=300})
 local late=e:add({anim=false,mg=true,x=0.1,nodes=10,chains=3});e:advance(60);late.nodes=120;e:advance(360)
 check("sparse single-only recovery discovers a late-born part",sessions(state)==9,sessions(state))
 check("late-born graph contributes all its present chains",state.lastChainTotal==211,state.lastChainTotal)
end

-- Join/respawn/world teardown operate on actual handles, never debug/resource IDs.
do
 local e,state,C,R,avatars,parts=setup(1,8,{scoreUnitsPerFrame=2})
 local original=state.sessions[1]
 for p=2,4 do local av,armor=e:player("join"..p,(p-1)*20,8);avatars[p],parts[p]=av,armor end
 e:advance(180)
 check("one-to-four join fills all 32 genuine model instances",sessions(state)==32,sessions(state))
 local survived=false;for _,s in ipairs(state.sessions or{})do if s==original then survived=true end end
 check("late join never rebuilds the first player's existing session",survived)
 check("single scoring remains bounded while filling four players",C.scoreMax<=2,C.scoreMax)
 local victim=parts[2][1];e:remove(victim);C.updates={};e:advance(5)
 survived=false;for _,s in ipairs(state.sessions or{})do if s==original then survived=true end end
 check("single death keeps healthy teammate session objects",survived and sessions(state)==31)
 check("single death grace prevents writes during teardown",nUpdates(C,parts[1])==0,nUpdates(C,parts[1]))
 check("removed single unit is rejected before native Unit calls",e.deadCalls==0,e.deadCalls)
 e:advance(30)
 check("healthy single physics resumes after finite death grace",nUpdates(C,parts[1])>0)
 e.unreadable=true;e:advance(1)
 check("untrusted inventory discards all single session handles",state.sessions==nil and state.singleState==nil)
 check("untrusted inventory never probes stale single units",e.deadCalls==0)
 e.unreadable=false;e:advance(180)
 check("readable inventory restores surviving single instances",sessions(state)==31,sessions(state))
 e.worlds={};e:advance(1)
 check("world disappearance clears the private single state",state.sessions==nil and state.singleState==nil)
 check("world disappearance never dereferences the missing World",e.staleWorldCalls==0,e.staleWorldCalls)
 e.worlds={e.world};e:advance(180)
 check("world recovery restores the single route",sessions(state)==31,sessions(state))
end

-- Camera/first-person ownership and per-session staggering are copied from master.
do
 local e,state,C,R,avatars,parts=setup(4,8,{maxChainsPerFrame=600})
 e.camera=avatars[4].position.x;e:advance(10)
 check("single first-person lock learns the fourth real player",state.singleState.selfUnit==avatars[4])
 check("every part of the selected primary has stride one",allStride(state,avatars[4],1))
 local primary=true;for _,s in ipairs(state.sessions)do if s.owner==avatars[4] and s.singleOwnerOrder~=1 then primary=false end end
 check("first-person lock reprioritizes all primary single parts",primary)
 e.camera=avatars[4].position.x-4.5;avatars[3].position.x=e.camera-0.8;e:advance(180)
 check("learned primary survives a third-person camera-nearest teammate",state.singleState.selfUnit==avatars[4] and allStride(state,avatars[4],1))
end
do
 local e=fakeEngine();local av1,part1=e:player("primary",0,8);local av2,part2=e:player("near",4,8)
 local state,C=install(e,opts({maxChainsPerFrame=300}));e:advance(120);C.updates={};e:advance(6)
 local strides={};for _,s in ipairs(state.sessions)do if s.owner==av2 then strides[s.singleStride]=true end end
 check("near singles use the exact mainline budget tier",strides[3] and next(strides,3)==nil)
 check("primary gets every frame while near teammate is tiered",nUpdates(C,part1)==48 and nUpdates(C,part2)==16,nUpdates(C,part1).."/"..nUpdates(C,part2))
 local times={};for _,u in ipairs(part2)do for _,row in ipairs(C.updates[u]or{})do times[row.time]=true end end
 local n=0;for _ in pairs(times)do n=n+1 end
 check("same-owner parts are staggered by session index, not one burst",n==6,n)
 local accumulated=true;for _,u in ipairs(part2)do for _,row in ipairs(C.updates[u]or{})do if math.abs(row.dt-0.03)>1e-8 then accumulated=false end end end
 check("single teammate stride retains exact accumulated dt",accumulated)
end
do
 local e=fakeEngine();local av1,part1=e:player("unknown1",0,8);local av2,part2=e:player("unknown2",20,8);av2.nodes=180;e.cameraMissing=true
 local state,C=install(e,opts({maxChainsPerFrame=160}));e:advance(120)
 check("unknown camera cannot throttle any unconfirmed primary",allStride(state,av1,1)and allStride(state,av2,1))
 e.cameraMissing=false;e.camera=0;e:advance(120)
 check("single camera retry learns the real primary without a full scan",state.singleState.selfUnit==av1 and allStride(state,av1,1),"self="..tostring(state.singleState.selfUnit and state.singleState.selfUnit.name).." fp="..tostring(state.singleState.fpLockFrames).." err="..tostring(state.driveErrorLogged).." camera="..tostring(state.cache.cameraUsable))
 C.updates={};local clock=e.clock;for _=1,20 do rawget(_G,"render")()end
 check("duplicate callback time does not integrate physics again",nUpdates(C,part1)==0 and e.clock==clock)
end

-- Only single sessions participate in preview cleanup, even in a mixed container set.
do
 local e=fakeEngine();local av,armor=e:player("mixed",0,18);for i,u in ipairs(armor)do u.native=i>17 end
 local single,native=singleRig(),{bones={{name="hd2n_aabbccdd_phys_1_skirt"}},drivers={version=2}}
 local C=fakeCompat(e);C.select_rig=function(S,units,carriers)
  local row={rig=units[1].native and native or single,path="mixed",score=1,total=1,full=true};return row,{row}
 end
 local state=install(e,opts({carriers={{rig=single,path="single"},{rig=native,path="native"}}}),C);e:advance(120)
 local nativeSession;for _,s in ipairs(state.sessions)do if s.unit==armor[18]then nativeSession=s end end
 e:advance(120,0.01,function()av.position.x=av.position.x+0.01;for i=1,8 do armor[i].position.x=armor[i].position.x+0.01 end end)
 local preserved=false;for _,s in ipairs(state.sessions)do if s==nativeSession then preserved=true end end
 check("mixed policy does not classify native/dual sessions as single",nativeSession and nativeSession.singleMainline==nil)
 check("mixed preview cleanup preserves the native session object",preserved and sessions(state)==9,sessions(state))
 check("mixed preview cleanup releases only the nine single previews",#C.released==9,#C.released)
end
if installed then installed.uninstall()end
check("single uninstall restores render and clears the install key",rawget(_G,"__hd2physbone_runtime")==nil)
print("single-mainline-regression: "..checks.." checks, "..failures.." failures")
assert(failures==0,"single mainline regression failure")
