-- HD2-Addon: mods/hd2modmanager/attachment_fix
-- B23 test01: dynamic native mount transferred through converter wrist axes.
-- A separate pure-physics addon may run alongside this experiment.
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
local profile=(function()
-- INSERT TRANSFER PROFILE
end)()
-- A new latest-session file leaves the old multi-day evidence untouched.
local path=assert(loader.log_directory,'Chef log directory unavailable')..'/hd2_grip_b23_compact.log'
local handle,why=io.open(path,'w');assert(handle,'Cannot open B23 log: '..tostring(why))
local closed,frame,lastFlush=false,0,0
local log,logContext=Transfer.newLogSink(function(line,urgent)
    if handle then
        handle:write(os.date('%Y-%m-%d %H:%M:%S'),' [grip_b23] ',line,'\n')
        local now=stingray.Application.time_since_launch()
        if urgent or now-lastFlush>=2 then handle:flush();lastFlush=now end
    end
end,function()return stingray.Application.time_since_launch()end,profile.logging)
local sceneContext={inMission=loader.in_mission,world=loader.world}
local viewGuard=FirstPersonGuard.new(stingray,sceneContext)
sceneContext.firstPerson=viewGuard.sample
sceneContext.fpWorld=viewGuard.world
sceneContext.fpActor=viewGuard.actor
local made,runtime=pcall(AttachmentRuntime.install,stingray,{profile=profile,logger=log,armMath=ArmMath,transfer=Transfer,sceneContext=sceneContext})
if not made then handle:close();error(runtime) end
__hd2_grip_b23=runtime
local function stop(reason)
    if closed then return end
    local ok,err=pcall(runtime.stop,runtime,reason or 'shutdown')
    if not ok then log('{"event":"shutdown_error","variant":"'..profile.variant..'"}') end
    handle:flush();handle:close();handle=nil;closed=true;__hd2_grip_b23=nil
    if not ok then error(err) end
end
local function step(phase)
    if closed then return end
    if phase=='update' then frame=frame+1 end
    local ok,err=pcall(runtime.tick,runtime,phase,frame,stingray.Application.time_since_launch())
    if not ok then
        log('{"event":"callback_error","phase":"'..phase..'","variant":"'..profile.variant..'"}')
        stop('callback_error');error(err)
    end
end
return {version=Transfer.VERSION,update=function()step('update')end,render=function()step('render')end,
    shutdown=function()stop('shutdown')end,on_stop=function()stop('on_stop')end}
