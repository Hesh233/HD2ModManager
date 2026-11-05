local function copy(v)
 if type(v)~='table' then return v end;local r={};for k,x in pairs(v) do r[k]=copy(x) end;return r
end
local units={};local clock=0;local calls=0;local checks=0
for i,p in ipairs(fixture.localPoses) do assert(#p.p==3 and #p.q==4,'bad fixture pose '..i..' '..#p.p..' '..#p.q) end
local function check(v,message)checks=checks+1;assert(v,message)end
local function unit(avatar,x,resource)
 local u={alive=true,avatar=avatar,nodes=avatar and profile.expectedAvatarNodes or profile.expectedModelNodes,x=x,resource=resource,
  locals=copy(fixture.localPoses),names=fixture.names,parents=fixture.parents,writes=0,written={}}
 units[#units+1]=u;return u
end
local A=unit(true,0,'avatar');local B=unit(true,4,'avatar');local armor=unit(false,0,profile.targets.body[1])
local function world(u,index)
 local p=copy(u.locals[index]);local parent=u.parents[index]
 if parent~=0 then p=adapter.compose(world(u,parent),p) else p.p[1]=p.p[1]+u.x end
 return p
end
local function packed(p)
 local x,y,z,w=unpack(p.q)
 local r={1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,
  2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,
  2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y,p.p[1],p.p[2],p.p[3]}
 if p.scaled then r[1]=r[1]*2;r[2]=r[2]*2;r[3]=r[3]*2 end
 return r
end
local S={Unit={},World={},Application={},IdString64={to_hex=function(id)return id end},
 Vector3=setmetatable({to_elements=function(v)return unpack(v)end},{__call=function(_,...)return {...}end}),
 Quaternion={to_elements=function(v)return unpack(v)end,from_elements=function(...)return {...}end},
 Matrix4x4={to_elements=function(p)return unpack(packed(p))end,from_quaternion_position=function(q,p)return {q=q,p=p}end}}
S.Application.worlds=function()return {1}end
S.Application.string_to_id32=function(name)return name end
S.Application.time_since_launch=function()return clock end
S.World.units=function()local r={};for _,u in ipairs(units) do if u.alive then r[#r+1]=u end end;return r end
S.World.units_by_resource=function()local r={};for _,u in ipairs(units) do if u.alive and u.avatar then r[#r+1]=u end end;return r end
S.World.update_unit=function(_,u)check(u.alive,'update dead unit')end
S.Unit.alive=function(u)return u.alive end
S.Unit.has_animation_state_machine=function(u)return u.avatar end
S.Unit.num_scene_graph_items=function(u)return u.nodes end
S.Unit.resource_name=function(u)return u.resource end
S.Unit.has_node=function(u,n)return u.names[n]~=nil and u.names[n]<=u.nodes end
S.Unit.node=function(u,n)return u.names[n] or -1 end
S.Unit.world_position=function(u,n)assert(u.alive and n<=u.nodes);return world(u,n).p end
S.Unit.world_rotation=function(u,n)assert(u.alive and n<=u.nodes);return world(u,n).q end
S.Unit.local_pose=function(u,n)assert(u.alive and n<=u.nodes);return u.locals[n] end
S.Unit.set_local_pose=function(u,n,p)
 assert(u.alive and n>=1 and n<=u.nodes);u.locals[n]=copy(p);u.writes=u.writes+1;u.written[n]=true;calls=calls+1
end
local runtime=adapter.new(S,profile,function()end,{settleFrames=2,scanFrames=1})
local frame=0
local function tick(n)for _=1,n or 1 do frame=frame+1;clock=clock+1/60;runtime:tick(frame)end end
local original={};for _,r in ipairs(profile.vpk) do original[r.index]=world(A,r.referenceIndex+1) end
tick(3)
check(runtime.stats.active==1 and A.writes>0 and B.writes==0,'per-player match failed')
local moved=0
for _,r in ipairs(profile.vpk) do
 if r.policy=='original-world' then check(not A.written[r.index+1],'controller input was overwritten') end
 check(adapter.close(world(A,r.referenceIndex+1),original[r.index]),'shadow node changed')
 if r.ownerSlot=='head' then check(adapter.close(world(A,r.index+1),original[r.index]),'body switched helmet')
 elseif not adapter.close(world(A,r.index+1),original[r.index]) then moved=moved+1 end
end
check(moved>0,'no VPK attachment movement')
local stable={};for _,r in ipairs(profile.vpk) do stable[r.index]=world(A,r.index+1) end
tick(100)
for _,r in ipairs(profile.vpk) do check(adapter.close(world(A,r.index+1),stable[r.index]),'feedback drift') end
-- Simulate a native procedural aim controller moving the hand after animation.
-- A VPK reference remains coherent with the VPK hand, regardless of that
-- native-only pose delta. The old mixed-space formula moved the weapon away.
local weapon;for _,r in ipairs(profile.vpk) do if r.standardName=='attach_weapon' then weapon=r end end
local driver=weapon.driverAnchorIndex+1
local savedDriver=copy(A.locals[driver]);A.locals[driver].p[3]=A.locals[driver].p[3]+.45
tick(1)
check(adapter.close(world(A,weapon.index+1),world(A,weapon.sourceReferenceIndex+1)),'native aim leaked into VPK weapon offset')
A.locals[driver]=savedDriver
for _,r in ipairs(profile.vpk) do if r.policy=='original-world' then
 A.locals[r.index+1].p[2]=A.locals[r.index+1].p[2]+.2
 local expected=copy(A.locals[r.index+1]);tick(1)
 check(adapter.close(A.locals[r.index+1],expected) and not A.written[r.index+1],'live controller pose was reset')
 A.locals[r.index+1]=copy(fixture.localPoses[r.index+1])
end end
for i=1,20 do
 A.x=i*.01;armor.x=A.x
 A.locals[1].q={0,0,math.sin(i*.01),math.cos(i*.01)};armor.locals[1].q=copy(A.locals[1].q)
 tick(1);check(runtime.stats.active==1 and B.writes==0,'moving/turning owner lost')
end
for _,r in ipairs(profile.vpk) do original[r.index]=world(A,r.referenceIndex+1) end
local writes=calls;runtime:tick(frame);check(calls==writes,'duplicate timestamp wrote poses')
armor.alive=false;tick(1)
check(runtime.stats.active==0,'unequip did not deactivate')
for _,r in ipairs(profile.vpk) do check(adapter.close(world(A,r.index+1),original[r.index]),'unequip did not restore') end
armor.alive=true;B.x=A.x;B.locals[1]=copy(A.locals[1]);tick(3)
check(runtime.stats.active==0 and runtime.stats.ambiguous>0,'coincident avatars were assigned')
B.x=4;tick(3);check(runtime.stats.active==1,'reacquire failed')
local helmet=unit(false,4,profile.targets.head[1]);helmet.locals[1]=copy(B.locals[1]);tick(3)
check(runtime.stats.active==2 and B.writes>0,'independent helmet profile failed')
for _,r in ipairs(profile.vpk) do
 if r.ownerSlot=='body' then check(adapter.close(world(B,r.index+1),world(B,r.referenceIndex+1)),'helmet switched body') end
end
runtime.mode='off';tick(1);check(runtime.stats.active==0,'off did not restore')
runtime.mode='observe';writes=calls;tick(3);check(calls==writes,'observe mode wrote')
runtime.mode='apply';A.nodes=profile.expectedAvatarNodes-1;tick(3);check(runtime.avatars[A]==nil,'rebuilt skeleton retained')
runtime:release();check(not runtime.avatars[B].active,'release failed')
local head;for _,r in ipairs(profile.vpk) do if r.ownerSlot=='head' and r.policy=='source-reference' then head=r;break end end
B.locals[head.referenceIndex+1].scaled=true;writes=calls
local ok=pcall(function()tick(1)end);check(not ok and calls==writes,'non-rigid batch partially wrote')
runtime:release()
check(B.locals[head.index+1].scaled==true and not runtime.avatars[B].active,'rollback lost original scale')
return {checks=checks,selectedNodes=#profile.vpk,writeCalls=calls,sourceMovedNodes=moved,feedbackFrames=100}
