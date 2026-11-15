-- Simulate the observed lazy animated-root cache: a parent write changes the
-- chest immediately, but a child world's cache is frozen until same-local touch.
local fkResult={};local fkDelegate=U.set_local_pose;local updateDelegate=S.World.update_unit;local worldDelegate=U.world_pose
local fkActive=false;local watched={};local frozen={};local touchCount=0
U.set_local_pose=function(u,n,m)
 if fkActive and u==A and watched[n] then
  check(near(m,A.locals[n],2e-5),'TEST Source FK changed animation local value')
  A.locals[n]=copy(m);frozen[n]=nil;recycled();writes=writes+1;touchCount=touchCount+1
  if failAt==writes then failAt=nil;error('injected_source_fk_setter_failure')end
 else fkDelegate(u,n,m)end
end
U.world_pose=function(u,n)
 if fkActive and u==A and frozen[n] then return copy(frozen[n])end
 return worldDelegate(u,n)
end
S.World.update_unit=function(w,u)
 local before=u==A and copy(A.cache) or nil
 updateDelegate(w,u)
 if fkActive and u==A then
  for n,parent in pairs(watched)do
   if before[n] and before[parent] and not near(before[parent],A.cache[parent],1e-7) then frozen[n]=copy(before[n])end
  end
 end
end
local function fk_start()
 fkActive=false;watched={};frozen={}
 repaired_start('dbb6c961c59fadc1');runtime:stop()
 integratedProfile.rightGrip.enabled=false;integratedProfile.leftGrip.enabled=false;integratedProfile.rightAttachmentEnabled=false
 integratedProfile.testRepairs.sourceFkRefresh.enabled=true
 for _,group in ipairs(integratedProfile.testRepairs.sourceFkRefresh.levels)do
  for _,node in ipairs(group)do
   if node.name:find('_clavicle',1,true) or node.name:find('_neck',1,true)then watched[node.index+1]=node.parent+1 end
  end
 end
 runtime=module.new(S,integratedProfile,function(line)logs[#logs+1]=line end,arm_math,
  {inMission=function()return true end,world=function()return 1 end,firstPerson=function()return false end})
 fkActive=true;touchCount=0
 return copy(A.locals)
end
local input=fk_start();local nativeBefore=copy(A.locals[nativeRight]);local gunBefore=copy(gun.locals)
step(runtime,'render',10300,1030)
check(not runtime.disabled,'TEST Source FK runtime disabled')
for n,parent in pairs(watched)do
 local expected=numpy_multiply(A.cache[parent],A.locals[n]);local actual=U.world_pose(A,n)
 check(near(expected,actual,2e-5),'TEST Source FK refresh failed')
end
check(touchCount>0 and runtime.stats.sourceFkTouches>0,'TEST Source FK refresh failed: no same-local touches')
check(near(A.locals[nativeRight],nativeBefore),'TEST Source FK wrote native r_hand')
all_same(gun.locals,gunBefore,'TEST Source FK wrote weapon locals')
runtime:stop();all_same(A.locals,input,'TEST Source FK shutdown changed animation locals')
-- Native animation/physics may change while the Source roots need another
-- refresh. No accumulation or global scale correction is allowed.
input=fk_start();local chest=integratedProfile.bodySync.outputs[2].native.index+1
for i=1,6 do
 A.locals[chest]=multiply(A.locals[chest],transform(.13*i));refresh_all()
 step(runtime,'render',10310+i,1031+i*.1)
 check(not runtime.disabled,'TEST Source FK moving-parent disabled')
 for n,parent in pairs(watched)do
  check(near(U.world_pose(A,n),numpy_multiply(A.cache[parent],A.locals[n]),2e-5),'TEST Source FK moving parent stale')
 end
end
local fresh=copy(A.locals[chest]);runtime:stop()
check(near(A.locals[chest],fresh),'TEST Source FK restore overwrote native animation')
fkResult.sameLocalDirtyRefresh=true;fkResult.parentMovementAndShutdown=true;fkResult.nativeAndWeaponUnchanged=true
fkActive=false;U.set_local_pose=fkDelegate;U.world_pose=worldDelegate;S.World.update_unit=updateDelegate
result15.sourceFkRefresh=fkResult
