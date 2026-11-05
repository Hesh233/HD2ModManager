"""Exercise shipped Lua 5.1 physics against the actual native rig, without the game."""
import json,math,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
work=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(work/'test-runtime'))
sys.path.append(str(root.parents[1]))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.native_skeleton import row_pose
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import _calculate_world_transforms

lua=LuaRuntime(unpack_returned_tuples=True)
compat=lua.execute((root/'HD2PhysBoneCompat/src/physbone_compat.lua').read_text(encoding='utf-8-sig'))
rig=compat.parse_rig((work/'project/models/test01/physbone-rig.bin').read_bytes())
assert not isinstance(rig,tuple),rig
m=json.loads((work/'project/models/test01/source-skeleton.json').read_text(encoding='utf-8'))
unit=UnitData.parse((work/'avatar.toc').read_bytes()); bones=BonesData.parse((work/'bones.toc').read_bytes())
world=_calculate_world_transforms(unit.transforms,unit.parents)
by_hash={h:i for i,h in enumerate(unit.name_hashes)}
nodes={name:by_hash[h]+1 for name,h in zip(bones.names,bones.hashes)}
poses={}
for i,w in enumerate(world): poses[i+1]={'world':w.position,'rotation':w.rotation}
for i,node in enumerate(m['bones'],len(unit.name_hashes)+1):
    nodes[node['name']]=i; pose=row_pose(node['world'])
    poses[i]={'world':pose.position,'rotation':pose.rotation,'local':node['local']['rotation']+node['local']['position']}
lua.globals().compat=compat; lua.globals().rig=rig
lua.globals().nodes=lua.table_from(nodes,recursive=True); lua.globals().poses=lua.table_from(poses,recursive=True)
result=lua.execute('''
local S={ Application={string_to_id32=function(n) return n end},
    Vector3={to_elements=function(v) return unpack(v) end},
    Quaternion={to_elements=function(v) return unpack(v) end},
    Matrix4x4={to_elements=function(v) return unpack(v) end}, Unit={} }
S.Unit.alive=function() return true end
S.Unit.num_scene_graph_items=function() return 196 end
S.Unit.has_node=function(_,n) return nodes[n]~=nil end
S.Unit.node=function(_,n) return nodes[n] end
S.Unit.local_pose=function(_,n) return poses[n]['local'] end
S.Unit.world_position=function(_,n) return poses[n].world end
S.Unit.world_rotation=function(_,n) return poses[n].rotation end
local session=compat.attach(S,{},rig,{fastWrite=false})
local bones, maxAngle, maxLengthError=0,0,0
for _,item in ipairs(session.sessions) do
    assert(item.anchorNode==nodes[item.chain[1].parentName],'mapped to HD2 driver instead of real Source parent')
    assert(item.tip~=nil,'tip solver did not initialize')
    bones=bones+#item.nodes
    local anchor=poses[item.anchorNode].world
    for frame=1,600 do
        local t=frame/60
        local yaw=.25*math.sin(t*2)
        compat.step_tip(item.tip,1/60,anchor[1]+.025*math.sin(t*5),anchor[2],anchor[3],0,0,math.sin(yaw/2),math.cos(yaw/2))
        local rotations=compat.local_rotations(item.tip,0,0,math.sin(yaw/2),math.cos(yaw/2))
        for _,r in ipairs(rotations) do
            for _,v in ipairs(r) do assert(v==v and math.abs(v)<100,'non-finite/excessive rotation') end
            maxAngle=math.max(maxAngle,math.abs(r[4]))
        end
        for _,tip in ipairs(item.tip.tips) do
            assert(tip.px==tip.px and math.abs(tip.px)<100)
            assert(tip.py==tip.py and math.abs(tip.py)<100)
            assert(tip.pz==tip.pz and math.abs(tip.pz)<100)
        end
    end
end
assert(bones==17,'some authored physics bones were skipped')
assert(maxAngle>0.001,'no physical response')
return {chains=#session.sessions,bones=bones,frames=600,maxAngle=maxAngle}
''')
report={'status':'PASS','game_tested':False,'lua_version':'5.1','chains':result['chains'],'bones':result['bones'],
        'simulated_frames_per_chain':result['frames'],'max_simulated_angle_degrees':math.degrees(result['maxAngle']),
        'all_source_parent_anchors_resolved':True,'model_scale':m['modelScale']}
(work/'physics-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
mp=LuaRuntime(); mp.globals().arg=mp.table_from({0:str(root/'HD2PhysBoneCompat/test/mp_harness.lua')})
mp.execute((root/'HD2PhysBoneCompat/test/mp_harness.lua').read_text(encoding='utf-8-sig'))
