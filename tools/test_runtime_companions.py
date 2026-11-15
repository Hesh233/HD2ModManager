"""Synthetic production B3 calibration tests; no game data, logs, model files or deployment."""
from pathlib import Path
import copy
import hashlib
import json
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.runtime_companions import compile_dual_fp_graph, prepare_option_profile, FP_RESOURCE
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.motion_skeleton import matrix, relative
from anim_batch_mod.processor import WorldTransform


def raw_unit(names, parents, positions):
    poses = [WorldTransform(list(p), [0., 0., 0., 1.], [1., 1., 1.]) for p in positions]
    local = [p if parent is None else relative(poses[parent], p) for p, parent in zip(poses, parents)]
    header = bytearray(64)
    struct.pack_into('<Q', header, 8, 1234)
    struct.pack_into('<Q', header, 32, 5678)
    struct.pack_into('<I', header, 52, 64)
    count = len(names)
    body = bytearray(struct.pack('<I', count) + bytes(12))
    body += b''.join(struct.pack('<16f', *matrix(p)) for p in local)
    body += b''.join(struct.pack('<16f', *matrix(p, True)) for p in poses)
    body += b''.join(struct.pack('<HH', 1, parent if parent is not None else 65535) for parent in parents)
    body += struct.pack('<' + str(count) + 'I', *[bone_name_hash(n) for n in names])
    return bytes(header + body + b'unchanged mesh skin material payload')


def graph_fixture():
    names = ['root', 'camera', 'skeleton', 'boss', 'chest', 'placeholder5', 'placeholder6', 'recoil_offset']
    positions = [[0., 0., 0.] for _ in names]
    nodes = [dict(name='source_root', hash=bone_name_hash('source_root'), parent=None, driver=None)]
    source_positions = [[0., 0., 0.]]
    for side, sign in [('r', 1.), ('l', -1.)]:
        joints = [('clavicle', [.05*sign, 0., .5]), ('shoulder', [.1*sign, 0., .5]),
            ('elbow', [.3*sign, 0., .5]), ('hand', [.5*sign, 0., .5]),
            ('middle_finger1', [.55*sign, 0., .5]), ('index_finger1', [.55*sign, .025, .51]),
            ('pinky_finger1', [.55*sign, -.025, .49]), ('hand_twist', [.45*sign, 0., .5])]
        start = len(nodes)
        for j, (joint, p) in enumerate(joints):
            driver = side + '_' + joint
            names.append(driver); positions.append(p)
            source_name = 'source_' + driver if joint != 'hand_twist' else 'source_zhandtwist_' + side
            parent = 0 if j == 0 else (start + j - 1 if j < 4 else start + 3)
            nodes.append(dict(name=source_name, hash=bone_name_hash(source_name), parent=parent,
                driver=driver if joint != 'hand_twist' else None))
            source_positions.append([p[0]*1.1, p[1], p[2]])
    # A physical auxiliary child must remain outside the unanimated FP output domain.
    nodes.append(dict(name='source_phys_hair', hash=bone_name_hash('source_phys_hair'), parent=0, driver=None, physics=True))
    source_positions.append([0., 0., .7])
    while len(names) < 63:
        names.append('native_placeholder_' + str(len(names))); positions.append([0., 0., 0.])
    parents = [None] + [0] * 62
    fp_raw = raw_unit(names, parents, positions)
    channel_names = names[:47]
    bones_raw = struct.pack('<II', 47, 0) + struct.pack('<47I', *map(bone_name_hash, channel_names))
    bones_raw += b''.join(n.encode() + b'\0' for n in channel_names)
    source_names = names + [n['name'] for n in nodes]
    source_parents = parents + [0 if n['parent'] is None else 63 + n['parent'] for n in nodes]
    model = UnitData.parse(raw_unit(source_names, source_parents, positions + source_positions))
    manifest = dict(boneNamespace='synthetic_character', modelScale=1.1, bones=nodes)
    models = {'0000000000000001': model, '0000000000000002': copy.deepcopy(model), '0000000000000003': copy.deepcopy(model)}
    roles = {'0000000000000001': 'RightArm', '0000000000000002': 'LeftArm', '0000000000000003': 'RightArm'}
    return fp_raw, bones_raw, models, manifest, roles


