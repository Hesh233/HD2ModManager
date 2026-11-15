-- HD2-Addon: mods/hd2modmanager/attachment_fix
-- Production B3: model-calibrated TP runtime and independent FP Source output.
-- Physics remains a separate addon; this package does not embed a physics solver.
local loader=...
assert(type(loader)=='table' and loader.loader=='Chef Shared Loader','B23 requires Chef Shared Loader')
local ArmMath=(function()
-- INSERT LEGACY ARM MATH
end)()
local Transfer=(function()
-- INSERT TRANSFER MODULE
end)()
local FirstPersonGuard=(function()
-- INSERT FIRST PERSON GUARD
end)()
local AttachmentRuntime=(function()
-- INSERT ATTACHMENT ADAPTER
end)()
local FirstPersonSource=(function()
-- INSERT FIRST PERSON SOURCE MODULE
end)()
local OptionSwitches=(function()
-- INSERT OPTION SWITCH MODULE
end)()
local HiddenFirstPerson=(function()
-- INSERT HIDDEN FIRST PERSON MODULE
end)()
local profile=(function()
-- INSERT TRANSFER PROFILE
end)()
-- A new latest-session file leaves the old multi-day evidence untouched.
local directory=assert(loader.log_directory,'Chef log directory unavailable')
local detailed=profile.testRepairs and profile.testRepairs.enabled and profile.logging.detailed==true
local testRun=false
assert(profile.testRepairs==nil,'test_profile_refused_by_production_runtime')
assert(profile.repairPolicy and profile.repairPolicy.schema=='hd2-attachment-repair-policy-v1' and profile.repairPolicy.version=='1.0.19','production_repair_profile_required')
local stem=testRun and ((detailed and 'hd2_grip_TEST_DETAILED_' or 'hd2_grip_TEST_PERF_')..profile.testRepairs.modelLabel..(profile.testRepairs.logTag and ('_'..profile.testRepairs.logTag) or '')..'_'..os.date('%Y%m%d_%H%M%S')) or 'hd2_grip_b23_compact'
local part,partBytes=1,0
local function logPath() return directory..'/'..stem..(testRun and string.format('.part%02d',part) or '')..'.log' end
local handle,why=io.open(logPath(),'w');assert(handle,'Cannot open B23 log: '..tostring(why))
local closed,frame,lastFlush=false,0,0
local lastPhysicsCheckTime,lastPhysicsCheckFrame=nil,nil
local perf={sourceSeconds=0,transferSeconds=0,finalSeconds=0,postPhysicsSeconds=0,postPhysicsCalls=0,renderCalls=0,updateCalls=0,maxRenderSeconds=0};local lastPerfLog=0
local log,logContext=Transfer.newLogSink(function(line,urgent)
    if handle then
        if testRun and partBytes+#line+64>(profile.logging.segmentBytes or 16777216) then
            handle:flush();handle:close();part=part+1;partBytes=0
            handle,why=io.open(logPath(),'w');assert(handle,'Cannot rotate TEST log: '..tostring(why))
        end
        handle:write(os.date('%Y-%m-%d %H:%M:%S'),testRun and (detailed and ' [TEST_ONLY_DETAILED] ' or ' [TEST_ONLY_PERF] ') or ' [grip_b23] ',line,'\n')
        partBytes=partBytes+#line+64
        local now=stingray.Application.time_since_launch()
        if urgent or now-lastFlush>=2 then handle:flush();lastFlush=now end
    end
end,function()return stingray.Application.time_since_launch()end,profile.logging)
local sceneContext={inMission=loader.in_mission,world=loader.world}
local viewGuard=FirstPersonGuard.new(stingray,sceneContext,profile.firstPersonSource and profile.firstPersonSource.avatar)
sceneContext.firstPerson=viewGuard.sample
sceneContext.fpWorld=viewGuard.world
sceneContext.fpActor=viewGuard.actor
local runtime,fpSource,hiddenFp,initialized
local function initialize()
 if initialized then return end
 local selection=OptionSwitches.resolve(profile,function(owner)return package.loaded[owner]end)
 OptionSwitches.apply(profile,selection)
 log(Transfer.encodeDiagnostic({event='attachment_option_selection',selection=selection,source='deployed_Chef_option_modules_from_standard_manifest',restartRequired=true},false))
 local made,value=pcall(AttachmentRuntime.install,stingray,{profile=profile,logger=log,armMath=ArmMath,transfer=Transfer,sceneContext=sceneContext})
 assert(made,value);runtime=value
 if selection.fpArms then
  fpSource=FirstPersonSource.new(stingray,profile.firstPersonSource,ArmMath,viewGuard,function(row)log(Transfer.encodeDiagnostic(row,false))end,sceneContext)
  sceneContext.fpMembership=function()return fpSource:membership()end
  sceneContext.fpSourceModels=function(p)return fpSource:visibilityModels(p)end
  sceneContext.fpSourcePermit=function(unit,world,frame)return fpSource:permit(unit,world,frame)end
 else
  hiddenFp=HiddenFirstPerson.new(stingray,profile.firstPersonSource,viewGuard,sceneContext,function(row)log(Transfer.encodeDiagnostic(row,false))end)
  sceneContext.fpSourcePermit=function()return false end
 end
 initialized=true;__hd2_grip_b23=runtime
