-- Keep every prior regression, then exercise new Source outputs/native ADS goal.
local rightChecksBefore=checks
local realSet=U.set_local_pose
local allowRight=false;local rightIndices={}
for _,n in ipairs(right_profile.rightGrip.outputs)do rightIndices[n.index+1]=true end
U.set_local_pose=function(u,n,m)
 if rightIndices[n] and allowRight then
  check(u==A,'right writer touched another Unit')
  local value=copy(m);recycled();u.locals[n]=value;writes=writes+1
  if failAt==writes then failAt=nil;error('injected_right_output_failure')end
 else realSet(u,n,m)end
end
local function new_start(id)
 integratedProfile=copy(right_profile);runtime=start_candidate(id)
 A.locals=copy(right_fixture.matrices);A.parents=copy(right_fixture.parents)
 A.count=#right_fixture.hashes;A.names={}
 for i,h in ipairs(right_fixture.hashes)do A.names[h]=i end
 allowRight=true;refresh_all()
 return runtime
end
local function aim_native()
 local marker=gun.names[hash_name('IK_right')]
 local root=A.cache[integratedProfile.rightGrip.nodes[2].index+1]
 local old=copy(A.cache[nativeRight]);local ik=copy(gun.cache[marker])
 local desired=copy(old)
 local goal={root[10]+.14,root[11]+.08,root[12]+.28}
 for j=1,3 do desired[j+9]=goal[j]-(ik[j+9]-old[j+9])end
 A.locals[nativeRight]=numpy_relative(A.cache[A.parents[nativeRight]+1],desired)
 refresh_all();native_contact();refresh_all()
 return copy(A.cache[ti]),copy(gun.cache[marker]),copy(A.cache[integratedProfile.sourceRight.index+1])
end
local result111={sidearms={}}
for id in pairs(right_profile.gripFixes.sidearms)do
 new_start(id);local mount,goal,sourceBefore=aim_native()
 check(goal[12]-sourceBefore[12]>.10,'fixture did not reproduce native raised/Source low aiming')
 local input=copy(A.locals);local gunInput=copy(gun.locals)
 for i=1,3 do
  local refs={}
  for j,n in ipairs(integratedProfile.rightGrip.nodes)do refs[j]=copy(A.locals[n.index+1])end
  step(runtime,'render',7000+i,700+i*.02)
  check(not runtime.disabled and runtime.stats.rightWrites==i,'right aim output not applied '..id)
  check(near(A.cache[ti],mount,2e-5),'native aiming gun root pulled down '..id)
  local c=integratedProfile.rightGrip
  local endpoint=processor_endpoint(A.cache[c.nodes[2].index+1],A.cache[c.nodes[3].index+1],A.cache[c.nodes[4].index+1],goal)
  local actual=A.cache[integratedProfile.sourceRight.index+1]
  for j=1,3 do check(math.abs(actual[j+9]-endpoint[j])<2e-5,'right endpoint diverged from shared converter IK')end
  check(separation(actual,goal)<2e-5,'right hand did not reach reachable native aim goal '..id)
  local registered=numpy_multiply(actual,integratedProfile.rightAxes)
  for j=1,9 do check(math.abs(registered[j]-goal[j])<2e-5,'right grip axis registration changed '..id)end
  for j,n in ipairs(c.nodes)do check(near(A.locals[n.index+1],refs[j]),'private animated right reference overwritten')end
  all_same(gun.locals,gunInput,'P4/sidearm internal animation overwritten')
  step(runtime,'update',7000+i,700+i*.02)
  check(near(A.cache[ti],mount,2e-5),'update discarded native aim mount')
 end
 runtime:stop();all_same(A.locals,input,'right output shutdown restore')
 result111.sidearms[id]=true
end
-- Right hand follows the real held weapon through aim AND reload/free-left.
-- Holster (different link) releases right outputs; left policy remains independent.
new_start('8d3d52a3b2f19402');local mount,goal=aim_native();local input=copy(A.locals)
step(runtime,'render',7100,710);local rightCount=runtime.stats.rightWrites;local leftCount=runtime.stats.leftWrites
native_contact(.30);step(runtime,'render',7101,710.02)
check(not runtime.disabled and runtime.stats.rightWrites==rightCount+1,'real right-hand grip lost during free-left/reload')
check(runtime.stats.leftWrites==leftCount,'free/reload left hand forced into two-hand grip')
check(near(A.cache[ti],mount,2e-5),'reload gun body displaced from native path')
gunMount=hash_name('attach_weapon');refresh_all();step(runtime,'render',7102,710.04)
check(runtime.stats.rightWrites==rightCount+1,'holstered weapon forced right arm')
for _,n in ipairs(integratedProfile.rightGrip.outputs)do check(near(A.locals[n.index+1],input[n.index+1]),'right IK survived holster')end
gunMount=hash_name('attach_hand_r');refresh_all();native_contact();step(runtime,'render',7103,710.06)
check(runtime.stats.rightWrites==rightCount+2,'right-hand reentry failed')
runtime:stop();result111.freeLeftReloadAndHolsterReentry=true
-- A late animation pass writes original channel indices, never named outputs.
new_start('8d3d52a3b2f19402');mount,goal=aim_native();input=copy(A.locals)
step(runtime,'render',7150,715);local held={}
for _,n in ipairs(integratedProfile.rightGrip.outputs)do held[n.index+1]=copy(A.locals[n.index+1])end
for _,i in ipairs(fixture.animationIndices)do
 check(not rightIndices[i+1],'right output has an animation channel')
 A.locals[i+1]=copy(input[i+1])
