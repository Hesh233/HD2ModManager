"""Compare model bind display, reference bind and runtime-mapped attachments."""
import json,math,sys,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'tools'))
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.native_skeleton import bone_name_hash,row_pose
from verify_native_v8_grip import records,read
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
ref=UnitData.parse((W/'unit-anim-reference.toc').read_bytes());rw=_calculate_world_transforms(ref.transforms,ref.parents)
f,rs=records(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
try:raw=read(f,next(r for r in rs if r[0]==int('a152e9ef3754a3d0',16) and r[1]==UNIT_TYPE_ID))
finally:f.close()
u=UnitData.parse(raw);uw=_calculate_world_transforms(u.transforms,u.parents);at=struct.unpack_from('<I',raw,52)[0]+16+64*len(u.transforms)
stored=[row_pose(struct.unpack_from('<16f',raw,at+64*i)) for i in range(len(u.transforms))]
m=json.loads((P/'source-skeleton.json').read_text());bydriver={n['driver']:n for n in m['bones'] if n['driver']}
rows=[]
for name in ('r_hand','l_hand','attach_weapon','attach_hand_r','attach_hand_l','chest'):
    h=bone_name_hash(name);i=u.name_hashes.index(h);ri=ref.name_hashes.index(h)
    row={'name':name,'modelIndex0':i,'referenceIndex0':ri,'modelBindWorld':uw[i].position,'modelStoredWorld':stored[i].position,'referenceWorld':rw[ri].position,'bindToReferenceMetres':math.dist(uw[i].position,rw[ri].position),'storedToReferenceMetres':math.dist(stored[i].position,rw[ri].position)}
    if name in bydriver:
        si=u.name_hashes.index(bydriver[name]['hash']);row.update(sourceName=bydriver[name]['name'],sourceModelIndex0=si,sourceBindWorld=uw[si].position,sourceStoredWorld=stored[si].position)
    rows.append(row)
report={'status':'COMPLETE','gameTested':False,'rows':rows,'scope':'Read-only model/Unit reference bind comparison. Animated standard names are shared engine outputs; Blender rest display does not observe post-render Lua targets.'}
(W/'model-attachment-bind-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
