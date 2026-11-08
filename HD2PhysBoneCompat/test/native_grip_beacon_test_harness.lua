-- Held beacon: retain native attach_hand_r AND attach_weapon, let Source hand
-- follow; no setters on beacon, raw auxiliary nodes, FX or released projectiles.
local function beacon_start()
 repaired_start('cf8934ff6567a42d');gun.visible=false
 local policy=integratedProfile.testRepairs.beacon
 integratedProfile.consumers[policy.resource]=copy(test_beacon_spec)
 integratedProfile.allowedConsumers[policy.resource]=true
 local orb=make(weapon_assets[policy.resource])
 local aw=A.names[hash_name('attach_weapon')]
 local native=copy(A.cache[aw]);orb.locals[1]=copy(native)
 orb.linkOwner=A;orb.linkIndex=aw;orb.linkRoot=orb.names[hash_name('locator_beacon')]
 linkedItems={orb};groups[1][#groups[1]+1]=orb;refresh_all()
 return orb,aw,native
end
local orb,aw,nativeWeapon=beacon_start()
local nativeMount=copy(A.cache[ti]);local input=copy(A.locals);local orbInput=copy(orb.locals)
local body=orb.names[hash_name('game_mesh')]
local auxBefore=numpy_relative(orb.cache[body],orb.cache[37])
step(runtime,'render',9300,930)
check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST beacon custom hand writer missing')
check(near(A.cache[ti],nativeMount,3e-5),'TEST beacon native hand mount moved')
check(near(A.cache[aw],nativeWeapon,3e-5),'TEST beacon attach_weapon native path moved')
check(near(numpy_relative(orb.cache[body],orb.cache[37]),auxBefore,3e-5),'TEST beacon body/auxiliary offset changed')
all_same(orb.locals,orbInput,'TEST beacon local pose modified')
-- Game throw/release: stop following. Lua must not alter the free Unit.
orb.linkOwner=nil;orb.locals[1][10]=orb.locals[1][10]+1.;refresh_all()
local released=copy(orb.locals);local rightCount=runtime.stats.rightWrites
step(runtime,'update',9300,930.01);step(runtime,'render',9301,930.02)
check(runtime.stats.rightWrites==rightCount,'TEST released beacon still claimed')
all_same(orb.locals,released,'TEST released projectile modified');runtime:stop()
-- Ambiguous same-world beacons: keep native path, no arbitrary hand ownership.
orb,aw,nativeWeapon=beacon_start()
local second=make(weapon_assets[integratedProfile.testRepairs.beacon.resource])
second.locals[1]=copy(nativeWeapon);second.linkOwner=A;second.linkIndex=aw;second.linkRoot=second.names[hash_name('locator_beacon')]
linkedItems[#linkedItems+1]=second;groups[1][#groups[1]+1]=second;refresh_all()
step(runtime,'render',9310,931)
check(not runtime.disabled and runtime.stats.rightWrites==0,'TEST ambiguous beacon claimed a hand')
check(near(A.cache[aw],nativeWeapon,3e-5),'TEST ambiguous beacon native path moved')
runtime:stop()
-- A same-position beacon in another world/player must not claim this hand.
repaired_start('cf8934ff6567a42d');gun.visible=false
local policy=integratedProfile.testRepairs.beacon
integratedProfile.consumers[policy.resource]=copy(test_beacon_spec);integratedProfile.allowedConsumers[policy.resource]=true
local foreign=make(weapon_assets[policy.resource]);local bi=B.names[hash_name('attach_weapon')]
foreign.locals[1]=copy(B.cache[bi]);foreign.linkOwner=B;foreign.linkIndex=bi;foreign.linkRoot=foreign.names[hash_name('locator_beacon')]
groups[2][#groups[2]+1]=foreign;refresh(foreign)
local bBefore=copy(B.locals);local foreignBefore=copy(foreign.locals)
step(runtime,'render',9320,932)
check(not runtime.disabled and runtime.stats.rightWrites==0,'TEST other-world beacon claimed local hand')
all_same(B.locals,bBefore,'TEST beacon wrote other player');all_same(foreign.locals,foreignBefore,'TEST beacon wrote foreign item');runtime:stop()
local probeSeen=false;for _,line in ipairs(logs)do if line:find('"event":"test_beacon_probe"',1,true)then probeSeen=true end end
check(probeSeen,'TEST beacon full pose telemetry absent')
result15.beaconNativePath={heldAndAuxiliaryOffset=true,releaseNoProjectileWrites=true,ambiguityFailsClosed=true,otherWorldUnchanged=true,fullPoseProbe=true}
