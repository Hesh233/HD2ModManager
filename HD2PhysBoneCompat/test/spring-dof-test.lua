-- Flag-driven linear DOFs. Numeric Source references + ownership/writer/lifecycle tests.
local M = assert(loadfile(arg[1] or "HD2PhysBoneCompat/src/physbone_compat.lua"))()
local q = M._q
local checks = 0
local function check(name, ok)
 checks = checks + 1
 assert(ok, name)
 print("  PASS " .. name)
end
local function close(a,b,e) return math.abs(a-b) <= (e or 1e-10) end
local function params(overrides)
 local p={length=1,tipMass=0,yawStiffness=50,yawDamping=10,pitchStiffness=50,pitchDamping=10,
 alongStiffness=100,alongDamping=3,angleLimit=0,baseMass=0,baseStiffness=100,baseDamping=3,
 baseMinLeft=-.006,baseMaxLeft=.006,baseMinUp=-.006,baseMaxUp=.006,
 baseMinForward=-.006,baseMaxForward=.006,baseLeftFriction=0,baseUpFriction=0,baseForwardFriction=0}
 for k,v in pairs(overrides or {}) do p[k]=v end
 return p
end
local function tip(flags,p,count,module)
 module=module or M;count=count or 1
 local t={bones={},tips={},segDirLocal={},dirs={},basePoses={}}
 for i=1,count do
  local g=module.gains_of(p or params(),1,1,{flags=flags})
  t.bones[i]={gains=g,offLocal={(i-1)*.2,0,0},frameLocal={1,0,0,0,1,0}}
  t.tips[i]={ready=false,px=0,py=0,pz=0,vx=0,vy=0,vz=0}
  t.segDirLocal[i]={0,0,1}
  t.basePoses[i]={px=i==1 and 0 or .2,py=0,pz=0,bindQ={0,0,0,1},bindParentQ={0,0,0,1}}
  if g.baseSpring then t.hasBaseSpring=true;t.hasLinearDofs=true end
  if g.freeLength then t.hasFreeLength=true;t.hasLinearDofs=true end
 end
 return t
end
local function step(t,dt,x,y,z) M.step_tip(t,dt,x or 0,y or 0,z or 0,0,0,0,1) end

local fixed=M.gains_of(params(),1,1,{flags=0x31})
check("0x31 keeps fixed length and no base spring",not fixed.freeLength and fixed.baseSpring==nil)
local both=M.gains_of(params(),1,1,{flags=0x51})
check("0x51 enables independent base and axial spring",both.freeLength and both.baseSpring and both.kAlong==100)
local onlyTip=M.gains_of(params(),1,1,{flags=0x19})
check("0x19 enables axial but not base",onlyTip.freeLength and onlyTip.baseSpring==nil)
local rigid=M.gains_of(params(),1,1,{flags=0x62})
check("rigid tip has gravity but not flexible spring forces",rigid.rigidTip and rigid.kAlong==nil and rigid.baseSpring~=nil)
local baseOnly=M.gains_of(params(),1,1,{flags=0x40})
check("base-only flags leave tip orientation kinematic",baseOnly.noTipFlex and baseOnly.baseSpring and not baseOnly.freeLength)
local inactive=M.gains_of(params({alongStiffness=0/0,baseMass=0/0}),1,1,{flags=0x31})
check("inactive parameter groups are not evaluated",inactive.invalidLinearParams==nil)
local invalid=M.gains_of(params({alongStiffness=math.huge,baseMinLeft=1,baseMaxLeft=-1}),1,1,{flags=0x51})
check("nonfinite or reversed authored parameters fail closed",invalid.invalidLinearParams and not invalid.freeLength and invalid.baseSpring==nil)
local scaled=M.gains_of(params({baseMass=10}),.02,.03,{flags=0x71}).baseSpring
check("base distance and gravity units are converted separately",close(scaled.minimum[1],-.006*.02) and close(scaled.g,.3))

