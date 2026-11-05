-- Appended to attachments_layout_harness's fixture setup. Each split model
-- has a cached graph; animated inputs reset at frame start, as an independent
-- consumer can otherwise hide a missing explicit refresh behind live reads.
local parts={}
for _,resource in ipairs(profile.consumerTargets.body)do
 parts[#parts+1]=make(false,A.x,resource,A)
end
world=function(u,index)
 if u.owner and u.cached and u.cached[index] then return copy(u.cached[index])end
 local p=copy(u.locals[index]);local parent=u.parents[index]
 if parent~=0 then p=adapter.compose(world(u,parent),p)else p.p[1]=p.p[1]+u.x end
 return p
end
local function refresh(u,count)
 if not u.owner then return end
 u.cached={}
 for index,h in ipairs(u.hashes)do
  local source=u.owner.names[h]
  if source then
   local p=world(u.owner,source);p.p[1]=p.p[1]+u.x-u.owner.x
   u.cached[index]=p
  end
 end
 if count then u.refreshes=(u.refreshes or 0)+1 end
end
S.World.update_unit=function(_,u)
 check(u.alive,'refresh on dead split Unit')
 refresh(u,true)
end
-- Give the native grip a measurable change. The solver and animation inputs
-- are identical for old/new modules; only consumer refresh membership differs.
local nativeHand=profile.armChains[1].nativeHand+1
A.locals[nativeHand].p[2]=A.locals[nativeHand].p[2]+.04
local animationA=copy(A.locals);local animationB=copy(B.locals)
tick=function(n)
 for _=1,n or 1 do
  frame=frame+1;clock=clock+1/60
  A.locals=copy(animationA);B.locals=copy(animationB)
  for _,u in ipairs(units)do if u.alive then refresh(u,false)end end
  runtime:tick(frame)
 end
end
tick(4)
check(runtime.stats.active==1,'original torso selector did not activate')
local gaps={};local weightedHands=0
for _,part in ipairs(parts)do
 check((part.refreshes or 0)>0,'split part not refreshed: '..part.resource)
 check(part.writes==0,'split consumer received direct local-pose writes')
 for _,chain in ipairs(profile.armChains)do
  for _,node in ipairs(chain.nodes)do if node.index==chain.hand then
   local hash=hash_name(node.name);local index=part.names[hash]
   local a=world(A,chain.hand+1);local b=world(part,index)
   local d=0;for j=1,3 do d=d+(a.p[j]-b.p[j])^2 end
   gaps[#gaps+1]=math.sqrt(d)
   check(adapter.close(a,b),'split part retained pre-solver arm pose: '..part.resource)
   if weighted_hand_resources[part.resource]==node.name then weightedHands=weightedHands+1 end
  end end
 end
end
check(weightedHands==2,'actual drawn left/right hand Units were not covered')
-- Only the original torso/head Units can select the body slot.
armor.visible=false;tick(4)
check(runtime.stats.active==0,'split arm alone activated the entire body profile')
armor.visible=true;tick(4)
check(runtime.stats.active==1,'torso selector did not reacquire')
local part=parts[1];local count=part.refreshes
part.visible=false;tick(1)
check(part.refreshes==count,'hidden split model refreshed')
part.visible=true;tick(2)
count=part.refreshes;local oldResource=part.resource
part.resource='ffffffffffffffff';tick(1)
check(part.refreshes==count,'changed-resource split model refreshed')
part.resource=oldResource;tick(3)
count=part.refreshes;local oldNodes=part.nodes
part.nodes=oldNodes-1;tick(1)
check(part.refreshes==count,'changed-layout split model refreshed')
part.nodes=oldNodes;tick(3)
count=part.refreshes
part.alive=false;tick(1)
check(part.refreshes==count,'destroyed split model refreshed')
part.alive=true;tick(3)
-- Ambiguous owners must not make a consumer into an activation selector.
B.x=A.x;animationB=copy(animationA);count=part.refreshes;tick(2)
check(runtime.stats.active==0 and part.refreshes==count,'ambiguous owner refreshed split model')
B.x=4;tick(3)
check(runtime.stats.active==1,'unique ownership did not reacquire')
check(readMissing==0,'missing name used as a valid node index')
local maxGap=0;for _,d in ipairs(gaps)do maxGap=math.max(maxGap,d)end
return {checks=checks,splitConsumers=#parts,weightedHandUnits=weightedHands,maxCachedHandGap=maxGap,
 independentModelGraphs=true,selectorsUnchanged=true,sourceLocalWritesOnly=true}
