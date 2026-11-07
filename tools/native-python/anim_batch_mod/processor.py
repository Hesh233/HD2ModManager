from __future__ import annotations

import copy
import tomllib
from bisect import bisect_right
from dataclasses import dataclass, field
from math import isfinite
from math import sqrt
from math import ceil
from pathlib import Path

from .formats import AnimationBoneState, AnimationData, AnimationEntry, BonesData, UnitData
from .math3d import (
    quat_inverse_rotate,
    quat_inverse,
    quat_multiply,
    quat_normalize,
    quat_rotate,
    quat_scale_angle,
    quat_slerp,
    vec_add,
    vec_close,
    vec_div,
    vec_lerp,
    vec_mul,
    vec_sub,
)


@dataclass
class IKChainConfig:
    chain: list[str]
    target_multiplier: list[float] | float = 1.0

    def __post_init__(self):
        self.chain = [str(name) for name in self.chain]
        if len(self.chain) != 2:
            raise ValueError("IK chain must contain exactly two bones")
        raw_multiplier = self.target_multiplier
        if isinstance(raw_multiplier, (list, tuple)):
            if len(raw_multiplier) != 3:
                raise ValueError("IK target_multiplier must contain exactly three numbers")
            values = [float(component) for component in raw_multiplier]
        else:
            value = float(raw_multiplier)
            values = [value, value, value]
        if not all(isfinite(value) for value in values):
            raise ValueError("IK target_multiplier must contain only finite numbers")
        self.target_multiplier = values


@dataclass
class ModConfig:
    offsets: dict[str, list[float]]
    required_bone: str = "cape4"
    distance_multipliers: dict[str, float] = field(default_factory=dict)
    rotate_multipliers: dict[str, float] = field(default_factory=dict)
    rotation_compensations: dict[str, list[float]] = field(default_factory=dict)
    ik_chains: dict[str, IKChainConfig] = field(default_factory=dict)

    def __post_init__(self):
        missing_offsets = sorted(set(self.distance_multipliers) - set(self.offsets))
        if missing_offsets:
            raise ValueError(
                "Distance multiplier requires a matching offset for: "
                + ", ".join(missing_offsets)
            )
        for bone_name, multiplier in self.distance_multipliers.items():
            value = float(multiplier)
            if not isfinite(value) or value < 0.0:
                raise ValueError(
                    f"Distance multiplier for {bone_name} must be a finite non-negative number"
                )
            self.distance_multipliers[bone_name] = value
        for bone_name, multiplier in self.rotate_multipliers.items():
            value = float(multiplier)
            if not isfinite(value) or value < 0.0:
                raise ValueError(
                    f"Rotate multiplier for {bone_name} must be a finite non-negative number"
                )
            self.rotate_multipliers[bone_name] = value
        for bone_name, rotation in self.rotation_compensations.items():
            if len(rotation) != 4:
                raise ValueError(
                    f"Rotation compensation for {bone_name} must contain exactly four numbers"
                )
            values = [float(component) for component in rotation]
            if not all(isfinite(value) for value in values):
                raise ValueError(f"Rotation compensation for {bone_name} must be finite")
            self.rotation_compensations[bone_name] = quat_normalize(values)

    @classmethod
    def load(cls, path: Path) -> "ModConfig":
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        offsets_data = data.get("bone_offsets", {})
        if not isinstance(offsets_data, dict):
            raise ValueError("[bone_offsets] must be a table")
        offsets = {}
        for bone_name, value in offsets_data.items():
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError(f"Offset for {bone_name} must contain exactly three numbers")
            offsets[bone_name] = [float(component) for component in value]
        multipliers_data = data.get("bone_distance_multipliers", {})
        if not isinstance(multipliers_data, dict):
            raise ValueError("[bone_distance_multipliers] must be a table")
        distance_multipliers = {
            str(bone_name): float(value)
            for bone_name, value in multipliers_data.items()
        }
        rotate_multipliers_data = data.get("bone_rotate_multipliers", {})
        if not isinstance(rotate_multipliers_data, dict):
            raise ValueError("[bone_rotate_multipliers] must be a table")
        rotate_multipliers = {
            str(bone_name): float(value)
            for bone_name, value in rotate_multipliers_data.items()
        }
        rotation_compensations_data = data.get("bone_rotation_compensations", {})
        if not isinstance(rotation_compensations_data, dict):
            raise ValueError("[bone_rotation_compensations] must be a table")
        rotation_compensations = {}
        for bone_name, value in rotation_compensations_data.items():
            if not isinstance(value, list) or len(value) != 4:
                raise ValueError(
                    f"Rotation compensation for {bone_name} must contain exactly four numbers"
                )
            rotation_compensations[str(bone_name)] = [float(component) for component in value]
        ik_chains_data = data.get("ik_chains", {})
        if not isinstance(ik_chains_data, dict):
            raise ValueError("[ik_chains] must be a table")
        ik_chains = {}
        for target_name, chain_data in ik_chains_data.items():
            if not isinstance(chain_data, dict):
                raise ValueError(f"IK chain {target_name} must be a table")
            chain = chain_data.get("chain")
            if not isinstance(chain, list):
                raise ValueError(f"IK chain {target_name} must define a chain list")
            if chain_data.get("policy", "fk-target") != "fk-target":
                raise ValueError("Experimental arm projection is unsupported; use standard IK chains")
            ik_chains[str(target_name)] = IKChainConfig(
                chain=chain,
                target_multiplier=chain_data.get("target_multiplier", [1.0, 1.0, 1.0]),
            )
        if not offsets and not rotation_compensations and not ik_chains:
            raise ValueError(
                "Config must contain at least one bone offset, rotation compensation, or IK chain"
            )
        required_bone = str(data.get("filter", {}).get("required_bone", "cape4"))
        return cls(
            offsets=offsets,
            distance_multipliers=distance_multipliers,
            rotate_multipliers=rotate_multipliers,
            rotation_compensations=rotation_compensations,
            ik_chains=ik_chains,
            required_bone=required_bone,
        )


@dataclass
class ModificationResult:
    changed_bones: list[str]
    generated_position_keys: int
    sample_count: int
    ik_corrections: int = 0
    ik_evaluations: int = 0
    unchanged: bool = False
    ik_max_error_before: float = 0.0
    ik_max_error_after: float = 0.0
    arm_target_projections: int = 0
    arm_requested_target_max_distance: float = 0.0


@dataclass
class WorldTransform:
    position: list[float]
    rotation: list[float]
    scale: list[float]


