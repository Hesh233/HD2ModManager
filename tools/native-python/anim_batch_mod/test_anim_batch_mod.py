from __future__ import annotations

import tempfile
import unittest
import struct
import copy
import math
from pathlib import Path

from anim_batch_mod.archive import ResourceIndex, TocArchive, TocEntry
from anim_batch_mod.batch import BatchJob, build_batch_entries, unit_context_signature
from anim_batch_mod.constants import ANIMATION_TYPE_ID, BONE_TYPE_ID, UNIT_TYPE_ID
from anim_batch_mod.formats import (
    AnimationBoneState,
    AnimationData,
    AnimationEntry,
    BonesData,
    LocalTransform,
    UnitData,
    patch_unit_positions,
)
from anim_batch_mod.processor import (
    IKChainConfig,
    ModConfig,
    WorldTransform,
    _apply_two_bone_ik,
    _calculate_world_transforms,
    measure_bone_distance,
    modify_animation_with_world_compensation,
)
from anim_batch_mod.math3d import quat_scale_angle
from anim_batch_mod.math3d import quat_multiply
from anim_batch_mod.math3d import vec_add, vec_mul, vec_sub
from anim_batch_mod.cli import (
    build_parser,
    build_unit_anim_overrides,
    build_unit_skeleton_overrides,
    build_base_anim_overrides,
    calculate_bone_offsets,
    calculate_bone_rotation_compensations,
    load_animation_ids,
    select_batch_jobs_by_number,
    resolve_unit_bones,
    write_generated_config,
    find_animation_ids_for_unit,
    find_units_with_bone,
)


class QueryCommandTest(unittest.TestCase):
    def test_filter_commands_accept_expected_options(self):
        args = build_parser().parse_args(["anim-filter", "--unitid", "0x10"])
        self.assertEqual(args.command, "anim-filter")
        self.assertEqual(args.unit_id, "0x10")
        args = build_parser().parse_args(["unit-filter", "--name", "hip"])
        self.assertEqual(args.command, "unit-filter")
        self.assertEqual(args.name, "hip")


IDENTITY = [0.0, 0.0, 0.0, 1.0]


class AnimationRoundTripTest(unittest.TestCase):
    def test_animation_round_trip(self):
        animation = make_animation()
        serialized = animation.to_bytes()
        parsed = AnimationData.parse(serialized)

        self.assertEqual(len(parsed.initial_bone_states), 3)
        self.assertEqual(len(parsed.entries), 2)
        self.assertEqual(parsed.entries[0].bone, 0)
        self.assertAlmostEqual(parsed.entries[0].time, 1000.0, places=3)


class UnitPatchTest(unittest.TestCase):
    def test_patch_unit_positions_rejects_multiplier_without_offset(self):
        unit, bones = make_unit_and_bones()
        with self.assertRaisesRegex(ValueError, "requires a matching offset"):
            patch_unit_positions(
                make_unit_bytes(unit), unit, bones, {}, {"child": 0.5}
            )

    def test_patch_unit_positions_changes_only_configured_bones(self):
        unit, bones = make_unit_and_bones()
        original = make_unit_bytes(unit)
        patched = patch_unit_positions(
            original, unit, bones, {"child": [0.5, -1.0, 0.25]}
        )

        self.assertEqual(len(patched), len(original))
        self.assertNotEqual(patched, original)
        parsed = UnitData.parse(patched)
        self.assertEqual(parsed.transforms[0].position, unit.transforms[0].position)
        for actual, expected in zip(parsed.transforms[1].position, [0.5, 1.0, 0.25]):
            self.assertAlmostEqual(actual, expected, places=5)
        self.assertEqual(parsed.transforms[2].position, unit.transforms[2].position)
        self.assertEqual(patched[:52], original[:52])
        self.assertEqual(patched[52 + 16 + 64 * 3 :], original[52 + 16 + 64 * 3 :])

    def test_patch_unit_positions_scales_configured_parent_child_distance(self):
        unit, bones = make_unit_and_bones()
        original = make_unit_bytes(unit)
        patched = patch_unit_positions(
            original,
            unit,
            bones,
            {"child": [0.5, -1.0, 0.25]},
            {"child": 0.5},
        )

        parsed = UnitData.parse(patched)
        for actual, expected in zip(parsed.transforms[1].position, [0.25, 0.5, 0.125]):
            self.assertAlmostEqual(actual, expected, places=5)


