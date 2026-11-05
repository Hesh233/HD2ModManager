-- Each armor fixture uses its own serialized model hash order and topology.
-- Model world reads emulate the game's name-bound avatar attachment; they do
-- not recycle the avatar node array or fabricate a model node count.
local function copy(v)
 if type(v)~='table' then return v end;local r={};for k,x in pairs(v) do r[k]=copy(x) end;return r
end
local units={};local clock=0;local checks=0;local logs={};local readMissing=0;local weaponComponentCount=0
local function check(v,message)checks=checks+1;assert(v,message)end
local function make(avatar,x,resource,owner)
 local shape=avatar and fixture.avatar or assert(fixture.models[resource])
 local u={alive=true,avatar=avatar,x=x,resource=resource,nodes=#shape.hashes,
  locals=copy(shape.localPoses),parents=shape.parents,hashes=shape.hashes,names={},writes=0,written={},owner=owner,missing={}}
 for i,h in ipairs(shape.hashes)do u.names[h]=i end
 units[#units+1]=u;return u
end
local A=make(true,0,'avatar');local B=make(true,4,'avatar')
local armor=make(false,0,profile.targets.body[1],A)
local function world(u,index)
 if u.owner then
  local i=u.owner.names[u.hashes[index]]
  if i then local p=world(u.owner,i);p.p[1]=p.p[1]+u.x-u.owner.x+(u.poseNoise or 0);return p end
 end
 local p=copy(u.locals[index]);local parent=u.parents[index]
 if parent~=0 then p=adapter.compose(world(u,parent),p)elseif u.linkPose then p=adapter.compose(u.linkPose,p)else p.p[1]=p.p[1]+u.x end
 return p
end
local function packed(p)
 local x,y,z,w=unpack(p.q)
 local r={1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,
  2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,
  2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y,p.p[1],p.p[2],p.p[3]}
 if p.scaled then r[1]=r[1]*2;r[2]=r[2]*2;r[3]=r[3]*2 end;return r
end
local S={Unit={},World={},Application={},IdString64={to_hex=function(id)return id end},
 Vector3=setmetatable({to_elements=function(v)return unpack(v)end},{__call=function(_,...)return {...}end}),
 Quaternion={to_elements=function(v)return unpack(v)end,from_elements=function(...)return {...}end},
 Matrix4x4={to_elements=function(p)return unpack(packed(p))end,from_quaternion_position=function(q,p)return {q=q,p=p}end}}
S.Application.worlds=function()return {1}end
S.Application.string_to_id32=function(name)return hash_name(name)end
S.Application.time_since_launch=function()return clock end
S.World.units=function()local r={};for _,u in ipairs(units)do if u.alive then r[#r+1]=u end end;return r end
S.World.units_by_resource=function()local r={};for _,u in ipairs(units)do if u.alive and u.avatar then r[#r+1]=u end end;return r end
S.World.update_unit=function(_,u)check(u.alive,'update dead unit')end
S.Mesh={visibility=function(m)if m.unknown then return nil end;return m.visible~=false end}
S.Unit.num_meshes=function()return 1 end
S.Unit.mesh=function(u)return {visible=u.visible,unknown=u.visibilityUnknown}end
S.Unit.alive=function(u)return u.alive end
S.Unit.has_animation_state_machine=function(u)return u.avatar==true end
S.Unit.num_scene_graph_items=function(u)return u.nodes end
S.Unit.resource_name=function(u)return u.resource end
S.Unit.has_node=function(u,h)return not u.missing[h] and u.names[h]~=nil and u.names[h]<=u.nodes end
S.Unit.node=function(u,h)
 if not S.Unit.has_node(u,h)then readMissing=readMissing+1;return 1 end
 return u.names[h]
end
S.Unit.world_position=function(u,n)assert(u.alive and n>=1 and n<=u.nodes);return world(u,n).p end
S.Unit.world_rotation=function(u,n)assert(u.alive and n>=1 and n<=u.nodes);return world(u,n).q end
S.Unit.local_pose=function(u,n)assert(u.alive and n>=1 and n<=u.nodes);return u.locals[n]end
S.Unit.set_local_pose=function(u,n,p)
 assert(u.alive and n>=1 and n<=u.nodes);u.locals[n]=copy(p);u.writes=u.writes+1;u.written[n]=true
end
local runtime=adapter.new(S,profile,function(fmt,...)logs[#logs+1]=string.format(fmt,...)end,{settleFrames=2,scanFrames=1,readbackFrames=120})
local frame=0
local function tick(n)for _=1,n or 1 do frame=frame+1;clock=clock+1/60;runtime:tick(frame)end end
local function hasLog(part)for _,s in ipairs(logs)do if s:find(part,1,true)then return true end end;return false end
check(armor.nodes~=A.nodes,'fixture recycles avatar count')
check(armor.names[hash_name(profile.signature[1].name)]~=A.names[hash_name(profile.signature[1].name)],'fixture recycles avatar indices')
tick(3)
check(runtime.stats.active==1 and #runtime.armor==1 and A.writes>0 and B.writes==0,'actual model layout was not selected')
armor.visible=false;tick(1)
check(runtime.stats.active==0,'hidden but alive armor kept the VPK profile')
armor.visible=true;tick(3)
check(runtime.stats.active==1,'visible armor did not reacquire')
armor.visibilityUnknown=true;tick(3)
check(runtime.stats.active==1,'unknown visibility treated as definitely hidden')
armor.visibilityUnknown=nil
check(hasLog('attachment_readback phase=render') and hasLog('consumer=unobserved'),'readback phase not explicit')
check(hasLog('geometry_diagnostic phase=render') and hasLog('native_hand_span=') and hasLog('grip_reference_error phase=render'),'hand geometry/reference diagnostics missing')
local firstReadbacks=runtime.stats.readbacks;tick(130)
check(runtime.stats.readbacks>firstReadbacks,'periodic attachment readback missing')
local blendedRows={};local weapon
for _,row in ipairs(profile.vpk)do
 if row.policy=='source-blended-reference' then
  blendedRows[#blendedRows+1]=row
  if row.standardName=='attach_weapon'then weapon=row end
 end
end
local function desired(u,row)
 local offset=adapter.relative(world(u,row.configuredAnchorIndex+1),world(u,row.sourceReferenceIndex+1))
 return adapter.compose(adapter.compose(world(u,row.sourceAnchorIndex+row.sourceIndexOffset+1),
  {p={0,0,0},q=row.axisCorrection}),offset)
end
local function checkBlended(message)
 for _,row in ipairs(blendedRows)do
  if row.ownerSlot=='body'then check(adapter.close(world(A,row.index+1),desired(A,row)),message..':'..tostring(row.standardName))end
 end
end
if #blendedRows>0 then
 check(weapon and weapon.configuredAnchorIndex~=weapon.driverAnchorIndex,'weapon uses live native hand as configured anchor')
 checkBlended('post-blend relative mapping')
 local start=world(A,weapon.index+1)
 local nativeHand=weapon.driverAnchorIndex+1;local savedHand=copy(A.locals[nativeHand])
 A.locals[nativeHand].p[1]=A.locals[nativeHand].p[1]+.25
 A.locals[nativeHand].q={0,0,math.sin(.3),math.cos(.3)}
 tick(1)
 check(adapter.close(world(A,weapon.index+1),start),'live native hand leaked into configured weapon offset')
 A.locals[nativeHand]=savedHand
 local anchor=weapon.configuredAnchorIndex+1;local savedAnchor=copy(A.locals[anchor])
 A.locals[anchor].p[1]=A.locals[anchor].p[1]+.1;tick(1)
 checkBlended('configured hand response')
 check(not adapter.close(world(A,weapon.index+1),start),'configured clone hand was ignored')
 A.locals[anchor]=savedAnchor;tick(1)
 -- Both configured branches meet at the original weapon parent (chest).
 -- Its procedural motion must cancel before mapping onto the Source hand.
 local common=weapon.parentIndex+1;local savedCommon=copy(A.locals[common])
 A.locals[common].p[2]=A.locals[common].p[2]+.2
 A.locals[common].q={math.sin(.2),0,0,math.cos(.2)};tick(1)
 check(adapter.close(world(A,weapon.index+1),start),'common native parent failed to cancel')
 checkBlended('common-parent cancellation')
 A.locals[common]=savedCommon;tick(1)
 local sourceHand=weapon.sourceAnchorIndex+weapon.sourceIndexOffset+1;local savedSource=copy(A.locals[sourceHand])
 A.locals[sourceHand].q={0,math.sin(.15),0,math.cos(.15)};tick(1)
 checkBlended('Source hand response')
 check(not adapter.close(world(A,weapon.index+1),start),'Source hand was ignored')
 A.locals[sourceHand]=savedSource;tick(1)
 -- No input pose may be first sampled after any output in the batch changes.
 local protected={};for _,row in ipairs(blendedRows)do
  protected[row.configuredAnchorIndex+1]=true;protected[row.sourceReferenceIndex+1]=true
  protected[row.sourceAnchorIndex+row.sourceIndexOffset+1]=true
 end
 local before=A.writes;local readPosition=S.Unit.world_position;local readRotation=S.Unit.world_rotation
 S.Unit.world_position=function(u,n)
  check(not(u==A and u.writes>before and protected[n]),'position input read after output write')
  return readPosition(u,n)
 end
 S.Unit.world_rotation=function(u,n)
  check(not(u==A and u.writes>before and protected[n]),'rotation input read after output write')
  return readRotation(u,n)
 end
 tick(1);S.Unit.world_position=readPosition;S.Unit.world_rotation=readRotation
 for i=1,4 do tick(1);check(adapter.close(world(A,weapon.index+1),start),'previous output fed into configured references')end
 local configKey=hash_name(weapon.configuredAnchorName);A.missing[configKey]=true;tick(3)
 check(runtime.stats.active==0,'missing configured anchor accepted')
 A.missing[configKey]=nil;tick(3);check(runtime.stats.active==1,'configured anchor reacquire failed')
end
for _,row in ipairs(profile.vpk)do
 if row.policy=='original-world' then check(not A.written[row.index+1],'aim input directly overwritten')end
end
local key=hash_name(profile.signature[1].name)
armor.missing[key]=true;tick(2)
check(runtime.stats.active==1 and hasLog('cached_name_miss=1'),'transient model has_node failure lost active owner')
armor.missing[key]=nil;tick(1)
check(runtime.models[armor].missingScans==0,'successful revalidation did not reset grace')
A.missing[key]=true;tick(2)
check(runtime.stats.active==1,'transient avatar has_node failure lost active owner')
A.missing[key]=nil;tick(1)
armor.missing[key]=true;tick(3)
check(runtime.stats.active==0 and #runtime.armor==0,'persistent missing signature accepted')
armor.missing[key]=nil;tick(3);check(runtime.stats.active==1,'reacquisition failed')
local originalIndex=armor.names[key];armor.names[key]=originalIndex+1;tick(1)
check(runtime.stats.active==0 and hasLog('index_mismatch:'),'same-count different-index model accepted')
armor.names[key]=originalIndex;tick(3)
local count=armor.nodes;armor.nodes=count-1;tick(1)
check(runtime.stats.active==0 and hasLog('model_nodes:'),'changed model count accepted')
armor.nodes=count;tick(3)
local originalResource=armor.resource;armor.resource='ffffffffffffffff';tick(1)
check(runtime.stats.active==0,'resource swap reused identity cache')
armor.resource=originalResource;tick(3)
armor.poseNoise=.02;tick(1);check(runtime.stats.active==0,'layout cache bypassed live ownership poses')
armor.poseNoise=nil;tick(3)
-- A fresh instance must prove every name; Unit.node's bogus missing-name index
-- must never be used as an alternative to has_node.
armor.alive=false;tick(1)
local unknown=make(false,A.x,profile.targets.body[1],A);unknown.missing[key]=true;tick(3)
check(runtime.stats.active==0 and readMissing==0,'new instance admitted through cached/missing name')
unknown.alive=false;armor.alive=true;tick(3)
-- Same-count avatar index replacement must not restore to invalid old indices.
local avatarIndex=A.names[key];local beforeWrites=A.writes;A.names[key]=avatarIndex+1;tick(1)
check(runtime.avatars[A]==nil and A.writes==beforeWrites,'invalid avatar graph received stale restore writes')
A.names[key]=avatarIndex;tick(3);check(runtime.stats.active==1,'avatar reacquire failed')
-- Moving, multiplayer ambiguity, independent head/body selection, unequip.
if fixture.consumers then
 local sampleRow;for _,r in ipairs(profile.vpk)do if r.standardName=='attach_samplepouch'then sampleRow=r end end
 local function consumer(resource,row)
  local shape=assert(fixture.consumers[resource])
  local u={alive=true,avatar=false,x=0,resource=resource,nodes=#shape.hashes,
   locals=copy(shape.localPoses),parents=shape.parents,hashes=shape.hashes,names={},writes=0,written={},missing={},linkOwner=A,linkRow=row,
   linkPose=world(A,row.referenceIndex+1),refreshes=0}
  for i,h in ipairs(shape.hashes)do u.names[h]=i end
  units[#units+1]=u;return u
 end
 local gun=consumer('a7ee1ebf58fcdf1f',weapon)
 local pouch=consumer('a9936cbe561e8180',sampleRow)
 local parts={}
 for _,spec in ipairs({{'6b88fea13ec2d78e','attach_muzzle'},{'9dbc8aa8702ac9e1','attach_optic'},
                      {'fa6c1158a93b8ec4','attach_mag'},{'309f7e645a8d2b56','attach_underbarrel'}})do
  if fixture.consumers[spec[1]] then
   local part=consumer(spec[1],weapon);part.linkRow=nil;part.linkOwner=gun
   part.linkNode=assert(gun.names[hash_name(spec[2])]);part.linkPose=world(gun,part.linkNode)
   parts[#parts+1]=part
  end
 end
 -- Put children ahead of their gun to reproduce engine enumeration order.
 if #parts>0 then for i,u in ipairs(units)do if u==gun then table.remove(units,i);break end end;units[#units+1]=gun end
 weaponComponentCount=#parts
 local originalUpdate=S.World.update_unit
 S.World.update_unit=function(w,u)
  originalUpdate(w,u)
  if u.linkRow then u.linkPose=world(u.linkOwner,u.linkRow.index+1);u.refreshes=u.refreshes+1 end
  if u.linkNode then u.linkPose=world(u.linkOwner,u.linkNode);u.refreshes=u.refreshes+1 end
 end
 tick(3)
 check(#runtime.consumers==2+#parts and gun.refreshes>0 and pouch.refreshes>0,'independent equipment graphs not refreshed')
 check(adapter.close(pouch.linkPose,world(A,sampleRow.index+1)),'sample pouch kept pre-write graph')
 local saved=A.locals[weapon.sourceAnchorIndex+weapon.sourceIndexOffset+1].p[1]
 A.locals[weapon.sourceAnchorIndex+weapon.sourceIndexOffset+1].p[1]=saved+.1;tick(1)
 check(adapter.close(gun.linkPose,world(A,weapon.index+1)),'weapon graph not refreshed after Source hand movement')
 for _,part in ipairs(parts)do
  check(part.refreshes>0 and adapter.close(part.linkPose,world(gun,part.linkNode)),'weapon component retained pre-gun graph')
  check(part.writes==0,'weapon component local pose was changed')
 end
 A.locals[weapon.sourceAnchorIndex+weapon.sourceIndexOffset+1].p[1]=saved
 armor.visible=false;tick(1)
 check(adapter.close(gun.linkPose,world(A,weapon.referenceIndex+1)),'weapon graph not refreshed after unequip restore')
 check(adapter.close(pouch.linkPose,world(A,sampleRow.referenceIndex+1)),'pouch graph not restored after unequip')
 for _,part in ipairs(parts)do check(adapter.close(part.linkPose,world(gun,part.linkNode)),'weapon component missed unequip restore')end
 check(gun.writes==0 and pouch.writes==0,'refresh mutated independent equipment local pose')
 armor.visible=true;tick(3)
 if #parts>0 then
  local part=parts[1];local before=part.refreshes;part.alive=false;tick(1)
  check(part.refreshes==before,'destroyed weapon component refreshed');part.alive=true
  local magazine=parts[3];local detached=copy(magazine.linkPose);magazine.linkNode=nil;magazine.linkOwner=nil;tick(1)
  check(adapter.close(magazine.linkPose,detached),'detached magazine was reattached')
 end
 local before=gun.refreshes;gun.alive=false;tick(1)
 check(gun.refreshes==before,'destroyed weapon refreshed')
 pouch.resource='ffffffffffffffff';before=pouch.refreshes;tick(1)
 check(pouch.refreshes==before,'changed equipment reused old cache')
 pouch.alive=false;tick(1)
 for _,part in ipairs(parts)do part.alive=false end
 S.World.update_unit=originalUpdate
end
for i=1,10 do A.x=i*.1;armor.x=A.x;tick(1);check(runtime.stats.active==1 and B.writes==0,'moving owner mismatch')end
B.x=A.x;B.locals=copy(A.locals);tick(3)
check(runtime.stats.active==0 and runtime.stats.ambiguous>0,'coincident avatars assigned arbitrarily')
B.x=4;tick(3);check(runtime.stats.active==1,'separated avatars not recovered')
local helmet=make(false,B.x,profile.targets.head[1],B);tick(3)
local headEnabled=not profile.preserveHeadAttachments
check(runtime.stats.active==(headEnabled and 2 or 1) and (headEnabled and B.writes>0 or not headEnabled and B.writes==0),'independent helmet policy not honored')
for _,row in ipairs(profile.vpk)do if row.ownerSlot=='body'then check(not B.written[row.index+1],'helmet switched body')end end
local saved=A.writes+B.writes;runtime:tick(frame);check(saved==A.writes+B.writes,'duplicate render timestamp wrote')
armor.alive=false;tick(1);check(runtime.stats.active==(headEnabled and 1 or 0) and not runtime.avatars[A].active,'unequip failed')
runtime.mode='off';tick(1);check(runtime.stats.active==0,'off failed')
runtime.mode='observe';saved=A.writes+B.writes;tick(3);check(saved==A.writes+B.writes,'observe wrote')
runtime:release()
local scaleUnit=B;local scaleSlot='head'
if not headEnabled then armor.alive=true;scaleUnit=A;scaleSlot='body' end
local headRow;for _,row in ipairs(profile.vpk)do if row.ownerSlot==scaleSlot and (row.policy=='source-reference' or row.policy=='source-blended-reference')then headRow=row;break end end
scaleUnit.locals[headRow.referenceIndex+1].scaled=true;runtime.mode='apply';saved=A.writes+B.writes
if not headEnabled then tick(1) end -- one settle frame, no pose writes
local ok=pcall(function()tick(1)end)
check(not ok and saved==A.writes+B.writes,'scaled batch partially wrote')
runtime:release();check(scaleUnit.locals[headRow.index+1].scaled==true,'rollback discarded reference scale')
check(readMissing==0,'read an unchecked node')
check(hasLog('missing_name:') and hasLog('model_signature='),'rejection reasons missing')
return {checks=checks,actualModelNodes=count,actualAvatarNodes=A.nodes,signatureNodes=#profile.signature,weaponComponentCount=weaponComponentCount,
 blendedReferenceRows=#blendedRows,readsForMissingNames=readMissing,readbacks=runtime.stats.readbacks,logLines=#logs,scope='real serialized layouts, simulated hash-bound poses and engine calls'}
