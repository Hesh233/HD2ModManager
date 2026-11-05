import copy
import math
import struct
import unittest
from types import SimpleNamespace

from anim_batch_mod.formats import AnimationData, AnimationBoneState, AnimationEntry, BonesData, UnitData, LocalTransform
from anim_batch_mod.math3d import quat_multiply, quat_rotate
from anim_batch_mod.native_skeleton import append_animation, append_state_machine_masks, validate_manifest, resolve_inline, _swing_between, convert_clip, bone_name_hash
from anim_batch_mod.processor import _build_tracks, _calculate_world_transforms, _apply_two_bone_ik, ModConfig


def row(x=0, y=0, z=0):
    return [1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,x,y,z,1.]


def fixture(additive=False):
    unit = UnitData(1, 2, [LocalTransform([0,0,0], [0,0,0,1], [1,1,1]),
        LocalTransform([0,0,1], [0,0,0,1], [1,1,1]),
        LocalTransform([1,0,0], [0,0,0,1], [1,1,1])], [None,0,1], [10,11,12])
    # Channel order deliberately differs from TransformInfo order.
    bones = BonesData(['arm', 'root', 'hips'], [12,10,11])
    nodes = []
    for i, (name,parent,driver,p,w) in enumerate([
        ('source-pelvis',None,'hips',[0,0,2],row(0,0,2)),
        ('source-arm',0,'arm',[2,0,0],row(2,0,2)),
        ('source-helper',1,None,[1,0,0],row(3,0,2))]):
        nodes.append(dict(sourceIndex=i, name=name, hash=100+i, parent=parent, driver=driver,
            world=w, local=dict(rotation=[1,0,0,0,1,0,0,0,1], position=p, scale=[1,1,1])))
    manifest = dict(version=1, driverHashes=unit.name_hashes,
                    driverWorld=[dict(values=row()),dict(values=row(0,0,1)),dict(values=row(1,0,1))], bones=nodes)
    states = [AnimationBoneState(list(unit.transforms[i].position), [0,0,0,1], [1,1,1], False,False,False)
              for i in [2,0,1]]
    if additive:
        states = [AnimationBoneState([0,0,0],[0,0,0,1],[0,0,0],False,False,False) for _ in states]
    animation = AnimationData(initial_bone_states=states, animation_length=1., is_additive=additive)
    return unit, bones, manifest, animation


