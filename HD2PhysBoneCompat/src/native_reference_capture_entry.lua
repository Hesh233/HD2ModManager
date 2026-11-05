-- HD2-Addon: mods/hd2modmanager/native_grip_capture
-- B21 standalone read-only native reference collector. Requires Chef 1.4.1.
local loader=...
assert(type(loader)=='table'and loader.loader=='Chef Shared Loader','B21 requires Chef Shared Loader')
local Capture=(function()
-- INSERT CAPTURE MODULE
end)()
local config=(function()
-- INSERT CAPTURE PROFILE
end)()
local path=assert(loader.log_directory,'loader log directory unavailable')..'/hd2_native_grip_capture.log'
local handle,why=io.open(path,'a');assert(handle,'Cannot open B21 log: '..tostring(why))
local frame,closed=0,false
local function log(value)
 if handle then handle:write(os.date('%Y-%m-%d %H:%M:%S'),' [native_capture] ',value,'\n')end
end
local capture=Capture.new(stingray,config,log)
handle:flush()
__hd2_native_grip_capture=capture
local function step(phase)
 if closed then return end
 if phase=='update'then frame=frame+1 end
 local ok,wrote=pcall(capture.tick,capture,phase,frame,stingray.Application.time_since_launch())
 if not ok then
  log('{"event":"callback_error","phase":"'..phase..'"}')
  capture:stop('callback_error');handle:flush();error(wrote)
 end
 if wrote and (phase=='render'or capture.stopped)then handle:flush()end
end
local function stop()
 if closed then return end
 capture:stop('shutdown');handle:flush();handle:close();handle=nil;closed=true
 __hd2_native_grip_capture=nil
end
return {version='1.0.0',update=function()step('update')end,render=function()step('render')end,
 shutdown=stop,on_stop=stop}
