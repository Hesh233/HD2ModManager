"""Transfer accepted arm rotations to Source axes without changing native controls."""
import copy
import math
import struct
from pathlib import Path

from .archive import TocArchive
from .constants import ANIMATION_TYPE_ID, TOC_MAGIC
from .formats import AnimationData, AnimationEntry, UnitData, BonesData
from .math3d import quat_multiply, quat_inverse,quat_rotate,quat_inverse_rotate,vec_sub,matrix3_columns_to_quaternion
from .processor import _build_tracks, _calculate_world_transforms, WorldTransform


class AnimationReference:
    """Bounded reads from an animation-only reference patch."""
    def __init__(self, path):
        self.path=Path(path)
        self.entries={}
        with self.path.open('rb') as stream:
            header=stream.read(72)
            magic,types,count=struct.unpack_from('<III',header)
            if magic!=TOC_MAGIC:raise ValueError('Invalid arm reference archive')
            stream.seek(72+32*types)
            for _ in range(count):
                r=struct.unpack('<QQQQQQQIIIIII',stream.read(80))
                if r[1]!=ANIMATION_TYPE_ID or r[3] or r[4] or r[8] or r[9] or r[0] in self.entries:
                    raise ValueError('Arm reference must contain unique inline animations only')
                if r[2]+r[7]>self.path.stat().st_size:raise ValueError('Arm reference payload out of bounds')
                self.entries[r[0]]=(r[2],r[7])

    def read(self, clip_id):
        if clip_id not in self.entries:raise ValueError(f'Arm reference lacks animation {clip_id}')
        offset,size=self.entries[clip_id]
        with self.path.open('rb') as stream:
            stream.seek(offset)
            return stream.read(size)


def arm_indices(manifest):
    nodes=manifest['bones']
    roots={i for i,n in enumerate(nodes) if n['driver'] in ('l_clavicle','r_clavicle')}
    selected=[]
    for i,node in enumerate(nodes):
        cursor=i
        while cursor is not None and cursor not in roots:cursor=nodes[cursor]['parent']
        if cursor in roots and node['driver'] is not None:selected.append(i)
    if len(roots)!=2 or not selected:raise ValueError('Arm reference requires both clavicle chains')
    return selected