class WorldCompensationTest(unittest.TestCase):
    def test_additive_without_changes_preserves_source_transition_tracks(self):
        animation = make_animation()
        animation.is_additive = True
        for state in animation.initial_bone_states:
            state.scale = [0.0, 0.0, 0.0]
        animation.entries.insert(
            0,
            AnimationEntry(
                type=1,
                bone=2,
                time=2000.0,
                data2=[0.0, 0.0, 0.0],
            ),
        )
        source_bytes = animation.to_bytes()
        source_entries = [
            (entry.bone, entry.subtype, entry.time, list(entry.data2))
            for entry in animation.entries
        ]
        source_initial = [
            (list(state.position), list(state.rotation), list(state.scale))
            for state in animation.initial_bone_states
        ]
        unit, bones = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={}),
            allow_additive=True,
            apply_offsets_to_additive=False,
        )

        self.assertEqual(
            [
                (entry.bone, entry.subtype, entry.time, list(entry.data2))
                for entry in animation.entries
            ],
            source_entries,
        )
        self.assertEqual(
            [
                (list(state.position), list(state.rotation), list(state.scale))
                for state in animation.initial_bone_states
            ],
            source_initial,
        )
        self.assertEqual(animation.to_bytes(), source_bytes)

    def test_additive_ik_keeps_effective_rotation_space(self):
        bones = BonesData(
            names=["root", "mid", "hand", "cape4"], hashes=[1, 2, 3, 4]
        )
        base_root_rotation = [0.0, 0.0, math.sin(math.pi / 9.0), math.cos(math.pi / 9.0)]
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], base_root_rotation, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, 1, None],
            name_hashes=[1, 2, 3, 4],
        )
        additive_root_rotation = [0.0, 0.0, math.sin(math.pi / 18.0), math.cos(math.pi / 18.0)]
        animation = AnimationData(
            initial_bone_states=[
                AnimationBoneState(
                    position=[0.0, 0.0, 0.0],
                    rotation=additive_root_rotation if index == 0 else IDENTITY,
                    scale=[0.0, 0.0, 0.0],
                    compress_position=False,
                    compress_rotation=False,
                    compress_scale=False,
                )
                for index in range(4)
            ],
            animation_length=1.0,
            is_additive=True,
        )

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(
                offsets={"hand": [0.0, 0.1, 0.0]},
                ik_chains={"hand": IKChainConfig(["root", "mid"], 1.0)},
            ),
            allow_additive=True,
            apply_offsets_to_additive=True,
            apply_ik_correction=True,
        )

        measured = measure_bone_distance(
            animation, bones, unit, frame=0, first_bone="root", last_bone="hand"
        )
        expected_rotation = [
            0.0,
            0.0,
            math.sin(math.pi / 6.0),
            math.cos(math.pi / 6.0),
        ]
        for actual, expected in zip(measured.last_rotation, expected_rotation):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_additive_ik_with_patched_unit_uses_same_unit_basis(self):
        bones = BonesData(names=["root", "mid", "hand", "cape4"], hashes=[1, 2, 3, 4])
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, 1, None],
            name_hashes=[1, 2, 3, 4],
        )
        animation = AnimationData(
            initial_bone_states=[
                AnimationBoneState(
                    position=[0.0, 0.0, 0.0],
                    rotation=IDENTITY,
                    scale=[0.0, 0.0, 0.0],
                    compress_position=False,
                    compress_rotation=False,
                    compress_scale=False,
                )
                for _ in range(4)
            ],
            animation_length=1.0,
        )
        for state in animation.initial_bone_states:
            state.position = [0.0, 0.0, 0.0]
            state.scale = [0.0, 0.0, 0.0]
        animation.is_additive = True
        entry = TocEntry(
            file_id=101,
            type_id=ANIMATION_TYPE_ID,
            toc_data=bytearray(animation.to_bytes()),
        )
        unit_id = 909
        unit_entry = TocEntry(
            file_id=unit_id,
            type_id=UNIT_TYPE_ID,
            toc_data=bytearray(make_unit_bytes(unit)),
        )
        index = FakeResourceIndex({101: entry}, {unit_id: unit_entry})
        jobs = [
            BatchJob(
                animation_id=101,
                animation_package="package",
                unit=unit,
                bones=bones,
                context_signature=unit_context_signature(unit, bones),
                unit_id=unit_id,
            )
        ]
        config = ModConfig(
            offsets={"mid": [0.2, 0.0, 0.0], "hand": [0.2, 0.0, 0.0]},
            ik_chains={"hand": IKChainConfig(["root", "mid"], 1.0)},
        )
        build = build_batch_entries(
            index,
            jobs,
            config,
            allow_additive=True,
            apply_ik_correction=True,
            add_unit=True,
        )
        self.assertFalse(build.issues)
        self.assertAlmostEqual(
            build.animations[0].modification.ik_max_error_before,
            0.0,
            places=5,
        )

    def test_ik_chain_corrects_end_effector_after_fk_rotation(self):
        bones = BonesData(
            names=["r_shoulder", "r_elbow", "r_hand", "cape4"],
            hashes=[10, 11, 12, 13],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, 1, None],
            name_hashes=[10, 11, 12, 13],
        )
        animation = AnimationData(
            initial_bone_states=[
                AnimationBoneState(
                    position=list(transform.position),
                    rotation=IDENTITY,
                    scale=[1.0, 1.0, 1.0],
                    compress_position=False,
                    compress_rotation=False,
                    compress_scale=False,
                )
                for transform in unit.transforms
            ],
            animation_length=1.0,
        )
        quarter_turn = [0.0, 0.0, math.sin(math.pi / 4.0), math.cos(math.pi / 4.0)]
        config = ModConfig(
            offsets={"r_hand": [0.0, 1.0, 0.0]},
            rotation_compensations={"r_shoulder": quarter_turn},
            ik_chains={
                "r_hand": IKChainConfig(
                    chain=["r_shoulder", "r_elbow"], target_multiplier=1.0
                )
            },
        )

        result = modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            config,
            apply_rotation_compensations=True,
            apply_ik_correction=True,
        )

        measured = measure_bone_distance(
            animation, bones, unit, frame=30, first_bone="r_shoulder", last_bone="r_hand"
        )
        self.assertAlmostEqual(measured.last_position[0], 2.0, places=4)
        self.assertAlmostEqual(measured.last_position[1], 1.0, places=4)
        self.assertGreater(result.ik_corrections, 0)
        self.assertIn("r_shoulder", result.changed_bones)
        self.assertIn("r_elbow", result.changed_bones)

    def test_ik_preserves_end_effector_world_rotation(self):
        bones = BonesData(
            names=["root", "mid", "hand", "cape4"], hashes=[1, 2, 3, 4]
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, 1, None],
            name_hashes=[1, 2, 3, 4],
        )
        hand_rotation = [0.0, 0.0, math.sin(math.pi / 6.0), math.cos(math.pi / 6.0)]
        animation = AnimationData(
            initial_bone_states=[
                AnimationBoneState(
                    position=list(transform.position),
                    rotation=hand_rotation if index == 2 else IDENTITY,
                    scale=[1.0, 1.0, 1.0],
                    compress_position=False,
                    compress_rotation=False,
                    compress_scale=False,
                )
                for index, transform in enumerate(unit.transforms)
            ],
            animation_length=1.0,
        )
        target_rotation = list(hand_rotation)
        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(
                offsets={"hand": [0.0, 1.0, 0.0]},
                ik_chains={"hand": IKChainConfig(["root", "mid"], 1.0)},
            ),
            apply_ik_correction=True,
        )
        measured = measure_bone_distance(
            animation, bones, unit, frame=0, first_bone="root", last_bone="hand"
        )
        for actual, expected in zip(measured.last_rotation, target_rotation):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_ik_keeps_current_elbow_side_when_target_crosses_chain_axis(self):
        local_transforms = [
            WorldTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            WorldTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            WorldTransform([0.0, 1.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
        ]
        _apply_two_bone_ik(
            local_transforms,
            [None, 0, 1],
            0,
            1,
            2,
            [-0.5, 0.8660254038, 0.0],
            IDENTITY,
        )
        world = _calculate_world_transforms(local_transforms, [None, 0, 1])
        self.assertGreater(world[1].position[1], 0.0)

    def test_ik_config_loads_xyz_target_multiplier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ik.toml"
            path.write_text(
                "[ik_chains.r_hand]\n"
                "chain = [\"r_shoulder\", \"r_elbow\"]\n"
                "target_multiplier = [0.25, -2.0, 1.5]\n",
                encoding="utf-8",
            )
            config = ModConfig.load(path)

        self.assertEqual(config.ik_chains["r_hand"].chain, ["r_shoulder", "r_elbow"])
        self.assertEqual(
            config.ik_chains["r_hand"].target_multiplier,
            [0.25, -2.0, 1.5],
        )

    def test_ik_config_expands_legacy_scalar_target_multiplier(self):
        config = IKChainConfig(["root", "mid"], 0.25)

        self.assertEqual(config.target_multiplier, [0.25, 0.25, 0.25])

    def test_ik_config_rejects_target_multiplier_with_wrong_dimensions(self):
        with self.assertRaisesRegex(ValueError, "exactly three"):
            IKChainConfig(["root", "mid"], [1.0, 2.0])

    def test_ik_target_multiplier_scales_each_world_axis_independently(self):
        original_target = [10.0, 20.0, 30.0]
        fk_target = [14.0, 16.0, 40.0]
        multiplier = [0.5, -2.0, 1.5]

        target = vec_add(
            original_target,
            vec_mul(vec_sub(fk_target, original_target), multiplier),
        )

        self.assertEqual(target, [12.0, 28.0, 45.0])

    def test_parser_accepts_ik_correction_switch(self):
        args = build_parser().parse_args(["batch", "--ik-correction", "true"])
        self.assertTrue(args.ik_correction)

    def test_parser_accepts_sort_patch_animation_id_range(self):
        args = build_parser().parse_args(["batch", "--sort-patch-anim-id", "3", "7"])
        self.assertEqual(args.sort_patch_anim_id, [3, 7])

    def test_parser_accepts_only_additive_switch(self):
        args = build_parser().parse_args(["batch", "--only-additive"])
        self.assertTrue(args.only_additive)

    def test_parser_accepts_only_non_additive_switch(self):
        args = build_parser().parse_args(["batch", "--only-non-additive"])
        self.assertTrue(args.only_non_additive)

    def test_parser_rejects_both_additive_filters(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["batch", "--only-additive", "--only-non-additive"]
            )

    def test_sort_patch_animation_id_selects_inclusive_sorted_range(self):
        jobs = [
            BatchJob(animation_id=40, animation_package="p", unit=None, bones=None, context_signature="",),
            BatchJob(animation_id=10, animation_package="p", unit=None, bones=None, context_signature="",),
            BatchJob(animation_id=30, animation_package="p", unit=None, bones=None, context_signature="",),
            BatchJob(animation_id=20, animation_package="p", unit=None, bones=None, context_signature="",),
        ]
        selected = select_batch_jobs_by_number(jobs, [2, 3])
        self.assertEqual([job.animation_id for job in selected], [20, 30])

    def test_parser_accepts_unit_skeleton_patch(self):
        args = build_parser().parse_args(
            ["generate-config", "--unit-skeleton", "skeleton.patch"]
        )
        self.assertEqual(args.unit_skeleton, Path("skeleton.patch"))

    def test_parser_accepts_generate_config_type2(self):
        args = build_parser().parse_args(["generate-config-type2", "--unit-skeleton", "unit.patch"])
        self.assertEqual(args.command, "generate-config-type2")

    def test_unit_anim_overrides_include_unit_and_bones(self):
        unit, _ = make_unit_and_bones()
        bones_bytes = struct.pack("<II", 1, 0) + struct.pack("<I", 99) + b"cape4\0"

        class Archive:
            def entries_of_type(self, type_id):
                if type_id == UNIT_TYPE_ID:
                    return [TocEntry(123, UNIT_TYPE_ID, bytearray(make_unit_bytes(unit)))]
                return [TocEntry(unit.bones_ref, BONE_TYPE_ID, bytearray(bones_bytes))]

            def get_entry(self, file_id, type_id):
                if type_id == BONE_TYPE_ID and file_id == unit.bones_ref:
                    return TocEntry(file_id, type_id, bytearray(bones_bytes))
                return None

        overrides = build_unit_anim_overrides([Archive()])
        self.assertEqual(overrides[123][0].transforms[0].position, unit.transforms[0].position)
        self.assertEqual(overrides[123][1].names, ["cape4"])

    def test_parser_keeps_unit_skeleton_optional(self):
        args = build_parser().parse_args(["batch"])
        self.assertIsNone(args.unit_skeleton)

    def test_parser_accepts_batch_config_directory_and_unit_id_file(self):
        args = build_parser().parse_args(
            [
                "batch",
                "--config-dir",
                "configs",
                "--unit-id-file",
                "units.txt",
            ]
        )
        self.assertEqual(args.config_dir, Path("configs"))
        self.assertEqual(args.unit_id_file, Path("units.txt"))

    def test_parser_accepts_generate_config_directory_output(self):
        args = build_parser().parse_args(
            [
                "generate-config",
                "--unit-id-file",
                "units.txt",
                "--output-config-dir",
                "configs",
            ]
        )
        self.assertEqual(args.output_config_dir, Path("configs"))

    def test_unit_skeleton_patch_supplies_bones(self):
        unit, _ = make_unit_and_bones()
        bones_bytes = struct.pack("<II", 1, 0) + struct.pack("<I", 99) + b"cape4\0"

        skeleton_patch = {123: BonesData.parse(bones_bytes)}
        package, bones = resolve_unit_bones(unit, 123, object(), skeleton_patch)
        self.assertEqual(package, "unit-skeleton")
        self.assertEqual(bones.names, ["cape4"])

    def test_unit_skeleton_directory_maps_each_unit_to_its_bones(self):
        unit_a, _ = make_unit_and_bones()
        unit_b = copy.deepcopy(unit_a)
        unit_b.bones_ref = 202
        bones_a = struct.pack("<II", 1, 0) + struct.pack("<I", 99) + b"cape4\0"
        bones_b = struct.pack("<II", 1, 0) + struct.pack("<I", 100) + b"hand\0"

        class Archive:
            def __init__(self, unit_id, unit, bones):
                self._entries = {
                    (unit_id, UNIT_TYPE_ID): TocEntry(
                        unit_id, UNIT_TYPE_ID, bytearray(make_unit_bytes(unit))
                    ),
                    (unit.bones_ref, BONE_TYPE_ID): TocEntry(
                        unit.bones_ref, BONE_TYPE_ID, bytearray(bones)
                    ),
                }

            def entries_of_type(self, type_id):
                return [entry for (file_id, entry_type), entry in self._entries.items()
                        if entry_type == type_id]

            def get_entry(self, file_id, type_id):
                return self._entries.get((file_id, type_id))

        overrides = build_unit_skeleton_overrides(
            [Archive(101, unit_a, bones_a), Archive(102, unit_b, bones_b)]
        )
        self.assertEqual(overrides[101].names, ["cape4"])
        self.assertEqual(overrides[102].names, ["hand"])

    def test_base_anim_directory_maps_each_unit_to_its_resources(self):
        unit_a, _ = make_unit_and_bones()
        unit_b = copy.deepcopy(unit_a)
        unit_b.bones_ref = 202

        class Archive:
            def __init__(self, unit_id, unit, bones):
                self._entries = {
                    (unit_id, UNIT_TYPE_ID): TocEntry(
                        unit_id, UNIT_TYPE_ID, bytearray(make_unit_bytes(unit))
                    ),
                    (unit.bones_ref, BONE_TYPE_ID): TocEntry(
                        unit.bones_ref, BONE_TYPE_ID, bytearray(bones)
                    ),
                }

            def entries_of_type(self, type_id):
                return [entry for (file_id, entry_type), entry in self._entries.items()
                        if entry_type == type_id]

            def get_entry(self, file_id, type_id):
                return self._entries.get((file_id, type_id))

        bones = struct.pack("<II", 1, 0) + struct.pack("<I", 99) + b"cape4\0"
        overrides = build_base_anim_overrides(
            [Archive(101, unit_a, bones), Archive(102, unit_b, bones)]
        )
        self.assertEqual(sorted(overrides), [101, 102])
        self.assertEqual(overrides[102][0].file_id, 102)

    def test_ik_rejects_non_contiguous_chain(self):
        bones = BonesData(
            names=["root", "mid", "hand", "cape4"], hashes=[1, 2, 3, 4]
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, None, 1, None],
            name_hashes=[1, 2, 3, 4],
        )
        animation = AnimationData(
            initial_bone_states=[
                AnimationBoneState(
                    position=list(transform.position),
                    rotation=IDENTITY,
                    scale=[1.0, 1.0, 1.0],
                    compress_position=False,
                    compress_rotation=False,
                    compress_scale=False,
                )
                for transform in unit.transforms
            ]
        )
        with self.assertRaisesRegex(ValueError, "direct child"):
            modify_animation_with_world_compensation(
                animation,
                bones,
                unit,
                ModConfig(
                    offsets={"hand": [0.0, 0.0, 0.0]},
                    ik_chains={"hand": IKChainConfig(["root", "mid"])},
                ),
                apply_ik_correction=True,
            )

    def test_rotation_compensation_is_disabled_by_default(self):
        animation = make_animation()
        native_rotation = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
        animation.entries[1].data2 = list(native_rotation)
        bones = BonesData(names=["r_shoulder", "child", "cape4"], hashes=[10, 11, 12])
        unit, _ = make_unit_and_bones()
        correction = [0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)]

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(
                offsets={"r_shoulder": [0.0, 0.0, 0.0]},
                rotation_compensations={"r_shoulder": correction},
            ),
        )

        final_rotation = next(
            entry.data2
            for entry in animation.entries
            if entry.is_rotation and entry.bone == 0 and entry.time == 1000
        )
        for actual, target in zip(final_rotation, native_rotation):
            self.assertAlmostEqual(actual, target, places=6)

    def test_rotation_compensation_applies_per_bone_when_enabled(self):
        animation = make_animation()
        native_rotation = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
        animation.entries[1].data2 = list(native_rotation)
        bones = BonesData(names=["r_shoulder", "child", "cape4"], hashes=[10, 11, 12])
        unit, _ = make_unit_and_bones()
        correction = [0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)]

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(
                offsets={"r_shoulder": [0.0, 0.0, 0.0]},
                rotation_compensations={"r_shoulder": correction},
            ),
            apply_rotation_compensations=True,
        )

        final_rotation = next(
            entry.data2
            for entry in animation.entries
            if entry.is_rotation and entry.bone == 0 and entry.time == 1000
        )
        expected = quat_multiply(correction, native_rotation)
        for actual, target in zip(final_rotation, expected):
            self.assertAlmostEqual(actual, target, places=6)

    def test_rotate_multiplier_scales_final_rotation_angle(self):
        animation = make_animation()
        half_angle = math.pi / 4.0
        animation.entries[1].data2 = [0.0, 0.0, math.sin(half_angle), math.cos(half_angle)]
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit, _ = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(
                offsets={"r_shoulder": [0.0, 0.0, 0.0]},
                rotate_multipliers={"r_shoulder": 0.5},
            ),
            apply_rotate_multipliers=True,
        )

        final_rotation = next(
            entry.data2
            for entry in animation.entries
            if entry.is_rotation and entry.bone == 0 and entry.time == 1000
        )
        expected = quat_scale_angle(
            [0.0, 0.0, math.sin(half_angle), math.cos(half_angle)],
            0.5,
        )
        for actual, target in zip(final_rotation, expected):
            self.assertAlmostEqual(actual, target, places=6)

    def test_rotate_multipliers_are_disabled_by_default(self):
        animation = make_animation()
        animation.entries[1].data2 = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
        bones = BonesData(names=["r_shoulder", "child", "cape4"], hashes=[10, 11, 12])
        unit, _ = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={"r_shoulder": [0.0, 0.0, 0.0]}, rotate_multipliers={"r_shoulder": 0.5}),
        )

        final_rotation = next(
            entry.data2
            for entry in animation.entries
            if entry.is_rotation and entry.bone == 0 and entry.time == 1000
        )
        self.assertAlmostEqual(final_rotation[2], math.sin(math.pi / 4), places=6)

    def test_zero_rotate_multiplier_preserves_native_rotation(self):
        animation = make_animation()
        native_rotation = [0.0, 0.0, math.sin(math.pi / 4), math.cos(math.pi / 4)]
        animation.entries[1].data2 = list(native_rotation)
        bones = BonesData(names=["r_shoulder", "child", "cape4"], hashes=[10, 11, 12])
        unit, _ = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={"r_shoulder": [0.0, 0.0, 0.0]}, rotate_multipliers={"r_shoulder": 0.0}),
            apply_rotate_multipliers=True,
        )

        final_rotation = next(
            entry.data2
            for entry in animation.entries
            if entry.is_rotation and entry.bone == 0 and entry.time == 1000
        )
        for actual, target in zip(final_rotation, native_rotation):
            self.assertAlmostEqual(actual, target, places=6)

    def test_measure_bone_distance_from_skeleton_pose(self):
        unit, bones = make_unit_and_bones()
        result = measure_bone_distance(
            None, bones, unit, frame=0, first_bone="r_shoulder", last_bone="child"
        )
        self.assertEqual(result.first_position, [0.0, 0.0, 0.0])
        self.assertEqual(result.last_position, [0.0, 2.0, 0.0])
        self.assertEqual(result.distance, 2.0)
        self.assertEqual(result.first_rotation, IDENTITY)

    def test_measure_bone_distance_samples_animation_frame(self):
        unit, bones = make_unit_and_bones()
        animation = make_animation()
        animation.entries.append(
            AnimationEntry(type=0, subtype=4, bone=1, time=1000.0, data2=[0.0, 4.0, 0.0])
        )
        result = measure_bone_distance(
            animation, bones, unit, frame=30, first_bone="r_shoulder", last_bone="child"
        )
        self.assertEqual(result.last_position, [0.0, 4.0, 0.0])
        self.assertEqual(result.distance, 4.0)

    def test_preserves_source_initial_scale_in_full_pose(self):
        animation = make_animation()
        animation.initial_bone_states[0].scale = [0.75, 0.75, 0.75]
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit, _ = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={"r_shoulder": [0.0, 0.0, 0.0]}),
        )

        self.assertEqual(animation.initial_bone_states[0].scale, [0.75, 0.75, 0.75])

    def test_bakes_complete_tracks_and_preserves_only_events(self):
        animation = make_animation()
        animation.entries.append(
            AnimationEntry(type=0, subtype=2, bone=0x12345678, time=450.5)
        )
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )

        result = modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]}),
        )

        self.assertEqual(result.generated_position_keys, 3 * 30)
        self.assertEqual(animation.animation_length, 1.0)
        self.assertEqual(
            [(entry.type, entry.subtype) for entry in animation.entries if entry.type == 0 and entry.subtype == 2],
            [(0, 2)],
        )
        transform_entries = [
            entry for entry in animation.entries if entry.type != 0 or entry.subtype != 2
        ]
        self.assertEqual(len(transform_entries), 3 * 30 * 2)
        self.assertEqual(
            {(entry.bone, entry.subtype) for entry in transform_entries},
            {(bone, subtype) for bone in range(3) for subtype in (4, 5)},
        )
        for bone in range(3):
            for subtype in (4, 5):
                times = [
                    entry.time
                    for entry in transform_entries
                    if entry.bone == bone and entry.subtype == subtype
                ]
                self.assertEqual(len(times), len(set(times)))
                self.assertEqual(times[-1], 1000)
        self.assertTrue(
            all(
                not state.compress_position
                and not state.compress_rotation
                and not state.compress_scale
                for state in animation.initial_bone_states
            )
        )
        self.assertTrue(all(state.scale == [1.0, 1.0, 1.0] for state in animation.initial_bone_states))

    def test_bake_tail_is_ceil_frame_but_length_uses_last_source_key(self):
        animation = make_animation()
        animation.animation_length = 0.75
        animation.entries[0].time = 749.0
        animation.entries[1].time = 749.0
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit, _ = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]}),
        )

        transform_times = [
            entry.time
            for entry in animation.entries
            if entry.is_position or entry.is_rotation
        ]
        self.assertEqual(max(transform_times), 766)
        self.assertAlmostEqual(animation.animation_length, 0.749)

    def test_static_animation_preserves_declared_length_when_baked(self):
        animation = make_animation()
        animation.animation_length = 3.65
        animation.entries = []
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit, _ = make_unit_and_bones()

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]}),
        )

        self.assertAlmostEqual(animation.animation_length, 3.65)
        transform_times = [
            entry.time
            for entry in animation.entries
            if entry.is_position or entry.is_rotation
        ]
        self.assertEqual(max(transform_times), 3666)

    def test_additive_requires_opt_in_and_compensates_in_rest_space(self):
        animation = make_animation()
        for state in animation.initial_bone_states:
            state.position = [0.0, 0.0, 0.0]
            state.scale = [0.0, 0.0, 0.0]
        animation.is_additive = True
        for entry in animation.entries:
            if entry.is_position:
                entry.data2 = [0.0, 0.0, 0.0]
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )
        config = ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]})

        with self.assertRaisesRegex(ValueError, "--allow-additive"):
            modify_animation_with_world_compensation(animation, bones, unit, config)

        result = modify_animation_with_world_compensation(
            animation, bones, unit, config, allow_additive=True
        )

        self.assertIn("r_shoulder", result.changed_bones)
        self.assertNotIn("child", result.changed_bones)
        self.assertEqual(animation.initial_bone_states[0].position, [1.0, 0.0, 0.0])
        child_keys = [
            entry for entry in animation.entries if entry.bone == 1 and entry.is_position
        ]
        self.assertTrue(child_keys)
        self.assertTrue(
            all(
                abs(entry.data2[0]) < 1e-5
                and abs(entry.data2[1]) < 1e-5
                and abs(entry.data2[2]) < 1e-5
                for entry in child_keys
            )
        )

    def test_additive_can_use_patched_unit_without_baking_offsets(self):
        animation = make_animation()
        for state in animation.initial_bone_states:
            state.position = [0.0, 0.0, 0.0]
            state.scale = [0.0, 0.0, 0.0]
        animation.is_additive = True
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit, _ = make_unit_and_bones()
        config = ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]})

        modify_animation_with_world_compensation(
            animation,
            bones,
            unit,
            config,
            allow_additive=True,
            apply_offsets_to_additive=False,
        )
        patched_unit = UnitData.parse(
            patch_unit_positions(make_unit_bytes(unit), unit, bones, config.offsets)
        )
        measured = measure_bone_distance(
            animation,
            bones,
            patched_unit,
            frame=0,
            first_bone="r_shoulder",
            last_bone="child",
        )

        self.assertAlmostEqual(measured.distance, 2.0, places=5)
        self.assertEqual(animation.initial_bone_states[0].position, [0.0, 0.0, 0.0])

    def test_event_record_bone_value_is_not_validated_as_index(self):
        animation = make_animation()
        animation.entries.append(
            AnimationEntry(type=0, subtype=2, bone=0x8C6B1234, time=300.0)
        )
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )

        modify_animation_with_world_compensation(
            animation, bones, unit, ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]})
        )

    def test_child_local_position_compensates_parent_offset(self):
        animation = make_animation()
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )
        config = ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]})

        result = modify_animation_with_world_compensation(animation, bones, unit, config)

        self.assertIn("r_shoulder", result.changed_bones)
        self.assertNotIn("child", result.changed_bones)
        self.assertEqual(animation.initial_bone_states[0].position, [1.0, 0.0, 0.0])
        for actual, expected in zip(
            animation.initial_bone_states[1].position, [0.0, 2.0, 0.0]
        ):
            self.assertAlmostEqual(actual, expected, places=5)
        child_keys = [
            entry for entry in animation.entries if entry.bone == 1 and entry.is_position
        ]
        self.assertTrue(child_keys)
        self.assertTrue(all(abs(entry.data2[0]) < 1e-5 for entry in child_keys))

    def test_parent_and_child_offsets_are_applied_independently(self):
        animation = make_animation()
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )
        config = ModConfig(
            offsets={
                "r_shoulder": [1.0, 0.0, 0.0],
                "child": [0.0, 1.0, 0.0],
            }
        )

        result = modify_animation_with_world_compensation(animation, bones, unit, config)

        self.assertIn("r_shoulder", result.changed_bones)
        self.assertIn("child", result.changed_bones)
        self.assertEqual(animation.initial_bone_states[0].position, [1.0, 0.0, 0.0])
        self.assertEqual(animation.initial_bone_states[1].position, [0.0, 3.0, 0.0])

    def test_configured_chain_restores_target_distance(self):
        animation = make_animation()
        animation.initial_bone_states[0].position = [1.0, 0.0, 0.0]
        animation.initial_bone_states[1].position = [0.0, 3.0, 0.0]
        animation.entries[0].data2 = [1.0, 0.0, 0.0]
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 3.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )
        config = ModConfig(
            offsets={"r_shoulder": [-1.0, 0.0, 0.0], "child": [0.0, -1.0, 0.0]}
        )

        modify_animation_with_world_compensation(animation, bones, unit, config)

        measured = measure_bone_distance(
            animation, bones, unit, frame=0, first_bone="r_shoulder", last_bone="child"
        )
        self.assertAlmostEqual(measured.distance, 2.0, places=5)

    def test_distance_multiplier_scales_configured_parent_child_segment(self):
        animation = make_animation()
        animation.initial_bone_states[0].position = [1.0, 0.0, 0.0]
        animation.initial_bone_states[1].position = [0.0, 3.0, 0.0]
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([1.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 3.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )
        config = ModConfig(
            offsets={"r_shoulder": [-1.0, 0.0, 0.0], "child": [0.0, -1.0, 0.0]},
            distance_multipliers={"child": 0.5},
        )

        modify_animation_with_world_compensation(animation, bones, unit, config)

        measured = measure_bone_distance(
            animation, bones, unit, frame=0, first_bone="r_shoulder", last_bone="child"
        )
        self.assertAlmostEqual(measured.distance, 1.0, places=5)

    def test_unanimated_descendant_does_not_block_configured_bone(self):
        animation = make_animation()
        bones = BonesData(
            names=["l_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 1.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None, 1],
            name_hashes=[10, 11, 12, 13],
        )
        config = ModConfig(offsets={"l_shoulder": [1.0, 0.0, 0.0]})

        result = modify_animation_with_world_compensation(animation, bones, unit, config)

        self.assertIn("l_shoulder", result.changed_bones)
        self.assertNotIn("child", result.changed_bones)
        self.assertEqual(animation.initial_bone_states[0].position, [1.0, 0.0, 0.0])

    def test_child_uses_parent_child_world_segment_when_parent_is_rotated(self):
        animation = make_animation()
        bones = BonesData(
            names=["r_shoulder", "child", "cape4"],
            hashes=[10, 11, 12],
        )
        quarter_turn_z = [0.0, 0.0, 0.7071067811865476, 0.7071067811865476]
        unit = UnitData(
            bones_ref=100,
            state_machine_ref=200,
            transforms=[
                LocalTransform([0.0, 0.0, 0.0], quarter_turn_z, [1.0, 1.0, 1.0]),
                LocalTransform([2.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
                LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            ],
            parents=[None, 0, None],
            name_hashes=[10, 11, 12],
        )
        animation.initial_bone_states[0].rotation = quarter_turn_z
        animation.entries[1].data2 = quarter_turn_z
        config = ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]})

        result = modify_animation_with_world_compensation(animation, bones, unit, config)

        self.assertIn("r_shoulder", result.changed_bones)
        self.assertNotIn("child", result.changed_bones)
        for actual, expected in zip(
            animation.initial_bone_states[1].position, [0.0, 2.0, 0.0]
        ):
            self.assertAlmostEqual(actual, expected, places=5)
        child_keys = [
            entry for entry in animation.entries if entry.bone == 1 and entry.is_position
        ]
        self.assertTrue(child_keys)
        self.assertTrue(
            all(
                abs(entry.data2[0]) < 1e-5
                and abs(entry.data2[1] - 2.0) < 1e-5
                and abs(entry.data2[2]) < 1e-5
                for entry in child_keys
            )
        )


class PatchRoundTripTest(unittest.TestCase):
    def test_patch_three_file_round_trip(self):
        animation_id = 123456789
        animation_bytes = make_animation().to_bytes()
        base = TocArchive(unknown=0, header_data=b"\x00" * 56, entries={})
        entry = TocEntry(
            file_id=animation_id,
            type_id=ANIMATION_TYPE_ID,
            toc_data=bytearray(animation_bytes),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "9ba626afa44a3aa3.patch_0"
            paths = base.write_patch(output, [entry])
            self.assertTrue(all(path.exists() for path in paths))
            parsed = TocArchive.parse_parts(
                paths[0].read_bytes(), paths[1].read_bytes(), paths[2].read_bytes()
            )
            parsed_entry = parsed.get_entry(animation_id, ANIMATION_TYPE_ID)
            self.assertIsNotNone(parsed_entry)
            AnimationData.parse(parsed_entry.toc_data)

    def test_batch_writes_multiple_animations_to_one_patch(self):
        unit, bones = make_unit_and_bones()
        entries = {
            animation_id: TocEntry(
                file_id=animation_id,
                type_id=ANIMATION_TYPE_ID,
                toc_data=bytearray(make_animation().to_bytes()),
            )
            for animation_id in (101, 202)
        }
        index = FakeAnimationIndex(entries)
        signature = unit_context_signature(unit, bones)
        jobs = [
            BatchJob(
                animation_id=animation_id,
                animation_package="package",
                unit=unit,
                bones=bones,
                context_signature=signature,
            )
            for animation_id in entries
        ]
        config = ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]})

        build = build_batch_entries(index, jobs, config)

        self.assertFalse(build.issues)
        self.assertEqual({entry.file_id for entry in build.entries}, {101, 202})
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "9ba626afa44a3aa3.patch_0"
            base = TocArchive(unknown=0, header_data=b"\x00" * 56, entries={})
            paths = base.write_patch(output, build.entries)
            parsed = TocArchive.parse_parts(
                paths[0].read_bytes(), paths[1].read_bytes(), paths[2].read_bytes()
            )
            self.assertEqual(
                {entry.file_id for entry in parsed.entries_of_type(ANIMATION_TYPE_ID)},
                {101, 202},
            )

    def test_batch_only_additive_skips_non_additive_animation(self):
        unit, bones = make_unit_and_bones()
        normal = make_animation()
        additive = make_animation()
        for state in additive.initial_bone_states:
            state.scale = [0.0, 0.0, 0.0]
        entries = {
            101: TocEntry(101, ANIMATION_TYPE_ID, bytearray(normal.to_bytes())),
            202: TocEntry(202, ANIMATION_TYPE_ID, bytearray(additive.to_bytes())),
        }
        index = FakeAnimationIndex(entries)
        signature = unit_context_signature(unit, bones)
        jobs = [
            BatchJob(animation_id, "package", unit, bones, signature)
            for animation_id in entries
        ]

        build = build_batch_entries(
            index,
            jobs,
            ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]}),
            allow_additive=True,
            only_additive=True,
        )

        self.assertFalse(build.issues)
        self.assertEqual([item.animation_id for item in build.animations], [202])
        self.assertEqual(
            [entry.file_id for entry in build.entries if entry.type_id == ANIMATION_TYPE_ID],
            [202],
        )

    def test_batch_only_non_additive_skips_additive_animation(self):
        unit, bones = make_unit_and_bones()
        normal = make_animation()
        additive = make_animation()
        for state in additive.initial_bone_states:
            state.scale = [0.0, 0.0, 0.0]
        entries = {
            101: TocEntry(101, ANIMATION_TYPE_ID, bytearray(normal.to_bytes())),
            202: TocEntry(202, ANIMATION_TYPE_ID, bytearray(additive.to_bytes())),
        }
        index = FakeAnimationIndex(entries)
        signature = unit_context_signature(unit, bones)
        jobs = [
            BatchJob(animation_id, "package", unit, bones, signature)
            for animation_id in entries
        ]

        build = build_batch_entries(
            index,
            jobs,
            ModConfig(offsets={"r_shoulder": [1.0, 0.0, 0.0]}),
            only_non_additive=True,
        )

        self.assertFalse(build.issues)
        self.assertEqual([item.animation_id for item in build.animations], [101])
        self.assertEqual(
            [entry.file_id for entry in build.entries if entry.type_id == ANIMATION_TYPE_ID],
            [101],
        )

    def test_batch_omits_unit_by_default(self):
        unit, bones = make_unit_and_bones()
        unit_id = 909
        animation_id = 101
        animation_entry = TocEntry(
            file_id=animation_id,
            type_id=ANIMATION_TYPE_ID,
            toc_data=bytearray(make_animation().to_bytes()),
        )
        unit_entry = TocEntry(
            file_id=unit_id,
            type_id=UNIT_TYPE_ID,
            toc_data=bytearray(make_unit_bytes(unit)),
        )
        index = FakeResourceIndex({animation_id: animation_entry}, {unit_id: unit_entry})
        jobs = [BatchJob(animation_id=animation_id, animation_package="package", unit=unit,
                         bones=bones, context_signature=unit_context_signature(unit, bones),
                         unit_id=unit_id)]

        build = build_batch_entries(index, jobs, ModConfig(offsets={"child": [0.5, -1.0, 0.25]}))

        self.assertFalse(build.issues)
        self.assertEqual([(entry.file_id, entry.type_id) for entry in build.entries],
                         [(animation_id, ANIMATION_TYPE_ID)])

    def test_batch_includes_one_patched_unit_when_enabled(self):
        unit, bones = make_unit_and_bones()
        unit_id = 909
        animation_id = 101
        animation_entry = TocEntry(
            file_id=animation_id,
            type_id=ANIMATION_TYPE_ID,
            toc_data=bytearray(make_animation().to_bytes()),
        )
        unit_entry = TocEntry(
            file_id=unit_id,
            type_id=UNIT_TYPE_ID,
            toc_data=bytearray(make_unit_bytes(unit)),
        )
        index = FakeResourceIndex({animation_id: animation_entry}, {unit_id: unit_entry})
        jobs = [
            BatchJob(
                animation_id=animation_id,
                animation_package="package",
                unit=unit,
                bones=bones,
                context_signature=unit_context_signature(unit, bones),
                unit_id=unit_id,
            )
        ]

        build = build_batch_entries(
            index,
            jobs,
            ModConfig(
                offsets={"child": [0.5, -1.0, 0.25]},
                distance_multipliers={"child": 0.5},
            ),
            add_unit=True,
        )

        self.assertFalse(build.issues)
        self.assertEqual(
            [(entry.file_id, entry.type_id) for entry in build.entries],
            [(unit_id, UNIT_TYPE_ID), (animation_id, ANIMATION_TYPE_ID)],
        )
        patched_unit = UnitData.parse(build.entries[0].toc_data)
        for actual, expected in zip(
            patched_unit.transforms[1].position, [0.25, 0.5, 0.125]
        ):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_batch_reuses_patched_unit_for_mixed_animation_modes(self):
        unit, bones = make_unit_and_bones()
        unit_id = 909
        normal_animation_id = 101
        additive_animation_id = 202
        normal_animation = make_animation()
        additive_animation = make_animation()
        additive_animation.is_additive = True
        for state in additive_animation.initial_bone_states:
            state.position = [0.0, 0.0, 0.0]
            state.scale = [0.0, 0.0, 0.0]

        animation_entries = {
            normal_animation_id: TocEntry(
                file_id=normal_animation_id,
                type_id=ANIMATION_TYPE_ID,
                toc_data=bytearray(normal_animation.to_bytes()),
            ),
            additive_animation_id: TocEntry(
                file_id=additive_animation_id,
                type_id=ANIMATION_TYPE_ID,
                toc_data=bytearray(additive_animation.to_bytes()),
            ),
        }
        unit_entry = TocEntry(
            file_id=unit_id,
            type_id=UNIT_TYPE_ID,
            toc_data=bytearray(make_unit_bytes(unit)),
        )
        index = FakeResourceIndex(animation_entries, {unit_id: unit_entry})
        signature = unit_context_signature(unit, bones)
        jobs = [
            BatchJob(
                animation_id=normal_animation_id,
                animation_package="package",
                unit=unit,
                bones=bones,
                context_signature=signature,
                unit_id=unit_id,
            ),
            BatchJob(
                animation_id=additive_animation_id,
                animation_package="package",
                unit=unit,
                bones=bones,
                context_signature=signature,
                unit_id=unit_id,
            ),
        ]

        build = build_batch_entries(
            index,
            jobs,
            ModConfig(offsets={"child": [0.5, -1.0, 0.25]}),
            allow_additive=True,
            add_unit=True,
        )

        self.assertFalse(build.issues)
        self.assertEqual(
            [(entry.file_id, entry.type_id) for entry in build.entries],
            [
                (unit_id, UNIT_TYPE_ID),
                (normal_animation_id, ANIMATION_TYPE_ID),
                (additive_animation_id, ANIMATION_TYPE_ID),
            ],
        )
        self.assertEqual(
            [item.animation_id for item in build.animations],
            [normal_animation_id, additive_animation_id],
        )

    def test_batch_does_not_emit_unit_when_all_animations_fail(self):
        unit, bones = make_unit_and_bones()
        unit_id = 909
        animation_id = 101
        animation_entry = TocEntry(
            file_id=animation_id,
            type_id=ANIMATION_TYPE_ID,
            toc_data=bytearray(),
        )
        unit_entry = TocEntry(
            file_id=unit_id,
            type_id=UNIT_TYPE_ID,
            toc_data=bytearray(make_unit_bytes(unit)),
        )
        index = FakeResourceIndex({animation_id: animation_entry}, {unit_id: unit_entry})
        job = BatchJob(
            animation_id=animation_id,
            animation_package="package",
            unit=unit,
            bones=bones,
            context_signature=unit_context_signature(unit, bones),
            unit_id=unit_id,
        )

        build = build_batch_entries(
            index,
            [job],
            ModConfig(offsets={"child": [0.5, -1.0, 0.25]}),
            add_unit=True,
        )

        self.assertTrue(build.issues)
        self.assertEqual(build.entries, [])


