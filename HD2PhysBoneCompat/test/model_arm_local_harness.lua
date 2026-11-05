-- Real serialized layouts; separate model local matrices and linked world
-- caches. A local setter updates a synthetic skin input snapshot. This models
-- the API contract under test, not the game's unobserved GPU implementation.
local parts={armor}
for resource in pairs(profile.modelLayouts)do
 if resource~=armor.resource then parts[#parts+1]=make(false,A.x,resource,A)end
end
local outsider=make(false,50,profile.targets.body[1],nil)
world=function(u,index)
 if u.owner and u.cached and u.cached[index]then return copy(u.cached[index])end
 local p=copy(u.locals[index]);local parent=u.parents[index]
 if parent~=0 then p=adapter.compose(world(u,parent),p)else p.p[1]=p.p[1]+u.x end
 return p
end
local function refresh(u,count)
 if not u.owner then return end
 u.cached={}
 for i,h in ipairs(u.hashes)do
  local source=u.owner.names[h]
  if source then
   local p=world(u.owner,source);p.p[1]=p.p[1]+u.x-u.owner.x;u.cached[i]=p
  end
 end
 if count then u.refreshes=(u.refreshes or 0)+1 end
end
S.World.update_unit=function(_,u)check(u.alive,'refresh destroyed unit');refresh(u,true)end
local originalSetter=S.Unit.set_local_pose
S.Unit.set_local_pose=function(u,n,p)
 originalSetter(u,n,p)
 if u.owner then
  u.skinInputs=u.skinInputs or {};u.skinInputs[n]=copy(p)
  u.skinInvalidations=(u.skinInvalidations or 0)+1
 end
end
local nativeHand=profile.armChains[1].nativeHand+1
A.locals[nativeHand].p[2]=A.locals[nativeHand].p[2]+.04
local animationA=copy(A.locals);local animationB=copy(B.locals)
tick=function(n)
 for _=1,n or 1 do
  frame=frame+1;clock=clock+1/60
  A.locals=copy(animationA);B.locals=copy(animationB)
  for _,u in ipairs(parts)do
   -- Incoming linked animation overwrites local inputs each frame. The later
   -- graph refresh is intentionally independent from the local setter.
   for i,h in ipairs(u.hashes)do
    local index=u.owner.names[h]
    if index then u.locals[i]=copy(u.owner.locals[index])end
   end
   u.skinInputs=copy(u.locals)
   if u.alive then refresh(u,false)end
  end
  runtime:tick(frame)
 end
end
local function delta(x,y)
 local a,b=packed(x),packed(y);local d=0
 for j=1,12 do d=math.max(d,math.abs(a[j]-b[j]))end
 return d
end
tick(4)
if measureOnly then
 local errors={}
 for _,u in ipairs(parts)do
  local e=0
  for _,r in ipairs(profile.modelArmLocalLayouts[u.resource])do e=math.max(e,delta(u.locals[r.index+1],A.locals[r.avatarIndex+1]))end
  errors[u.resource]=e
 end
 return errors
end
check(runtime.stats.active==1,'body did not activate')
local totalWritten=0
for _,u in ipairs(parts)do
 check(u.writes>0,'direct model local writes missing: '..u.resource)
 local allowed={}
 for _,r in ipairs(profile.modelArmLocalLayouts[u.resource])do
  allowed[r.index+1]=true
  check(delta(u.locals[r.index+1],A.locals[r.avatarIndex+1])<1e-9,'model local differs from solved Avatar')
  check(delta(u.skinInputs[r.index+1],A.locals[r.avatarIndex+1])<1e-9,'synthetic skin inputs were not invalidated')
 end
 for index in pairs(u.written)do check(allowed[index],'wrote outside eight arm nodes');totalWritten=totalWritten+1 end
 check(u.skinInvalidations==u.writes,'synthetic invalidation contract mismatch')
end
check(totalWritten==88,'not all eleven model layouts exercised')
check(outsider.writes==0,'unowned selector received local writes')
check(hasLog('model_arm_local_copy') and hasLog('after_max_element_error=0.000000'),'local copy readback missing')
local part
for _,u in ipairs(parts)do if u.resource=='d154442f2e33fdee'then part=u end end
check(part~=nil,'left arm fixture absent')
local function noWrites(message,change,undo)
 local before=part.writes;change();tick(1)
 check(part.writes==before,message);undo();tick(3)
 check(part.writes>before,'failed to reacquire after '..message)
end
noWrites('hidden model written',function()part.visible=false end,function()part.visible=true end)
local resource=part.resource
noWrites('changed resource written',function()part.resource='ffffffffffffffff'end,function()part.resource=resource end)
local nodes=part.nodes
noWrites('changed count written',function()part.nodes=nodes-1 end,function()part.nodes=nodes end)
noWrites('destroyed model written',function()part.alive=false end,function()part.alive=true end)
local row=profile.modelArmLocalLayouts[resource][1];local hash=hash_name(row.name)
noWrites('missing name accepted for direct write',function()part.missing[hash]=true end,function()part.missing[hash]=nil end)
local parentHash=hash_name(row.parentName)
noWrites('missing parent name accepted',function()part.missing[parentHash]=true end,function()part.missing[parentHash]=nil end)
local index=part.names[hash]
noWrites('wrong node index accepted',function()part.names[hash]=index+1 end,function()part.names[hash]=index end)
noWrites('missing Avatar name accepted',function()A.missing[hash]=true end,function()A.missing[hash]=nil end)
local parentIndex=part.names[parentHash]
noWrites('wrong parent index accepted',function()part.names[parentHash]=parentIndex+1 end,function()part.names[parentHash]=parentIndex end)
local prior=part.writes;B.x=A.x;animationB=copy(animationA);tick(2)
check(runtime.stats.active==0 and part.writes==prior,'ambiguous ownership wrote model locals')
B.x=4;tick(3);check(part.writes>prior,'unique ownership did not recover')
-- Direct nested matrix copy must preserve scale. Test in isolation so the
-- unchanged rigid arm solver is not asked to accept a scaled arm input.
local a=runtime.avatars[A];local item=runtime.models[part]
local sourceIndex=row.avatarIndex+1;A.locals[sourceIndex].scaled=true
check(runtime:sync_model_arm_locals(a,item,false),'isolated direct copy refused')
check(part.locals[row.index+1].scaled==true,'direct copy lost matrix scale')
A.locals[sourceIndex].scaled=nil;tick(3)
-- Validate every input before the first write, including the final row.
local toElements=S.Matrix4x4.to_elements
local final=profile.modelArmLocalLayouts[resource][8]
local bad=A.locals[final.avatarIndex+1]
S.Matrix4x4.to_elements=function(p)if p==bad then return 0/0,0,0,0,1,0,0,0,1,0,0,0 end;return toElements(p)end
prior=part.writes
local ok=pcall(runtime.sync_model_arm_locals,runtime,a,item,false)
check(not ok and part.writes==prior,'invalid final matrix partially wrote the model')
S.Matrix4x4.to_elements=toElements
-- Removing body selectors restores visible consumers from the Avatar's
-- restored current animation input, then updates the model graph once.
for _,u in ipairs(parts)do
 for _,id in ipairs(profile.targets.body)do if u.resource==id then u.visible=false end end
end
tick(1)
check(not runtime.avatars[A].armsActive,'body selector loss left arm solver active')
for _,r in ipairs(profile.modelArmLocalLayouts[part.resource])do
 check(delta(part.locals[r.index+1],A.locals[r.avatarIndex+1])<1e-9,'deactivation did not copy restored input')
end
check(runtime.models[part].armLocalOwner==nil,'deactivation retained model write ownership')
for _,u in ipairs(parts)do u.visible=true end;tick(3)
runtime:release()
for _,u in ipairs(parts)do
 for _,r in ipairs(profile.modelArmLocalLayouts[u.resource])do
  check(delta(u.locals[r.index+1],A.locals[r.avatarIndex+1])<1e-9,'release did not restore model from Avatar')
 end
 check(runtime.models[u].armLocalOwner==nil,'release retained model write ownership')
end
check(outsider.writes==0 and B.writes==0,'unowned model or unrelated Avatar written')
check(readMissing==0,'node lookup used a missing hash')
return {checks=checks,modelLayouts=#parts,nodesPerModel=8,uniqueWrittenNodes=totalWritten,
 independentModelLocals=true,simulatedSkinInvalidationOnly=true,scalePreserved=true,
 exactWriteScope=true,identityFailuresRejected=true,deactivationAndReleaseRestored=true,
 gpuBehavior='unobserved; fixture verifies direct local API calls only'}
