"""Serialized rig/name checks and an actual-layout Lua rejection reproducer."""
import csv, json, math, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'outputs/native-fix-20261103/test-runtime'))
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import animation_nodes, bone_name_hash
from anim_batch_mod.processor import _calculate_world_transforms
from lupa.lua51 import LuaRuntime
W=ROOT/'outputs/native-v6-analysis-20261104';P=ROOT/'outputs/native-v6-20261104/project'
m=json.loads((P/'source-skeleton.json').read_text()); profile=json.loads((P/'attachment-profile.json').read_text())
def read_type(path,kind):
    with path.open('rb') as f:
        h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+nt*32)
        rows=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
        r=next(r for r in rows if r[1]==kind);f.seek(r[2]);return f.read(r[7])
model=UnitData.parse(read_type(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0',UNIT_TYPE_ID))
avatar=UnitData.parse(read_type(P/'animations/runtime/9ba626afa44a3aa3.patch_2',UNIT_TYPE_ID))
bones=BonesData.parse(read_type(P/'animations/runtime/9ba626afa44a3aa3.patch_2',BONE_TYPE_ID))
names=dict(zip(bones.hashes,bones.names));names.update({b['hash']:b['name'] for b in m['bones']})
with (W/'bone-map.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f);writer.writerow(['SourceIndex','VPKName','NormalizedName','HashDecimal','ModelUnitIndex0','AvatarUnitIndex0','ParentSourceIndex','Driver'])
    for b in m['bones']:
        h=b['hash'];writer.writerow([b['sourceIndex'],b['sourceName'],b['name'],h,model.name_hashes.index(h),avatar.name_hashes.index(h) if h in avatar.name_hashes else '',b['parent'],b['driver']])
diffs=[]
for b in m['bones']:
    i=model.name_hashes.index(b['hash']);expected=0 if b['parent'] is None else model.name_hashes.index(m['bones'][b['parent']]['hash'])
    if model.parents[i]!=expected:diffs.append(b['name'])
    assert b['hash']==bone_name_hash(b['name'])
assert not diffs
# This fixture uses serialized model indices and hashes, not the avatar's layout
# recycled as a pretend model. Poses emulate hash-bound animation attachment.
world=_calculate_world_transforms(avatar.transforms,avatar.parents)
poses=[{'p':list(t.position),'q':list(t.rotation)} for t in world]
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().profile=lua.table_from(profile,recursive=True)
lua.globals().bone_hash=bone_name_hash
lua.globals().avatar_hashes=lua.table_from(avatar.name_hashes)
lua.globals().model_hashes=lua.table_from(model.name_hashes)
lua.globals().avatar_poses=lua.table_from(poses,recursive=True)
lua.globals().adapter=lua.execute((ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text())
result=lua.execute('''
local A={alive=true,avatar=true,names={},poses=avatar_poses,count=#avatar_hashes}
local B={alive=true,names={},poses={},count=#model_hashes}
for i,h in ipairs(avatar_hashes)do A.names[h]=i end
for i,h in ipairs(model_hashes)do B.names[h]=i;B.poses[i]=A.poses[A.names[h]] or {p={0,0,0},q={0,0,0,1}} end
local now=0
local S={Application={},World={},Unit={},Vector3={},Quaternion={},IdString64={}}
S.Application.string_to_id32=function(n)return bone_hash(n)end
S.Application.worlds=function()return {1}end
S.Application.time_since_launch=function()now=now+1;return now end
S.World.units=function()return {A,B}end
S.World.units_by_resource=function()return {A}end
S.Unit.alive=function(u)return u.alive end
S.Unit.has_animation_state_machine=function(u)return u.avatar==true end
S.Unit.num_scene_graph_items=function(u)return u.count end
S.Unit.has_node=function(u,id)return u.names[id]~=nil end
S.Unit.node=function(u,id)return u.names[id]end
S.Unit.resource_name=function()return profile.targets.body[1]end
S.IdString64.to_hex=function(x)return x end
S.Unit.world_position=function(u,i)return u.poses[i].p end
S.Unit.world_rotation=function(u,i)return u.poses[i].q end
S.Vector3.to_elements=function(v)return unpack(v)end
S.Quaternion.to_elements=function(v)return unpack(v)end
local function run(count)
 profile.expectedModelNodes=count
 local rt=adapter.new(S,profile,function()end,{settleFrames=2,scanFrames=1})
 -- Only intercept pose writes; run production discovery and owner selection.
 local selected=0;rt.write=function()selected=selected+1 end
 for frame=1,4 do rt:tick(frame)end
 return {armor=#rt.armor,active=rt.stats.active,batches=selected}
end
return {configuredCount=196,actualCount=B.count,before=run(196),withActualCount=run(B.count)}
''')
def plain(v): return {k:plain(x) for k,x in v.items()} if hasattr(v,'items') else v
result=plain(result); assert result['before']['armor']==0 and result['withActualCount']['active']==1
report={'modelNodes':len(model.transforms),'avatarNodes':len(avatar.transforms),'sourceBones':len(m['bones']),'parentMismatches':diffs,'luaReproduction':result,'scope':'serialized indices/hashes, simulated hash-bound poses; no live pose write or deployment','namesInCompanion':sum(b['hash'] in bones.hashes for b in m['bones']),'manifestNamesVerified':True}
(W/'rig-and-lua.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