class NativeSkeletonTests(unittest.TestCase):
    def test_motion_layer_translation_uses_configured_bind_without_reapplying_static_offset(self):
        unit,bones,manifest,animation=fixture()
        layer_name='test_motion_root'
        manifest['motionLayers']=[dict(name=layer_name,hash=bone_name_hash(layer_name),
            parentHash=10,driverHash=10,driverUnitIndex=0,driver='root')]
        manifest['motionParentOverrides']={'1':0}
        bind=copy.deepcopy(manifest['bones'][1]['local']);bind['position']=[2.,0.,2.]
        manifest['motionLocalOverrides']={'1':bind}
        options={'align_standard_grips':False,'ik_correction':False,'fps':1}
        for multiplier in (1.,1.3):
            config=ModConfig(offsets={'arm':[.3,0.,.15]},distance_multipliers={'arm':multiplier},required_bone='arm')
            for movement in (0.,.1):
                clip=copy.deepcopy(animation);clip.initial_bone_states[0].position[0]+=movement
                converted=AnimationData.parse(convert_clip(clip.to_bytes(),bones,unit,manifest,config,options)[0])
                actual=converted.initial_bone_states[len(bones.names)+1].position
                expected=[2.+movement*multiplier,0.,2.]
                for a,e in zip(actual,expected):self.assertAlmostEqual(a,e,places=6)
            additive=fixture(True)[3]
            converted=AnimationData.parse(convert_clip(additive.to_bytes(),bones,unit,manifest,config,options)[0])
            self.assertLess(max(abs(v) for v in converted.initial_bone_states[len(bones.names)+1].position),1e-6)

    def test_shorter_source_legs_keep_original_planted_and_moving_foot_paths(self):
        names=['root','hips','l_thigh','l_knee','l_foot','r_thigh','r_knee','r_foot']
        positions=[[0,0,0],[0,0,1.5],[.1,0,0],[0,.25,-.7],[0,-.25,-.7],[-.1,0,0],[0,.25,-.7],[0,-.25,-.7]]
        parents=[None,0,1,2,3,1,5,6]
        unit=UnitData(1,2,[LocalTransform(p,[0,0,0,1],[1,1,1]) for p in positions],parents,list(range(10,18)))
        bones=BonesData(names,unit.name_hashes);world=_calculate_world_transforms(unit.transforms,parents)
        source=copy.deepcopy(unit.transforms)
        for i in (1,3,4,6,7):source[i].position=[v*.85 for v in source[i].position]
        sw=_calculate_world_transforms(source,parents)
        nodes=[dict(sourceIndex=i,name='src-'+name,hash=100+i,parent=parents[i],driver=name,
            world=row(*sw[i].position),local=dict(rotation=[1,0,0,0,1,0,0,0,1],position=source[i].position,scale=[1,1,1]))
            for i,name in enumerate(names)]
        manifest=dict(version=1,driverHashes=unit.name_hashes,driverWorld=[dict(values=row(*w.position)) for w in world],bones=nodes)
        original=AnimationData(initial_bone_states=[AnimationBoneState(t.position,t.rotation,t.scale,False,False,False)
            for t in unit.transforms],animation_length=1.)
        for frame in range(1,11):
            local=copy.deepcopy(unit.transforms);local[1].position[2]+=.025*math.sin(frame*math.pi/5)
            for a,b,c in ((2,3,4),(5,6,7)):
                target=list(world[c].position)
                if c==7:target[1]+=.1*frame/10
                _apply_two_bone_ik(local,parents,a,b,c,target,[0,0,0,1])
            for i,t in enumerate(local):
                original.entries.extend([AnimationEntry(0,4,i,100.*frame,t.position),AnimationEntry(0,5,i,100.*frame,t.rotation)])
        errors=[]
        for enabled in (False,True):
            clip=copy.deepcopy(original)
            append_animation(clip,bones,unit,manifest,sample_times=[100.*i for i in range(11)],
                grip_animation=original,align_standard_feet=enabled)
            tracks=_build_tracks(clip);maximum=0.
            for frame in range(11):
                local=[LocalTransform(*(track[i+8].evaluate(100.*frame) for track in tracks)) for i in range(8)]
                actual=_calculate_world_transforms(local,parents)
                for c in (4,7):
                    expected=list(sw[c].position)
                    if c==7:expected[1]+=.1*frame/10
                    maximum=max(maximum,math.dist(actual[c].position,expected))
            errors.append(maximum)
        self.assertGreater(errors[0],.005)
        self.assertLess(errors[1],1e-6)

    def test_coincident_joints_do_not_generate_rotation_from_roundoff(self):
        self.assertEqual(_swing_between([2e-7,-3e-7,0],[0,0,1]),[0,0,0,1])
        q=_swing_between([0,0,1],[0,0,-1])
        self.assertLess(math.dist(quat_rotate(q,[0,0,1]),[0,0,-1]),1e-12)

    def test_masks_follow_driver_channel_order_and_helper_parent(self):
        unit,bones,manifest,_ = fixture()
        data=bytearray(80)
        struct.pack_into('<II',data,28,2,80)
        data.extend(struct.pack('<III',2,12,28))
        data.extend(struct.pack('<I3fI3f',3,1,.25,0,3,0,1,.5))
        old=bytes(data)
        result,count=append_state_machine_masks(data,bones,manifest)
        self.assertEqual(count,2)
        self.assertEqual(result[:32],old[:32]); self.assertEqual(result[36:len(old)],old[36:])
        offset=struct.unpack_from('<I',result,32)[0]
        for i,expected in enumerate(([1,.25,0,0,1,1],[0,1,.5,.5,0,0])):
            start=offset+struct.unpack_from('<I',result,offset+4+i*4)[0]
            self.assertEqual(struct.unpack_from('<I',result,start)[0],6)
            self.assertEqual(list(struct.unpack_from('<6f',result,start+4)),expected)
        struct.pack_into('<I',data,92,2)
        with self.assertRaisesRegex(ValueError,'channel count'): append_state_machine_masks(data,bones,manifest)

    def test_anatomical_calibration_does_not_accumulate_arm_correction(self):
        names=['hips','l_shoulder','l_elbow','l_hand']
        positions=[[0,0,0],[1,0,0],[0,1,0],[0,1,0]]
        unit=UnitData(1,2,[LocalTransform(p,[0,0,0,1],[1,1,1]) for p in positions],
                      [None,0,1,2],[10,11,12,13])
        bones=BonesData(names,[10,11,12,13])
        nodes=[dict(sourceIndex=i,name='src-'+name,hash=100+i,parent=None if i==0 else i-1,driver=name,
                    world=row(i,0,0),local=dict(rotation=[1,0,0,0,1,0,0,0,1],position=[0 if i==0 else 1,0,0],scale=[1,1,1]))
               for i,name in enumerate(names)]
        manifest=dict(version=1,driverHashes=unit.name_hashes,driverWorld=[dict(values=row()) for _ in names],bones=nodes)
        for additive in (False,True):
            states=[AnimationBoneState([0,0,0] if additive else p,[0,0,0,1],
                                       [0,0,0] if additive else [1,1,1],False,False,False) for p in positions]
            animation=AnimationData(initial_bone_states=states,animation_length=.1,is_additive=additive)
            append_animation(animation,bones,unit,manifest)
            if additive:
                for s in animation.initial_bone_states[4:]:
                    self.assertGreater(abs(s.rotation[3]),1-1e-12)
            else:
                world=_calculate_world_transforms(animation.initial_bone_states[4:],[None,0,1,2])
                for a,b in [(1,2),(2,3)]:
                    segment=[world[b].position[j]-world[a].position[j] for j in range(3)]
                    self.assertLess(math.dist(segment,[0,1,0]),1e-12)

    def test_bind_pose_roundtrip_and_permuted_channels(self):
        unit,bones,manifest,animation = fixture()
        original = copy.deepcopy(animation.initial_bone_states)
        append_animation(animation,bones,unit,manifest)
        restored = AnimationData.parse(animation.to_bytes())
        self.assertEqual(restored.initial_bone_states[:3], original)
        self.assertEqual([s.position for s in restored.initial_bone_states[3:]], [[0,0,2],[2,0,0],[1,0,0]])

    def test_rotation_motion_keeps_helpers_and_bone_lengths(self):
        unit,bones,manifest,animation = fixture()
        q = [0,0,math.sqrt(.5),math.sqrt(.5)]
        animation.entries = [AnimationEntry(0,5,0,1000.,q), AnimationEntry(0,4,2,1000.,[4,0,1]),
                             AnimationEntry(0,2,77,250.,[])]
        original = copy.deepcopy(animation.entries)
        metrics = append_animation(animation,bones,unit,manifest)
        restored = AnimationData.parse(animation.to_bytes())
        tracks = _build_tracks(restored)
        self.assertLess(metrics['max_bone_length_error'], 1e-12)
        for t in [0,123,500,1000]:
            self.assertAlmostEqual(math.dist(tracks[0][4].evaluate(t),[0,0,0]),2,places=6)
            self.assertEqual(tracks[0][5].evaluate(t), [1,0,0])
        self.assertEqual(tracks[0][3].evaluate(1000), [4,0,2])
        rotated = quat_rotate(tracks[1][4].evaluate(1000), [1,0,0])
        self.assertAlmostEqual(rotated[1], 1, places=6)
        self.assertEqual([e for e in animation.entries if e.bone < 3 or e.subtype == 2], sorted(original,key=lambda e:e.time))

    def test_additive_identity_and_motion(self):
        unit,bones,manifest,animation = fixture(True)
        q = [0,0,math.sqrt(.5),math.sqrt(.5)]
        animation.entries = [AnimationEntry(0,5,0,1000.,q)]
        append_animation(animation,bones,unit,manifest)
        restored = AnimationData.parse(animation.to_bytes())
        self.assertTrue(restored.is_additive)
        for state in restored.initial_bone_states[3:]:
            self.assertEqual(state.position,[0,0,0])
            self.assertEqual(state.rotation,[0,0,0,1])
            self.assertEqual(state.scale,[0,0,0])
        tracks = _build_tracks(restored)
        self.assertAlmostEqual(quat_rotate(tracks[1][4].evaluate(1000),[1,0,0])[1],1,places=6)

    def test_malformed_manifest_is_rejected(self):
        _,_,manifest,_ = fixture()
        for mutate in [lambda m:m['bones'][1].update(parent=1),
                       lambda m:m['bones'][1].update(hash=10),
                       lambda m:m['bones'][1].update(sourceIndex=0),
                       lambda m:m['bones'][1]['local']['rotation'].__setitem__(0,-1),
                       lambda m:m['bones'][1]['local']['scale'].__setitem__(1,2),
                       lambda m:m['bones'][1]['world'].__setitem__(12,float('nan'))]:
            invalid=copy.deepcopy(manifest); mutate(invalid)
            with self.assertRaises(ValueError): validate_manifest(invalid)

    def test_external_payload_is_not_silently_dropped(self):
        header=bytearray(152)
        struct.pack_into('<II',header,4,0,1)
        struct.pack_into('<QQ',header,72,5,6)
        store=SimpleNamespace(load_toc_header=lambda package: header)
        index=SimpleNamespace(locate=lambda *args:'sample',resolve=lambda *args:('sample','entry'))
        self.assertEqual(resolve_inline(index,store,5,6,{}),('sample','entry'))
        struct.pack_into('<I',header,72+60,100)
        with self.assertRaisesRegex(ValueError,'external stream/GPU'):
            resolve_inline(index,store,5,6,{})


if __name__ == '__main__': unittest.main()
