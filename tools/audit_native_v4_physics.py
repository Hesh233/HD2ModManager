"""Validate real rig bind axes, FK directions and both engine write paths in Lua 5.1."""
import json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-v4-20261103'
BASE=ROOT/'outputs/native-fix-20261103'
sys.path.insert(0,str(BASE/'test-runtime'));sys.path.append(str(ROOT.parents[1]))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.native_skeleton import row_pose
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import _calculate_world_transforms

lua=LuaRuntime(unpack_returned_tuples=True)
compat=lua.execute((ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua').read_text(encoding='utf-8-sig'))
rig=compat.parse_rig((WORK/'project/models/test01/physbone-rig.bin').read_bytes())
assert not isinstance(rig,tuple),rig
m=json.loads((WORK/'project/models/test01/source-skeleton.json').read_text())
unit=UnitData.parse((BASE/'avatar.toc').read_bytes());bones=BonesData.parse((BASE/'bones.toc').read_bytes())
world=_calculate_world_transforms(unit.transforms,unit.parents)
by_hash={h:i for i,h in enumerate(unit.name_hashes)}
nodes={name:by_hash[h]+1 for name,h in zip(bones.names,bones.hashes)}
poses={i+1:{'world':w.position,'rotation':w.rotation} for i,w in enumerate(world)}
for i,node in enumerate(m['bones'],len(unit.name_hashes)+1):
    nodes[node['name']]=i; pose=row_pose(node['world'])
    poses[i]={'world':pose.position,'rotation':pose.rotation,'local':node['local']['rotation']+node['local']['position']}
lua.globals().compat=compat;lua.globals().rig=rig
lua.globals().nodes=lua.table_from(nodes,recursive=True);lua.globals().poses=lua.table_from(poses,recursive=True)
result=lua.execute('''
local Q=compat._q
local function mul(a,b) return {Q.mul(a[1],a[2],a[3],a[4],b[1],b[2],b[3],b[4])} end
local function inv(a) return {-a[1],-a[2],-a[3],a[4]} end
local function rot(a,v) return {Q.rot(a[1],a[2],a[3],a[4],v[1],v[2],v[3])} end
local function distance(a,b) local v=0;for i=1,#a do v=v+(a[i]-b[i])^2 end;return math.sqrt(v) end
local function matrix(q,p)
 local x,y,z,w=unpack(q)
 return {1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,
  2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,
  2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y,p[1],p[2],p[3],q=q}
end
local S={Application={string_to_id32=function(n)return n end},Unit={},
 Vector3=setmetatable({to_elements=function(v)return unpack(v)end},{__call=function(_,...)return {...}end}),
 Quaternion={to_elements=function(v)return unpack(v)end,from_elements=function(...)return {...}end,
  axis_angle=function(a,t)return {Q.axis_angle(a[1],a[2],a[3],t)}end},
 Matrix4x4={to_elements=function(v)return unpack(v,1,12)end,from_quaternion_position=matrix,
  is_valid=function()return true end}}
local written={}
S.Unit.alive=function()return true end
S.Unit.num_scene_graph_items=function()return 196 end
S.Unit.has_node=function(_,n)return nodes[n]~=nil end
S.Unit.node=function(_,n)return nodes[n]end
S.Unit.local_pose=function(_,n)return poses[n]['local']end
S.Unit.world_position=function(_,n)return poses[n].world end
S.Unit.world_rotation=function(_,n)return poses[n].rotation end
S.Unit.set_local_rotation=function(_,n,q) written[n]={q=q,p={unpack(poses[n]['local'],10,12)}}end
S.Unit.set_local_pose=function(_,n,p) written[n]={q=p.q,p={unpack(p,10,12)}}end
local session=compat.attach(S,{},rig,{fastWrite=false})
local boneCount,restError,directionError,writeError=0,0,0,0
for _,item in ipairs(session.sessions)do
 assert(item.anchorNode==nodes[item.chain[1].parentName])
 boneCount=boneCount+#item.nodes
 local anchor=poses[item.anchorNode]
 for k,base in ipairs(item.basePoses)do
  local q={compat.compose_bind_rotation({0,0,1,0},base)}
  local actual=matrix(q,{base.px,base.py,base.pz})
  for j=1,9 do restError=math.max(restError,math.abs(actual[j]-base.r[j]))end
 end
 for frame=1,600 do
  local t=frame/60; local aq=mul(anchor.rotation,{Q.axis_angle(0,0,1,.25*math.sin(t*2))})
  compat.step_tip(item.tip,1/60,anchor.world[1]+.025*math.sin(t*5),anchor.world[2],anchor.world[3],unpack(aq))
  local deltas=compat.local_rotations(item.tip,unpack(aq));local cumulative={0,0,0,1};local bind={0,0,0,1}
  for k,base in ipairs(item.basePoses)do
   bind=mul(bind,base.bindQ)
   cumulative=mul(cumulative,{compat.compose_bind_rotation(deltas[k],base)})
   local boneDirection=rot(inv(bind),item.tip.segDirLocal[k])
   local actual=rot(mul(aq,cumulative),boneDirection)
   directionError=math.max(directionError,distance(actual,item.tip.dirs[k] or rot(aq,item.tip.segDirLocal[k])))
  end
 end
end
assert(boneCount==17 and #session.sessions==12)
print('measured bind projection / FK direction errors',restError,directionError)
assert(restError<2e-5,restError)
-- swing_axis intentionally suppresses angles below acos(0.9999995) (~0.001 rad).
assert(directionError<0.0011,directionError)
-- Drive the public update API. Read back both the fast quaternion write and the
-- matrix/debug write, then compare FK directions with the solver's world targets.
for _,mode in ipairs({'fast','matrix','checked'})do
 compat._fastWrite=mode=='fast';session.debugPoseCheck=mode=='checked'
 for _,item in ipairs(session.sessions)do item.lastWritten=nil;item.staticFrames=999 end
 written={};local count=compat.update(session,1/60)
 assert(count==17,tostring(mode)..':'..tostring(count)..':'..tostring(session.firstFailReason))
 for _,item in ipairs(session.sessions)do
  local cumulative={0,0,0,1};local bind={0,0,0,1};local aq=poses[item.anchorNode].rotation
  for k,base in ipairs(item.basePoses)do
   local value=written[item.nodes[k]];assert(value and value.q)
   assert(distance(value.p,{base.px,base.py,base.pz})<1e-10,'translation changed')
   bind=mul(bind,base.bindQ);cumulative=mul(cumulative,value.q)
   local actual=rot(mul(aq,cumulative),rot(inv(bind),item.tip.segDirLocal[k]))
   writeError=math.max(writeError,distance(actual,item.tip.dirs[k]))
  end
 end
end
assert(writeError<0.0011,writeError)
-- Identity-axis rigs retain the same output, and non-X half turns retain sign.
for _,q in ipairs({{0,0,0,1},{0,math.sqrt(.5),-math.sqrt(.5),0},{.5,.5,.5,.5}})do
 local base={bindQ=q,bindParentQ={0,0,0,1}}
 local out={compat.compose_bind_rotation({0,0,1,0},base)}
 assert(distance(out,q)<1e-10)
end
return {bones=boneCount,chains=#session.sessions,restError=restError,directionError=directionError,writeError=writeError}
''')
report={'status':'PASS','luaVersion':'5.1','gameTested':False,'framesPerChain':600,**dict(result.items())}
(WORK/'physics-audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
mp=LuaRuntime();mp.globals().arg=mp.table_from({0:str(ROOT/'HD2PhysBoneCompat/test/mp_harness.lua')})
mp.execute((ROOT/'HD2PhysBoneCompat/test/mp_harness.lua').read_text(encoding='utf-8-sig'))
