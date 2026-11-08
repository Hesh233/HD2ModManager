-- P/40-K inverse experiment: independent Source wrist -> native two-bone arm.
local reverseResult={}
local reverseDelegate=U.set_local_pose;local reverseAllow={}
U.set_local_pose=function(u,n,m)
 if u==A and reverseAllow[n] then
  local value=copy(m);recycled();u.locals[n]=value;writes=writes+1
  if failAt==writes then failAt=nil;error('injected_native_reverse_failure')end
 else reverseDelegate(u,n,m)end
end
local function reverse_start(rid)
 repaired_start(rid or 'dbb6c961c59fadc1');aim_native();native_contact(.30)
 integratedProfile.bodySync.enabled=false
 integratedProfile.testRepairs.nativeReverse.enabled=true
 integratedProfile.testRepairs.nativeReverse.maxShiftMetres=1
 reverseAllow={}
 for i,node in ipairs(integratedProfile.testRepairs.nativeReverse.arm.nodes)do
  if i>1 then reverseAllow[node.index+1]=true end
 end
 local root=integratedProfile.testRepairs.nativeReverse.arm.nodes[2].index+1
 local ci=integratedProfile.rightGrip.nodes[1].index+1
 local source=A.cache[integratedProfile.sourceRight.index+1];local desired=copy(A.cache[ci])
 local goal={A.cache[root][10]+.12,A.cache[root][11]+.08,A.cache[root][12]+.24}
 for j=1,3 do desired[j+9]=desired[j+9]+goal[j]-source[j+9]end
 A.locals[ci]=numpy_relative(A.cache[A.parents[ci]+1],desired);refresh_all()
 return copy(A.locals),ci
end
local input,ci=reverse_start();local source=copy(A.cache[integratedProfile.sourceRight.index+1])
local native=copy(A.cache[integratedProfile.nativeRight.index+1]);local gunInput=copy(gun.locals)
local gunBasis=copy(gun.cache[weaponRoot]);local offsetLengths={}
for _,node in ipairs(integratedProfile.testRepairs.nativeReverse.arm.nodes)do offsetLengths[node.index+1]=copy(A.locals[node.index+1])end
step(runtime,'render',9800,980)
check(not runtime.disabled and runtime.stats.nativeReverseWrites==1,'TEST native reverse right output missing')
check(runtime.stats.rightWrites==0,'TEST native reverse also ran forward follower')
local actual=A.cache[integratedProfile.nativeRight.index+1]
check(separation(actual,source)<2e-5,'TEST native reverse right wrist missed Source')
check(near(A.cache[integratedProfile.sourceRight.index+1],source,2e-5),'TEST native reverse changed Source master')
for j=1,9 do check(math.abs(actual[j]-native[j])<3e-5,'TEST native reverse changed original wrist aim')end
for n,before in pairs(offsetLengths)do
 for j=10,12 do check(math.abs(A.locals[n][j]-before[j])<2e-5,'TEST native reverse stretched native bone offset')end
end
for j=1,9 do check(math.abs(gun.cache[weaponRoot][j]-gunBasis[j])<3e-5,'TEST native reverse changed gun aim axes')end
all_same(gun.locals,gunInput,'TEST native reverse wrote gun animation')
-- Drive only Source clavicle position across yaw/pitch-like offsets. Native must
-- follow each new independent wrist, without any accumulated previous override.
local base=copy(A.locals[ci]);local ni=integratedProfile.nativeRight.index+1
for frame=1,12 do
 local moved=copy(base);moved[10]=moved[10]+.025*math.sin(frame*.7);moved[12]=moved[12]+.025*math.cos(frame*.7)
 A.locals[ci]=moved;refresh_all();local goal=copy(A.cache[integratedProfile.sourceRight.index+1])
 step(runtime,'render',9800+frame,980+frame*.11)
 check(not runtime.disabled and separation(A.cache[ni],goal)<2e-5,'TEST native reverse moving Source target diverged')
 check(near(A.cache[integratedProfile.sourceRight.index+1],goal,2e-5),'TEST native reverse feedback moved Source')
end
A.locals[ci]=base;refresh_all();runtime:stop()
all_same(A.locals,input,'TEST native reverse shutdown restore')
reverseResult.sourceMasterAndNativeAimPreserved=true;reverseResult.noStretch=true;reverseResult.movingTargetNoFeedback=true
-- Setter failures after each native write and later attachment/mount writes roll back.
for _,fault in ipairs({1,2,3,4,5,8})do
 input=reverse_start();failAt=fault;step(runtime,'render',9900+fault,990+fault*.01)
 check(runtime.disabled and #runtime.pending==0,'TEST native reverse partial rollback failed')
 all_same(A.locals,input,'TEST native reverse partial rollback mutated animation');runtime:stop()
end
reverseResult.partialRollback=true
-- Excessive/unreachable targets keep the native arm untouched and use baseline V4.
input,ci=reverse_start();A.locals[ci][10]=A.locals[ci][10]+3;refresh_all()
local nativeInput=copy(A.locals[ni]);step(runtime,'render',9920,992)
check(not runtime.disabled and runtime.stats.nativeReverseWrites==0 and runtime.stats.rightWrites==1,'TEST native reverse unreachable fallback missing')
check(near(A.locals[ni],nativeInput),'TEST native reverse unreachable wrote native hand');runtime:stop()
reverseResult.unreachableFallsBack=true
-- Holstering restores native changes; no carried P/40-K is allowed to drive hands.
input=reverse_start();step(runtime,'render',9930,993);gunMount=hash_name('pistol');refresh_all()
step(runtime,'render',9931,993.11)
check(not runtime.disabled and runtime.stats.nativeReverseWrites==1,'TEST native reverse holster kept native follower')
for _,node in ipairs(integratedProfile.testRepairs.nativeReverse.arm.nodes)do
 check(near(A.locals[node.index+1],input[node.index+1]),'TEST native reverse holster native restore missing')
end
runtime:stop();reverseResult.holsterRelease=true
-- Other sidearms remain forward-driven; the native hand and arm are never written.
input=reverse_start('cf8934ff6567a42d');local nativeInput=copy(A.locals[ni])
step(runtime,'render',9940,994)
check(not runtime.disabled and runtime.stats.nativeReverseWrites==0 and runtime.stats.rightWrites==1,'TEST native reverse leaked to another weapon')
check(near(A.locals[ni],nativeInput),'TEST native reverse modified non-P40 native hand');runtime:stop()
reverseResult.otherWeaponsUnchanged=true
U.set_local_pose=reverseDelegate
result15.nativeReverse=reverseResult
