"""Synthetic guard test for the existing Source-order single-skeleton solver.
Uses the unchanged production literal; NOT actual bind-selection or FPS evidence.
"""
from pathlib import Path
import argparse, importlib, json
ROOT=Path(__file__).resolve().parents[2]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();OUT=args.output.resolve();assert OUT.is_relative_to(ROOT)
code=(OUT/'B-extracted/physbone_compat.lua').read_text('utf8')
# Expose the literal ONLY in this in-memory test chunk. Never write it into a ZIP.
assert code.endswith('return M\n');instrumented=code[:-len('return M\n')]+'M._sourceGuardFixture=T1201\nreturn M\n'
fixture=r'''
local function copy(x)if type(x)~='table'then return x end;local t={};for k,v in pairs(x)do t[k]=copy(v)end;return t end
local _,original=next(C._sourceGuardFixture.units);local profile=copy(original)
local driverNodes,physicalNodes={},{}
for _,r in ipairs(profile.records)do
 if r.kind==2 then r.rules='POISON: remote VRD MUST NOT evaluate';if not r.excludedWrist then driverNodes[r.node]=true end
 else physicalNodes[r.node]=true end
end
local reads,writes,flush=0,{},0
local S={Unit={},World={},Quaternion={},Matrix4x4={},Vector3={}}
S.Unit.alive=function()return true end;S.Unit.num_scene_graph_items=function()return C._sourceGuardFixture.nodeCount end
S.Unit.world_position=function(u,n)reads=reads+1;return{0,0,0}end
S.Unit.world_rotation=function(u,n)reads=reads+1;return{0,0,0,1}end
S.Unit.set_local_pose=function(u,n,p)writes[n]=(writes[n]or 0)+1 end
S.World.update_unit=function()flush=flush+1 end
S.Vector3.to_elements=function(v)return unpack(v)end;setmetatable(S.Vector3,{__call=function(_,x,y,z)return{x,y,z}end})
S.Quaternion.to_elements=function(q)return unpack(q)end;S.Quaternion.from_elements=function(x,y,z,w)return{x,y,z,w}end
S.Quaternion.axis_angle=function(a,t)local s=math.sin(t/2);return{a[1]*s,a[2]*s,a[3]*s,math.cos(t/2)}end
S.Matrix4x4.from_quaternion_position=function(q,p)return{q=q,p=p}end
local st={time=0,frames=0,records={},saved={},last={},profile=profile,resource=profile.resource}
for _,r in ipairs(profile.records)do if not r.excludedWrist then
 st.records[r.source]={preQ={0,0,0,1},preP={0,0,0}}
 st.saved[#st.saved+1]={node=r.node,pose={r={1,0,0,0,1,0,0,0,1},px=0,py=0,pz=0}}
end end
local session={S=S,world={},unit={},sessions={},drivers={},singleMainline=true,test1201Source=st,logger=function()end}
-- This is a synthetic dispatcher guard check, not a substitute for real preflight.
C.session_health=function()return'ok'end
C.single_remote_policy_transition(session,variant=='A',true);session.evaluateDrivers=false
for f=1,30 do C.begin_frame(f);C.update(session,1/120)end
local count=0;for n in pairs(writes)do assert(not driverNodes[n],'Source route wrote a remote driver');count=count+1 end
assert((session.driverWrites or 0)==0,'Source route counted remote VRD writes')
if variant=='A'then assert(reads==0 and count==0 and flush==0 and (session.tipApplied or 0)==0,'A Source route was evaluated')
else assert(session.tipApplied==30 and count==49 and reads>0,'B must retain all 49 Source spring nodes')end
local restored=C.release(session)
if variant=='A'then assert(restored==0,'A repeats a pose hand-back')else assert(restored==49,'B restores spring nodes only, not nine VRD helpers')end
for n in pairs(writes)do assert(not driverNodes[n],'release wrote an excluded Source driver')end
return{variant=variant,syntheticReads=reads,physicalNodesWritten=count,restored=restored,driverWrites=session.driverWrites or 0}
'''
rows=[]
for vm in ['lua51','luajit21']:
 L=importlib.import_module('lupa.'+vm).LuaRuntime
 for variant in ['A','B']:
  lua=L(unpack_returned_tuples=True);C=lua.execute(instrumented);lua.globals().C=C;lua.globals().variant=variant
  got=lua.execute(fixture);row=dict(got.items());row['vm']=vm;rows.append(row)
report={'status':'PASS_SYNTHETIC_SOURCE_INLINE_VRD_GATE_ONLY','poisonedRemoteVrdRulesNeverEvaluated':True,'notRealBindSelectionTest':True,'notGameFps':True,'productionLiteralOnlyExposedInMemory':True,'cases':rows}
(OUT/'source-route-gate-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(report,indent=2))
