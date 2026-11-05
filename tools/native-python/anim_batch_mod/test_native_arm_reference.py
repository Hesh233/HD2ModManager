import copy
import math
import unittest
from anim_batch_mod.native_arm_reference import apply_arm_reference,arm_indices
from anim_batch_mod.formats import AnimationData,AnimationBoneState,AnimationEntry,UnitData,BonesData,LocalTransform
from anim_batch_mod.processor import _calculate_world_transforms,_build_tracks,WorldTransform


def fixture():
    names=['root']+[s+'_'+j for s in ('l','r') for j in ('clavicle','shoulder','elbow','hand')]
    parents=[None,0,1,2,3,0,5,6,7]
    positions=[[0,0,0],[0,1,1],[.1,0,0],[.3,0,0],[.25,0,0],[0,-1,1],[.1,0,0],[.3,0,0],[.25,0,0]]
    unit=UnitData(1,2,[LocalTransform(p,[0,0,0,1],[1,1,1]) for p in positions],parents,list(range(9)))
    bones=BonesData(names,list(range(9)));worlds=_calculate_world_transforms(unit.transforms,parents)
    nodes=[]
    for i in range(1,9):
        p=worlds[i].position
        nodes.append(dict(sourceIndex=i-1,name='source_'+names[i],hash=100+i,driver=names[i],
            parent=None if parents[i]==0 else parents[i]-1,
            local=dict(position=positions[i],rotation=[1,0,0,0,1,0,0,0,1],scale=[1,1,1]),
            world=[1,0,0,0,0,1,0,0,0,0,1,0,*p,1]))
    manifest=dict(version=1,bones=nodes,driverHashes=list(range(9)),driverWorld=[])
    reference=AnimationData(animation_length=1,initial_bone_states=[AnimationBoneState(t.position,t.rotation,t.scale,False,False,False) for t in unit.transforms])
    reference.entries=[AnimationEntry(0,5,2,500,[math.sin(.4),0,0,math.cos(.4)])]
    baseline=copy.deepcopy(reference)
    baseline.initial_bone_states += [AnimationBoneState(positions[i],[0,math.sin(.6),0,math.cos(.6)],[1,1,1],False,False,False) for i in range(1,9)]
    baseline.entries += [AnimationEntry(0,4,11,300,[.1,.02,0]),AnimationEntry(0,5,0,300,[0,0,math.sin(.1),math.cos(.1)])]
    baseline.entries.sort(key=lambda e:e.time)
    return baseline.to_bytes(),reference.to_bytes(),bones,unit,manifest


