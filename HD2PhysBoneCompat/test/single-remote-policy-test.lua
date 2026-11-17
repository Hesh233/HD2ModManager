-- A/B DEFAULT-policy regression: real runtime + fake engine, NOT a game FPS test.
-- Reuse the established fake-engine helpers, without rerunning its full-policy tests.
if not arg[1] or not arg[2] then print("SKIP single-remote-policy: supply isolated A/B runtime AND compat paths");return end
local file=assert(io.open("HD2PhysBoneCompat/test/single-mainline-regression-test.lua","r"))
local original=file:read("*a");file:close()
local marker="-- Positive metadata gating: native/untagged rigs do not acquire the new policy."
local at=assert(original:find(marker,1,true))
local exports=[[
return {check=check,fakeEngine=fakeEngine,fakeCompat=fakeCompat,install=install,opts=opts,
 nUpdates=nUpdates,sessions=sessions,allStride=allStride,singleRig=singleRig,
 finish=function()if installed then installed.uninstall()end;print("single-remote-policy: "..checks.." checks, "..failures.." failures");assert(failures==0)end}
]]
local H=assert(loadstring(original:sub(1,at-1)..exports))()
local check=H.check
local runtimePath=assert(arg[1]);local compatPath=assert(arg[2])
local inspect=assert(loadfile(runtimePath))();local variant=inspect.REMOTE_TEST_VARIANT
local off=variant=="A"
check("test uses a default A/B policy, not a full-policy override",variant=="A" or variant=="B")
check("default policy matches its distinct version",(off and inspect.VERSION=="2.3.9" and inspect.REMOTE_TEST_POLICY=="self-only") or (not off and inspect.VERSION=="2.3.10" and inspect.REMOTE_TEST_POLICY=="remote-no-vrd"))
local function compat(e)
 local C=H.fakeCompat(e);local attach,update=C.attach,C.update
 C.attach=function(S,u,rig,options)
  local s=attach(S,u,rig,options);s.drivers={};for i=1,6 do s.drivers[i]={node=i}end;return s
 end
 C.single_remote_policy_transition=function(s,p,v)
  if p and s.singleRemotePhysicsExcluded~=true then s.singleRemoteHadUpdate=false end
  if p or s.singleRemotePhysicsExcluded then s.pendingDt=0 end
 end
 C.update=function(s,dt)
  local n=update(s,dt);local row=C.updates[s.unit][#C.updates[s.unit]]
  row.evaluateDrivers=s.evaluateDrivers;row.physicsOff=s.singleRemotePhysicsExcluded;row.remote=s.singleRemoteIsRemote
  if s.evaluateDrivers~=false then s.driverWrites=(s.driverWrites or 0)+6 end
  return n
 end
 return C
end
local function setup(players,pieces,localPlayer,values)
 local e=H.fakeEngine();local avatars,parts={},{}
 for p=1,players do local a,b=e:player("p"..p,(p-1)*20,pieces);avatars[p],parts[p]=a,b end
 e.camera=avatars[localPlayer or 1].position.x
 local C=compat(e);local state,_,R=H.install(e,H.opts(values),C);e:advance(120)
 return e,state,C,R,avatars,parts
end
local function driversEnabled(C,units,wanted)
 for _,u in ipairs(units)do for _,row in ipairs(C.updates[u]or{})do if row.evaluateDrivers~=wanted then return false end end end
 return true
end
for _,players in ipairs({1,2,4})do
 local selected=players;local e,state,C,R,av,parts=setup(players,7,selected)
 C.updates={};e:advance(120)
 check(players.."p learns the local instance even when last in the initial roster",state.singleState.selfUnit==av[selected])
 check(players.."p keeps all seven pieces per player (four players is not a unit cap)",H.sessions(state)==players*7,H.sessions(state))
 check(players.."p local physics updates all seven parts every frame",H.nUpdates(C,parts[selected])==840,H.nUpdates(C,parts[selected]))
 check(players.."p local VRD remains enabled",driversEnabled(C,parts[selected],true))
 check(players.."p local stride remains one",H.allStride(state,av[selected],1))
 local others=0;local dtOk=true;local pendingOk=true
 for p=1,players do if p~=selected then
  others=others+H.nUpdates(C,parts[p]);check(players.."p remote "..p.." has no VRD evaluation",driversEnabled(C,parts[p],false))
 end end
 for _,s in ipairs(state.sessions)do
  if s.singleRemoteIsRemote then
   if off and s.pendingDt~=0 then pendingOk=false end
   for _,row in ipairs(C.updates[s.unit]or{})do if math.abs(row.dt-.01)>1e-8 then dtOk=false end end
  end
 end
 check(players.."p remote solver count matches A/B",others==(off and 0 or (players-1)*840),others)
 check(players.."p A has no disabled-time accumulation",pendingOk)
 check(players.."p B preserves original remote dt",dtOk)
 check(players.."p diagnostic records exact remote exclusions",state.remoteTestStats.physicsExcluded==(off and (players-1)*7*26 or 0) and state.remoteTestStats.vrdExcluded==(players-1)*7*6)
 check(players.."p unknown owner count is zero",state.remoteTestStats.unknownOwners==0)
 check(players.."p has no dead native accesses",e.deadCalls==0)
end
do
 local e,state,C,R,av,parts=setup(4,17,4,{maxChainsPerFrame=160,maxUnits=4})
 C.updates={};e:advance(60)
 check("over-budget self retains all 17 complete-chain sessions",H.nUpdates(C,parts[4])==1020)
 check("over-budget self retains VRD and stride one",driversEnabled(C,parts[4],true) and H.allStride(state,av[4],1))
end
do
 local e,state,C,R,av,parts=setup(4,7,4)
 -- Third-person: another player is nearer the camera, but is not the learned self.
 e.camera=av[4].position.x-4.5;av[3].position.x=e.camera-.8
 C.updates={};e:advance(120)
 check("a camera-nearest teammate cannot become local by sorting",state.singleState.selfUnit==av[4] and state.remoteTestSelf==av[4])
 check("camera-nearest teammate cannot disable the learned local player",H.nUpdates(C,parts[4])==840 and driversEnabled(C,parts[4],true))
 check("learned local player is never throttled",H.allStride(state,av[4],1))
end
do
 local e=H.fakeEngine();local av,parts={},{}
 for p=1,4 do av[p],parts[p]=e:player("identical-resource-name",(p-1)*20,7);av[p].name="same-id";for _,u in ipairs(parts[p])do u.name="same-id"end end
 e.camera=av[2].position.x;local C=compat(e);local state=H.install(e,H.opts(),C);e:advance(120);C.updates={};e:advance(60)
 check("same-resource/name actors remain 28 distinct sessions",H.sessions(state)==28)
 check("same resource/name does not suppress the local instance",H.nUpdates(C,parts[2])==420)
 local n=0;for p=1,4 do if p~=2 then n=n+H.nUpdates(C,parts[p])end end
 check("same-name remote instances receive the intended separate gates",n==(off and 0 or 1260))
end
do
 local e=H.fakeEngine();local a,p=e:player("unknown-local",0,7);local b,q=e:player("unknown-team",20,7);e.cameraMissing=true
 local C=compat(e);local state=H.install(e,H.opts(),C);e:advance(120);C.updates={};e:advance(60)
 check("unknown multiplayer identity fails open instead of disabling self",state.remoteTestStats.identity=="ambiguous-aim-first-person" and H.nUpdates(C,p)==420 and H.nUpdates(C,q)==420)
 check("unknown identity cannot silently disable either player's VRD",driversEnabled(C,p,true) and driversEnabled(C,q,true))
 e.cameraMissing=false;e.camera=0;e:advance(120);C.updates={};e:advance(60)
 check("first-person identification enables the gate without a restart",state.remoteTestStats.identity=="fp-confirmed" and state.remoteTestSelf==a)
 check("newly identified local keeps full solver and VRD",H.nUpdates(C,p)==420 and driversEnabled(C,p,true))
 check("identified remote receives A/B immediately",H.nUpdates(C,q)==(off and 0 or 420) and driversEnabled(C,q,false))
 -- Returning to full mode proves disabled time was discarded, not caught up.
 state.options.singleRemoteTestPolicy="full";C.updates={};e:advance(6)
 check("re-enable restores remote solver and VRD without rebuilding rig",H.nUpdates(C,q)==42 and driversEnabled(C,q,true))
 local exact=true;for _,u in ipairs(q)do for _,row in ipairs(C.updates[u]or{})do if math.abs(row.dt-.01)>1e-8 then exact=false end end end
 check("re-enable does not inject accumulated disabled dt",exact)
end
do
 local e,state,C,R,av,parts=setup(2,7,1)
 e:remove(av[1]);for _,u in ipairs(parts[1])do e:remove(u)end;e:advance(120);C.updates={};e:advance(60)
 check("surviving teammate is not relabeled self after local death",state.remoteTestStats.identity=="await-local-respawn" and state.remoteTestStats.selfUnits==0)
 check("local death preserves the intended remote gate",H.nUpdates(C,parts[2])==(off and 0 or 420) and driversEnabled(C,parts[2],false))
 local a,p=e:player("local-respawn",40,7);e.camera=40;e:advance(180);C.updates={};e:advance(60)
 check("respawn learns a new local instance",state.remoteTestSelf==a and state.remoteTestStats.identity=="fp-confirmed")
 check("respawn local physics and VRD both resume",H.nUpdates(C,p)==420 and driversEnabled(C,p,true))
 check("death/respawn never dereferences removed Units",e.deadCalls==0)
 e.worlds={};e:advance(1)
 check("world loss clears remote identity and sessions",state.sessions==nil and state.remoteTestConfirmedSelf==nil and state.remoteTestStats==nil)
 check("world loss never dereferences missing world",e.staleWorldCalls==0)
 e.worlds={e.world};e:advance(180)
 check("world recovery relearns local with no stale identities",state.remoteTestSelf==a)
 C.updates={};for i=1,20 do _G.render()end
 check("duplicate render time does not run another solver",H.nUpdates(C,p)==0)
end
do
 local e=H.fakeEngine();local a,p=e:player("local",0,1);local b,q=e:player("remote",20,2);q[2].native=true
 local C=compat(e);C.select_rig=function(S,units,carriers)local rig=units[1].native and {bones={{name="hd2n_aa_phys_skirt"}},drivers={version=2}} or H.singleRig();local row={rig=rig,path="mixed",score=1,total=1,full=true};return row,{row}end
 local state=H.install(e,H.opts(),C);e:advance(120);C.updates={};e:advance(60)
 local native;for _,s in ipairs(state.sessions)do if s.unit==q[2] then native=s end end
 check("native/dual never receives a single remote flag",native and native.singleMainline==nil and native.singleRemoteVrdExcluded==nil and native.singleRemotePhysicsExcluded==nil)
 check("native/dual retains original solver and VRD",H.nUpdates(C,{q[2]})==60 and driversEnabled(C,{q[2]},true))
end
do
 local actual=assert(loadfile(compatPath))()
 check("compat API rejects remote VRD before any engine read",actual.update_drivers({singleRemoteVrdExcluded=true,drivers={{}}},.01)==0)
 check("compat API rejects remote full update before any engine read",actual.update({singleRemotePhysicsExcluded=true},.01)==0)
 check("compat API avoids repeated remote pose restoration",actual.release({singleRemotePhysicsExcluded=true})==0)
end
H.finish()