def option_fixture():
    profile = dict(models={'source-body': {'count': 81}}, attachments=[{'node': {'name': 'attach_samplepouch'}}])
    manifest = dict(boneNamespace='synthetic_character', modelScale=1.1)
    settings = dict(version=1, enabled=True, bones=['attach_hand_r', 'attach_hand_l'], excludeHeadDescendants=True)
    fp = dict(expandedUnitSha256='a'*64, version='1.0.1', modelLabel='Character')
    return profile, manifest, settings, fp


class ProductionGraphTests(unittest.TestCase):
    def test_preserves_all_native_bytes_and_47_channels_and_excludes_physics(self):
        raw, bones, models, manifest, roles = graph_fixture()
        expanded, contract = compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')
        before, after = UnitData.parse(raw), UnitData.parse(expanded)
        prefix = bytearray(expanded[:len(raw)]); prefix[52:56] = raw[52:56]
        self.assertEqual(bytes(prefix), raw)
        self.assertEqual(after.name_hashes[:63], before.name_hashes)
        self.assertEqual(after.parents[:63], before.parents)
        self.assertEqual(after.bones_ref, before.bones_ref)
        self.assertEqual(after.state_machine_ref, before.state_machine_ref)
        self.assertEqual(contract['animationChannels'], 47)
        self.assertEqual(contract['animationChannelsAdded'], 0)
        self.assertEqual(contract['originalBonesSha256'], hashlib.sha256(bones).hexdigest())
        self.assertEqual(contract['avatar']['resource'], FP_RESOURCE)
        self.assertNotIn('source_phys_hair', [n['name'] for n in contract['sourceNodes']])
        self.assertEqual(len(after.parents), 64 + len(contract['sourceNodes']))
        self.assertEqual(set(contract['arms']), {'r', 'l'})
        self.assertEqual(len(contract['models']), 3)
        self.assertTrue(all(set(n['modelIndices']) == set(models) for n in contract['sourceNodes']))
        self.assertFalse(contract['modelChanged']); self.assertFalse(contract['physicsNodesDriven'])
        for arm in contract['arms'].values():
            self.assertGreater(arm['upperMetres'], .001); self.assertGreater(arm['forearmMetres'], .001)

    def test_both_arm_sides_required_without_prototype_fallback(self):
        raw, bones, models, manifest, roles = graph_fixture()
        roles.pop('0000000000000002')
        with self.assertRaisesRegex(ValueError, 'Both verified Source arm'):
            compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')

    def test_parent_cycle_rejected_before_ancestor_walk(self):
        raw, bones, models, manifest, roles = graph_fixture()
        manifest['bones'][1]['parent'] = 1
        with self.assertRaisesRegex(ValueError, 'parent-first'):
            compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')

    def test_duplicate_source_driver_is_not_silently_overwritten(self):
        raw, bones, models, manifest, roles = graph_fixture()
        manifest['bones'][2]['driver'] = manifest['bones'][1]['driver']
        with self.assertRaisesRegex(ValueError, 'Duplicate FP Source driver'):
            compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')

    def test_receiver_duplicate_hash_rejected(self):
        raw, bones, models, manifest, roles = graph_fixture()
        models['0000000000000002'].name_hashes[-1] = models['0000000000000002'].name_hashes[-2]
        with self.assertRaisesRegex(ValueError, 'Ambiguous FP receiver'):
            compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')

    def test_source_entry_hash_collision_rejected(self):
        raw, bones, models, manifest, roles = graph_fixture()
        original = bone_name_hash
        def hasher(name):
            return original('root') if name.startswith('__hd2_fp_source_entry_') else original(name)
        with patch('anim_batch_mod.runtime_companions.bone_name_hash', side_effect=hasher):
            with self.assertRaisesRegex(ValueError, 'entry hash collision'):
                compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')

    def test_prefers_explicit_target_receiver_without_requiring_all_alternatives(self):
        raw, bones, models, manifest, roles = graph_fixture()
        manifest['_fpPreferredArmTargets'] = {'RightArm': '0000000000000003'}
        _, contract = compile_dual_fp_graph(raw, bones, models, manifest, roles, 'Character')
        self.assertEqual(contract['model']['resource'], '0000000000000003')
        self.assertEqual(len(contract['models']), 3)