local free=tip(0x01);local constrained=tip(0x21)
local rp,rv,maximum=1,0,0
for i=0,720 do
 local z=.03*math.sin(2*math.pi*i/240);local dt=1/240
 rv=rv+(100*(z+1-rp)-3*rv)*dt;rp=rp+rv*dt
 step(free,dt,0,0,z);step(constrained,dt,0,0,z)
 assert(close(free.tips[1].pz,rp,1e-10) and close(free.tips[1].vz,rv,1e-10),"Source axial Euler mismatch")
 assert(close(constrained.tips[1].pz,z+1) and close(constrained.tips[1].vz,0),"fixed branch moved radially")
 maximum=math.max(maximum,math.abs(free.tips[1].span-1))
 local r=M.local_rotations(free,0,0,0,1)[1]
 assert(close(r[4],0),"pure axial dynamics must not create mesh scaling or rotation")
end
check("zero-gravity axial dynamics match Source reference for 721 frames",maximum>.01)
check("fixed projection and radial velocity removal are flag-conditional",close(constrained.tips[1].span or 1,1))

-- In a bent chain the target direction and authored force frame differ.
-- Equal stiffness/damping on all three axes must still equal k*error-c*velocity.
local iso=tip(0x01,params({yawStiffness=20,pitchStiffness=20,alongStiffness=20,yawDamping=2,pitchDamping=2,alongDamping=2}),2)
step(iso,.001);iso.tips[1].px=.1
local it=iso.tips[2];it.px,it.py,it.pz=.3,.02,1.1;it.vx,it.vy,it.vz=.2,.1,-.2
local ox,oy,oz,vx,vy,vz=it.px,it.py,it.pz,it.vx,it.vy,it.vz
step(iso,.001);local d=iso.dirs[1]
check("axial force completes yaw/pitch frame without double-counting",close(it.vx,vx+(20*(.2+d[1]-ox)-2*vx)*.001) and close(it.vy,vy+(20*(d[2]-oy)-2*vy)*.001) and close(it.vz,vz+(20*(d[3]-oz)-2*vz)*.001))

local undamped=tip(0x01,params({alongDamping=0}));local damped=tip(0x01,params({alongDamping=20}))
step(undamped,1/240);step(damped,1/240)
undamped.tips[1].pz=1.1;damped.tips[1].pz=1.1
for i=1,240 do step(undamped,1/240);step(damped,1/240) end
check("authored along damping changes the actual response",math.abs(damped.tips[1].pz-1)<math.abs(undamped.tips[1].pz-1)*.1)
local zeroK=tip(0x01,params({alongStiffness=0,alongDamping=0}))
step(zeroK,1/240);zeroK.tips[1].pz=1.2;step(zeroK,1/240)
check("zero along stiffness is respected, not replaced by a default",close(zeroK.tips[1].span,1.2))

local ballistic=tip(0x02,params({tipMass=1,yawStiffness=10000,pitchStiffness=10000}))
step(ballistic,.01);ballistic.tips[1].px=.1;step(ballistic,.01)
check("rigid flags do not apply flexible restorative forces",close(ballistic.tips[1].px,.1) and close(ballistic.tips[1].vz,-.02))
local badTip=tip(0x01);step(badTip,1/240);badTip.tips[1].px=0/0;step(badTip,1/240)
check("nonfinite axial state resets before any pose can be constructed",badTip.tips[1].linearResets==1 and badTip.tips[1].px==badTip.tips[1].px)
local badBase=tip(0x40);step(badBase,1/240);badBase.tips[1].baseSpringState.px=math.huge;step(badBase,1/240)
check("nonfinite base state resets to its current animation goal",badBase.tips[1].linearResets==1 and close(badBase.localPositions[1][1],0))

local root=tip(0x71);local bp,bv,last=0,0,0;local largest=0
for i=0,720 do
 local x=.03*math.sin(2*math.pi*i/240);local dt=1/240
 bv=bv+(100*(x-bp)-3*bv)*dt;bp=bp+bv*dt
 bp=x+math.max(-.006,math.min(.006,bp-x));bv=(bp-last)/dt;last=bp
 step(root,dt,x)
 local st=root.tips[1].baseSpringState
 assert(close(st.px,bp,1e-10) and close(st.vx,bv,1e-9),"Source base reference mismatch")
 assert(math.abs(root.localPositions[1][1])<=.006+1e-10,"authored base limit exceeded")
 largest=math.max(largest,math.abs(root.localPositions[1][1]))