@dataclass
class BoneDistanceResult:
    first_position: list[float]
    first_rotation: list[float]
    last_position: list[float]
    last_rotation: list[float]
    distance: float


def measure_bone_distance(
    animation: AnimationData | None,
    bones: BonesData,
    unit: UnitData,
    frame: int,
    first_bone: str,
    last_bone: str,
) -> BoneDistanceResult:
    """Sample two named bones and return their world-space transforms."""
    if frame < 0:
        raise ValueError("--frame must be non-negative")
    name_to_animation = {name: index for index, name in enumerate(bones.names)}
    for name in (first_bone, last_bone):
        if name not in name_to_animation:
            raise ValueError(f"Bone '{name}' does not exist in the skeleton")
    if len(unit.transforms) != len(unit.parents) or len(unit.transforms) != len(unit.name_hashes):
        raise ValueError("Unit transform hierarchy is incomplete")
    if animation is not None and len(animation.initial_bone_states) != len(bones.names):
        raise ValueError(
            "Animation/Bones count mismatch: "
            f"animation={len(animation.initial_bone_states)}, bones={len(bones.names)}"
        )

    local_transforms = [
        WorldTransform(
            position=list(transform.position),
            rotation=list(transform.rotation),
            scale=list(transform.scale),
        )
        for transform in unit.transforms
    ]
    if animation is not None:
        position_tracks, rotation_tracks, scale_tracks = _build_tracks(animation)
        time = frame * (1000.0 / 30.0)
        transform_by_hash = {name_hash: index for index, name_hash in enumerate(unit.name_hashes)}
        for animation_index, bone_hash in enumerate(bones.hashes):
            transform_index = transform_by_hash.get(bone_hash)
            if transform_index is None:
                raise ValueError(f"Animated bone '{bones.names[animation_index]}' is missing from Unit")
            sampled = WorldTransform(
                position=position_tracks[animation_index].evaluate(time),
                rotation=rotation_tracks[animation_index].evaluate(time),
                scale=scale_tracks[animation_index].evaluate(time),
            )
            if animation.is_additive:
                sampled = _compose_additive_local(unit.transforms[transform_index], sampled)
            local_transforms[transform_index] = sampled

    world = _calculate_world_transforms(local_transforms, unit.parents)
    first_index = transform_by_name(bones, unit, first_bone)
    last_index = transform_by_name(bones, unit, last_bone)
    first = world[first_index]
    last = world[last_index]
    delta = vec_sub(last.position, first.position)
    return BoneDistanceResult(
        first_position=first.position,
        first_rotation=first.rotation,
        last_position=last.position,
        last_rotation=last.rotation,
        distance=sqrt(sum(value * value for value in delta)),
    )


def transform_by_name(bones: BonesData, unit: UnitData, name: str) -> int:
    bone_index = bones.names.index(name)
    bone_hash = bones.hashes[bone_index]
    try:
        return unit.name_hashes.index(bone_hash)
    except ValueError as error:
        raise ValueError(f"Bone '{name}' is missing from Unit") from error


class Track:
    def __init__(self, keys, interpolate):
        deduplicated = {}
        for time, value in keys:
            deduplicated[float(time)] = list(value)
        self.keys = sorted(deduplicated.items())
        self.times = [item[0] for item in self.keys]
        self.interpolate = interpolate

    def evaluate(self, time: float):
        if time <= self.times[0]:
            return list(self.keys[0][1])
        if time >= self.times[-1]:
            return list(self.keys[-1][1])
        right = bisect_right(self.times, time)
        left_time, left_value = self.keys[right - 1]
        right_time, right_value = self.keys[right]
        factor = (time - left_time) / (right_time - left_time)
        return self.interpolate(left_value, right_value, factor)