class ArmReferenceTests(unittest.TestCase):
    def test_clavicle_restore_preserves_shoulder_origins_and_accepted_arm_directions(self):
        raw,ref,b,u,m=fixture()
        old,_=apply_arm_reference(raw,ref,b,u,m)
        result,metrics=apply_arm_reference(raw,ref,b,u,m,preserve_clavicles=True)
        self.assertEqual(metrics['clavicle_motion'],'original')
        parents=u.parents+[0 if n['parent'] is None else 9+n['parent'] for n in m['bones']]
        def world(data,t):
            tracks=_build_tracks(AnimationData.parse(data))
            return _calculate_world_transforms([WorldTransform(*(tr[i].evaluate(t) for tr in tracks)) for i in range(17)],parents)
        for t in (0,300,500,1000):
            before,accepted,after=[world(d,t) for d in (raw,old,result)]
            for shoulder,elbow,hand in ((10,11,12),(14,15,16)):
                self.assertLess(math.dist(before[shoulder].position,after[shoulder].position),1e-6)
                for index in (shoulder,elbow,hand):
                    self.assertGreater(abs(sum(a*b for a,b in zip(accepted[index].rotation,after[index].rotation))),1-1e-6)
        a,z=AnimationData.parse(old),AnimationData.parse(result)
        changed={9,10,13,14}
        for i,(x,y) in enumerate(zip(a.initial_bone_states,z.initial_bone_states)):
            self.assertEqual(x.position,y.position);self.assertEqual(x.scale,y.scale)
            if i not in changed:self.assertEqual(x.rotation,y.rotation)
        keep=lambda a:[(e.type,e.subtype,e.bone,e.time,e.data2) for e in a.entries if not(e.is_rotation and e.bone in changed)]
        self.assertEqual(keep(a),keep(z))

    def test_only_source_arm_rotations_change(self):
        raw,ref,b,u,m=fixture()
        result,metrics=apply_arm_reference(raw,ref,b,u,m)
        a,z=AnimationData.parse(raw),AnimationData.parse(result)
        changed={len(b.names)+i for i in arm_indices(m)}
        for i,(old,new) in enumerate(zip(a.initial_bone_states,z.initial_bone_states)):
            self.assertEqual(old.position,new.position)
            self.assertEqual(old.scale,new.scale)
            if i not in changed:self.assertEqual(old.rotation,new.rotation)
        def keep(animation):return [(e.type,e.subtype,e.bone,e.time,e.data2) for e in animation.entries if not(e.is_rotation and e.bone in changed)]
        self.assertEqual(keep(a),keep(z))
        self.assertEqual(metrics['arm_reference_channels'],8)
        # The accepted upper-arm key is present even when baseline keys were constant.
        key=next(e for e in z.entries if e.is_rotation and e.bone==10 and e.time==500)
        tracks=_build_tracks(z)
        local=[WorldTransform(*(tr[i].evaluate(500) for tr in tracks)) for i in range(17)]
        parents=u.parents+[0 if n['parent'] is None else 9+n['parent'] for n in m['bones']]
        world=_calculate_world_transforms(local,parents)
        direction=[x-y for x,y in zip(world[11].position,world[10].position)]
        self.assertGreater(direction[0],0)
        self.assertLess(abs(direction[1])+abs(direction[2]),1e-6)

    def test_negative_reference_segments_keep_positive_source_lengths_and_follow_direction(self):
        raw,ref,b,u,m=fixture();r=AnimationData.parse(ref)
        r.initial_bone_states[3].position=[-.3,0,0]
        r.initial_bone_states[4].position=[-.25,0,0]
        result,_=apply_arm_reference(raw,r.to_bytes(),b,u,m)
        z=AnimationData.parse(result);tracks=_build_tracks(z)
        local=[WorldTransform(*(tr[i].evaluate(500) for tr in tracks)) for i in range(17)]
        parents=u.parents+[0 if n['parent'] is None else 9+n['parent'] for n in m['bones']]
        world=_calculate_world_transforms(local,parents)
        for a,c in ((10,11),(11,12)):
            direction=[x-y for x,y in zip(world[c].position,world[a].position)]
            self.assertLess(direction[0],0)
            self.assertLess(abs(direction[1])+abs(direction[2]),1e-6)
            self.assertGreater(local[c].position[0],0)

    def test_additive_is_byte_identical(self):
        raw,ref,b,u,m=fixture()
        a,r=AnimationData.parse(raw),AnimationData.parse(ref)
        for clip in (a,r):
            clip.is_additive=True
            for state in clip.initial_bone_states:state.scale=[0,0,0]
        raw=a.to_bytes()
        self.assertEqual(apply_arm_reference(raw,r.to_bytes(),b,u,m)[0],raw)

    def test_incompatible_reference_rejected_but_old_millisecond_rounding_allowed(self):
        raw,ref,b,u,m=fixture();r=AnimationData.parse(ref)
        r.animation_length=.999
        apply_arm_reference(raw,r.to_bytes(),b,u,m)
        r.animation_length=.8
        with self.assertRaises(ValueError):apply_arm_reference(raw,r.to_bytes(),b,u,m)


if __name__=='__main__':unittest.main()