end
check("zero baseMass still has inertial motion and exact bounds",largest>.0059)
check("base velocity participates in the motion gate",root.maxSpeed2>0)
local chain=tip(0x40,params(),2)
for i=0,240 do step(chain,1/240,.02*math.sin(2*math.pi*i/240)) end
local x=.02*math.sin(2*math.pi)
local expected=x+chain.localPositions[1][1]+chain.localPositions[2][1]
check("parent and child displacements propagate exactly once",close(expected,chain.tips[2].baseSpringState.px))
local rotated=tip(0x40,params({baseMinUp=-.002,baseMaxUp=.002}))
rotated.basePoses[1].bindQ={0,0,math.sin(math.pi/4),math.cos(math.pi/4)}
for i=0,240 do
 step(rotated,1/240,.03*math.sin(2*math.pi*i/240),.02*math.cos(2*math.pi*i/240))
 local st=rotated.tips[1].baseSpringState;local gx=.03*math.sin(2*math.pi*i/240);local gy=.02*math.cos(2*math.pi*i/240)
 local ex,ey,ez=q.rot(0,0,-math.sin(math.pi/4),math.cos(math.pi/4),st.px-gx,st.py-gy,st.pz)
 assert(math.abs(ex)<=.006+1e-9 and math.abs(ey)<=.002+1e-9,"base bounds used wrong bone axes")
end
check("asymmetric base bounds use authored bone axes, not world axes",true)
local friction=tip(0x40,params({baseStiffness=0,baseDamping=0,baseLeftFriction=3,baseMinLeft=0,baseMaxLeft=0,baseMinUp=-10,baseMaxUp=10}))
step(friction,1/240);local fs=friction.tips[1].baseSpringState;fs.px=.1;fs.vy=1
step(friction,1/240)
check("contact friction affects tangent axes on the following step",close(fs.fy,-3))
local noFlex=tip(0x40,params({tipMass=100,baseMass=1,baseMinForward=-1,baseMaxForward=1}))
for i=1,100 do step(noFlex,1/240) end
check("base-only gravity does not accidentally enable tip flex",close(M.local_rotations(noFlex,0,0,0,1)[1][4],0) and noFlex.localPositions[1][3]<0)

-- The accepted constrained/no-base numeric branch must stay bitwise equivalent.
if arg[2] then
 local f=io.open(arg[2],"rb")
 if f then
  f:close();local old=assert(loadfile(arg[2]))();local a=tip(0x31,params({tipMass=10,angleLimit=.3}),3);local b=tip(0x31,params({tipMass=10,angleLimit=.3}),3,old)
  for i=0,720 do
   local x=.02*math.sin(i/37);step(a,1/240,x);old.step_tip(b,1/240,x,0,0,0,0,0,1)
   for k=1,3 do for _,field in ipairs({"px","py","pz","vx","vy","vz"}) do assert(a.tips[k][field]==b.tips[k][field],"constrained baseline changed") end end
  end
  check("constrained/no-base branch is bitwise identical to accepted 1.2.4",true)
 end
end