def modify_animation_with_world_compensation(
    animation: AnimationData,
    bones: BonesData,
    unit: UnitData,
    config: ModConfig,
    allow_additive: bool = False,
    apply_offsets_to_additive: bool = True,
    apply_rotate_multipliers: bool = False,
    apply_rotation_compensations: bool = False,
    apply_ik_correction: bool = False,
    preserve_hand_bend_frame: bool = True,
    preserve_source_key_times: bool = False,
    preserve_unmodified_channels: bool = False,
    source_arm_constraints: bool = False,
    preserve_playback_timing: bool = False,
    playback_reference: AnimationData | None = None,
) -> ModificationResult:
    if any(not isinstance(v, bool) for v in (preserve_hand_bend_frame, preserve_source_key_times, preserve_unmodified_channels, source_arm_constraints, preserve_playback_timing)):
        raise ValueError("Processing profile switches must be booleans")
    if animation.is_additive and not allow_additive:
        raise ValueError(
            "Additive animation requires --allow-additive; its zero-scale basis "
            "uses a separate composition model"
        )
    if len(animation.initial_bone_states) != len(bones.names):
        raise ValueError(
            "Animation/Bones count mismatch: "
            f"animation={len(animation.initial_bone_states)}, bones={len(bones.names)}"
        )
    if preserve_unmodified_channels:
        # Opt-in bit passthrough for untouched compressed rotations. Decode /
        # re-encode otherwise moves a source control point by up to 0.1 degrees.
        # The writer only reuses bits when the decoded value is still identical.
        for state in animation.initial_bone_states:state._keep_original_rotation = True
        for entry in animation.entries:
            if entry.is_rotation:entry._keep_original_rotation = True
    source_animation_length = animation.animation_length
    source_initial_bone_states = copy.deepcopy(animation.initial_bone_states)
    source_entries = copy.deepcopy(animation.entries)
    source_transform_entries = [
        copy.deepcopy(entry)
        for entry in animation.entries
        if entry.is_position or entry.is_rotation or entry.is_scale
    ]
    if config.required_bone not in bones.names:
        raise ValueError(
            f"Selected Unit does not use required bone '{config.required_bone}'"
        )

    bone_name_to_index = {name: index for index, name in enumerate(bones.names)}
    missing = [name for name in config.offsets if name not in bone_name_to_index]
    if missing:
        raise ValueError(f"Configured bones are missing from the animation skeleton: {missing}")
    if apply_rotate_multipliers:
        missing_rotate = [
            name for name in config.rotate_multipliers if name not in bone_name_to_index
        ]
        if missing_rotate:
            raise ValueError(
                "Configured rotation multiplier bones are missing from the animation skeleton: "
                + ", ".join(missing_rotate)
            )
    if apply_rotation_compensations:
        missing_rotation = [
            name for name in config.rotation_compensations if name not in bone_name_to_index
        ]
        if missing_rotation:
            raise ValueError(
                "Configured rotation compensation bones are missing from the animation skeleton: "
                + ", ".join(missing_rotation)
            )
    ik_indices = {}
    if apply_ik_correction:
        for target_name, chain_config in config.ik_chains.items():
            names = [*chain_config.chain, target_name]
            missing_ik = [name for name in names if name not in bone_name_to_index]
            if missing_ik:
                raise ValueError(
                    "Configured IK bones are missing from the animation skeleton: "
                    + ", ".join(missing_ik)
                )
            root_index = bone_name_to_index[chain_config.chain[0]]
            mid_index = bone_name_to_index[chain_config.chain[1]]
            target_index = bone_name_to_index[target_name]
            # Parent relationships are checked after animation/unit mapping is built.
            ik_indices[target_name] = (root_index, mid_index, target_index)

    transform_by_hash = {}
    for index, name_hash in enumerate(unit.name_hashes):
        transform_by_hash.setdefault(name_hash, index)
    animation_to_transform = []
    for bone_name, bone_hash in zip(bones.names, bones.hashes):
        transform_index = transform_by_hash.get(bone_hash)
        if transform_index is None:
            raise ValueError(
                f"Animated bone '{bone_name}' ({bone_hash}) is missing from Unit TransformInfo"
            )
        animation_to_transform.append(transform_index)
    transform_to_animation = {
        transform_index: animation_index
        for animation_index, transform_index in enumerate(animation_to_transform)
    }
    if apply_ik_correction:
        for target_name, (root_index, mid_index, target_index) in ik_indices.items():
            root_transform = animation_to_transform[root_index]
            mid_transform = animation_to_transform[mid_index]
            target_transform = animation_to_transform[target_index]
            if unit.parents[mid_transform] != root_transform:
                raise ValueError(
                    f"IK chain {target_name!r} requires its second bone to be a direct child of the first"
                )
            if unit.parents[target_transform] != mid_transform:
                raise ValueError(
                    f"IK chain {target_name!r} requires the target bone to be a direct child of the second bone"
                )
            ik_indices[target_name] = (root_transform, mid_transform, target_transform)
    configured_transform_offsets = (
        {
            animation_to_transform[bone_name_to_index[name]]: offset
            for name, offset in config.offsets.items()
        }
        if apply_offsets_to_additive or not animation.is_additive
        else {}
    )
    configured_distance_multipliers = {
        animation_to_transform[bone_name_to_index[name]]: multiplier
        for name, multiplier in config.distance_multipliers.items()
    }
    position_tracks, rotation_tracks, scale_tracks = _build_tracks(animation)
    last_transform_time = _last_transform_time(animation)
    reference_dense = playback_reference is not None and not animation.is_additive
    sample_times = _build_bake_times(last_transform_time)
    if reference_dense:
        if playback_reference.is_additive or len(playback_reference.initial_bone_states) != len(bones.names):
            raise ValueError('Playback reference skeleton/additive type differs')
        if any(state.compress_position or state.compress_rotation or state.compress_scale
               for state in playback_reference.initial_bone_states):
            raise ValueError('Normal playback reference must have a complete uncompressed initial pose')
        pose_keys = {}
        for entry in playback_reference.entries:
            if entry.is_position or entry.is_rotation:
                if entry.type != 0 or entry.subtype not in (4,5):
                    raise ValueError('Normal playback reference must use dense float pose keys')
                pose_keys.setdefault(float(entry.time),set()).add((entry.bone,entry.subtype))
        expected = {(i,k) for i in range(len(bones.names)) for k in (4,5)}
        if any(keys != expected for keys in pose_keys.values()):
            raise ValueError('Normal playback reference has an incomplete pose frame')
        sample_times = [0.0] + sorted(time for time in pose_keys if time > 0.)
    elif preserve_playback_timing:
        sample_times = _build_playback_times(animation)
    elif preserve_source_key_times and (animation.is_additive or preserve_unmodified_channels):
        # Keep native control points, including short recoil peaks, when a
        # standard modifier genuinely requires additive baking. Unchanged
        # additive channels still follow the existing passthrough path below.
        sample_times = sorted(set(sample_times) | {
            float(entry.time) for entry in source_transform_entries
            if 0.0 <= entry.time <= last_transform_time
        })
    generated_positions: dict[int, list[tuple[float, list[float]]]] = {
        animation_index: [] for animation_index in range(len(bones.names))
    }
    generated_rotations: dict[int, list[tuple[float, list[float]]]] = {
        animation_index: [] for animation_index in range(len(bones.names))
    }
    ik_corrections = 0
    ik_evaluations = 0
    ik_max_error_before = 0.0
    ik_max_error_after = 0.0
    arm_target_projections = 0
    arm_requested_target_max_distance = 0.0
    ik_changed_animation_indices: set[int] = set()

    for time in sample_times:
        local_transforms = [
            WorldTransform(
                position=list(transform.position),
                rotation=list(transform.rotation),
                scale=list(transform.scale),
            )
            for transform in unit.transforms
        ]
        for animation_index, transform_index in enumerate(animation_to_transform):
            sampled = WorldTransform(
                position=position_tracks[animation_index].evaluate(time),
                rotation=rotation_tracks[animation_index].evaluate(time),
                scale=scale_tracks[animation_index].evaluate(time),
            )
            if animation.is_additive:
                base = unit.transforms[transform_index]
                local_transforms[transform_index] = _compose_additive_local(base, sampled)
            else:
                local_transforms[transform_index] = sampled

        original_world = _calculate_world_transforms(local_transforms, unit.parents)
        new_world_positions: dict[int, list[float]] = {}
        new_local_positions: dict[int, list[float]] = {}
        effective_local_positions: dict[int, list[float]] = {}

        def calculate_new_position(transform_index: int) -> list[float]:
            cached = new_world_positions.get(transform_index)
            if cached is not None:
                return cached
            parent = unit.parents[transform_index]
            parent_position = (
                [0.0, 0.0, 0.0] if parent is None else calculate_new_position(parent)
            )
            if transform_index in transform_to_animation:
                configured_offset = configured_transform_offsets.get(transform_index)
                local_position = list(local_transforms[transform_index].position)
                if configured_offset is not None:
                    # generate-config emits a local Unit-transform delta for
                    # each bone. Apply every configured delta independently so
                    # a parent/child chain matches base_anim segment lengths.
                    local_position = vec_add(local_position, configured_offset)
                    if parent is not None:
                        multiplier = configured_distance_multipliers.get(
                            transform_index, 1.0
                        )
                        local_position = [value * multiplier for value in local_position]
                if parent is None:
                    target = local_position
                elif configured_offset is not None:
                    target = vec_add(
                        parent_position,
                        quat_rotate(
                            original_world[parent].rotation,
                            vec_mul(original_world[parent].scale, local_position),
                        ),
                    )
                else:
                    # Unconfigured animated descendants retain their sampled
                    # parent-child world segment when an ancestor moves.
                    target = vec_add(
                        parent_position,
                        vec_sub(
                            original_world[transform_index].position,
                            original_world[parent].position,
                        ),
                    )
                    local_position = vec_div(
                        quat_inverse_rotate(
                            original_world[parent].rotation,
                            vec_sub(target, parent_position),
                        ),
                        original_world[parent].scale,
                    )
                if animation.is_additive:
                    base = unit.transforms[transform_index]
                    effective_local_positions[transform_index] = list(local_position)
                    local_position = _decompose_additive_position(base, local_position)
                else:
                    effective_local_positions[transform_index] = list(local_position)
                new_local_positions[transform_index] = local_position
                new_world_positions[transform_index] = target
                return target

            local = local_transforms[transform_index]
            if parent is None:
                world_position = list(local.position)
            else:
                world_segment = vec_sub(
                    original_world[transform_index].position,
                    original_world[parent].position,
                )
                world_position = vec_add(
                    parent_position,
                    world_segment,
                )
            new_world_positions[transform_index] = world_position
            return world_position

        for transform_index in range(len(unit.transforms)):
            calculate_new_position(transform_index)
        for transform_index, local_position in new_local_positions.items():
            local_transforms[transform_index].position = list(
                effective_local_positions[transform_index]
            )

        for animation_index, transform_index in enumerate(animation_to_transform):
            rotation = rotation_tracks[animation_index].evaluate(time)
            if animation.is_additive:
                rotation = quat_multiply(
                    unit.transforms[transform_index].rotation,
                    rotation,
                )
            if apply_rotation_compensations:
                correction = config.rotation_compensations.get(bones.names[animation_index])
                if correction is not None:
                    rotation = quat_normalize(quat_multiply(correction, rotation))
            if apply_rotate_multipliers:
                bone_name = bones.names[animation_index]
                multiplier = config.rotate_multipliers.get(bone_name, 1.0)
                if multiplier != 0.0:
                    rotation = quat_scale_angle(rotation, multiplier)
            local_transforms[transform_index].rotation = list(rotation)

        if apply_ik_correction:
            fk_targets = {}
            for target_name, (_, _, target_transform) in ik_indices.items():
                fk_target = new_world_positions[target_transform]
                original_target = original_world[target_transform].position
                multiplier = config.ik_chains[target_name].target_multiplier
                fk_targets[target_name] = vec_add(
                    original_target,
                    vec_mul(vec_sub(fk_target, original_target), multiplier),
                )
            current_world = _calculate_world_transforms(local_transforms, unit.parents)
            for target_name, (root_transform, mid_transform, target_transform) in ik_indices.items():
                target = fk_targets[target_name]
                hinge_axis = reference_direction = None
                constrained_arm = source_arm_constraints and not animation.is_additive and target_name in ('l_hand', 'r_hand')
                if constrained_arm:
                    # The requested ray is still the real standard IK target, not
                    # our current FK. A source-sized limb cannot reproduce the
                    # original Avatar's reach. Project its distance using the SOURCE
                    # elbow angle and actual new lengths; retain target direction.
                    r, m, h = (current_world[i] for i in (root_transform, mid_transform, target_transform))
                    sr, sm, sh = (original_world[i] for i in (root_transform, mid_transform, target_transform))
                    a, b = vec_sub(sm.position, sr.position), vec_sub(sh.position, sm.position)
                    la, lb = _distance(a, [0.,0.,0.]), _distance(b, [0.,0.,0.])
                    na, nb = _distance(r.position, m.position), _distance(m.position, h.position)
                    if la*lb > 1e-12 and na*nb > 1e-12:
                        cosine = max(-1., min(1., sum(x*y for x,y in zip(a,b))/(la*lb)))
                        reach = sqrt(max(0., na*na+nb*nb+2*na*nb*cosine))
                        ray = _normalize_vector(vec_sub(target,r.position),vec_sub(sh.position,sr.position))
                        projected = vec_add(r.position,[v*reach for v in ray])
                        displacement = _distance(projected,target)
                        if displacement > 1e-5:arm_target_projections += 1
                        arm_requested_target_max_distance = max(arm_requested_target_max_distance,displacement)
                        target = projected
                        plane = _cross(a,b)
                        if _distance(plane,[0.,0.,0.]) > la*lb*1e-5:
                            hinge_axis = quat_inverse_rotate(sr.rotation,_normalize_vector(plane))
                            reference_direction = quat_rotate(r.rotation,quat_inverse_rotate(sr.rotation,vec_sub(sh.position,sr.position)))
                before = _distance(current_world[target_transform].position, target)
                target_world_rotation = list(current_world[target_transform].rotation)
                previous_joint_rotations = {i:list(local_transforms[i].rotation) for i in (root_transform,mid_transform,target_transform)}
                twist_transform = None
                twist_world_rotation = None
                if constrained_arm:
                    twist_name = target_name.replace('_hand','_hand_twist')
                    if twist_name in bone_name_to_index:
                        twist_transform = animation_to_transform[bone_name_to_index[twist_name]]
                        if unit.parents[twist_transform] == mid_transform:
                            twist_world_rotation = list(current_world[twist_transform].rotation)
                ik_max_error_before = max(ik_max_error_before, before)
                ik_evaluations += 1
                _apply_two_bone_ik(
                    local_transforms,
                    unit.parents,
                    root_transform,
                    mid_transform,
                    target_transform,
                    target,
                    target_world_rotation,
                    preserve_bend_frame=constrained_arm or (preserve_hand_bend_frame and target_name in ('l_hand', 'r_hand')),
                    hinge_axis=hinge_axis,
                    reference_direction=reference_direction,
                )
                current_world = _calculate_world_transforms(local_transforms, unit.parents)
                if constrained_arm:
                    # The wrist twist is a sibling of the hand, not its child.
                    # Preserve its independent input WORLD orientation when IK
                    # rotates the forearm; do not inject the forearm's new roll.
                    if twist_world_rotation is not None:
                        local_transforms[twist_transform].rotation = quat_normalize(quat_multiply(
                            quat_inverse(current_world[mid_transform].rotation),twist_world_rotation))
                        ik_changed_animation_indices.add(transform_to_animation[twist_transform])
                    for i,rotation in previous_joint_rotations.items():
                        if abs(sum(a*b for a,b in zip(rotation,local_transforms[i].rotation))) < 1.-1e-10:
                            ik_changed_animation_indices.add(transform_to_animation[i])
                after = _distance(current_world[target_transform].position, target)
                ik_max_error_after = max(ik_max_error_after, after)
                if before > 1e-5 and after < before:
                    ik_corrections += 1
                    ik_changed_animation_indices.update(
                        transform_to_animation[index]
                        for index in (root_transform, mid_transform, target_transform)
                        if index in transform_to_animation
                    )

        for animation_index, transform_index in enumerate(animation_to_transform):
            generated_positions[animation_index].append(
                (time, new_local_positions[transform_index])
            )
            rotation = list(local_transforms[transform_index].rotation)
            if animation.is_additive:
                rotation = quat_normalize(
                    quat_multiply(
                        quat_inverse(unit.transforms[transform_index].rotation),
                        rotation,
                    )
                )
            generated_rotations[animation_index].append(
                (time, rotation)
            )

    position_changed_indices = set()
    for animation_index, values in generated_positions.items():
        if any(
            not vec_close(value, position_tracks[animation_index].evaluate(time))
            for time, value in values
        ):
            position_changed_indices.add(animation_index)
    changed_indices = sorted(position_changed_indices | ik_changed_animation_indices)
    if reference_dense:
        # The user-accepted playback pack is the authority for untouched rotation
        # channels and the boundary scale pose, not the sparse game-source layout.
        # Keep model-dependent IK / explicit rotation edits; copy other reference
        # controls verbatim so their start/end interpolation is exactly comparable.
        changed_rotations = set(ik_changed_animation_indices)
        if apply_ik_correction:
            changed_rotations.update(transform_to_animation[i] for chain in ik_indices.values() for i in chain)
        if apply_rotation_compensations:
            changed_rotations.update(bone_name_to_index[n] for n in config.rotation_compensations)
        if apply_rotate_multipliers:
            changed_rotations.update(bone_name_to_index[n] for n,v in config.rotate_multipliers.items() if v != 1.0)
        reference_rotations = {(entry.bone,float(entry.time)):entry.data2
            for entry in playback_reference.entries if entry.is_rotation}
        for i in range(len(bones.names)):
            if i not in changed_rotations:
                generated_rotations[i] = [(0.,list(playback_reference.initial_bone_states[i].rotation))] + [
                    (time,list(reference_rotations[(i,time)])) for time in sample_times[1:]]

    # Batch Additive exports use the patched Unit as the position basis. Keep
    # untouched source channels and the source frame-zero pose so blending into
    # the clip does not introduce a new discontinuity. Only IK or explicitly
    # requested rotation processing needs newly baked rotation keys.
    preserve_additive_source = animation.is_additive and not apply_offsets_to_additive
    if (preserve_additive_source or preserve_unmodified_channels) and not reference_dense:
        output_position_indices = position_changed_indices
        output_rotation_indices = set(ik_changed_animation_indices)
        if apply_rotation_compensations:
            output_rotation_indices.update(
                bone_name_to_index[name]
                for name in config.rotation_compensations
            )
        if apply_rotate_multipliers:
            output_rotation_indices.update(
                bone_name_to_index[name]
                for name in config.rotate_multipliers
            )
    else:
        output_position_indices = set(range(len(bones.names)))
        output_rotation_indices = set(range(len(bones.names)))

    if not output_position_indices and not output_rotation_indices:
        animation.initial_bone_states = source_initial_bone_states
        animation.entries = source_entries
        return ModificationResult(
            changed_bones=[],
            generated_position_keys=0,
            sample_count=len(sample_times),
            ik_evaluations=ik_evaluations,
            unchanged=True,
        )

    # Blender's exporter writes a complete uncompressed pose at frame zero,
    # then one position and one rotation key for every bone at every baked
    # frame. Keep event records, but discard every source transform record.
    if (preserve_additive_source or preserve_unmodified_channels) and not reference_dense:
        animation.initial_bone_states = source_initial_bone_states
    else:
        animation.initial_bone_states = [
            AnimationBoneState(
                position=list(generated_positions[index][0][1]),
                rotation=list(generated_rotations[index][0][1]),
                # Keep the source rest scale in the complete frame-zero pose.
                # Game animations commonly use a uniform scale just below one;
                # replacing it with identity changes every parent-child world
                # segment and appears as arm/limb stretching.
                scale=(
                    [0.0, 0.0, 0.0]
                    if animation.is_additive
                    else list(playback_reference.initial_bone_states[index].scale) if reference_dense
                    else list(scale_tracks[index].evaluate(0.0))
                ),
                compress_position=False,
                compress_rotation=False,
                compress_scale=False,
            )
            for index in range(len(bones.names))
        ]
    if (preserve_additive_source or preserve_unmodified_channels) and not reference_dense:
        for index in output_position_indices:
            animation.initial_bone_states[index].position = list(
                generated_positions[index][0][1]
            )
            animation.initial_bone_states[index].compress_position = False
        for index in output_rotation_indices:
            animation.initial_bone_states[index].rotation = list(
                generated_rotations[index][0][1]
            )
            animation.initial_bone_states[index].compress_rotation = False

    event_entries = [
        entry
        for entry in animation.entries
        if not (entry.is_position or entry.is_rotation or entry.is_scale)
    ]
    baked_entries = []
    seen_transform_keys = set()
    for sample_index, time in enumerate(sample_times[1:], start=1):
        for animation_index in range(len(bones.names)):
            if animation_index in output_position_indices:
                position = generated_positions[animation_index][sample_index][1]
                key = (animation_index, "position", _wire_time_key(time) if preserve_playback_timing or reference_dense else int(time))
                if key not in seen_transform_keys:
                    seen_transform_keys.add(key)
                    baked_entries.append(
                        AnimationEntry(
                            type=0,
                            subtype=4,
                            bone=animation_index,
                            time=float(time) if preserve_source_key_times or preserve_playback_timing or reference_dense else int(time),
                            data2=list(position),
                        )
                    )
            if animation_index in output_rotation_indices:
                rotation = generated_rotations[animation_index][sample_index][1]
                key = (animation_index, "rotation", _wire_time_key(time) if preserve_playback_timing or reference_dense else int(time))
                if key not in seen_transform_keys:
                    seen_transform_keys.add(key)
                    baked_entries.append(
                        AnimationEntry(
                            type=0,
                            subtype=5,
                            bone=animation_index,
                            time=float(time) if preserve_source_key_times or preserve_playback_timing or reference_dense else int(time),
                            data2=list(rotation),
                        )
                    )

    preserved_entries = [
        entry
        for entry in source_transform_entries
        if not (
            (entry.is_position and entry.bone in output_position_indices)
            or (entry.is_rotation and entry.bone in output_rotation_indices)
        )
    ]
    animation.entries = sorted(
        event_entries + preserved_entries + baked_entries,
        key=lambda entry: entry.time,
    )
    animation.animation_length = (playback_reference.animation_length if reference_dense else
        source_animation_length if preserve_playback_timing else last_transform_time / 1000.0)
    generated_key_count = len(generated_positions) * max(0, len(sample_times) - 1)
    return ModificationResult(
        changed_bones=[bones.names[index] for index in changed_indices],
        generated_position_keys=generated_key_count,
        sample_count=len(sample_times),
        ik_corrections=ik_corrections,
        ik_evaluations=ik_evaluations,
        ik_max_error_before=ik_max_error_before,
        ik_max_error_after=ik_max_error_after,
        arm_target_projections=arm_target_projections,
        arm_requested_target_max_distance=arm_requested_target_max_distance,
    )


