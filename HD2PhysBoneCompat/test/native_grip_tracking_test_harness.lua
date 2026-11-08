-- V5 is observation-only: verify true marker offsets, phase sampling, and V4-equivalent writes.
local trackingResult={}
local function tracking_start(enabled)
 repaired_start('dbb6c961c59fadc1');aim_native();native_contact(.30)
 integratedProfile.testRepairs.gripTracking.enabled=enabled
 -- Synthetic receiver: add only verified model hash/index probe rows.
 for _,spec in pairs(integratedProfile.models)do
  spec.testGripProbes={}
  for _,key in ipairs({'sourceHand','sourceElbow'})do
   local node=integratedProfile.testRepairs.gripTracking.actorNodes[key]
   local i=node and model.names[node.hash]
   if i then spec.testGripProbes[#spec.testGripProbes+1]={name=node.name,hash=node.hash,index=i-1,parent=model.parents[i]}end
  end
 end
 return copy(A.locals)
end
local function tracking_row(stage)
 for i=#logs,1,-1 do
  local line=logs[i]
  if line:find('"event":"test_grip_tracking_probe"',1,true) and line:find('"stage":"'..stage..'"',1,true)
   and line:find('"status":"verified_p40k_link"',1,true) then
   local raw=line:match('"sourceWristInGrip":%[([^%]]+)%]');local m={}
   if raw then for n in raw:gmatch('[^,]+')do m[#m+1]=tonumber(n)end end
   return line,m
  end
 end
end
local oldDebugTracking=S.World.debug_camera_pose
S.World.debug_camera_pose=function(w)check(w==1,'TEST tracking used foreign camera world');return transform(.37)end
local input=tracking_start(false);local countBefore=writes
step(runtime,'render',9600,960)
local baseline={avatar=copy(A.locals),model=copy(model.locals),gun=copy(gun.locals),writes=writes-countBefore}
runtime:stop();all_same(A.locals,input,'TEST tracking-off shutdown restore')
input=tracking_start(true);countBefore=writes
step(runtime,'render',9600,960)
check(not runtime.disabled,'TEST tracking disabled runtime')
all_same(A.locals,baseline.avatar,'TEST tracking changed V4 avatar outputs')
all_same(model.locals,baseline.model,'TEST tracking changed V4 model outputs')
all_same(gun.locals,baseline.gun,'TEST tracking changed V4 gun outputs')
check(writes-countBefore==baseline.writes,'TEST tracking added pose setters')
local line,m=tracking_row('final_output')
check(line and #m==12,'TEST tracking live gun-frame observation missing')
check(line:find('"cameraWorld"',1,true) and line:find('"models"',1,true),'TEST tracking camera/model same-frame fields missing')
check(line:find('"skinMatricesObserved":false',1,true),'TEST tracking falsely asserted GPU state')
local marker=gun.names[hash_name('IK_right')]
check(near(m,numpy_relative(gun.cache[marker],A.cache[integratedProfile.sourceRight.index+1]),2e-5),'TEST tracking does not measure live gun marker')
-- A moving marker with an unchanged native-hand proxy MUST appear in this metric.
-- This does not assert that V5 changed the solver's position authority.
local source=copy(A.cache[integratedProfile.sourceRight.index+1]);local native=copy(A.cache[integratedProfile.nativeRight.index+1])
gun.locals[marker][12]=gun.locals[marker][12]+.04;refresh_all()
step(runtime,'render',9601,960.11)
local shiftedLine,shifted=tracking_row('final_output')
check(shiftedLine and #shifted==12,'TEST tracking moved-marker row missing')
check(near(shifted,numpy_relative(gun.cache[marker],A.cache[integratedProfile.sourceRight.index+1]),2e-5),'TEST tracking hid live marker movement')
check(separation(m,shifted)>.025,'TEST tracking reused self-validating native-hand target')
local nextLine=tracking_row('next_render_input');check(nextLine,'TEST tracking next-frame input missing')
runtime:stop();all_same(A.locals,input,'TEST tracking shutdown restore')
S.World.debug_camera_pose=oldDebugTracking
trackingResult.liveMarkerIndependentMetric=true;trackingResult.sameFrameCameraAndModels=true
trackingResult.v4SolverAndWriteCountsUnchanged=true;trackingResult.nextRenderInput=true
result15.gripTracking=trackingResult
