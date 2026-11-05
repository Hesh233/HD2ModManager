import copy
import struct
import unittest
from unittest.mock import patch

from anim_batch_mod.formats import AnimationEntry, AnimationData, BonesData
from anim_batch_mod.native_animation import read_blocks, preserve_driver_channels
from anim_batch_mod.native_skeleton import convert_clip, animation_nodes, append_bones, bone_name_hash, validate_manifest
from anim_batch_mod.test_native_skeleton import fixture
from anim_batch_mod.processor import _build_tracks


class NativeAnimationIsolationTests(unittest.TestCase):
    def test_legacy_mixed_stream_repair_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Mixed driver streams'):
            preserve_driver_channels(b'',b'')

    def test_driver_adjustment_only_reaches_added_channels(self):
        unit, bones, manifest, animation = fixture()
        original = animation.to_bytes()
        def adjust(a, *_args, **_kwargs):
            a.initial_bone_states[2].position[2] += 3
        with patch('anim_batch_mod.native_skeleton.modify_animation_with_world_compensation', side_effect=adjust):
            result, _ = convert_clip(original, bones, unit, manifest, None, {'fps': 1})
        parsed = AnimationData.parse(result)
        self.assertEqual(animation.initial_bone_states[2].position, parsed.initial_bone_states[2].position)
        self.assertNotEqual(parsed.initial_bone_states[2].position, parsed.initial_bone_states[3].position)

    def test_irregular_compressed_stream_becomes_synchronous_float_without_pose_loss(self):
        for additive in (False,True):
            unit,bones,manifest,animation=fixture(additive)
            for s in animation.initial_bone_states:
                s.compress_position=s.compress_rotation=s.compress_scale=True
            animation.entries=[AnimationEntry(1,0,2,987,[0,0,0] if additive else [1,1,1]),
                AnimationEntry(2,0,0,173,[.2,.1,.3]),AnimationEntry(2,0,0,619,[.4,.8,.3]),
                AnimationEntry(3,0,1,151,[0,0,.2,.979795897]),AnimationEntry(3,0,1,850,[0,0,.6,.8]),
                AnimationEntry(0,2,0xffffffff,501,[]),AnimationEntry(0,2,123,501,[])]
            raw=animation.to_bytes(); original=AnimationData.parse(raw)
            out,_=convert_clip(raw,bones,unit,manifest,None,{'apply_driver_config':False})
            parsed=AnimationData.parse(out)
            self.assertEqual(original.animation_length,parsed.animation_length)
            self.assertEqual(parsed.is_additive,additive)
            for block in read_blocks(out):
                self.assertFalse(any(block.flags))
                times=[e[0] for e in block.entries]
                self.assertEqual(times,sorted(times))
                self.assertTrue(all(int.from_bytes(e[2][:2],'little') in (2,4,5,6) for e in block.entries))
            self.assertEqual([(e.bone,e.time) for e in original.entries if e.subtype==2],
                [(e.bone,e.time) for e in parsed.entries if e.subtype==2])
            a,b=_build_tracks(original),_build_tracks(parsed)
            for t in range(0,1000,7):
                for kind in range(3):
                    for channel in range(3):
                        self.assertLess(max(abs(x-y) for x,y in zip(a[kind][channel].evaluate(t),b[kind][channel].evaluate(t))),2e-6)

    def test_physics_alias_does_not_change_model_bone_names(self):
        _, bones, manifest, _ = fixture()
        manifest['bones'][2]['physics'] = True
        before = copy.deepcopy(manifest)
        nodes = animation_nodes(manifest)
        self.assertEqual(before, manifest)
        self.assertEqual(nodes[:2], manifest['bones'][:2])
        self.assertNotEqual(nodes[2]['hash'], manifest['bones'][2]['hash'])
        self.assertEqual(nodes[2]['hash'], bone_name_hash(nodes[2]['name']))
        data = struct.pack('<II', 3, 1) + struct.pack('<I3II', 0, *bones.hashes, 3) + b'arm\0root\0hips\0'
        parsed = BonesData.parse(append_bones(data, manifest))
        self.assertNotIn(manifest['bones'][2]['hash'], parsed.hashes)
        self.assertIn(nodes[2]['hash'], parsed.hashes)
        manifest['bones'][2]['driver'] = 'arm'
        with self.assertRaisesRegex(ValueError, 'animation drivers'): validate_manifest(manifest)


if __name__ == '__main__': unittest.main()
