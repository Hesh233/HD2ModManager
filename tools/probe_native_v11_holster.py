import sys,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import row_pose,bone_name_hash
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_rotate,quat_inverse,quat_multiply,vec_sub
W=ROOT/'outputs/native-v11-20261104'
m=json.loads((W/'project/source-skeleton.json').read_text())
p=json.loads((W/'project/attachment-profile.json').read_text())
orig=UnitData.parse((ROOT/'outputs/native-fix-20261103/avatar.toc').read_bytes())
ref=UnitData.parse((ROOT/'outputs/native-v10-20261104/unit-anim-reference.toc').read_bytes())
ow=_calculate_world_transforms(orig.transforms,orig.parents);rw=_calculate_world_transforms(ref.transforms,ref.parents)
sw=[row_pose(n['world']) for n in m['bones']]
def pose(v):return dict(p=v.position,q=v.rotation)
for name in ('sling','pistol','backpack','support','support_mg'):
    i=orig.name_hashes.index(bone_name_hash(name));j=ref.name_hashes.index(bone_name_hash(name))
    row=next((r for r in p['vpk'] if r['index']==i),None)
    print(name,'index',i,'parent',orig.parents[i],'original',pose(ow[i]),'reference',pose(rw[j]))
    if row:
        a=row['driverAnchorIndex'];si=row['sourceAnchorIndex'];q=quat_inverse(sw[si].rotation)
        print('  anchor',row['driverAnchorName'],'source',pose(sw[si]),'ref',pose(rw[ref.name_hashes.index(orig.name_hashes[a])]))
        print('  ref_to_source_bind',quat_rotate(q,vec_sub(rw[j].position,sw[si].position)),quat_multiply(q,rw[j].rotation))