-- Minimal actual-pose fake engine: setters mutate the state, allowing readback.
local function engine(flags)
 local state={alive=true,anchor={0,0,0},pose={q={0,0,0,1},p={0,0,.1}},setPose=0,setRotation=0,forbidden=0,fail=false}
 local function guard() if not state.alive then state.forbidden=state.forbidden+1;error("dead access") end end
 local S={Application={},Unit={},World={},Vector3={},Quaternion={},Matrix4x4={}}
 S.Application.string_to_id32=function(n)return n=="chest" and 10 or (n=="breast" and 20 or 30) end
 S.Unit.alive=function()return state.alive end
 S.Unit.num_scene_graph_items=function()guard();return 3 end
 S.Unit.name_hash=function()guard();return "linear-fixture-"..flags end
 S.Unit.has_node=function(_,n)guard();return n==10 or n==20 end
 S.Unit.node=function(_,n)guard();return n==10 and 1 or 2 end
 S.Unit.local_pose=function(_,n)guard();return n==1 and {q={0,0,0,1},p={0,0,0}} or state.pose end
 S.Unit.local_rotation=function(_,n)guard();return n==1 and {0,0,0,1} or state.pose.q end
 S.Unit.world_position=function(_,n)guard();if n==1 then return state.anchor end;return {state.anchor[1]+state.pose.p[1],state.anchor[2]+state.pose.p[2],state.anchor[3]+state.pose.p[3]} end
 S.Unit.world_rotation=function(_,n)guard();return n==1 and {0,0,0,1} or state.pose.q end
 S.Unit.set_local_rotation=function(_,n,v)guard();state.setRotation=state.setRotation+1;state.pose.q=v end
 S.Unit.set_local_pose=function(_,n,v)guard();if state.fail then error("injected setter failure") end;state.setPose=state.setPose+1;state.pose=v end
 S.World.update_unit=function()guard() end
 setmetatable(S.Vector3,{__call=function(_,x,y,z)return {x,y,z} end})
 S.Vector3.to_elements=function(v)return unpack(v) end
 S.Quaternion.to_elements=function(v)return unpack(v) end
 S.Quaternion.from_elements=function(x,y,z,w)return {x,y,z,w} end
 S.Quaternion.axis_angle=function(a,t)return {q.axis_angle(a[1],a[2],a[3],t)} end
 S.Matrix4x4.from_quaternion_position=function(r,p)return {q=r,p=p} end
 S.Matrix4x4.is_valid=function()return true end
 S.Matrix4x4.to_elements=function(v)
  local values={};for _,a in ipairs({{1,0,0},{0,1,0},{0,0,1}}) do local x,y,z=q.rot(v.q[1],v.q[2],v.q[3],v.q[4],a[1],a[2],a[3]);values[#values+1]=x;values[#values+1]=y;values[#values+1]=z end
  for i=1,3 do values[#values+1]=v.p[i] end;return unpack(values)
 end
 local rig={version=2,bones={{index=1,parent=0,name="breast",parentName="chest",flags=flags,pos={0,0,.1},params=params({length=.2})}}}
 local session=M.attach(S,{},rig,{rigLengthUnit="meter",gravityScale=1,world={}})
 return S,state,session
end
local S,state,session=engine(0x40)
local moved=0
for i=0,180 do
 state.anchor[1]=.003*math.sin(2*math.pi*i/60);M.update(session,1/60)
 moved=math.max(moved,math.abs(state.pose.p[1]))
end
check("position-only motion is written even with zero rotation",state.setPose>20 and moved>.001)
check("linear writes use matrix path even when rotation fast path is enabled",state.setPose>0 and M._fastWrite==true)
local poses=state.setPose;local item=session.sessions[1]
check("positions are part of dirty pose state",item.lastWritten[1][5]~=nil)
M.release(session)
check("release restores original local position and orientation",close(state.pose.p[1],0) and close(state.pose.p[3],.1) and close(state.pose.q[4],1))
check("release clears base and axial state",not item.tip.tips[1].ready and item.tip.tips[1].baseSpringState==nil and item.tip.localPositions==nil)
state.anchor[1]=0;M.update(session,1/60)
check("same-session reattach does not reuse a displaced spring",close(state.pose.p[1],0))
state.anchor[1]=2;M.update(session,1/60)
check("teleport resync also resets base position",close(state.pose.p[1],0))
state.fail=true;state.anchor[1]=2.003
local prior=state.setPose;M.update(session,1/60);state.fail=false;M.update(session,1/60)
check("failed position write is retried rather than marked clean",state.setPose>prior)
session.debugPoseCheck=true;state.anchor[1]=2.001;M.update(session,1/60)
check("checked matrix writer also emits a finite linear pose",state.pose.p[1]==state.pose.p[1])
local quota=state.setPose;state.anchor[1]=2.002;M.update(session,1/60,0)
check("zero write quota does not write or mark a linear pose clean",state.setPose==quota)
M.update(session,1/60,1);check("deferred linear pose is written when quota resumes",state.setPose>quota)
state.alive=false;local before=state.setPose;M.update(session,1/60);M.release(session)
check("destroyed unit receives no reads or restoration writes",state.forbidden==0 and state.setPose==before)
print("linear DOF checks="..checks)
