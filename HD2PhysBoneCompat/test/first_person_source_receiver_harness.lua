-- Actual FP97 and model264 layouts, independent caches and recyclable matrices.
local function copy(t)if type(t)~='table'then return t end;local r={};for k,v in pairs(t)do r[k]=copy(v)end;return r end
local float32=false
local checks=0;local function check(v,s)checks=checks+1;assert(v,s)end
local function mul(a,b)local r={};for c=0,2 do for i=1,3 do local v=0;for k=0,2 do v=v+a[k*3+i]*b[c*3+k+1]end;r[c*3+i]=v end end;for i=1,3 do r[i+9]=a[i+9]+a[i]*b[10]+a[i+3]*b[11]+a[i+6]*b[12]end;if float32 then for i,v in ipairs(r)do r[i]=f32(v)end end;return r end
local function make(f)local u={alive=true,resource=f.resource,count=#f.parents,parents=copy(f.parents),locals=copy(f.matrices),hashes=copy(f.hashes),names={},cache={}};for i,h in ipairs(u.hashes)do u.names[h]=i end;return u end
local fp=make(fp_fixture);local model=make(model_fixture);local tpModel=make(model_fixture);local groups={[1]={tpModel},[2]={fp,model}};local receiver=true;local view=true;local mission=true
local externalRootShift=0;local externalRootShiftY=0;local externalRootShiftZ=0;local pendingNativeShift;local lateOutputShift=false;local writesSinceFlush=0;local liveNative;local freezeSource=false
model.nativeReceiver=true
local function calc(u)
 local cache={}
 if u==fp and liveNative then for i,m in pairs(liveNative)do cache[i+1]=copy(m);if float32 then for j,v in ipairs(cache[i+1])do cache[i+1][j]=f32(v)end end end end
 local function node(i)
  if cache[i]then return cache[i]end
  local p=u.parents[i];cache[i]=p and mul(node(p+1),u.locals[i])or copy(u.locals[i])
  if u==fp and not p then cache[i][10]=cache[i][10]+externalRootShift;cache[i][11]=cache[i][11]+externalRootShiftY;cache[i][12]=cache[i][12]+externalRootShiftZ end
  return cache[i]
 end
 for i=1,u.count do node(i)end;u.cache=cache
end
local function refresh(u)
 local old=u.cache;calc(u)
 if u==fp and freezeSource then for _,n in ipairs(contract.avatar.outputs)do u.cache[n.index+1]=copy(old[n.index+1])end end
 if u==model or u==tpModel or u.nativeReceiver then
  if u.nativeReceiver then
   for _,n in ipairs(contract.model.nativeMatches)do u.cache[n.index+1]=copy(fp.cache[n.fpIndex+1])end
   if receiver then for _,n in ipairs(contract.sourceNodes)do u.cache[n.modelIndex+1]=copy(u.holdSources and u.holdSources[n.modelIndex+1]or fp.cache[n.index+1])end end
  end
 end
end
refresh(fp);refresh(model);refresh(tpModel)
local originalNative={};for i=1,63 do originalNative[i]=copy(fp.locals[i])end;local originalModel=copy(model.locals);local originalTP=copy(tpModel.locals)
local writes=0;local nativeWrites=0;local modelWrites=0;local reads=0;local scratch={};local tokens={};local logs={}
local function recycled(v)for k in pairs(scratch)do scratch[k]=nil end;if v then for k,x in pairs(v)do scratch[k]=x end end;return scratch end
local S={Application={},World={},Unit={},Matrix4x4={},IdString64={}};local U,W,A,X=S.Unit,S.World,S.Application,S.Matrix4x4
A.worlds=function()recycled();return {1,2}end;A.string_to_id32=function(name)local id={};tokens[id]=hash_name(name);return id end
W.units=function(w)recycled();return groups[w]or{}end;W.units_by_resource=function(w,path)recycled();check(path=='content/fac_helldivers/fp_cha_avatar/fp_cha_avatar','wrong FP query');return w==2 and {fp}or{}end
W.debug_camera_pose=function()local m=copy(fp.cache[51]);if not view then m[10]=m[10]+2 end;return recycled(m)end
U.alive=function(u)recycled();return u.alive end;U.resource_name=function(u)recycled();return u.resource end;S.IdString64.to_hex=function(x)recycled();return x end
U.num_scene_graph_items=function(u)recycled();return u.count end
U.has_node=function(u,id)recycled();assert(tokens[id],'raw IdString');return u.names[tokens[id]]~=nil end;U.node=function(u,id)recycled();assert(tokens[id],'raw node ID');return u.names[tokens[id]]end
U.scene_graph_parent=function(u,i)recycled();local p=u.parents[i];return p and p+1 or nil end
U.local_pose=function(u,i)reads=reads+1;assert(u.alive and i<=u.count);return recycled(u.locals[i])end;U.world_pose=function(u,i)reads=reads+1;assert(u.alive and i<=u.count);return recycled(u.cache[i])end
X.to_elements=function(m)return unpack(m)end;X.from_elements=function(...)return recycled({...})end
U.set_local_pose=function(u,i,m)writes=writes+1;if u~=fp then modelWrites=modelWrites+1;error('model pose writer')end;if i<=63 then nativeWrites=nativeWrites+1;error('native FP writer')end;u.locals[i]=copy(m);writesSinceFlush=writesSinceFlush+1 end
W.update_unit=function(w,u)
 recycled()
 if u==fp then
  if pendingNativeShift then
   if type(pendingNativeShift)=='table'then externalRootShift=externalRootShift+pendingNativeShift[1];externalRootShiftY=externalRootShiftY+pendingNativeShift[2];externalRootShiftZ=externalRootShiftZ+pendingNativeShift[3]
   else externalRootShift=externalRootShift+pendingNativeShift end
   pendingNativeShift=nil
  end
  if lateOutputShift and writesSinceFlush>=#contract.avatar.outputs then externalRootShift=externalRootShift+.04;lateOutputShift=false end
  writesSinceFlush=0
 end
 refresh(u)
end
local ctx={world=function()return 1 end,inMission=function()return mission end};local guard=guard_module.new(S,ctx,contract.avatar)
local rt=source_module.new(S,contract,arm_math,guard,function(r)logs[#logs+1]=copy(r);if fixture_log_tap then fixture_log_tap(r)end end,ctx)
local function frame(i)
 fp.locals[8][10]=.07*i;fp.locals[8][12]=.02*math.sin(i*.1);local n=34+1;local a=.025*i;fp.locals[n][1]=math.cos(a);fp.locals[n][2]=math.sin(a);fp.locals[n][4]=-math.sin(a);fp.locals[n][5]=math.cos(a)
 refresh(fp);refresh(model);rt:tick('update',i,i*.1);rt:tick('render',i,i*.1)
end
mission=false;local before=writes;frame(1);check(writes==before,'ship got FP Source writes');mission=true
for i=2,12 do frame(i)end
for _,n in ipairs(contract.sourceNodes)do
 local world=fp.cache[n.index+1];local parent=fp.cache[n.parent+1];local d=0;for j=10,12 do d=d+(world[j]-parent[j])^2 end
 local length=0;for j=10,12 do length=length+n.bindLocal[j]^2 end
 check(math.abs(math.sqrt(d)-math.sqrt(length))<1e-5,'FP Source segment stretched')
end
check(rt.stats.failures==0,'FP pipeline failure');check(rt.stats.receiverMatches>=8,'FP Source receiver failed');check(rt:permit(model,2,12),'FP verified right model not permitted');check(not rt:permit(tpModel,1,12),'TP same-resource instance permitted')
for i=1,63 do for j,v in ipairs(originalNative[i])do
 if i~=8 and i~=35 then check(math.abs(fp.locals[i][j]-v)<1e-7,'native FP local overwritten')end
end end
for i,m in ipairs(model.locals)do for j,v in ipairs(m)do check(v==originalModel[i][j],'model local changed')end end
for i,m in ipairs(tpModel.locals)do for j,v in ipairs(m)do check(v==originalTP[i][j],'TP model local changed')end end
-- The live failure lacks actual Source matrices. Reproduce its class without
-- pretending this synthetic cache schedule is the observed engine root cause.
local failuresBefore=rt.stats.failures
for i=30,37 do
 rt:tick('update',i,i*.1)
 pendingNativeShift=.025 -- native external owner advanced; FP cache is still old
 rt:tick('render',i,i*.1)
 check(rt.stats.failures==failuresBefore,'stale native producer cache caused Source readback failure')
end
check(rt:permit(model,2,37),'fresh native-input proof did not permit the verified receiver')
local foundReceiver,foundCapture,foundNext=false,false,false
for _,row in ipairs(logs)do
 if row.event=='fp_source_receiver'then foundReceiver=true;check(row.outputs and #row.outputs==#contract.sourceNodes,'all Source receiver samples not logged')end
 if row.event=='fp_native_and_melee_capture'then foundCapture=true end
 if row.event=='fp_source_next_render'then foundNext=true;check(row.outputRestoredSinceWrite==true,'next-render diagnostic falsely assumes prior output is held')end
end
check(foundCapture and foundReceiver,'native capture starved successful receiver diagnostics')
check(foundNext,'next-render reception diagnostic lost across update restoration')
-- Distinct-frame proof and slow genuine receiver movement (0.4mm per frame).
view=false;rt:tick('render',110,11);view=true;rt:tick('update',111,11.1);rt:tick('render',111,11.1)
rt:tick('render',111,11.15);check(rt.proof==1 and not rt:permit(model,2,111),'duplicate render counted as distinct motion proof frame')
for i=112,123 do rt:tick('update',i,i*.1);pendingNativeShift=.0004;rt:tick('render',i,i*.1)end
check(rt:permit(model,2,123),'slow continuous verified receiver motion remained hidden')
-- All matrices can match within 2mm while the actual model remains frozen.
-- Oscillating Source displacement exceeds 2mm in Euclidean span; actual model span is zero.
local hold={};for _,n in ipairs(contract.sourceNodes)do hold[n.modelIndex+1]=copy(model.cache[n.modelIndex+1])end
model.holdSources=hold;view=false;rt:tick('render',130,13);view=true
local offset=0
for i=131,138 do
 rt:tick('update',i,i*.1);local wanted=i%2==1 and .0012 or -.0012
 pendingNativeShift={wanted-offset,wanted-offset,wanted-offset};offset=wanted;rt:tick('render',i,i*.1)
 check(not rt:permit(model,2,i),'tolerance-matching frozen receiver displayed')
end
rt:tick('update',139,13.9);model.holdSources=nil;externalRootShift=externalRootShift-offset;externalRootShiftY=externalRootShiftY-offset;externalRootShiftZ=externalRootShiftZ-offset;refresh(fp);refresh(model)
-- A stale Source output is NOT fixed by accepting the matching stale model.
rt:tick('update',40,4);fp.cache[contract.sourceNodes[1].index+1][10]=fp.cache[contract.sourceNodes[1].index+1][10]+.02
freezeSource=true;rt:tick('render',40,4)
check(rt.stats.sourceWorldReadbackFailures>0 and not rt:permit(model,2,40),'frozen Source output was displayed')
freezeSource=false;refresh(fp);refresh(model)
-- A native owner that changes again during output flush stays fail-closed.
rt:tick('update',41,4.1);lateOutputShift=true;rt:tick('render',41,4.1)
check(rt.stats.nativeWorldChangedDuringOutput>0 and not rt:permit(model,2,41),'native drift during Source write was displayed')
local sourceDetail,nativeDetail=false,false
for _,row in ipairs(logs)do
 if row.event=='fp_source_unavailable' and row.detail then
  if row.detail.stage=='source_world_readback'then sourceDetail=row.detail.actualWorld and row.detail.expectedWorld and row.detail.parentWorld end
  if row.detail.stage=='native_input_changed_during_source_flush'then nativeDetail=true end
 end
end
check(sourceDetail and nativeDetail,'readback failure lacks actual source/native matrices')
-- Replay all 32 measured native FP47 snapshots with float32 FK and exact layouts.
float32=true
for j,sample in ipairs(live_samples)do
 local i=60+j;rt:tick('update',i,i*.1);liveNative={}
 for _,n in ipairs(sample.nativePoses)do liveNative[n.index]=copy(n.world)end
 local failure=rt.stats.failures;rt:tick('render',i,i*.1)
 check(rt.stats.failures==failure,'recorded FP47 float32 replay failed')
 for _,n in ipairs(contract.sourceNodes)do
  local world=fp.cache[n.index+1];local parent=fp.cache[n.parent+1];local d=0;local length=0
  for k=10,12 do d=d+(world[k]-parent[k])^2;length=length+n.bindLocal[k]^2 end
  check(math.abs(math.sqrt(d)-math.sqrt(length))<8e-5,'recorded FP Source segment stretched beyond float32 tolerance')
 end
end
check(#live_samples==32 and rt:permit(model,2,92),'recorded FP47 receiver replay did not prove live motion')
liveNative=nil;float32=false;externalRootShift=0;externalRootShiftY=0;externalRootShiftZ=0;refresh(fp);refresh(model)
view=false;before=writes;rt:tick('render',13,1.3);check(not rt:permit(model,2,13),'TP transition retained FP permit');check(writes>=before,'restore path missing')
-- Old failure fixture: native bones/root move but Source receive remains frozen.
view=true;receiver=false;refresh(model);for i=14,17 do frame(i)end;check(rt.stats.receiverMisses>0,'frozen receiver accepted');check(not rt:permit(model,2,17),'frozen receiver displayed')
-- Ambiguity: two exact matching FP instances means no writes/permit.
receiver=true;local duplicate=make(model_fixture);duplicate.nativeReceiver=true;refresh(duplicate);for _,n in ipairs(contract.model.nativeMatches)do duplicate.cache[n.index+1]=copy(fp.cache[n.fpIndex+1])end;groups[2]={fp,model,duplicate};rt:tick('update',18,1.8);before=writes;rt:tick('render',18,1.8);check(writes==before,'ambiguous FP wrote output');groups[2]={fp,model}
-- Source schema mismatch and killed instances cannot leak writes.
fp.count=96;rt:tick('render',19,1.9);check(not rt:permit(model,2,19),'unknown FP layout displayed');fp.count=#fp.parents
-- A native FP63 installation is capture-only, never a relaxed FP97 writer.
rt:tick('update',100,10);fp.count=63;before=writes;rt:tick('render',100,10)
check(writes==before and not rt:permit(model,2,100),'native FP63 received Source writes or show permission')
local nativeOnly=false
for _,row in ipairs(logs)do if row.event=='fp_source_graph_not_installed'and row.actualCount==63 then nativeOnly=true end end
check(nativeOnly,'native FP63 capture-only diagnostic missing');fp.count=#fp.parents;refresh(fp);refresh(model)
for i=20,23 do frame(i)end;fp.alive=false;before=writes;rt:tick('update',24,2.4);check(writes==before,'dead FP restored through setter');rt:stop()
check(nativeWrites==0 and modelWrites==0,'forbidden pose writes')
return {status='PASS_PENDING_GAME_TEST',checks=checks,sourceWrites=rt.stats.writes,restores=rt.stats.restores,receiverMatches=rt.stats.receiverMatches,receiverMisses=rt.stats.receiverMisses,nativeWrites=nativeWrites,modelWrites=modelWrites,readCalls=reads,slowContinuousReceiverMotionVerified=true,distinctRenderFramesVerified=true,frozenWithinToleranceReceiverRejected=true,native63CaptureOnlyVerified=true,nativeRefreshBeforeSamplingVerified=true,staleProducerScheduleReproduced=true,sourceFreezeRejected=true,nativeOutputDriftRejected=true,recordedNativeReplaySamples=#live_samples,perEventProofLogging=true,nextRenderAfterRestoreLogged=true,logs=logs}
