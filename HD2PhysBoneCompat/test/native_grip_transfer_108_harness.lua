-- Candidate-only expectations, appended AFTER the original 1.0.7 regression suite.
local baselineChecks=checks
integratedProfile=copy(candidate_profile)
local fixed={}
local function pad_main()
    local filler=make({resource='0000000000000001',hashes={hash_name('root')},parents={},matrices={transform(0)}})
    while #groups[1]<130 do groups[1][#groups[1]+1]=filler end
end
local function start_candidate(resource,mount)
    runtime=integrated_weapon(resource,mount or 'attach_hand_r');pad_main();refresh_all();return runtime
end
local function native_contact(extra)
    local marker=gun.names[hash_name('IK_left')]
    local original=gunMount==hash_name('attach_weapon') and A.cache[A.names[gunMount]] or A.cache[oi]
    local intended=numpy_multiply(original,numpy_relative(gun.cache[weaponRoot],gun.cache[marker]))
    intended[10]=intended[10]+(extra or 0)
    local index=integratedProfile.nativeLeft.index+1
    A.locals[index]=numpy_relative(A.cache[A.parents[index]+1],intended);refresh_all()
end
for _,resource in ipairs({'9f80d67a12a7e40f','73d84eaae8c75342','9eb160830321bfd6','a955c4ea6f6d4203'}) do
    start_candidate(resource);native_contact(resource=='a955c4ea6f6d4203' and .11 or 0)
    local baseOutputs={};for _,row in ipairs(integratedProfile.leftGrip.outputs) do baseOutputs[row.index+1]=copy(A.locals[row.index+1]) end
    step(runtime,'render',5000,500)
    check(not runtime.disabled and runtime.stats.leftWrites==1,'native two-hand intent did not apply '..resource)
    native_contact(.30);local writesBefore=runtime.stats.leftWrites
    step(runtime,'render',5001,500.02)
    check(not runtime.disabled and runtime.stats.leftWrites==writesBefore,'free/reload hand was overridden '..resource)
    for index,pose in pairs(baseOutputs) do check(near(A.locals[index],pose),'old left IK survived intent release') end
    native_contact(resource=='a955c4ea6f6d4203' and .11 or 0);step(runtime,'render',5002,500.04)
    check(runtime.stats.leftWrites==writesBefore+1,'two-hand intent did not resume '..resource)
    runtime:stop();fixed[resource]={contactApplied=true,freeHandPreserved=true,reentryApplied=true}
end
-- Sidearm Schmitt band: cold 4cm is not aiming, 2cm enters, 4.5cm holds,
-- 6cm releases, 4cm stays free, 3cm re-enters. No sticky old IK output.
start_candidate('73d84eaae8c75342')
local sequence={{.04,0},{.02,1},{.045,2},{.06,2},{.04,2},{.03,3}}
for i,row in ipairs(sequence) do
    native_contact(row[1]);step(runtime,'render',5030+i,503+i*.02)
    check(not runtime.disabled and runtime.stats.leftWrites==row[2],'sidearm hysteresis state incorrect')
end
runtime:stop();fixed.sidearmHysteresis=true
local invalid=copy(integratedProfile);invalid.leftGrip.intent.primaryLeaveMetres=.01
check(not pcall(make_runtime,invalid),'invalid reversed intent thresholds accepted')
fixed.invalidThresholdsRejected=true

-- GP-20 may use the other native weapon mount and must remain two-handed.
start_candidate('9eb160830321bfd6','attach_weapon');native_contact()
step(runtime,'render',5050,505)
check(not runtime.disabled and runtime.stats.leftWrites==1,'GP20 carry link lost two-hand intent')
runtime:stop();fixed.gp20OtherMount=true

-- Unknown skeleton/game_mesh props are not equipment. Measure the same scene
-- twice with only the optimization switches changed (all other policies equal).
local function prop_scene(optimized)
    local saved=copy(integratedProfile.performance)
    if not optimized then integratedProfile.performance={};integratedProfile.allowedConsumers=nil end
    start_candidate('9f80d67a12a7e40f');native_contact()
    local props={}
    for i=1,32 do
        local item=make({resource=string.format('fefefefefe%06x',i),
            hashes={hash_name('skeleton'),hash_name('game_mesh'),hash_name('root')},
            parents={[2]=0,[3]=0},matrices={transform(0),transform(0),transform(0)}})
        item.linkOwner=A;item.linkRoot=1;item.linkIndex=ti
        props[item]=true;linkedItems[#linkedItems+1]=item;groups[1][#groups[1]+1]=item
    end
    refresh_all();local beforeCalls=calls
    step(runtime,'render',5100,510)
    local frameCalls=calls-beforeCalls;local found,updated=0,0
    for _,item in ipairs(runtime.consumers) do if props[item.unit] then found=found+1 end end
    for _,item in ipairs(refreshTrace) do if props[item] then updated=updated+1 end end
    check(not runtime.disabled,'performance scene disabled')
    runtime:stop();integratedProfile.performance=saved
    integratedProfile.allowedConsumers=copy(candidate_profile.allowedConsumers)
    return {recognized=found,refreshed=updated,engineCalls=frameCalls}
end
local legacy=prop_scene(false);local optimized=prop_scene(true)
check(legacy.recognized==32 and optimized.recognized==0 and optimized.refreshed==0,'strict consumer scope failed')
check(optimized.engineCalls<legacy.engineCalls,'candidate did not reduce mock engine calls')
fixed.performance={legacy=legacy,optimized=optimized}

-- Exact non-skeletal Epoch and fuel-canister layouts; no local setters/relinks.
for _,spec in ipairs(candidate_components) do
    start_candidate('9f80d67a12a7e40f');native_contact()
    local item=make(spec);item.linkOwner=A;item.linkRoot=1;item.linkIndex=ti
    linkedItems={item};groups[1][#groups[1]+1]=item;refresh_all()
    local before=copy(item.locals);step(runtime,'render',5200,520)
    local found,updated=false,false
    for _,row in ipairs(runtime.consumers) do found=found or row.unit==item end
    for _,row in ipairs(refreshTrace) do updated=updated or row==item end
    check(found and updated and not runtime.disabled,'exact component was not refreshed '..item.resource)
    for i=1,item.count do check(near(item.locals[i],before[i]),'component local pose modified') end
    item.linkOwner=gun;item.linkIndex=gun.names[hash_name('IK_left')]
    refresh_all();step(runtime,'render',5201,520.02)
    check(near(item.cache[item.linkRoot],gun.cache[item.linkIndex]),'component re-link cache separated')
    runtime:stop();fixed[item.resource]={recognized=true,refreshed=true,localPosePreserved=true,engineRelinkPreserved=true}
end

-- Captured preview population: all writes bypassed without hardcoding its ID.
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r');groups[11]=groups[1];groups[1]=nil
local snapshot=copy(A.locals);step(runtime,'render',5300,530)
check(not runtime.disabled and runtime.stats.writes==0 and runtime.stats.leftWrites==0
    and runtime.stats.bodyNodeWrites==0 and runtime.stats.attachmentWrites==0,'small-world isolation still writes')
for i=1,A.count do check(near(A.locals[i],snapshot[i]),'preview local modified') end
runtime:stop();fixed.previewSmallWorldBypassed=true
return {status='PASS_PENDING_GAME_TEST',baselineChecks=baselineChecks,checks=checks,fixed=fixed,gameTested=false,logs=logs}

