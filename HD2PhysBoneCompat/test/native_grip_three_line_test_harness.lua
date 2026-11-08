-- Three-line opt-in tests appended to the complete historical weapon suite.
local repairResult={}
local function repaired_start(id,lines)
 new_start(id);runtime:stop()
 integratedProfile.testRepairs=copy(test_repair_configuration)
 integratedProfile.testRepairs.poseProbes={}
 local aimNodes={}
 for key,node in pairs(integratedProfile.testRepairs.aimNodes or {})do
  local n=A.names[node.hash]
  if n then local copyNode=copy(node);copyNode.index=n-1;copyNode.parent=A.parents[n];aimNodes[key]=copyNode end
 end
 integratedProfile.testRepairs.aimNodes=aimNodes
 if integratedProfile.testRepairs.bodyDiagnostics then
  local pairs={}
  for _,pair in ipairs(integratedProfile.testRepairs.bodyDiagnostics.pairs or {})do
   local row=copy(pair);local valid=true
   for _,key in ipairs({'source','native','reference'})do
    local node=row[key]
    if node then
     local i=A.names[node.hash]
     if i then node.index=i-1;node.parent=A.parents[i]else valid=false end
    end
   end
   if valid then pairs[#pairs+1]=row end
  end
  integratedProfile.testRepairs.bodyDiagnostics.pairs=pairs
 end

 if integratedProfile.testRepairs.nativeReverse then
  local nodes={}
  for _,node in ipairs(integratedProfile.testRepairs.nativeReverse.arm.nodes)do
   local i=A.names[node.hash];check(i,'TEST native reverse fixture node missing')
   local n=copy(node);n.index=i-1;n.parent=A.parents[i];nodes[#nodes+1]=n
  end
  integratedProfile.testRepairs.nativeReverse.arm.nodes=nodes
  -- Historical accepted cases remain the V4 baseline; the new suite opts in.
  integratedProfile.testRepairs.nativeReverse.enabled=false
 end

 if integratedProfile.testRepairs.gripTracking then
  local nodes={}
  for key,node in pairs(integratedProfile.testRepairs.gripTracking.actorNodes or {})do
   local i=A.names[node.hash]
   if i then local n=copy(node);n.index=i-1;n.parent=A.parents[i];nodes[key]=n end
  end
  integratedProfile.testRepairs.gripTracking.actorNodes=nodes
 end
 integratedProfile.testRepairs.lines=lines or {handContact=true,stockPolicy=true,components=true}
 integratedProfile.logging={compact=false,detailed=true};integratedProfile.maxRecords=1000000
 if integratedProfile.testRepairs.lines.stockPolicy then
  for _,rid in ipairs({'027dec442cc26a90','0b882808c6f498e8','9eb160830321bfd6'}) do integratedProfile.leftGrip.weaponTargets[rid].leftPolicy='always' end
 end
 if integratedProfile.testRepairs.lines.components then
  for rid,spec in pairs(test_component_specs) do integratedProfile.consumers[rid]=copy(spec);integratedProfile.allowedConsumers[rid]=true end
 end
 runtime=module.new(S,integratedProfile,function(line)logs[#logs+1]=line end,arm_math,
  {inMission=function()return true end,world=function()return 1 end,firstPerson=function()return false end})
 return runtime
end
local function contact_point(m,v)
 return {m[10]+m[1]*v[1]+m[4]*v[2]+m[7]*v[3],m[11]+m[2]*v[1]+m[5]*v[2]+m[8]*v[3],m[12]+m[3]*v[1]+m[6]*v[2]+m[9]*v[3]}
end
-- Marker orientation is NOT native wrist orientation. Goal direction changes
-- must not force Source hand roll when native post-IK wrist is unchanged.
for _,rid in ipairs({'9eb160830321bfd6','027dec442cc26a90','0b882808c6f498e8','cf8934ff6567a42d'}) do
 repaired_start(rid);aim_native();native_contact(.30)
 local mi=gun.names[hash_name('IK_right')]
 gun.locals[mi]=multiply(gun.locals[mi],transform(.7));refresh_all()
 local native=copy(A.cache[integratedProfile.nativeRight.index+1])
 local target=contact_point(native,integratedProfile.testRepairs.contacts.right.native)
 local input=copy(A.locals);local gunBefore=copy(gun.locals);local mount=copy(A.cache[ti])
 step(runtime,'render',9000,900)
 check(not runtime.disabled and runtime.stats.rightWrites==1,'test contact right output missing '..rid)
 local source=A.cache[integratedProfile.sourceRight.index+1]
 local registered=numpy_multiply(source,integratedProfile.rightAxes)
 for j=1,9 do check(math.abs(registered[j]-native[j])<3e-5,'TEST right consumed weapon marker orientation '..rid)end
 local actual=contact_point(source,integratedProfile.testRepairs.contacts.right.source)
 for j=1,3 do check(math.abs(actual[j]-target[j])<3e-5,'TEST right contact proxy missed '..rid..' axis='..j..' actual='..actual[j]..' target='..target[j])end
 all_same(gun.locals,gunBefore,'TEST contact mutated weapon locals')
 check(near(A.cache[ti],mount,3e-5),'reachable TEST contact displaced gun')
 step(runtime,'update',9000,900.01);runtime:stop();all_same(A.locals,input,'TEST right restore')
end
repairResult.rightNativeOrientationAndContact=true
-- Main-weapon left hand must follow the corrected gun, not the old native path.
repaired_start('ce063aa33d95a812')
gun=make(weapon_assets['ce063aa33d95a812']);gunParent=model;gunMount=hash_name('attach_hand_r')
weaponRoot=gun.names[hash_name('root')];under=gun.names[hash_name('attach_underbarrel')]
linkedItems={};groups[1]={A,model,gun};pad_main();refresh_all()
local li=gun.names[hash_name('IK_left')]
local live=gun.cache[li];local rootLeft=A.cache[integratedProfile.leftGrip.nodes[2].index+1]
local expectedMount=numpy_multiply(numpy_multiply(A.cache[integratedProfile.sourceRight.index+1],integratedProfile.rightAxes),A.locals[oi])
if integratedProfile.sourceRightMount then expectedMount=A.cache[integratedProfile.sourceRightMount.index+1]end
local ci=integratedProfile.rightGrip.nodes[1].index+1
local shifted=copy(A.cache[ci]);local delta={.15,.02,.18}
for j=1,3 do shifted[j+9]=shifted[j+9]+rootLeft[j+9]+delta[j]-(live[j+9]+expectedMount[j+9]-A.cache[ti][j+9])end
A.locals[ci]=numpy_relative(A.cache[A.parents[ci]+1],shifted);refresh_all();native_contact()
local ni=integratedProfile.nativeLeft.index+1
local native=copy(A.cache[ni]);local rotated=multiply(native,transform(.33))
A.locals[ni]=numpy_relative(A.cache[A.parents[ni]+1],rotated);refresh_all()
local originalGrip=numpy_multiply(A.cache[oi],numpy_relative(gun.cache[weaponRoot],gun.cache[li]))
local nativeBefore=copy(A.cache[ni]);local leftInput=copy(A.locals)
step(runtime,'render',9050,905)
check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST rebased left output missing')
local rebased=numpy_multiply(gun.cache[li],numpy_relative(originalGrip,nativeBefore))
local leftSource=A.cache[integratedProfile.sourceLeft.index+1]
local registered=numpy_multiply(leftSource,integratedProfile.leftAxes)
for j=1,9 do check(math.abs(registered[j]-rebased[j])<4e-5,'TEST left consumed marker rotation')end
local actual=contact_point(leftSource,integratedProfile.testRepairs.contacts.left.source)
local wanted=contact_point(rebased,integratedProfile.testRepairs.contacts.left.native)
for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST left did not rebase to final gun contact')end
runtime:stop();all_same(A.locals,leftInput,'TEST left restore')
repairResult.leftRebasedOrientationAndContact=true
-- New contact outputs obey the existing transactional fail-closed restoration.
for _,fault in ipairs({1,3,4,5})do
 repaired_start('cf8934ff6567a42d');aim_native();native_contact(.30)
 local input=copy(A.locals);failAt=fault;step(runtime,'render',9070+fault,907+fault*.01)
 check(runtime.disabled,'TEST contact setter failure was swallowed')
 all_same(A.locals,input,'TEST contact rollback');runtime:stop()
end
repairResult.contactRollback=true
-- Stock weapons use two-hand contact intent, not the one-hand ADS-only gate.
repaired_start('0b882808c6f498e8',{handContact=false,stockPolicy=true,components=false})
native_contact(.08);local input=copy(A.locals);step(runtime,'render',9100,910)
check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST stock eight-centimetre native intent rejected')
native_contact(.30);step(runtime,'render',9101,910.02)
check(runtime.stats.leftWrites==1,'TEST stock reload/free-left forced grip')
runtime:stop();repairResult.stockIntentAndRelease=true
-- Actual AR-61 magazine was filtered out. Exact signature enables refresh;
-- neither refresh nor reload is allowed to mutate part local transforms.
repaired_start('ce063aa33d95a812',{handContact=false,stockPolicy=false,components=true})
gun=make(weapon_assets['ce063aa33d95a812']);gunParent=model;gunMount=hash_name('attach_hand_r')
weaponRoot=gun.names[hash_name('root')];under=gun.names[hash_name('attach_underbarrel')]
linkedItems={};groups[1]={A,model,gun};pad_main();refresh_all()
local mag=add_component('89cce4d15db88aa8','attach_mag');native_contact(.30);refresh_all()
local partBefore=copy(mag.locals);step(runtime,'render',9200,920)
check(not runtime.disabled,'TEST AR61 disabled')
local found=false;for _,item in ipairs(runtime.consumers)do if item.spec.resource==mag.resource then found=true end end
check(found,'TEST AR61 exact magazine not discovered')
check(near(mag.cache[mag.linkRoot],gun.cache[mag.linkIndex]),'TEST AR61 magazine cache detached')
all_same(mag.locals,partBefore,'TEST AR61 part locals changed')
mag.linkOwner=model;mag.linkIndex=model.names[hash_name('attach_hand_l')];refresh_all();step(runtime,'render',9201,920.02)
check(near(mag.cache[mag.linkRoot],model.cache[mag.linkIndex]),'TEST AR61 reload relink lost')
all_same(mag.locals,partBefore,'TEST AR61 reload part locals changed');runtime:stop()
repairResult.ar61MagazineAndNativeReload=true
-- Detailed recording must survive later weapons, while retaining a hard cap.
local clockTime=0;local disk={};local sink,budget=module.newLogSink(function(s)disk[#disk+1]=s end,function()return clockTime end,
 {recordSeconds=3600,maxBytes=1048576,exceptionIntervalSeconds=.25})
sink('{"event":"applied"}');clockTime=600;sink('{"event":"test_pose_trace","stage":"late_weapon"}')
check(not budget.stopped and disk[#disk]:find('late_weapon',1,true),'TEST detailed log ended at 90 seconds')
clockTime=3601;sink('{"event":"test_pose_trace"}');check(budget.stopped,'TEST detailed log unbounded')
sink('{"event":"complete"}');check(disk[#disk]:find('complete',1,true),'TEST detailed terminal summary lost')
local seen=false;for _,s in ipairs(logs)do if s:find('"event":"test_pose_trace"',1,true) and s:find('"testOnly":true',1,true)then seen=true end end
check(seen,'TEST detailed pose trace missing test marker')
repairResult.detailedFullMatrixLifecycle=true
result15.threeLineTest=repairResult
