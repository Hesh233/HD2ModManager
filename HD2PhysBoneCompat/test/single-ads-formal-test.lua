-- Offline release gate only. No new gameplay/test-package cycle requested.
if not arg[1] or not arg[2] then print("SKIP: requires formal runtime + compat");return end
local f=assert(io.open("HD2PhysBoneCompat/test/single-mainline-regression-test.lua","r"));local source=f:read("*a");f:close()
local marker="-- Positive metadata gating: native/untagged rigs do not acquire the new policy."
local at=assert(source:find(marker,1,true))
local H=assert(loadstring(source:sub(1,at-1)..[[
return {check=check,fakeEngine=fakeEngine,fakeCompat=fakeCompat,install=install,opts=opts,nUpdates=nUpdates,sessions=sessions,allStride=allStride,singleRig=singleRig,
finish=function()if installed then installed.uninstall()end;print("single-ads-formal: "..checks.." checks, "..failures.." failures");assert(failures==0)end}
]]))()
local check=H.check;local R0=assert(loadfile(arg[1]))();local A=R0.FORMAL_PHYSICS_VARIANT=="A"
check("formal identity revision and policy are present",R0.IDENTITY_POLICY=="first-person-aim-once-v1" and (A or R0.FORMAL_PHYSICS_VARIANT=="B"))
local function make(players,pieces,selected,values)
 local e=H.fakeEngine();local avatars,parts={},{}
 for p=1,players do avatars[p],parts[p]=e:player("p"..p,(p-1)*20,pieces)end
 e.fpOwner=avatars[selected or 1];e.camera=e.fpOwner.position.x;e.fp=false;e.fpCalls=0
 local fp=e:add({nodes=63,anim=true,mg=false,eligible=false,name="retained-fp"});fp.fp=true;e.fpGraph=fp
 local originalApi=e.api
 e.api=function(self)
  local S=originalApi(self);local has,node,alive,by=S.Unit.has_node,S.Unit.node,S.Unit.alive,S.World.units_by_resource
  S.Unit.has_node=function(u,n)if u.fp then return n=="camera" or n=="root"end;return has(u,n)end
  S.Unit.node=function(u,n)if u.fp then return n=="root" and 5 or (e.badCameraNode or 51)end;return node(u,n)end
  S.Unit.resource_name=function(u)return u.fp and "d0cf4d493ca08bed" or "4d1c334d294dfa97"end
  S.IdString64={to_hex=function(x)return x end}
  S.World.units_by_resource=function(w,res)
   if res=="content/fac_helldivers/fp_cha_avatar/fp_cha_avatar" then
    e.fpCalls=e.fpCalls+1;return e.fpGraph and {e.fpGraph}or{}
   end
   return by(w,res)
  end
  S.World.debug_camera_pose=function()if e.cameraMissing then return nil end;return{x=e.camera,y=0,z=e.fp and 1.7 or 4.5}end
  S.Unit.world_pose=function(u,n)
   alive(u);assert(u.fp and n==51);e.fpPoseReads=(e.fpPoseReads or 0)+1
   return{x=e.fpOwner.position.x+(e.fpOffset or 0),y=0,z=1.7}
  end
  S.Matrix4x4.to_elements=function(p)return 1,0,0,0,1,0,0,0,1,p.x,p.y,p.z end
  return S
 end
 local C=H.fakeCompat(e);local attach,update=C.attach,C.update
 C.attach=function(S,u,r,opts)local s=attach(S,u,r,opts);s.drivers={};for i=1,6 do s.drivers[i]={node=i}end;return s end
 C.single_remote_policy_transition=function(s,p,v)if p or s.singleRemotePhysicsExcluded then s.pendingDt=0 end end
 C.update=function(s,dt)local n=update(s,dt);local row=C.updates[s.unit][#C.updates[s.unit]];row.vrd=s.evaluateDrivers;row.off=s.singleRemotePhysicsExcluded
  if s.evaluateDrivers~=false then s.driverWrites=(s.driverWrites or 0)+6 end;return n end
 local state,_,R=H.install(e,H.opts(values),C);e:advance(120)
 return e,state,C,R,avatars,parts
end
local function vrd(C,parts,wanted)
 for _,u in ipairs(parts)do for _,r in ipairs(C.updates[u]or{})do if r.vrd~=wanted then return false end end end;return true
end
for _,n in ipairs({1,2,4})do
 local e,st,C,R,av,parts=make(n,7,n)
 C.updates={};e:advance(60)
 check(n.."p retained graph/root-near camera cannot enable self before FP",st.singleState.selfUnit==nil and st.singleState.adsIdentity.checks==0)
 check(n.."p pre-aim dispatch policy is exact",H.nUpdates(C,parts[n])==(A and 0 or 420))
 local disabled=true;for p=1,n do disabled=disabled and vrd(C,parts[p],false)end
 check(n.."p VRD is disabled for every unconfirmed instance",disabled)
 e.fp=true;e:advance(80)
 check(n.."p unique FP view learns the correct instance",st.singleState.selfUnit==av[n] and st.singleState.adsIdentity.owner==av[n])
 check(n.."p owner checks run only during the three FP proofs",st.singleState.adsIdentity.checks==3)
 local calls=e.fpCalls;local checks=st.singleState.adsIdentity.checks;C.updates={};e:advance(120)
 check(n.."p no FP query after first confirmation",e.fpCalls==calls and st.singleState.adsIdentity.checks==checks)
 check(n.."p local solver and VRD remain full-rate",H.nUpdates(C,parts[n])==840 and vrd(C,parts[n],true) and H.allStride(st,av[n],1))
 local count=0;for p=1,n do if p~=n then count=count+H.nUpdates(C,parts[p]);check(n.."p remote VRD stays disabled",vrd(C,parts[p],false))end end
 check(n.."p remote solver follows its formal A/B policy",count==(A and 0 or (n-1)*840))
 e.fp=false;e.camera=av[n].position.x-4.5;C.updates={};e:advance(120)
 check(n.."p third-person exit does not recheck or stop local physics",e.fpCalls==calls and H.nUpdates(C,parts[n])==840)
 check(n.."p does not dereference dead units",e.deadCalls==0)
end
do
 local e,st,C,R,av,parts=make(4,17,4,{maxChainsPerFrame=160,maxUnits=4})
 e.fp=true;e:advance(80);C.updates={};e:advance(60)
 check("four players is not four units; all 17 local parts survive",H.sessions(st)==68 and H.nUpdates(C,parts[4])==1020)
 check("over-budget local VRD and stride one remain unchanged",vrd(C,parts[4],true) and H.allStride(st,av[4],1))
 local calls=e.fpCalls;e.fp=false;e.camera=av[4].position.x-4.5;av[3].position.x=e.camera-.8;C.updates={};e:advance(60)
 check("camera-nearest teammate cannot replace the latched local instance",st.singleState.selfUnit==av[4] and e.fpCalls==calls and H.nUpdates(C,parts[4])==1020)
end
do
 local e,st,C,R,av,parts=make(2,7,1);e.fp=true;e.badCameraNode=52;e:advance(80)
 check("wrong FP native camera node cannot enable physics",st.singleState.selfUnit==nil)
 e.badCameraNode=nil;e.fpGraph.nodes=97;e:advance(80)
 check("appended Source outputs preserve the verified native FP prefix",st.singleState.selfUnit==av[1])
 local calls=e.fpCalls;local extra,extraParts=e:player("late",40,7);e.fp=false;e:advance(120)
 check("teammate join never restarts first-person identification",e.fpCalls==calls and st.singleState.selfUnit==av[1])
 e:remove(parts[1][1]);local replacement=e:add({anim=false,name="replaced-part",x=.01});e:advance(120)
 check("same-owner armor replacement does not restart identity checks",e.fpCalls==calls and st.singleState.selfUnit==av[1])
 check("replacement inherits local VRD automatically",vrd(C,{replacement},true) and H.nUpdates(C,{replacement})>0)
 e:remove(av[1]);for _,u in ipairs(parts[1])do if u.alive then e:remove(u)end end;e:advance(120)
 check("local instance death clears the latch without promoting a teammate",st.singleState.selfUnit==nil and st.singleState.adsIdentity.owner==nil)
 local fresh,newParts=e:player("respawn",60,7);e.fpOwner=fresh;e.camera=60;e.fp=false;e:advance(120)
 check("respawn does not enable VRD without a new FP aim",st.singleState.selfUnit==nil and vrd(C,newParts,false))
 e.fp=true;e:advance(100);C.updates={};e:advance(60)
 check("new lifetime can confirm once and restore its own full physics",st.singleState.selfUnit==fresh and H.nUpdates(C,newParts)==420 and vrd(C,newParts,true))
 check("lifecycle never dereferences removed Units",e.deadCalls==0)
 e.worlds={};e:advance(1)
 check("world disappearance discards all old identity/session handles",st.singleState==nil and st.sessions==nil and e.staleWorldCalls==0)
 e.worlds={e.world};e.fp=false;e:advance(180)
 check("new world stays waiting until another verified FP view",st.singleState.selfUnit==nil)
 e.fp=true;e:advance(100);local k=e.fpCalls;e:advance(120)
 check("recovered world confirms once then stops all FP queries",st.singleState.selfUnit==fresh and e.fpCalls==k)
end
do
 local e,st,C,R,av,parts=make(2,7,1)
 e.fp=true;av[2].position.x=av[1].position.x;e:advance(100)
 check("two TP avatars at the FP point are ambiguous, not chosen by rank",st.singleState.selfUnit==nil)
 av[2].position.x=20;e:advance(100)
 check("unique owner proof becomes available without reinstalling",st.singleState.selfUnit==av[1])
 check("formal package never installs the old long performance sampler",st.perf==nil)
end
H.finish()
