"""Offline assertions on the actual Source rig and current-game bind/masks."""
import copy,json,math,struct,sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[3]))
from anim_batch_mod.native_skeleton import append_animation,append_state_machine_masks,local_pose,row_pose
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.processor import _calculate_world_transforms

work=Path(sys.argv[1]); manifest=json.loads((work/'project/models/test01/source-skeleton.json').read_text(encoding='utf-8-sig'))
unit=UnitData.parse((work/'avatar.toc').read_bytes()); bones=BonesData.parse((work/'bones.toc').read_bytes())
transforms={h:i for i,h in enumerate(unit.name_hashes)}
states=[AnimationBoneState(t.position,t.rotation,t.scale,False,False,False) for t in [unit.transforms[transforms[h]] for h in bones.hashes]]
animation=AnimationData(initial_bone_states=copy.deepcopy(states),animation_length=.1)
append_animation(animation,bones,unit,manifest)
src=animation.initial_bone_states[len(states):]
world=_calculate_world_transforms([unit.transforms[0],*src],[None,*[0 if n['parent'] is None else 1+n['parent'] for n in manifest['bones']]])
original=[row_pose(n['world']) for n in manifest['bones']]
drivers=_calculate_world_transforms(unit.transforms,unit.parents)
by_name={n:i+1 for n,i in ((n['driver'],i) for i,n in enumerate(manifest['bones'])) if n is not None}
driver_names=dict(zip(bones.names,[transforms[h] for h in bones.hashes]))
angles=[]
def angle(a,b):
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))))))
for a,b in [('hips','spine1'),('spine1','spine2'),('spine2','chest'),('chest','neck'),('neck','head'),
            *[(s+x,s+y) for s in ('l_','r_') for x,y in [('clavicle','shoulder'),('shoulder','elbow'),('elbow','hand'),('thigh','knee'),('knee','foot')]]]:
    if a not in by_name or b not in by_name: continue
    ia,ib=by_name[a],by_name[b]; da,db=driver_names[a],driver_names[b]
    target=[drivers[db].position[j]-drivers[da].position[j] for j in range(3)]
    before=[original[ib-1].position[j]-original[ia-1].position[j] for j in range(3)]
    after=[world[ib].position[j]-world[ia].position[j] for j in range(3)]
    if min(math.sqrt(sum(v*v for v in before)),math.sqrt(sum(v*v for v in target)))<1e-4: continue
    angles.append(dict(segment=a+' -> '+b,before_degrees=angle(before,target),after_degrees=angle(after,target)))
    assert angles[-1]['after_degrees']<.05,angles[-1]
neutral=AnimationData(initial_bone_states=[AnimationBoneState([0,0,0],[0,0,0,1],[0,0,0],False,False,False) for _ in states],animation_length=.1,is_additive=True)
append_animation(neutral,bones,unit,manifest)
max_error=max(1-abs(s.rotation[3]) for s in neutral.initial_bone_states[len(states):])
assert max_error<1e-10,max_error
mask=(work/'state-machine.toc').read_bytes(); patched,count=append_state_machine_masks(mask,bones,manifest)
offset=struct.unpack_from('<I',patched,32)[0]
for i in range(count):
    start=offset+struct.unpack_from('<I',patched,offset+4+4*i)[0]
    assert struct.unpack_from('<I',patched,start)[0]==len(states)+len(src)
report=dict(status='PASS',game_tested=False,model_scale=manifest['modelScale'],source_bones=len(src),blend_masks=count,
            blend_channels=len(states)+len(src),neutral_additive_rotation_error=max_error,reference_segments=angles)
(work/'motion-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