class ProductionIdentityTests(unittest.TestCase):
    def test_marker_identity_is_deterministic_and_profile_compilation_idempotent(self):
        profile, manifest, settings, fp = option_fixture()
        identity = prepare_option_profile(profile, manifest, settings, fp)
        self.assertEqual(identity, prepare_option_profile(profile, manifest, settings, fp))
        self.assertEqual(profile['optionSwitches']['bones'], settings['bones'])
        self.assertEqual([s['key'] for s in profile['optionSwitches']['specs']], ['fp_arms', 'bone:attach_hand_r', 'bone:attach_hand_l'])

    def test_same_model_keeps_package_identity_when_scale_or_target_changes(self):
        p, m, settings, fp = option_fixture(); prepare_option_profile(p, m, settings, fp)
        q, n, _, _ = option_fixture(); n['modelScale'] = 1.2; q['models']['new-target'] = {'count': 81}
        prepare_option_profile(q, n, settings, fp)
        self.assertEqual(p['optionSwitches']['modelIdentity'], q['optionSwitches']['modelIdentity'])
        self.assertNotEqual(p['optionSwitches']['identity'], q['optionSwitches']['identity'])

    def test_changed_settings_or_same_sized_fp_graph_get_fresh_marker_owners(self):
        p, m, settings, fp = option_fixture(); baseline = prepare_option_profile(p, m, settings, fp)
        for change in ['bone-order', 'disabled', 'fp-bind']:
            q, n, s, f = option_fixture()
            if change == 'bone-order': s['bones'].reverse()
            if change == 'disabled': s['enabled'] = False
            if change == 'fp-bind': f['expandedUnitSha256'] = 'b'*64
            self.assertNotEqual(prepare_option_profile(q, n, s, f), baseline)
            self.assertEqual(q['optionSwitches']['modelIdentity'], p['optionSwitches']['modelIdentity'])

    def test_different_model_namespace_cannot_share_marker_or_package_identity(self):
        p, m, s, fp = option_fixture(); prepare_option_profile(p, m, s, fp)
        q, n, _, _ = option_fixture(); n['boneNamespace'] = 'another_character'
        prepare_option_profile(q, n, s, fp)
        self.assertNotEqual(p['optionSwitches']['identity'], q['optionSwitches']['identity'])
        self.assertNotEqual(p['optionSwitches']['modelIdentity'], q['optionSwitches']['modelIdentity'])

    def test_test_repairs_even_null_cannot_be_promoted(self):
        p, m, s, fp = option_fixture(); p['testRepairs'] = None
        with self.assertRaisesRegex(ValueError, 'Test profile'):
            prepare_option_profile(p, m, s, fp)

    def test_unknown_head_duplicate_or_non_boolean_settings_rejected(self):
        for change in ['head', 'duplicate', 'enabled', 'namespace']:
            p, m, s, fp = option_fixture()
            if change == 'head': s['bones'].append('attach_head')
            if change == 'duplicate': s['bones'].append(s['bones'][0])
            if change == 'enabled': s['enabled'] = 1
            if change == 'namespace': m['boneNamespace'] = ''
            with self.assertRaises(ValueError): prepare_option_profile(p, m, s, fp)

    def test_nonfinite_calibration_cannot_generate_markers(self):
        p, m, s, fp = option_fixture(); p['badMatrix'] = float('nan')
        with self.assertRaises(ValueError): prepare_option_profile(p, m, s, fp)

    def test_fp_marker_remains_enabled_when_global_tp_gate_is_disabled(self):
        from lupa.lua51 import LuaRuntime
        vm = LuaRuntime(unpack_returned_tuples=True)
        module = vm.execute((ROOT/'HD2PhysBoneCompat/src/production/attachment_option_switches.lua').read_text(encoding='utf-8'))
        profile, manifest, settings, fp = option_fixture()
        settings['enabled'] = False
        prepare_option_profile(profile, manifest, settings, fp)
        profile['attachments'][0]['node']['index'] = 100
        profile['leftGrip'] = {}; profile['rightGrip'] = {}
        profile['attachmentFixSettings'] = settings
        def lookup(owner):
            spec = next(s for s in profile['optionSwitches']['specs'] if s['owner'] == owner)
            return vm.table_from(dict(schema=profile['optionSwitches']['schema'], key=spec['key'], enabled=True))
        state = module.resolve(vm.table_from(profile, recursive=True), lookup)
        applied = module.apply(vm.table_from(profile, recursive=True), state)
        self.assertTrue(state['fpArms']); self.assertEqual(state['activeBoneCount'], 0)
        self.assertEqual(len(state['invalid']), 0)
        self.assertTrue(applied['firstPersonSource']['runtimeEnabled'])
        self.assertFalse(applied['firstPersonSource']['hiddenOnly'])
        self.assertFalse(applied['rightAttachmentEnabled']); self.assertFalse(applied['leftGrip']['enabled'])


if __name__ == '__main__':
    unittest.main()