end
refresh_all()
for i,pose in pairs(held)do check(near(A.locals[i],pose),'late animation erased right output')end
check(separation(A.cache[integratedProfile.sourceRight.index+1],goal)<2e-5,'late animation lost right aim hand')
runtime:stop();result111.rightSurvivesLateAnimation=true
-- Preserve actual game animation of cylinder/swivel, with no gun-local setters.
new_start('8d3d52a3b2f19402');mount,goal=aim_native()
local cyl=gun.names[hash_name('cylinder')];local swivel=gun.names[hash_name('cylinder_swivel')]
check(cyl and swivel,'P4 internal animation fixture unavailable')
gun.locals[cyl]=multiply(gun.locals[cyl],transform(.2));gun.locals[swivel]=multiply(gun.locals[swivel],transform(-.1))
refresh_all();local gunBefore=copy(gun.locals)
step(runtime,'render',7200,720)
check(not runtime.disabled and runtime.stats.rightWrites==1,'P4 animated cylinder fixture failed')
all_same(gun.locals,gunBefore,'cylinder/reload animation modified');runtime:stop()
result111.cylinderAnimationPreserved=true
-- Exact new frame rollback after each of 3 right output writes and later mount/left writes.
for _,fault in ipairs({3,4,5,6,10,24,25,26})do
 new_start('8d3d52a3b2f19402');aim_native();input=copy(A.locals);failAt=fault
 step(runtime,'render',7250+fault,725+fault*.01)
 check(runtime.disabled and #runtime.pending==0,'right transaction partial rollback failed '..fault)
 all_same(A.locals,input,'right transaction restore');runtime:stop()
end
result111.partialRollback=true
-- The native model/no-owner segment emits read-only part telemetry, no writer authorization.
new_start('8d3d52a3b2f19402');aim_native();model.visible=false
input=copy(A.locals);local writesBefore=writes;step(runtime,'render',7300,730)
check(not runtime.disabled and runtime.stats.writes==0 and runtime.stats.rightWrites==0,'native-only telemetry enabled writes')
check(writes==writesBefore,'native-only probe has setters');all_same(A.locals,input,'native-only avatar changed');runtime:stop()
local luaSeen,nativeSeen,cylinderSeen=false,false,false
for _,line in ipairs(logs)do
 if line:find('"event":"sidearm_probe"',1,true)then
  luaSeen=luaSeen or line:find('"path":"lua"',1,true)~=nil
  nativeSeen=nativeSeen or line:find('"path":"native"',1,true)~=nil
  cylinderSeen=cylinderSeen or line:find('"cylinder"',1,true)~=nil
 end
end
check(luaSeen and nativeSeen and cylinderSeen,'staged P4 probe did not cover both paths/cylinder')
result111.readOnlyNativeAndLuaProbe=true
-- A stale visible P4 linked at the same mount as a primary must not force
-- the primary's Source right arm into the pistol pose.
new_start('968211c0033dce64')
local staleSpec;for _,f in ipairs(fixture.weapons)do if f.resource=='8d3d52a3b2f19402' then staleSpec=f end end
local stale=make(staleSpec);stale.linkOwner=model;stale.linkIndex=ti;stale.linkRoot=stale.names[hash_name('skeleton')]
linkedItems={stale};groups[1][#groups[1]+1]=stale;refresh_all()
input=copy(A.locals);step(runtime,'render',7320,732)
check(not runtime.disabled and runtime.stats.rightWrites==0,'stale pistol overrode primary right grip')
for _,n in ipairs(integratedProfile.rightGrip.outputs)do check(near(A.locals[n.index+1],input[n.index+1]),'primary right output changed')end
runtime:stop();result111.primaryStaleSidearmAmbiguityBlocked=true
-- A real native 107-node Avatar is accepted for OBSERVATION, never for writing.
new_start('8d3d52a3b2f19402');model.visible=false
A.count=107;A.names={};for i=1,107 do A.names[right_fixture.hashes[i]]=i end
refresh_all();input=copy(A.locals);writesBefore=writes
step(runtime,'render',7350,735)
check(not runtime.disabled and #runtime.actors==0 and #runtime.observerActors==1,'native 107 observer classification failed')
check(writes==writesBefore and runtime.stats.writes==0,'native 107 observer authorized pose writes')
all_same(A.locals,input,'native 107 observer mutation');runtime:stop()
result111.native107ObserverNotWriter=true
return {status='PASS_PENDING_GAME_TEST',checks=checks,priorChecks=rightChecksBefore,rightAim=result111,gameTested=false,logs=logs}
