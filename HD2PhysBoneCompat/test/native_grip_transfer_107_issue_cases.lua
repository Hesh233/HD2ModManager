-- Append to the existing B23 harness, not a second runtime/solver.
-- These assertions characterize defects of the shipped 1.0.7, not repaired behavior.
local issueBaselineChecks,issueBaselineCases=checks,integratedCases
local issues={}
local originalUnits=S.World.units
local enumerations,enumerated=0,0
S.World.units=function(w)
    local rows=originalUnits(w);enumerations=enumerations+1;enumerated=enumerated+#rows;return rows
end

-- A reload/free-hand animation can leave the grip while the gun stays linked.
-- Native hand separation is the actual input; no invented ADS/reload API is used.
local function separated_hand_case(resource)
    runtime=integrated_weapon(resource,'attach_hand_r')
    local nativeLeft=integratedProfile.nativeLeft.index+1
    A.locals[nativeLeft][10]=A.locals[nativeLeft][10]+.30
    refresh_all()
    step(runtime,'render',4000,400)
    local written=runtime.stats.leftWrites
    check(not runtime.disabled and written==1,'shipped separated-hand counterexample changed')
    local out={resource=resource,leftWrites=written,policy=integratedProfile.leftGrip.weaponTargets[resource].leftPolicy,
        input='native left hand moved 0.30m away; weapon still linked to attach_hand_r'}
    runtime:stop();return out
end
issues.primaryReloadPosture=separated_hand_case('9f80d67a12a7e40f')
issues.sidearmNonAimOrReloadPosture=separated_hand_case('73d84eaae8c75342')

-- A skeleton/game_mesh signature also describes non-equipment props.
-- Close props are all admitted/refreshed, even with unknown resource IDs.
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r')
local props={}
for i=1,32 do
    local item=make({resource=string.format('fefefefefe%06x',i),
        hashes={hash_name('skeleton'),hash_name('game_mesh'),hash_name('root')},
        parents={[2]=0,[3]=0},matrices={transform(0),transform(0),transform(0)}})
    item.linkOwner=A;item.linkRoot=1;item.linkIndex=ti
    props[item]=true;linkedItems[#linkedItems+1]=item;groups[1][#groups[1]+1]=item
end
refresh_all();local startEnumerations,startEnumerated=enumerations,enumerated
step(runtime,'render',4100,410)
local recognized=0
for _,item in ipairs(runtime.consumers) do if props[item.unit] then recognized=recognized+1 end end
local propRefreshes=0
for _,item in ipairs(refreshTrace) do if props[item] then propRefreshes=propRefreshes+1 end end
check(recognized==32 and propRefreshes>32,'generic prop classifier counterexample changed')
local scanTime=runtime.lastScan
local firstEnumerations,firstEnumerated=enumerations-startEnumerations,enumerated-startEnumerated
local nextEnumerations,nextEnumerated=enumerations,enumerated
step(runtime,'render',4101,410.01)
check(runtime.lastScan==scanTime,'second frame unexpectedly rescanned')
check(enumerations>nextEnumerations,'per-render full membership enumeration disappeared')
issues.performance={unknownPropsRecognized=recognized,propRefreshCallsFirstFrame=propRefreshes,
    worldUnitsEnumeratedFirstFrame=firstEnumerated,worldEnumerationsFirstFrame=firstEnumerations,
    worldEnumerationsWithoutRescan=enumerations-nextEnumerations,
    unitEntriesWithoutRescan=enumerated-nextEnumerated,
    scanSeconds=integratedProfile.scanSeconds}
runtime:stop()

-- Add the real Epoch 12-node component exported by the previous B18 probe.
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r')
local epoch=make(issue_epoch_fixture);epoch.linkOwner=A;epoch.linkRoot=1;epoch.linkIndex=ti
linkedItems={epoch};groups[1][#groups[1]+1]=epoch;refresh_all()
step(runtime,'render',4200,420)
local found=false;for _,item in ipairs(runtime.consumers) do found=found or item.unit==epoch end
local refreshed=false;for _,item in ipairs(refreshTrace) do refreshed=refreshed or item==epoch end
check(not found and not refreshed,'Epoch omission counterexample changed')
issues.epochComponent={resource=epoch.resource,nodeCount=epoch.count,recognized=found,refreshed=refreshed}
runtime:stop()

-- The actual log identifies the arsenal Avatar in world 11. Simulate that
-- world without claiming that its number is a stable preview API.
runtime=integrated_weapon('9f80d67a12a7e40f','attach_hand_r')
groups[11]=groups[1];groups[1]=nil
local fingerBefore={}
for _,n in ipairs(issue_finger_nodes) do fingerBefore[n]=separation(A.cache[n],A.cache[A.parents[n]+1]) end
step(runtime,'render',4300,430)
check(not runtime.disabled and runtime.stats.leftWrites==1,'world-11 correction counterexample changed')
local maximumError,maximumRatio=0,1
for _,n in ipairs(issue_finger_nodes) do
    local length=separation(A.cache[n],A.cache[A.parents[n]+1])
    maximumError=math.max(maximumError,math.abs(length-fingerBefore[n]))
    if fingerBefore[n]>1e-8 then maximumRatio=math.max(maximumRatio,length/fingerBefore[n]) end
end
check(maximumError<1e-5,'mock FK introduced literal finger bone stretching')
issues.preview={world=11,applied=true,leftWrites=runtime.stats.leftWrites,
    bodyWrites=runtime.stats.bodyNodeWrites,attachmentWrites=runtime.stats.attachmentWrites,
    fingerNodesTested=#issue_finger_nodes,maxFingerBoneLengthError=maximumError,
    maxFingerBoneLengthRatio=maximumRatio,
    limitation='cached-world FK only; no GPU skinning, LOD, actual preview animation, or mixed-addon proof'}
runtime:stop()
return {baselineChecks=issueBaselineChecks,baselineIntegratedCases=issueBaselineCases,
    checks=checks,issues=issues,status='SHIPPED_1_0_7_DEFECT_COUNTEREXAMPLES_OBSERVED'}