class BatchContextTest(unittest.TestCase):
    def test_state_machine_id_does_not_change_compensation_context(self):
        unit, bones = make_unit_and_bones()
        other = UnitData(
            bones_ref=unit.bones_ref,
            state_machine_ref=999,
            transforms=unit.transforms,
            parents=unit.parents,
            name_hashes=unit.name_hashes,
        )
        self.assertEqual(
            unit_context_signature(unit, bones),
            unit_context_signature(other, bones),
        )


class ConfigGenerationTest(unittest.TestCase):
    def test_config_load_reads_bone_rotate_multipliers(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            path.write_text(
                "[bone_offsets]\nr_shoulder = [0.0, 0.0, 0.0]\n"
                "\n[bone_rotate_multipliers]\nr_shoulder = 0.5\n",
                encoding="utf-8",
            )

            config = ModConfig.load(path)

            self.assertEqual(config.rotate_multipliers, {"r_shoulder": 0.5})

    def test_config_load_reads_rotation_compensations(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            path.write_text(
                "[bone_offsets]\nr_shoulder = [0.0, 0.0, 0.0]\n"
                "\n[bone_rotation_compensations]\nr_shoulder = [0.0, 0.0, 0.5, 0.8660254]\n",
                encoding="utf-8",
            )

            config = ModConfig.load(path)

            for actual, expected in zip(
                config.rotation_compensations["r_shoulder"][:3], [0.0, 0.0, 0.5]
            ):
                self.assertAlmostEqual(actual, expected, places=6)

    def test_parser_accepts_rotation_compensation_switch(self):
        args = build_parser().parse_args(["batch", "--rotation-compensation", "true"])
        self.assertTrue(args.rotation_compensation)

    def test_calculates_local_rotation_compensation(self):
        original_unit, bones = make_unit_and_bones()
        base_unit = copy.deepcopy(original_unit)
        base_unit.transforms[0].rotation = [0.0, 0.0, math.sin(math.pi / 8), math.cos(math.pi / 8)]

        compensations = calculate_bone_rotation_compensations(
            base_unit, bones, original_unit, bones
        )

        self.assertAlmostEqual(compensations["r_shoulder"][2], math.sin(math.pi / 8), places=6)

    def test_config_writer_includes_rotation_compensations(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            write_generated_config(
                path,
                {"r_shoulder": [-0.035, 0.0, 0.0]},
                {"r_shoulder": [-0.08, 0.0, 0.03]},
                rotation_compensations={"r_shoulder": [0.0, 0.0, 0.5, 0.8660254]},
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("[bone_rotation_compensations]", text)
            self.assertIn("r_shoulder = [0.0, 0.0, 0.5, 0.8660254]", text)

    def test_parser_accepts_explicit_rotate_multipliers_boolean(self):
        args = build_parser().parse_args(["batch", "--rotate-multipliers", "true"])
        self.assertTrue(args.rotate_multipliers)
        args = build_parser().parse_args(["batch", "--rotate-multipliers", "false"])
        self.assertFalse(args.rotate_multipliers)

    def test_config_load_accepts_legacy_offsets_without_multiplier_table(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            path.write_text(
                "[bone_offsets]\nr_shoulder = [0.0, 0.0, 0.0]\n",
                encoding="utf-8",
            )

            config = ModConfig.load(path)

            self.assertEqual(config.distance_multipliers.get("r_shoulder", 1.0), 1.0)

    def test_config_load_accepts_rotation_only_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            path.write_text(
                "[bone_rotation_compensations]\nr_shoulder = [0.0, 0.0, 0.0, 1.0]\n",
                encoding="utf-8",
            )

            config = ModConfig.load(path)

            self.assertEqual(config.offsets, {})
            self.assertIn("r_shoulder", config.rotation_compensations)

    def test_calculates_base_minus_original_local_offsets_and_world_deltas(self):
        original_unit, bones = make_unit_and_bones()
        base_unit = copy.deepcopy(original_unit)
        base_unit.transforms[0].position = [1.0, 0.0, 0.0]
        base_unit.transforms[1].position = [0.0, 2.0, 0.0]

        offsets, world_deltas = calculate_bone_offsets(
            base_unit, bones, original_unit, bones
        )

        self.assertEqual(offsets, {"r_shoulder": [1.0, 0.0, 0.0]})
        self.assertEqual(world_deltas["r_shoulder"], [1.0, 0.0, 0.0])

    def test_config_writer_includes_local_values_and_world_comments(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            write_generated_config(
                path,
                {"r_shoulder": [-0.035, 0.0, 0.0]},
                {"r_shoulder": [-0.08, 0.0, 0.03]},
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("r_shoulder = [-0.035, 0.0, 0.0]", text)
            self.assertIn("world_delta = [-0.08, 0.0, 0.03]", text)
            self.assertEqual(ModConfig.load(path).offsets["r_shoulder"], [-0.035, 0.0, 0.0])
            self.assertEqual(ModConfig.load(path).distance_multipliers["r_shoulder"], 1.0)

    def test_config_load_rejects_distance_multiplier_without_offset(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            path.write_text(
                "[bone_offsets]\nr_shoulder = [0.0, 0.0, 0.0]\n"
                "[bone_distance_multipliers]\nchild = 0.5\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "requires a matching offset"):
                ModConfig.load(path)

    def test_tolerance_filters_small_local_differences(self):
        original_unit, bones = make_unit_and_bones()
        base_unit = copy.deepcopy(original_unit)
        base_unit.transforms[0].position = [0.5e-6, 0.0, 0.0]

        offsets, _ = calculate_bone_offsets(
            base_unit, bones, original_unit, bones, tolerance=1e-6
        )

        self.assertEqual(offsets, {})

    def test_config_writer_rejects_empty_offsets(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "No bone offsets"):
                write_generated_config(
                    Path(temporary_directory) / "config.toml", {}, {}
                )

    def test_config_writer_accepts_rotation_only_config(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.toml"
            write_generated_config(
                path,
                {},
                {},
                rotation_compensations={"r_shoulder": [0.0, 0.0, 0.5, 0.8660254]},
            )

            config = ModConfig.load(path)

            self.assertEqual(config.offsets, {})
            self.assertIn("r_shoulder", config.rotation_compensations)


class AnimationIdFileTest(unittest.TestCase):
    def test_reads_decimal_hex_comments_and_deduplicates_ids(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "animation_ids.txt"
            path.write_text(
                "\ufeff101\n0xCA\n101 # duplicate\n\n# ignored\n",
                encoding="utf-8",
            )

            self.assertEqual(load_animation_ids(path), {101, 202})

    def test_rejects_empty_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_path = Path(temporary_directory) / "empty.txt"
            empty_path.write_text("\n# comment\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty"):
                load_animation_ids(empty_path)

            invalid_path = Path(temporary_directory) / "invalid.txt"
            invalid_path.write_text("101\nnot-an-id\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                load_animation_ids(invalid_path)

    def test_animation_id_and_file_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                [
                    "batch",
                    "--animation-id",
                    "101",
                    "--animation-id-file",
                    "ids.txt",
                ]
            )

class ResourceIndexCacheTest(unittest.TestCase):
    def test_disk_cache_is_reused(self):
        file_id = 0xFEDCBA9876543210
        type_id = ANIMATION_TYPE_ID
        header = bytearray(72 + 32 + 80)
        struct.pack_into("<IIII56s", header, 0, 4026531857, 1, 1, 0, b"\x00" * 56)
        struct.pack_into("<QQQII", header, 72, 0, type_id, 1, 16, 64)
        struct.pack_into("<QQ", header, 104, file_id, type_id)
        store = FakeStore(header)

        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_path = Path(temporary_directory) / "resource_index.sqlite3"
            first = ResourceIndex(store, cache_path, {type_id})
            self.assertFalse(first.load_or_build())
            self.assertEqual(first.locate(file_id, type_id), "package")
            first.close()

            second = ResourceIndex(store, cache_path, {type_id})
            self.assertTrue(second.load_or_build())
            self.assertEqual(second.locate(file_id, type_id), "package")
            second.close()


class FakeStore:
    def __init__(self, header):
        self.header = header

    def index_package_names(self):
        return ["package"]

    def load_toc_header(self, package_name):
        return self.header

    def index_fingerprint(self):
        return "test-fingerprint"


class FakeAnimationIndex:
    def __init__(self, entries):
        self.entries = entries

    def resolve(self, file_id, type_id):
        if type_id != ANIMATION_TYPE_ID or file_id not in self.entries:
            raise LookupError(file_id)
        return "package", self.entries[file_id]


class FakeResourceIndex(FakeAnimationIndex):
    def __init__(self, entries, unit_entries):
        super().__init__(entries)
        self.unit_entries = unit_entries

    def resolve(self, file_id: int, type_id: int):
        if type_id == UNIT_TYPE_ID and file_id in self.unit_entries:
            return "package", self.unit_entries[file_id]
        return super().resolve(file_id, type_id)


def make_unit_and_bones():
    bones = BonesData(
        names=["r_shoulder", "child", "cape4"],
        hashes=[10, 11, 12],
    )
    unit = UnitData(
        bones_ref=100,
        state_machine_ref=200,
        transforms=[
            LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            LocalTransform([0.0, 2.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
            LocalTransform([0.0, 0.0, 0.0], IDENTITY, [1.0, 1.0, 1.0]),
        ],
        parents=[None, 0, None],
        name_hashes=[10, 11, 12],
    )
    return unit, bones


def make_unit_bytes(unit: UnitData) -> bytes:
    transform_info_offset = 56
    transform_count = len(unit.transforms)
    data = bytearray(transform_info_offset + 16 + transform_count * 64 + transform_count * 64 + transform_count * 4 + transform_count * 4)
    struct.pack_into("<QQQQQ", data, 0, 1, unit.bones_ref, 2, 3, unit.state_machine_ref)
    struct.pack_into("<IIII", data, 40, 0, 0, 0, transform_info_offset)
    struct.pack_into("<I", data, transform_info_offset, transform_count)
    for index, transform in enumerate(unit.transforms):
        offset = transform_info_offset + 16 + index * 64
        struct.pack_into("<3f", data, offset + 36, *transform.position)
        struct.pack_into("<3f", data, offset + 48, *transform.scale)
    parent_offset = transform_info_offset + 16 + transform_count * 128
    for index, parent in enumerate(unit.parents):
        struct.pack_into("<HH", data, parent_offset + index * 4, index, index if parent is None else parent)
    names_offset = parent_offset + transform_count * 4
    for index, bone_hash in enumerate(unit.name_hashes):
        struct.pack_into("<I", data, names_offset + index * 4, bone_hash)
    return bytes(data)


def make_animation() -> AnimationData:
    animation = AnimationData(
        initial_bone_states=[
            AnimationBoneState(
                position=[0.0, 0.0, 0.0],
                rotation=IDENTITY,
                scale=[1.0, 1.0, 1.0],
                compress_position=False,
                compress_rotation=False,
                compress_scale=False,
            )
            for _ in range(3)
        ],
        animation_length=1.0,
    )
    animation.initial_bone_states[1].position = [0.0, 2.0, 0.0]
    animation.entries = [
        AnimationEntry(
            type=0,
            subtype=4,
            bone=0,
            time=1000.0,
            data2=[0.0, 0.0, 0.0],
        ),
        AnimationEntry(
            type=0,
            subtype=5,
            bone=0,
            time=1000.0,
            data2=IDENTITY,
        ),
    ]
    return animation


if __name__ == "__main__":
    unittest.main()
