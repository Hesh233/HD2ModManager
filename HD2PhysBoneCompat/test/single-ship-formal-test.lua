-- Ship correction release gate; no game/deployment/test package requested.
if not arg[1]or not arg[2]then print("SKIP formal ship runtime/compat required");return end
local f=assert(io.open("HD2PhysBoneCompat/test/single-ads-formal-test.lua","r"));local old=f:read("*a");f:close()
local at=assert(old:find('for _,n in ipairs({1,2,4})do',1,true));local prefix=old:sub(1,at-1)
prefix=prefix:gsub('e.fp=false;e.fpCalls=0','e.fp=false;e.fpCalls=0;e.levels=(values and values.sceneLevels)or 0;e.mission=e.levels>10;e.wid=1;e.stable=true')
prefix=prefix:gsub('local S=originalApi%(self%);','local S=originalApi(self);if not (values and values.sceneViaLoader) then S.World.num_levels=function()return e.levels end end;')
prefix=prefix:gsub('local state,_,R=H.install%(e,H.opts%(values%),C%);',[[local opts=H.opts(values);opts.sceneContext={api=1,world=function()if e.stable then return e.world end end,world_id=function()return e.wid end,in_mission=function()return e.mission end,call=function(name,w)assert(name=="World.num_levels" and w==e.world);e.levelCalls=(e.levelCalls or 0)+1;return e.levels end};local state,_,R=H.install(e,opts,C);]])
local body=[[
for _,lv in ipairs({1,2})do for _,n in ipairs({1,2,4})do
 local e,st,C,R,av,parts=make(n,7,n,{sceneLevels=lv})
 C.updates={};local calls=e.fpCalls;e:advance(60)
 check(lv.."lvl/"..n.."p ship is classified without any first-person query",st.singleState.sceneMode=="ship" and calls==0 and e.fpCalls==0 and st.singleState.adsIdentity==nil)
 local runs=0;local allVrd=true;for p=1,n do runs=runs+H.nUpdates(C,parts[p]);allVrd=allVrd and vrd(C,parts[p],true)end
 check(lv.."lvl/"..n.."p A/B ship has full spring dispatch for every actor",runs==n*420,runs)
 check(lv.."lvl/"..n.."p A/B ship VRD is enabled for every actor",allVrd)
 check(lv.."lvl/"..n.."p ship never falsely learns a local identity",st.singleState.selfUnit==nil)
end end
do
 local e,st,C,R,av,parts=make(4,7,4,{sceneLevels=1})
 local world=e.world;e.levels=1042;e.mission=true;e.wid=2;e:advance(1);C.updates={};e:advance(40)
 check("same-world ship to mission changes the policy immediately",e.world==world and st.singleState.sceneMode=="mission" and st.singleState.selfUnit==nil)
 local count=0;local noVrd=true;for p=1,4 do count=count+H.nUpdates(C,parts[p]);noVrd=noVrd and vrd(C,parts[p],false)end
 check("ship VRD cannot leak into any unconfirmed mission actor",noVrd)
 check("mission pre-aim retains the exact A/B spring policy",count==(A and 0 or 1120),count)
 e.fp=true;e:advance(100);C.updates={};e:advance(60)
 check("mission still confirms local identity once by actual FP view",st.singleState.selfUnit==av[4] and st.singleState.adsIdentity.checks==3)
 check("confirmed mission local has full spring and VRD",H.nUpdates(C,parts[4])==420 and vrd(C,parts[4],true))
 local remote=0;for p=1,3 do remote=remote+H.nUpdates(C,parts[p]);check("confirmed mission remote "..p.." VRD remains off",vrd(C,parts[p],false))end
 check("confirmed mission remote spring policy stays A/B",remote==(A and 0 or 1260))
 local fpCalls=e.fpCalls;e.fp=false;e.levels=2;e.mission=false;e.wid=3;e:advance(1);C.updates={};e:advance(60)
 count=0;allVrd=true;for p=1,4 do count=count+H.nUpdates(C,parts[p]);allVrd=allVrd and vrd(C,parts[p],true)end
 check("same-world return to ship restores everyone's springs and VRD",count==1680 and allVrd)
 check("return to ship does not query first-person or retain the mission latch",e.fpCalls==fpCalls and st.singleState.selfUnit==nil and st.singleState.adsIdentity==nil)
 e.levels=900;e.mission=true;e.wid=4;e:advance(40)
 check("next mission requires its own initial aim rather than old ship/mission identity",st.singleState.sceneMode=="mission" and st.singleState.selfUnit==nil)
end
do
 local e,st,C,R,av,parts=make(2,7,1,{sceneLevels=0})
 C.updates={};e:advance(60)
 check("level zero/loading is not falsely classified as ship",st.singleState.sceneMode=="unknown" and vrd(C,parts[1],false) and vrd(C,parts[2],false))
 e.levels=1;e.stable=false;e:advance(40)
 check("loader's unavailable main world overrides a tempting ship level",st.singleState.sceneMode=="unknown")
 e.stable=true;e:advance(40)
 check("stable main world restores the genuine ship branch",st.singleState.sceneMode=="ship")
end
do
 local e,st,C,R,av,parts=make(2,7,1,{sceneLevels=2,sceneViaLoader=true})
 check("actual Chef call helper works when the protected World API omits levels",st.singleState.sceneMode=="ship" and (e.levelCalls or 0)>0)
 check("Chef api revision number is never treated as a callable",st.options.sceneContext.api==1)
 e.levels=nil;e.mission=true;e.wid=7;e:advance(40)
 check("positive loader mission signal works without level data",st.singleState.sceneMode=="mission")
 e.mission=false;e:advance(1)
 check("temporary same-id mission checking false does not open ship VRD",st.singleState.sceneMode=="unknown")
 e.wid=8;e:advance(1)
 check("new stable non-mission id can restore the loader ship fallback",st.singleState.sceneMode=="ship")
end
H.finish()
]]
assert(loadstring(prefix..body))()