def _distance(a, b):
    return sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _normalize_vector(vector, fallback=None):
    length = sqrt(sum(component * component for component in vector))
    if length < 1e-8:
        return list(fallback or [1.0, 0.0, 0.0])
    return [component / length for component in vector]


def _cross(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _quat_from_to(source, target):
    source = _normalize_vector(source)
    target = _normalize_vector(target)
    dot = max(-1.0, min(1.0, sum(source[index] * target[index] for index in range(3))))
    if dot > 1.0 - 1e-7:
        return [0.0, 0.0, 0.0, 1.0]
    if dot < -1.0 + 1e-7:
        axis = _cross(source, [1.0, 0.0, 0.0])
        if _distance(axis, [0.0, 0.0, 0.0]) < 1e-7:
            axis = _cross(source, [0.0, 1.0, 0.0])
        axis = _normalize_vector(axis)
        return [axis[0], axis[1], axis[2], 0.0]
    axis = _cross(source, target)
    return quat_normalize([axis[0], axis[1], axis[2], 1.0 + dot])


def _apply_two_bone_ik(
    local_transforms,
    parents,
    root_index,
    mid_index,
    target_index,
    target,
    target_world_rotation=None,
    *,
    pole_state=None,
    soft_distance=0.0,
    delta_time=1.0 / 30.0,
    preserve_bend_frame=False,
    hinge_axis=None,
    reference_direction=None,
):
    """Adjust a direct two-bone chain while preserving position and end rotation."""
    current = _calculate_world_transforms(local_transforms, parents, (root_index, mid_index, target_index))
    root = current[root_index]
    mid = current[mid_index]
    end = current[target_index]
    first_vector = vec_sub(mid.position, root.position)
    second_vector = vec_sub(end.position, mid.position)
    first_length = _distance(mid.position, root.position)
    second_length = _distance(end.position, mid.position)
    if first_length < 1e-8 or second_length < 1e-8:
        return

    target_vector = vec_sub(target, root.position)
    target_distance = _distance(target, root.position)
    direction = _normalize_vector(target_vector, first_vector)
    minimum = abs(first_length - second_length) + 1e-7
    maximum = first_length + second_length - 1e-7
    clamped_distance = max(minimum, min(maximum, target_distance))
    if soft_distance > 0.0:
        from math import exp
        soft = min(soft_distance, (maximum - minimum) * .25)
        threshold = maximum - soft
        if target_distance > threshold:
            clamped_distance = maximum - soft * exp(-(target_distance - threshold) / soft)
    if target_distance < 1e-8:
        direction = _normalize_vector(first_vector)

    current_mid_offset = vec_sub(mid.position, root.position)
    current_parallel = [
        component * sum(current_mid_offset[index] * direction[index] for index in range(3))
        for component in direction
    ]
    current_bend = vec_sub(current_mid_offset, current_parallel)
    if _distance(current_bend, [0.0, 0.0, 0.0]) >= 1e-7:
        # Keep the existing elbow side. Recomputing this from a cross-product
        # alone flips the bend when the target crosses the chain axis.
        bend_side = _normalize_vector(current_bend)
    else:
        bend_normal = _cross(first_vector, second_vector)
        if _distance(bend_normal, [0.0, 0.0, 0.0]) < 1e-7:
            bend_normal = _cross(first_vector, quat_rotate(root.rotation, [0.0, 0.0, 1.0]))
            if _distance(bend_normal, [0.0, 0.0, 0.0]) < 1e-7:
                bend_normal = _cross(first_vector, quat_rotate(root.rotation, [0.0, 1.0, 0.0]))
        bend_normal = _normalize_vector(bend_normal)
        bend_side = _normalize_vector(_cross(bend_normal, direction))
    if pole_state is not None or preserve_bend_frame:
        # Keep the pole in the shoulder parent's coordinates. World-space
        # history would oppose actor turns. Rate-limit only the pole, not the
        # hand target; a near-straight input otherwise flips the elbow plane.
        from math import atan2, cos, sin, pi
        plane = quat_rotate(root.rotation,hinge_axis) if hinge_axis is not None else _cross(first_vector, second_vector)
        if _distance(plane,[0.,0.,0.]) >= first_length*second_length*1e-5:
            # Transport the input chain's whole bend plane toward the target.
            # Projecting only its upper arm onto the target ray is singular
            # whenever that ray crosses the upper-arm axis.
            swing = _quat_from_to(reference_direction if reference_direction is not None else vec_sub(end.position,root.position),direction)
            plane = quat_rotate(swing,_normalize_vector(plane))
            # first x second points opposite to direction x elbow_offset.
            # Reversing this cross product reflects even a fully bent elbow.
            bend_side = _normalize_vector(_cross(direction,plane),bend_side)
    if pole_state is not None:
        from math import atan2, cos, sin, pi
        parent = parents[root_index]
        parent_rotation = current[parent].rotation if parent is not None else [0., 0., 0., 1.]
        if 'pole' in pole_state:
            previous_pole = quat_rotate(parent_rotation, pole_state['pole'])
            previous_pole = vec_sub(previous_pole, [d * sum(a*b for a,b in zip(previous_pole,direction)) for d in direction])
            if _distance(previous_pole, [0.,0.,0.]) > 1e-6:
                previous_pole = _normalize_vector(previous_pole)
                cosine = max(-1., min(1., sum(a*b for a,b in zip(previous_pole,bend_side))))
                # The input elbow plane has no reliable sign near extension.
                # Choose its continuous hemisphere instead of orbiting halfway
                # around the arm when a tiny input bend changes sign.
                near_extension = (
                    sum(a*b for a,b in zip(first_vector,second_vector))
                    / (first_length*second_length) > .999
                )
                if cosine < 0. and near_extension:
                    bend_side = [-v for v in bend_side]
                    cosine = -cosine
                sine = sum(a*b for a,b in zip(_cross(previous_pole,bend_side), direction))
                angle = atan2(sine, cosine)
                limit = max(0., delta_time) * 4. * pi
                angle = max(-limit, min(limit, angle))
                tangent = _cross(direction, previous_pole)
                bend_side = [a*cos(angle)+b*sin(angle) for a,b in zip(previous_pole,tangent)]
        pole_state['pole'] = quat_inverse_rotate(parent_rotation, bend_side)
    first_projection = (
        clamped_distance * clamped_distance
        + first_length * first_length
        - second_length * second_length
    ) / (2.0 * clamped_distance)
    bend_height = sqrt(max(0.0, first_length * first_length - first_projection * first_projection))
    desired_mid = vec_add(
        root.position,
        vec_add(
            [component * first_projection for component in direction],
            [component * bend_height for component in bend_side],
        ),
    )
    desired_first_vector = vec_sub(desired_mid, root.position)
    root_delta = _quat_from_to(first_vector, desired_first_vector)
    endpoint = vec_add(root.position, [d*clamped_distance for d in direction]) if pole_state is not None or soft_distance > 0. else target
    desired_second_vector = vec_sub(endpoint, desired_mid)
    constrained_frame = False
    if pole_state is not None or preserve_bend_frame:
        # A pole determines the whole arm plane, not just the elbow position.
        # Transport both axes of the upper-arm frame into that plane. A
        # shortest-arc swing alone, followed by independently limited rolls,
        # can put a valid elbow on the back of its own upper-arm frame.
        input_normal = _cross(first_vector, second_vector)
        if hinge_axis is not None:
            input_normal = quat_rotate(root.rotation, hinge_axis)
        elif _distance(input_normal, [0., 0., 0.]) >= first_length*second_length*1e-5:
            input_normal = _normalize_vector(input_normal)
            if pole_state is not None:
                pole_state['hinge_normal'] = quat_inverse_rotate(root.rotation, input_normal)
        elif pole_state is not None and 'hinge_normal' in pole_state:
            input_normal = quat_rotate(root.rotation, pole_state['hinge_normal'])
        desired_normal = _cross(desired_first_vector, desired_second_vector)
        if (_distance(input_normal, [0., 0., 0.]) > 1e-8
                and _distance(desired_normal, [0., 0., 0.]) > 1e-8):
            axis = _normalize_vector(desired_first_vector)
            swung_normal = quat_rotate(root_delta, input_normal)
            swung_normal = vec_sub(swung_normal, [v*sum(a*b for a,b in zip(swung_normal,axis)) for v in axis])
            if _distance(swung_normal, [0., 0., 0.]) > 1e-8:
                # atan2 gives the roll explicitly about the segment axis,
                # including the antiparallel-normal case.
                from math import atan2, sin, cos
                start_normal = _normalize_vector(swung_normal)
                end_normal = _normalize_vector(desired_normal)
                roll = atan2(sum(a*b for a,b in zip(_cross(start_normal,end_normal),axis)),
                             sum(a*b for a,b in zip(start_normal,end_normal)))
                correction = [v*sin(roll/2) for v in axis]+[cos(roll/2)]
                root_delta = quat_normalize(quat_multiply(correction, root_delta))
                constrained_frame = True
    desired_root_rotation = quat_normalize(quat_multiply(root_delta, root.rotation))

    rotated_second_vector = quat_rotate(root_delta, second_vector)
    mid_delta = _quat_from_to(rotated_second_vector, desired_second_vector)
    desired_mid_rotation = quat_normalize(
        quat_multiply(mid_delta, quat_multiply(root_delta, mid.rotation))
    )
    if pole_state is not None:
        # Keep both input joint frames. At a straight-arm singularity the
        # shortest-arc solution can jump in axial roll; limit only that roll
        # against the previous frame transported onto the new bone direction.
        # Swing, bone lengths, wrist position and palm orientation stay exact.
        from math import atan2, sin, cos, pi
        frames = pole_state.setdefault('joint_frames', {})
        def continuous_roll(key, desired, direction):
            axis = _normalize_vector(direction)
            if key in frames:
                old_q, old_axis = frames[key]
                old_q = quat_multiply(parent_rotation, old_q)
                old_axis = quat_rotate(parent_rotation, old_axis)
                dot = max(-1.,min(1.,sum(a*b for a,b in zip(old_axis,axis))))
                # No near-parallel dead zone: dropping tiny transports on
                # successive samples accumulates a visible hand-position drift.
                swing = quat_normalize([*_cross(old_axis,axis),1.+dot]) if dot > -1.+1e-12 else _quat_from_to(old_axis,axis)
                transported = quat_normalize(quat_multiply(swing,old_q))
                difference = quat_normalize(quat_multiply(desired,quat_inverse(transported)))
                if difference[3] < 0: difference = [-v for v in difference]
                roll = 2*atan2(sum(difference[i]*axis[i] for i in range(3)),difference[3])
                limit = max(0.,delta_time)*4*pi
                roll = max(-limit,min(limit,roll))
                twist = [v*sin(roll/2) for v in axis]+[cos(roll/2)]
                desired = quat_normalize(quat_multiply(twist,transported))
            frames[key] = (quat_multiply(quat_inverse(parent_rotation),desired),quat_inverse_rotate(parent_rotation,axis))
            return desired
        if constrained_frame:
            # Limiting this roll separately would break the plane constraint.
            # The pole itself has already been rate-limited above.
            frames['upper'] = (quat_multiply(quat_inverse(parent_rotation),desired_root_rotation),
                               quat_inverse_rotate(parent_rotation,_normalize_vector(desired_first_vector)))
        else:
            desired_root_rotation = continuous_roll('upper',desired_root_rotation,desired_first_vector)
        desired_mid_rotation = continuous_roll('forearm',desired_mid_rotation,desired_second_vector)

    parent = parents[root_index]
    if parent is None:
        local_transforms[root_index].rotation = desired_root_rotation
    else:
        local_transforms[root_index].rotation = quat_normalize(
            quat_multiply(quat_inverse(current[parent].rotation), desired_root_rotation)
        )
    local_transforms[mid_index].rotation = quat_normalize(
        quat_multiply(quat_inverse(desired_root_rotation), desired_mid_rotation)
    )
    if target_world_rotation is not None:
        updated_world = _calculate_world_transforms(local_transforms, parents, (target_index,))
        target_parent = parents[target_index]
        if target_parent is None:
            local_transforms[target_index].rotation = quat_normalize(
                target_world_rotation
            )
        else:
            local_transforms[target_index].rotation = quat_normalize(
                quat_multiply(
                    quat_inverse(updated_world[target_parent].rotation),
                    target_world_rotation,
                )
            )


def _compose_additive_local(base, delta: WorldTransform) -> WorldTransform:
    """Compose a plugin additive basis transform onto the Unit local rest TRS."""
    return WorldTransform(
        position=vec_add(
            base.position,
            quat_rotate(base.rotation, vec_mul(base.scale, delta.position)),
        ),
        rotation=quat_multiply(base.rotation, delta.rotation),
        # The Blender importer uses identity scale for additive matrix_basis.
        scale=list(base.scale),
    )


def _decompose_additive_position(base, effective_position):
    """Convert an effective local position back to the additive position delta."""
    return vec_div(
        quat_inverse_rotate(
            base.rotation,
            vec_sub(effective_position, base.position),
        ),
        base.scale,
    )


def _build_tracks(animation: AnimationData):
    positions = [
        [(0.0, state.position)] for state in animation.initial_bone_states
    ]
    rotations = [
        [(0.0, state.rotation)] for state in animation.initial_bone_states
    ]
    scales = [[(0.0, state.scale)] for state in animation.initial_bone_states]
    for entry in animation.entries:
        # Event records (type=0, subtype=2) carry an event/hash value in the
        # bone field, so only transform records can be validated/indexed here.
        if entry.is_position or entry.is_rotation or entry.is_scale:
            if entry.bone < 0 or entry.bone >= len(animation.initial_bone_states):
                raise ValueError(
                    f"Animation entry references invalid bone index {entry.bone}"
                )
        if entry.is_position:
            positions[entry.bone].append((entry.time, entry.data2))
        elif entry.is_rotation:
            rotations[entry.bone].append((entry.time, entry.data2))
        elif entry.is_scale:
            scales[entry.bone].append((entry.time, entry.data2))
    return (
        [Track(keys, vec_lerp) for keys in positions],
        [Track(keys, quat_slerp) for keys in rotations],
        [Track(keys, vec_lerp) for keys in scales],
    )


def _last_transform_time(animation: AnimationData) -> float:
    """Return the final source position/rotation key, excluding events/scales."""
    transform_times = [
        entry.time
        for entry in animation.entries
        if entry.is_position or entry.is_rotation
    ]
    if transform_times:
        return max(transform_times)
    return animation.animation_length * 1000.0


def _wire_time_key(time_ms):
    # Uncompressed HD2 keys store seconds as float32. Deduplicate only keys
    # that actually have the same serialized timestamp, not the same integer ms.
    import struct
    return struct.pack('<f', float(time_ms) / 1000.0)


def _build_playback_times(animation):
    """Native clip clock plus control points; never append a ceil-rounded hold frame."""
    import struct
    duration = float(animation.animation_length) * 1000.0
    if not isfinite(duration) or duration < 0:
        raise ValueError('Animation duration must be finite and non-negative')
    selected = {}
    def add(time, priority):
        if not isfinite(time) or time < 0:
            raise ValueError('Animation key time must be finite and non-negative')
        key = _wire_time_key(time)
        old = selected.get(key)
        if old is None or (priority, time) >= (old[0], old[1]):
            selected[key] = (priority, time)
    # Keep the existing 30Hz approximation only inside the native playback
    # interval. Source control times take precedence over redundant grid keys.
    frame_count = ceil(duration * 30.0 / 1000.0)
    for frame in range(1, frame_count):
        time = frame * 1000.0 / 30.0
        if time < duration and struct.unpack('<f', _wire_time_key(time))[0] * 1000.0 <= duration:
            add(time, 0)
    for entry in animation.entries:
        if entry.is_position or entry.is_rotation or entry.is_scale:
            # Existing native tail records are retained, not silently cropped.
            add(float(entry.time), 3)
    add(0.0, 2)
    add(duration, 2)
    return sorted(value[1] for value in selected.values())


def _build_bake_times(last_transform_time: float) -> list[float]:
    """Match the Blender exporter: frame zero through ceil(action.end)."""
    frame_count = ceil(max(0.0, last_transform_time) * 30.0 / 1000.0)
    times = [0.0]
    seen = {0}
    for frame in range(1, frame_count + 1):
        time = int(1000 * frame / 30)
        if time not in seen:
            seen.add(time)
            times.append(float(time))
    return times


def _calculate_world_transforms(local_transforms, parents, required_indices=None):
    result: list[WorldTransform | None] = [None] * len(local_transforms)
    active = set()

    def calculate(index: int) -> WorldTransform:
        cached = result[index]
        if cached is not None:
            return cached
        if index in active:
            raise ValueError(f"Cycle detected in Unit transform hierarchy at index {index}")
        active.add(index)
        local = local_transforms[index]
        parent = parents[index]
        if parent is None:
            world = WorldTransform(
                position=list(local.position),
                rotation=list(local.rotation),
                scale=list(local.scale),
            )
        else:
            parent_world = calculate(parent)
            world = WorldTransform(
                position=vec_add(
                    parent_world.position,
                    quat_rotate(
                        parent_world.rotation,
                        vec_mul(parent_world.scale, local.position),
                    ),
                ),
                rotation=quat_multiply(parent_world.rotation, local.rotation),
                scale=vec_mul(parent_world.scale, local.scale),
            )
        active.remove(index)
        result[index] = world
        return world

    for transform_index in range(len(local_transforms)) if required_indices is None else required_indices:
        calculate(transform_index)
    return result


def _parent_chain(index: int, parents: list[int | None]):
    """Yield the strict ancestors of a transform, nearest first."""
    seen = set()
    parent = parents[index]
    while parent is not None:
        if parent in seen:
            raise ValueError(f"Cycle detected in Unit transform hierarchy at index {index}")
        seen.add(parent)
        yield parent
        parent = parents[parent]