def _frame_rotation(primary, secondary):
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    def normalized(v):
        size=math.sqrt(dot(v,v))
        if size<1e-9:raise ValueError('Degenerate reference arm frame')
        return [x/size for x in v]
    x=normalized(primary)
    y=normalized(vec_sub(secondary,[a*dot(secondary,x) for a in x]))
    z=[x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
    return matrix3_columns_to_quaternion([x,y,z])


def restore_clavicle_motion(data, original_data, bones, manifest):
    """Keep original shoulder origins while preserving accepted arm directions.

    A clavicle rotation moves the shoulder through its fixed local offset. Restore
    that original rotation and compensate the direct shoulder child, so elbow
    flexion and all rotations below the shoulder stay byte-identical.
    """
    animation=AnimationData.parse(data);original=AnimationData.parse(original_data)
    if len(animation.initial_bone_states)!=len(original.initial_bone_states) or animation.is_additive!=original.is_additive or abs(animation.animation_length-original.animation_length)>1e-6:
        raise ValueError('Clavicle source must match the expanded animation')
    if animation.is_additive:return data
    nodes=manifest['bones'];count=len(bones.names)
    ids={n['driver']:i for i,n in enumerate(nodes) if n['driver']}
    current_tracks=_build_tracks(animation);original_tracks=_build_tracks(original)
    replaced=set();entries=[]
    for side in ('l','r'):
        a,b=ids[side+'_clavicle'],ids[side+'_shoulder']
        if nodes[b]['parent']!=a:raise ValueError('Shoulder must directly follow clavicle')
        clavicle,shoulder=count+a,count+b;replaced.update((clavicle,shoulder))
        times=sorted({0.,animation.animation_length*1000.,
            *range(10,math.ceil(animation.animation_length*1000.),10),
            *(e.time for e in animation.entries if e.is_rotation and e.bone in (clavicle,shoulder)),
            *(e.time for e in original.entries if e.is_rotation and e.bone==clavicle)})
        animation.initial_bone_states[clavicle].rotation=list(original.initial_bone_states[clavicle].rotation)
        entries.extend(copy.deepcopy(e) for e in original.entries if e.is_rotation and e.bone==clavicle)
        previous=None
        for t in times:
            q=quat_multiply(quat_inverse(original_tracks[1][clavicle].evaluate(t)),
                quat_multiply(current_tracks[1][clavicle].evaluate(t),current_tracks[1][shoulder].evaluate(t)))
            if previous is not None and sum(a*b for a,b in zip(previous,q))<0:q=[-v for v in q]
            previous=q
            if t==0:animation.initial_bone_states[shoulder].rotation=q
            else:entries.append(AnimationEntry(0,5,shoulder,t,q))
    animation.entries=[e for e in animation.entries if not(e.is_rotation and e.bone in replaced)]+entries
    animation.entries.sort(key=lambda e:e.time)
    return animation.to_bytes()


def apply_arm_reference(data, reference_data, bones, unit, manifest, preserve_clavicles=False):
    # Local import keeps the main converter and standalone incremental rebuild
    # on exactly the same retarget path without a module import cycle.
    from . import native_skeleton as native
    from .motion_skeleton import source_local
    animation=AnimationData.parse(data);reference=AnimationData.parse(reference_data)
    if (len(reference.initial_bone_states)!=len(bones.names)
            or reference.is_additive!=animation.is_additive
            or abs(reference.animation_length-animation.animation_length)>.0011):
        raise ValueError('Arm reference clip does not match channel count, additive flag or duration')
    if animation.is_additive:
        return data,dict(arm_reference='nonadditive-only; existing additive retained',arm_reference_channels=0)
    selected=arm_indices(manifest);count=len(bones.names);offset=len(unit.transforms)
    if len(animation.initial_bone_states)<count+len(manifest['bones']):raise ValueError('Missing Source arm channels')
    names={name:unit.name_hashes.index(h) for name,h in zip(bones.names,bones.hashes)}
    binds=[native.local_pose(source_local(n,i,manifest)) for i,n in enumerate(manifest['bones'])]
    driver_bind=_calculate_world_transforms(unit.transforms,unit.parents)
    refs,_=native._reference_rotations(manifest['bones'],binds,[native.row_pose(n['world']) for n in manifest['bones']],driver_bind,names,manifest)
    source_by_name={n['driver']:i for i,n in enumerate(manifest['bones']) if n['driver']}
    arm_frames={}
    for side in ('l','r'):
        a,b,c=[names[side+'_'+joint] for joint in ('shoulder','elbow','hand')]
        first=vec_sub(driver_bind[b].position,driver_bind[a].position)
        second=vec_sub(driver_bind[c].position,driver_bind[b].position)
        plane=[first[1]*second[2]-first[2]*second[1],first[2]*second[0]-first[0]*second[2],first[0]*second[1]-first[1]*second[0]]
        for joint,next_joint in (('clavicle','shoulder'),('shoulder','elbow'),('elbow','hand')):
            i=source_by_name[side+'_'+joint];driver=names[side+'_'+joint]
            secondary=plane if joint!='clavicle' and sum(v*v for v in plane)>1e-12 else quat_rotate(driver_bind[driver].rotation,[0,1,0])
            arm_frames[i]=(source_by_name[side+'_'+next_joint],names[side+'_'+next_joint],
                           quat_inverse_rotate(refs[i],secondary))
    # The complete graph is needed only to evaluate each arm's existing chest
    # parent. Source translations, torso/legs, controls and helper tracks stay intact.
    driver_by_hash={h:i for i,h in enumerate(unit.name_hashes)}
    from .motion_skeleton import source_parent,layers
    motion=layers(manifest);motion_by_hash={r['hash']:offset+len(manifest['bones'])+i for i,r in enumerate(motion)}
    parents=unit.parents+[source_parent(i,n,manifest,offset) for i,n in enumerate(manifest['bones'])]
    parents += [motion_by_hash.get(r['parentHash'],driver_by_hash.get(r['parentHash'])) for r in motion]
    channels_by_index={names[name]:ch for ch,name in enumerate(bones.names)}
    channels_by_index.update({offset+i:count+i for i in range(len(manifest['bones'])+len(motion))})
    base_tracks=_build_tracks(animation);ref_tracks=_build_tracks(reference)
    times=sorted({0.,animation.animation_length*1000.,
        *(e.time for e in reference.entries if (e.is_rotation or e.is_position or e.is_scale) and e.time<=animation.animation_length*1000.),
        *(e.time for e in animation.entries if e.is_rotation and e.bone in {count+i for i in selected})})
    parent_ids={parents[offset+i] for i in selected if parents[offset+i]-offset not in selected}
    ref_ids={names[manifest['bones'][i]['driver']] for i in selected}
    additions=[];previous={}
    for t in times:
        local=list(unit.transforms)+copy.deepcopy(binds)+[unit.transforms[r['driverUnitIndex']] for r in motion]
        for index,ch in channels_by_index.items():
            local[index]=WorldTransform(*(track[ch].evaluate(t) for track in base_tracks))
        current=_calculate_world_transforms(local,parents,parent_ids)
        ref_local=list(unit.transforms)
        for ch,index in enumerate(names.values()):ref_local[index]=WorldTransform(*(track[ch].evaluate(t) for track in ref_tracks))
        world=_calculate_world_transforms(ref_local,unit.parents,ref_ids)
        desired={}
        for i in selected:
            driver=names[manifest['bones'][i]['driver']]
            q=quat_multiply(quat_multiply(world[driver].rotation,quat_inverse(driver_bind[driver].rotation)),refs[i])
            if i in arm_frames:
                child,reference_child,secondary=arm_frames[i]
                actual_direction=vec_sub(world[reference_child].position,world[driver].position)
                source_direction=local[offset+child].position
                target_secondary=quat_rotate(q,secondary)
                # Negative/oblique reference bone translations are intentional
                # in some clips. Include them in the bone frame; copying only
                # its quaternion points a positive-length Source limb backwards.
                q=quat_multiply(_frame_rotation(actual_direction,target_secondary),
                                quat_inverse(_frame_rotation(source_direction,secondary)))
            desired[offset+i]=q
            parent=parents[offset+i]
            pq=desired[parent] if parent in desired else current[parent].rotation
            rotation=quat_multiply(quat_inverse(pq),q)
            if i in previous and sum(a*b for a,b in zip(previous[i],rotation))<0:rotation=[-v for v in rotation]
            previous[i]=rotation
            if t==0:animation.initial_bone_states[count+i].rotation=rotation
            else:additions.append(AnimationEntry(0,5,count+i,t,rotation))
    changed={count+i for i in selected}
    animation.entries=[e for e in animation.entries if not (e.is_rotation and e.bone in changed)]+additions
    animation.entries.sort(key=lambda e:e.time)
    result=animation.to_bytes()
    if preserve_clavicles:result=restore_clavicle_motion(result,data,bones,manifest)
    return result,dict(arm_reference='accepted-segment-frame-v15' if preserve_clavicles else 'accepted-segment-frame-v14',
                                    clavicle_motion='original' if preserve_clavicles else 'reference',
                                    arm_reference_channels=len(selected)-2 if preserve_clavicles else len(selected),
                                    arm_reference_samples=len(times),standard_grip_chains=0,max_standard_grip_error=None,
                                    arm_endpoint_constraint='none; accepted arm rotations')