end
local function stop(reason)
    if closed then return end
    if fpSource then fpSource:stop()end
    if hiddenFp then hiddenFp:stop()end
    log(Transfer.encodeDiagnostic({event='fp_callback_performance_complete',sourceMsTotal=perf.sourceSeconds*1000,transferMsTotal=perf.transferSeconds*1000,finalMsTotal=perf.finalSeconds*1000,postPhysicsMsTotal=perf.postPhysicsSeconds*1000,postPhysicsCalls=perf.postPhysicsCalls,renderCalls=perf.renderCalls,updateCalls=perf.updateCalls,maxRenderMs=perf.maxRenderSeconds*1000,screenFpsObserved=false,gpuTimeObserved=false},false))
    local ok,err=true,nil
    if runtime then ok,err=pcall(runtime.stop,runtime,reason or 'shutdown')end
    if not ok then log('{"event":"shutdown_error","variant":"'..profile.variant..'"}') end
    handle:flush();handle:close();handle=nil;closed=true;__hd2_grip_b23=nil
    if not ok then error(err) end
end
local function step(phase)
    if closed then return end
    if phase=='update' then frame=frame+1 end
    local now=stingray.Application.time_since_launch()
    local ok,err=pcall(function()
        initialize()
        local t0=os.clock();if fpSource then fpSource:tick(phase,frame,now)end;if hiddenFp then hiddenFp:tick(phase,frame,now)end;local t1=os.clock()
        runtime:tick(phase,frame,now);local t2=os.clock()
        perf.sourceSeconds=perf.sourceSeconds+t1-t0;perf.transferSeconds=perf.transferSeconds+t2-t1
        if fpSource and phase=='render' then
            local verified=fpSource:check('post_presentation',frame,now,true)
            if not verified then runtime:fpFinalizeVisibility(frame,now)end
            perf.finalSeconds=perf.finalSeconds+os.clock()-t2;perf.renderCalls=perf.renderCalls+1;perf.maxRenderSeconds=math.max(perf.maxRenderSeconds,os.clock()-t0)
            if now-lastPerfLog>=5 then lastPerfLog=now;log(Transfer.encodeDiagnostic({event='fp_callback_performance',frame=frame,time=now,sourceMsTotal=perf.sourceSeconds*1000,transferMsTotal=perf.transferSeconds*1000,finalMsTotal=perf.finalSeconds*1000,renderCalls=perf.renderCalls,updateCalls=perf.updateCalls,maxRenderMs=perf.maxRenderSeconds*1000,postPhysicsMsTotal=perf.postPhysicsSeconds*1000,postPhysicsCalls=perf.postPhysicsCalls,postPhysicsBridgeObserved=lastPhysicsCheckFrame~=nil,gpuTimeObserved=false,screenFpsObserved=false},false))end
        elseif phase=='update'then perf.updateCalls=perf.updateCalls+1 end
    end)
    if not ok then
        log('{"event":"callback_error","phase":"'..phase..'","variant":"'..profile.variant..'"}')
        stop('callback_error');error(err)
    end
end
local function afterPhysics()
    if closed or not initialized or not fpSource then return false end
    local now=stingray.Application.time_since_launch()
    if viewGuard.reset then viewGuard.reset()end
    lastPhysicsCheckFrame=frame;lastPhysicsCheckTime=now
    local t0=os.clock();local verified=fpSource:check('post_physics',frame,now,true)
    if not verified then runtime:fpFinalizeVisibility(frame,now)end
    perf.postPhysicsSeconds=perf.postPhysicsSeconds+os.clock()-t0;perf.postPhysicsCalls=perf.postPhysicsCalls+1
    return verified
end
return {fp_after_physics_a3=afterPhysics,version=testRun and profile.testRepairs.version or Transfer.VERSION,update=function()step('update')end,render=function()step('render')end,
    shutdown=function()stop('shutdown')end,on_stop=function()stop('on_stop')end}
