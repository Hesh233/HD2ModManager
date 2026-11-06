-- Incremental test07 cases. Original 1.0.7/1.0.8 suites run BEFORE this section.
local earlierChecks=checks
integratedProfile=copy(grip_fixed_profile)
local mission,missionWorld=true,1
make_runtime=function(p)
 return module.new(S,p or integratedProfile,function(line)logs[#logs+1]=line end,arm_math,
  {inMission=function()return mission end,world=function()return missionWorld end})
end
local fixed07={sidearms={}}
local function all_same(a,b,label)
 for i=1,#a do check(near(a[i],b[i]),label..':'..i)end
end
-- All registered secondary layouts, including GP-20; aim policy does not classify
-- SMGs/support guns as pistols. Live marker animations, not bind constants, win.
for id in pairs(integratedProfile.gripFixes.sidearms)do
 local found=false;for _,spec in ipairs(fixture.weapons)do if spec.resource==id then found=true end end
 if found then
  start_candidate(id);native_contact()
  local input=copy(A.locals);local gunInput=copy(gun.locals)
  local marker=gun.names[hash_name('IK_right')]
  check(marker~=nil,'registered sidearm lacks right marker')
  for frame=1,3 do
   if frame==2 then
    gun.locals[marker][12]=gun.locals[marker][12]+.017
    gunInput=copy(gun.locals);refresh_all()
   end
   step(runtime,'render',6000+frame,600+frame*.02)
   check(not runtime.disabled and runtime.stats.sidearmCorrections==frame,'sidearm alignment missing '..id)
   local hand=numpy_multiply(A.cache[integratedProfile.sourceRight.index+1],integratedProfile.rightAxes)
   check(separation(gun.cache[marker],hand)<2e-5,'right IK is not on registered hand '..id)
   all_same(gun.locals,gunInput,'weapon part local overwritten')
  end
  runtime:stop();all_same(A.locals,input,'sidearm restore');fixed07.sidearms[id]=true
 end
end
-- P-4 independent 7-node speedloader: no skeleton/pivot/IK. Explicit exact
-- signature allows graph refresh; neither its local nor the gun's is written.
start_candidate('8d3d52a3b2f19402');native_contact(.30)
local ammo=make(test07_components[1]);ammo.linkOwner=gun
ammo.linkIndex=gun.names[hash_name('attach_ammo')] or gun.names[hash_name('root')]
ammo.linkRoot=integratedProfile.consumers[ammo.resource].root+1
linkedItems={ammo};groups[1][#groups[1]+1]=ammo;refresh_all()
local ammoInput=copy(ammo.locals);local input=copy(A.locals)
step(runtime,'render',6100,610)
check(not runtime.disabled and runtime.stats.sidearmCorrections==1,'Senator alignment failed')
check(runtime.stats.leftWrites==0,'free sidearm left hand overridden')
check(near(ammo.cache[ammo.linkRoot],gun.cache[ammo.linkIndex]),'Senator speedloader detached')
local found=false;for _,item in ipairs(runtime.consumers)do found=found or item.unit==ammo end
check(found,'exact Senator speedloader not discovered')
all_same(ammo.locals,ammoInput,'speedloader local changed')
-- Existing engine relink to a hand during reload must remain owned by the engine.
ammo.linkOwner=model;ammo.linkIndex=model.names[hash_name('attach_hand_l')];refresh_all()
step(runtime,'render',6101,610.02)
check(not runtime.disabled and near(ammo.cache[ammo.linkRoot],model.cache[ammo.linkIndex]),'reload hand relink lost')
all_same(ammo.locals,ammoInput,'reload speedloader local changed')
runtime:stop();all_same(A.locals,input,'Senator restore');fixed07.senatorSpeedloader=true
-- A real foregrip is placed on the gun's animated underbarrel mount. A second
-- gun's nearby grip and an invisible grip must not be mistaken for this one.
local function underbarrel_scene()
 start_candidate('968211c0033dce64')
 -- Liberator fixture has attach_underbarrel; the graph root is placed by the engine.
 check(under~=nil,'weapon underbarrel fixture missing')
 grip=make(fixture.foregrip);grip.linkOwner=gun;grip.linkIndex=under
 grip.linkRoot=grip.names[hash_name('skeleton')]
 linkedItems={grip};groups[1][#groups[1]+1]=grip;refresh_all()
 local nativePose=numpy_multiply(A.cache[oi],numpy_relative(gun.cache[weaponRoot],grip.cache[grip.names[hash_name('IK_left')]]))
 local n=integratedProfile.nativeLeft.index+1
 A.locals[n]=numpy_relative(A.cache[A.parents[n]+1],nativePose);refresh_all()
end
underbarrel_scene();input=copy(A.locals)
step(runtime,'render',6200,620)
check(not runtime.disabled and runtime.stats.leftWrites==1 and runtime.stats.underbarrelTargets==1,'attached underbarrel not targeted')
local goal=grip.cache[grip.names[hash_name('IK_left')]]
local endpoint=processor_endpoint(A.cache[lri],A.cache[lmi],A.cache[lhi],goal)
for j=1,3 do check(math.abs(A.cache[lh][j+9]-endpoint[j])<1e-5,'left endpoint not on underbarrel') end
runtime:stop();all_same(A.locals,input,'underbarrel restore')
underbarrel_scene();local extra=make(fixture.foregrip)
extra.linkOwner=gun;extra.linkIndex=under;extra.linkRoot=extra.names[hash_name('skeleton')]
linkedItems[#linkedItems+1]=extra;groups[1][#groups[1]+1]=extra;refresh_all()
step(runtime,'render',6201,620.02)
check(not runtime.disabled and runtime.stats.leftWrites==0,'ambiguous underbarrel was guessed')
runtime:stop();fixed07.underbarrelUniqueLink=true
underbarrel_scene();grip.visible=false;native_contact()
step(runtime,'render',6202,620.04)
check(not runtime.disabled and runtime.stats.leftWrites==1 and runtime.stats.underbarrelTargets==0,'hidden underbarrel did not fall back to gun')
runtime:stop();fixed07.hiddenUnderbarrelIgnored=true
-- An underbarrel WEAPON may link at skeleton while its boss is animated below
-- that node. It is not another hand-held weapon and its live IK_left must win.
start_candidate('968211c0033dce64')
local launcherSpec
for _,spec in ipairs(fixture.weapons)do if spec.resource=='02eecd0b1fa49630' then launcherSpec=spec end end
check(launcherSpec~=nil,'underbarrel weapon fixture missing')
local launcher=make(launcherSpec);launcher.linkOwner=gun;launcher.linkIndex=under
launcher.linkRoot=launcher.names[hash_name('skeleton')]
linkedItems={launcher};groups[1][#groups[1]+1]=launcher;refresh_all()
local nativePose=numpy_multiply(A.cache[oi],numpy_relative(gun.cache[weaponRoot],launcher.cache[launcher.names[hash_name('IK_left')]]))
local nativeIndex=integratedProfile.nativeLeft.index+1
A.locals[nativeIndex]=numpy_relative(A.cache[A.parents[nativeIndex]+1],nativePose);refresh_all()
local launcherInput=copy(launcher.locals)
step(runtime,'render',6250,625)
check(not runtime.disabled and runtime.stats.underbarrelTargets==1 and runtime.stats.leftWrites==1,'underbarrel weapon skeleton link missed')
all_same(launcher.locals,launcherInput,'underbarrel weapon local changed');runtime:stop()
fixed07.underbarrelWeaponSkeletonLink=true
-- Ship population is larger than the preview guard. Chef state (not size/world
-- ordinal) still prevents all writes. Restore once on mission->ship, then idle.
start_candidate('8d3d52a3b2f19402');native_contact();input=copy(A.locals)
step(runtime,'render',6300,630);check(runtime.stats.writes==1,'mission did not apply')
mission=false;step(runtime,'render',6301,630.02)
all_same(A.locals,input,'mission-to-ship restoration')
local oldWrites=writes;local oldCalls=calls
for i=1,30 do step(runtime,'update',6301+i,630.02+i/60);step(runtime,'render',6301+i,630.02+i/60)end
check(writes==oldWrites and calls==oldCalls,'ship idle enumerates or writes Units')
mission=true;step(runtime,'render',6332,631)
check(not runtime.disabled and runtime.stats.writes==2,'mission reentry failed')
runtime:stop();fixed07.shipBypassAndReentry=true
start_candidate('9f80d67a12a7e40f');native_contact();input=copy(A.locals);missionWorld=2
step(runtime,'render',6350,635)
check(runtime.stats.writes==0,'non-main world modified during mission')
all_same(A.locals,input,'wrong mission world modified');runtime:stop();missionWorld=1
fixed07.onlyChefMissionWorld=true
-- The optimized transaction still unwinds every partially written pose and
-- rejects missing scene authorization rather than silently running on the ship.
for _,fault in ipairs({1,2,3,10,22,24})do
 integratedProfile=copy(grip_fixed_profile);start_candidate('9eb160830321bfd6');native_contact()
 local before=copy(A.locals);failAt=fault
 step(runtime,'render',6370+fault,637+fault*.01)
 check(runtime.disabled and #runtime.pending==0,'optimized partial write not rolled back')
 all_same(A.locals,before,'optimized rollback');runtime:stop()
end
fixed07.optimizedRollback=true
integratedProfile=copy(grip_fixed_profile);start_candidate('9f80d67a12a7e40f');runtime:stop()
local noContext=module.new(S,integratedProfile,function(line)logs[#logs+1]=line end,arm_math)
local before=copy(A.locals);step(noContext,'render',6398,639.8)
check(noContext.stats.writes==0,'missing Chef state authorized writes')
all_same(A.locals,before,'unauthorized scene');noContext:stop();fixed07.missingSceneFailsClosed=true
-- Same realistic population, identical correctness policy; change optimization
-- switches only. Count bridge calls and membership-set insertions, not game FPS.
local function cost_scene(optimized)
 local p=copy(grip_fixed_profile)
 if not optimized then
  p.performance.transactionIdentity=false;p.performance.cacheNodeChecks=false
  p.performance.sparseMembership=false;p.performance.negativeResourceCache=false;p.performance.snapshotPoseCache=false
 end
 integratedProfile=p;start_candidate('9f80d67a12a7e40f');native_contact()
 for i=1,5 do
  local part=make(fixture.model);linkedItems[#linkedItems+1]=part;groups[1][#groups[1]+1]=part
 end
 while #groups[1]<5300 do
  groups[1][#groups[1]+1]=make({resource='0000000000000001',hashes={hash_name('root')},parents={},matrices={transform(0)}})
 end
 refresh_all()
 local initialCalls=calls
 for i=1,30 do step(runtime,'render',6400+i,640+i*.016)end
 check(not runtime.disabled and runtime.stats.writes==30,'performance path lost writes')
 local result={engineCalls=calls-initialCalls,membershipEntries=runtime.stats.membershipEntries,
  modelRefreshes=runtime.stats.modelRefreshes,consumerRefreshes=runtime.stats.consumerRefreshes}
 runtime:stop();return result
end
fixed07.performance={before=cost_scene(false),after=cost_scene(true)}
check(fixed07.performance.after.engineCalls<fixed07.performance.before.engineCalls,'optimization failed to reduce bridge calls')
check(fixed07.performance.after.membershipEntries<fixed07.performance.before.membershipEntries*.1,'sparse membership ineffective')
-- A cached avatar is fully revalidated in the next transaction, fail closed.
integratedProfile=copy(grip_fixed_profile);start_candidate('9f80d67a12a7e40f');native_contact()
step(runtime,'render',6500,650);local beforeCount=runtime.stats.writes
A.count=A.count-1;step(runtime,'render',6501,650.02)
check(runtime.stats.writes==beforeCount,'changed avatar layout passed cached validation')
A.count=A.count+1;runtime:stop();fixed07.layoutRechecked=true
return {status='PASS_PENDING_GAME_TEST',checks=checks,earlierChecks=earlierChecks,test07=fixed07,gameTested=false,logs=logs}
