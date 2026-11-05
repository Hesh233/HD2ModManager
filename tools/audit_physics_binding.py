"""Check runtime conflict diagnostics and name-link ownership on the actual rig."""
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'outputs/native-fix-20261103'
WORK=ROOT/'outputs/native-regression-20261103'
sys.path.insert(0,str(OLD/'test-runtime'))
sys.path.append(str(ROOT.parents[1]))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.native_skeleton import load_manifest, animation_nodes, bone_name_hash
from anim_batch_mod.formats import UnitData
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID

lua=LuaRuntime(unpack_returned_tuples=True)
compat=lua.execute((ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua').read_text(encoding='utf-8-sig'))
rig=compat.parse_rig((OLD/'project/models/test01/physbone-rig.bin').read_bytes())
manifest=load_manifest(OLD/'project/models/test01/source-skeleton.json')
raw=WORK/'project/animations/runtime/9ba626afa44a3aa3.patch_2'
ar=TocArchive.parse_parts(raw.read_bytes(),b'',b'')
avatar=UnitData.parse(ar.entries_of_type(UNIT_TYPE_ID)[0].toc_data)
old_names={n['name']:True for n in manifest['bones']}
new_names={n['name']:True for n in animation_nodes(manifest)}
lua.globals().compat=compat; lua.globals().rig=rig
lua.globals().oldAvatar=lua.table_from(old_names)
lua.globals().newAvatar=lua.table_from(new_names)
lua.execute('''
local S={Application={string_to_id32=function(n) return n end},
         Unit={has_node=function(unit,n) return unit[n]==true end}}
assert(compat.shared_physics_nodes(S,oldAvatar,rig)==17)
assert(compat.shared_physics_nodes(S,newAvatar,rig)==0)
-- Model the engine's same-name linking: old shared nodes reset each simulated
-- physics write; private avatar names leave the armor's local rotation alone.
for _,b in ipairs(rig.bones) do
    local oldRotation,newRotation=.2,.2
    if S.Unit.has_node(oldAvatar,b.name) then oldRotation=0 end
    if S.Unit.has_node(newAvatar,b.name) then newRotation=0 end
    assert(oldRotation==0 and newRotation==.2)
end
''')
for n in manifest['bones']:
    assert bone_name_hash(n['name'])==n['hash']
    assert (n['hash'] in avatar.name_hashes) == (not n['physics'])
report=dict(status='PASS',old_shared_physics_bones=17,new_shared_physics_bones=0,
            unlinked_subtree_nodes=sum(n['physics'] for n in manifest['bones']),
            preserved_driven_source_nodes=sum(n['driver'] is not None for n in manifest['bones']),
            lua_version='5.1',game_tested=False,
            limitation='Name-link simulation and actual patch structure; engine result needs in-game verification')
(WORK/'reports/physics-binding.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
