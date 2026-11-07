from __future__ import annotations

import copy
import hashlib
import struct
from collections import deque
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

from .archive import PackageStore, ResourceIndex, TocArchive, TocEntry
from .constants import ANIMATION_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID, UNIT_TYPE_ID
from .formats import (
    AnimationData,
    BonesData,
    UnitData,
    parse_state_machine_animation_ids,
    patch_unit_positions,
)
from .processor import ModConfig, ModificationResult, modify_animation_with_world_compensation


@dataclass(frozen=True)
class BatchSource:
    archive_name: str
    unit_id: int


@dataclass
class BatchJob:
    animation_id: int
    animation_package: str
    unit: UnitData
    bones: BonesData
    context_signature: str
    sources: list[BatchSource] = field(default_factory=list)
    unit_id: int | None = None
    config: ModConfig | None = None
    playback_reference: AnimationData | None = None


@dataclass
class BatchIssue:
    scope: str
    message: str
    fatal: bool


@dataclass
class BatchDiscovery:
    archive_count: int = 0
    unit_count: int = 0
    matched_unit_count: int = 0
    filtered_missing_required_bone: int = 0
    filtered_missing_config_bones: int = 0
    jobs: list[BatchJob] = field(default_factory=list)
    issues: list[BatchIssue] = field(default_factory=list)

    @property
    def fatal_issues(self) -> list[BatchIssue]:
        return [issue for issue in self.issues if issue.fatal]


@dataclass
class BatchAnimationResult:
    animation_id: int
    package_name: str
    modification: ModificationResult


@dataclass
class BatchBuildResult:
    entries: list[TocEntry] = field(default_factory=list)
    animations: list[BatchAnimationResult] = field(default_factory=list)
    issues: list[BatchIssue] = field(default_factory=list)

    @property
    def fatal_issues(self) -> list[BatchIssue]:
        return [issue for issue in self.issues if issue.fatal]


def discover_batch_jobs(
    store: PackageStore,
    resource_index: ResourceIndex,
    archive_names: list[str],
    config: ModConfig,
    requested_unit_id: int | None = None,
    requested_unit_ids: set[int] | None = None,
    requested_animation_id: int | None = None,
    progress=None,
    requested_animation_ids: set[int] | None = None,
    include_ik_bones: bool = False,
    skeleton_overrides=None,
    config_by_unit=None,
) -> BatchDiscovery:
    if requested_unit_id is not None and requested_unit_ids is not None:
        raise ValueError("requested_unit_id and requested_unit_ids are mutually exclusive")
    if requested_animation_id is not None and requested_animation_ids is not None:
        raise ValueError(
            "requested_animation_id and requested_animation_ids are mutually exclusive"
        )
    if requested_animation_ids is not None:
        requested_animation_ids = set(requested_animation_ids)
    discovery = BatchDiscovery(archive_count=len(archive_names))
    jobs: dict[int, BatchJob] = {}
    ambiguous_animation_ids: set[int] = set()
    bones_cache: dict[tuple[int, int | None], BonesData] = {}
    state_cache: dict[int, list[int]] = {}
    requested_unit_seen = False
    requested_unit_seen_ids: set[int] = set()
    requested_animation_seen = False
    requested_animation_seen_ids: set[int] = set()

    for archive_index, archive_name in enumerate(archive_names, start=1):
        if progress:
            progress("archive", archive_index, len(archive_names), archive_name)
        try:
            archive = TocArchive.load_toc_only(store, archive_name)
        except Exception as error:
            discovery.issues.append(
                BatchIssue(archive_name, f"Failed to read archive: {error}", True)
            )
            continue

        unit_entries = archive.entries_of_type(UNIT_TYPE_ID)
        for unit_entry in unit_entries:
            discovery.unit_count += 1
            if requested_unit_id is not None and unit_entry.file_id != requested_unit_id:
                continue
            if requested_unit_ids is not None and unit_entry.file_id not in requested_unit_ids:
                continue
            requested_unit_seen = True
            requested_unit_seen_ids.add(unit_entry.file_id)
            unit_config = config_by_unit.get(unit_entry.file_id) if config_by_unit else config
            if unit_config is None:
                discovery.issues.append(BatchIssue(
                    f"{archive_name}/{unit_entry.file_id}",
                    "No config found for Unit",
                    True,
                ))
                continue
            try:
                unit = UnitData.parse(unit_entry.toc_data)
            except Exception as error:
                discovery.issues.append(
                    BatchIssue(
                        f"{archive_name}/{unit_entry.file_id}",
                        f"Failed to parse Unit: {error}",
                        False,
                    )
                )
                continue
            if not unit.bones_ref or not unit.state_machine_ref:
                discovery.issues.append(
                    BatchIssue(
                        f"{archive_name}/{unit_entry.file_id}",
                        "Unit has no BonesRef or StateMachineRef",
                        False,
                    )
                )
                continue

            try:
                custom_bones = (
                    skeleton_overrides.get(unit_entry.file_id)
                    if skeleton_overrides is not None
                    else None
                )
                cache_key = (
                    unit.bones_ref,
                    unit_entry.file_id if custom_bones is not None else None,
                )
                bones = bones_cache.get(cache_key)
                if bones is None:
                    bones = custom_bones
                    if bones is None:
                        _, bones_entry = resource_index.resolve(
                            unit.bones_ref, BONE_TYPE_ID
                        )
                        bones = BonesData.parse(bones_entry.toc_data)
                    bones_cache[cache_key] = bones
            except Exception as error:
                discovery.issues.append(
                    BatchIssue(
                        f"{archive_name}/{unit_entry.file_id}",
                        f"Failed to resolve Bones {unit.bones_ref}: {error}",
                        False,
                    )
                )
                continue

            if unit_config.required_bone not in bones.names:
                discovery.filtered_missing_required_bone += 1
                continue
            configured_bones = set(unit_config.offsets) | set(unit_config.rotation_compensations)
            if include_ik_bones:
                configured_bones |= set(unit_config.ik_chains)
                configured_bones |= {
                    bone for chain in unit_config.ik_chains.values() for bone in chain.chain
                }
            missing_config_bones = [
                bone_name for bone_name in configured_bones if bone_name not in bones.names
            ]
            if missing_config_bones:
                discovery.filtered_missing_config_bones += 1
                discovery.issues.append(
                    BatchIssue(
                        f"{archive_name}/{unit_entry.file_id}",
                        "Required skeleton is missing configured bones: "
                        + ", ".join(missing_config_bones),
                        False,
                    )
                )
                continue

            discovery.matched_unit_count += 1
            try:
                animation_ids = state_cache.get(unit.state_machine_ref)
                if animation_ids is None:
                    _, state_entry = resource_index.resolve(
                        unit.state_machine_ref, STATE_MACHINE_TYPE_ID
                    )
                    animation_ids = parse_state_machine_animation_ids(state_entry.toc_data)
                    state_cache[unit.state_machine_ref] = animation_ids
            except Exception as error:
                discovery.issues.append(
                    BatchIssue(
                        f"{archive_name}/{unit_entry.file_id}",
                        f"Failed to resolve StateMachine {unit.state_machine_ref}: {error}",
                        True,
                    )
                )
                continue

            signature = unit_context_signature(unit, bones) + repr(unit_config)
            source = BatchSource(archive_name, unit_entry.file_id)
            for animation_id in animation_ids:
                if (
                    requested_animation_id is not None
                    and animation_id != requested_animation_id
                ):
                    continue
                if (
                    requested_animation_ids is not None
                    and animation_id not in requested_animation_ids
                ):
                    continue
                requested_animation_seen = True
                requested_animation_seen_ids.add(animation_id)
                if animation_id in ambiguous_animation_ids:
                    continue
                try:
                    animation_package = resource_index.locate(
                        animation_id, ANIMATION_TYPE_ID
                    )
                except LookupError as error:
                    discovery.issues.append(
                        BatchIssue(
                            f"animation {animation_id}",
                            f"Referenced animation could not be resolved: {error}",
                            True,
                        )
                    )
                    continue

                existing = jobs.get(animation_id)
                if existing is None:
                    jobs[animation_id] = BatchJob(
                        animation_id=animation_id,
                        animation_package=animation_package,
                        unit=unit,
                        bones=bones,
                        context_signature=signature,
                        sources=[source],
                        unit_id=unit_entry.file_id,
                        config=unit_config,
                    )
                elif existing.context_signature == signature:
                    if source not in existing.sources:
                        existing.sources.append(source)
                else:
                    jobs.pop(animation_id, None)
                    ambiguous_animation_ids.add(animation_id)
                    discovery.issues.append(
                        BatchIssue(
                            f"animation {animation_id}",
                            "The same animation is referenced by different Unit transform "
                            "contexts; no context was selected for compensation",
                            True,
                        )
                    )

    if requested_unit_id is not None and not requested_unit_seen:
        raise LookupError(
            f"Unit {requested_unit_id} was not found in the matched archives"
        )
    if requested_unit_ids is not None:
        missing_unit_ids = sorted(requested_unit_ids - requested_unit_seen_ids)
        if missing_unit_ids:
            raise LookupError(
                "Units were not found in the matched archives: "
                + ", ".join(str(unit_id) for unit_id in missing_unit_ids)
            )
    if requested_animation_id is not None and not requested_animation_seen:
        raise LookupError(
            f"Animation {requested_animation_id} is not referenced by a matched cape Unit"
        )
    if requested_animation_ids is not None:
        missing_animation_ids = sorted(
            requested_animation_ids - requested_animation_seen_ids
        )
        if missing_animation_ids:
            formatted_ids = ", ".join(
                str(animation_id) for animation_id in missing_animation_ids
            )
            raise LookupError(
                "Animations are not referenced by a matched cape Unit: "
                + formatted_ids
            )
    discovery.jobs = sorted(jobs.values(), key=lambda job: job.animation_id)
    if not discovery.jobs and not discovery.fatal_issues:
        raise LookupError(
            "No animations matched the archive keyword, cape bone filter, and config bones"
        )
    return discovery


@dataclass(frozen=True)
class _ProcessOptions:
    allow_additive: bool
    apply_rotate_multipliers: bool
    apply_rotation_compensations: bool
    apply_ik_correction: bool
    only_additive: bool
    only_non_additive: bool
    preserve_hand_bend_frame: bool
    preserve_source_key_times: bool
    preserve_unmodified_channels: bool
    source_arm_constraints: bool
    preserve_playback_timing: bool
    preserve_unchanged_bytes: bool


@dataclass(frozen=True)
class _ProcessTask:
    """Pickled once per animation; context objects are shared by the caller."""

    animation_id: int
    package_name: str
    bones: BonesData
    unit: UnitData
    additive_unit: UnitData | None
    config: ModConfig
    animation_entry: TocEntry
    playback_reference: AnimationData | None
    reference_bytes: bytes | None
    use_loader: bool
    options: _ProcessOptions


def _run_batch_animation(task: _ProcessTask):
    """Module-level worker so ProcessPoolExecutor can import it in children."""
    try:
        options = task.options
        animation = AnimationData.parse(task.animation_entry.toc_data)
        if (options.only_additive and not animation.is_additive) or (
            options.only_non_additive and animation.is_additive
        ):
            return None, None, None
        processing_unit = (
            task.additive_unit
            if animation.is_additive and task.additive_unit is not None
            else task.unit
        )
        playback_reference = task.playback_reference
        if task.use_loader:
            if playback_reference is not None:
                raise ValueError('Use either a per-job reference or a lazy playback loader')
            playback_reference = AnimationData.parse(task.reference_bytes)
            if animation.is_additive != playback_reference.is_additive:
                raise ValueError('Game/reference additive type differs')
            if animation.is_additive and bytes(task.animation_entry.toc_data) != task.reference_bytes:
                raise ValueError('Additive source differs from accepted normal reference')
        modification = modify_animation_with_world_compensation(
            animation, task.bones, processing_unit, task.config,
            allow_additive=options.allow_additive,
            apply_offsets_to_additive=False,
            apply_rotate_multipliers=options.apply_rotate_multipliers,
            apply_rotation_compensations=options.apply_rotation_compensations,
            apply_ik_correction=options.apply_ik_correction,
            preserve_hand_bend_frame=options.preserve_hand_bend_frame,
            preserve_source_key_times=options.preserve_source_key_times,
            preserve_unmodified_channels=options.preserve_unmodified_channels,
            source_arm_constraints=options.source_arm_constraints,
            preserve_playback_timing=options.preserve_playback_timing,
            playback_reference=playback_reference,
        )
        modified_entry = copy.deepcopy(task.animation_entry)
        modified_entry.toc_data = bytearray(
            task.animation_entry.toc_data
            if options.preserve_unchanged_bytes and modification.unchanged
            else animation.to_bytes()
        )
        modified_entry.gpu_data = bytearray()
        modified_entry.stream_data = bytearray()
        return modified_entry, BatchAnimationResult(
            animation_id=task.animation_id,
            package_name=task.package_name,
            modification=modification,
        ), None
    except Exception as failure:
        return None, None, BatchIssue(
            f"animation {task.animation_id}",
            f"Failed to modify animation: {failure}",
            True,
        )


def build_batch_entries(
    resource_index: ResourceIndex,
    jobs: list[BatchJob],
    config: ModConfig,
    allow_additive: bool = False,
    progress=None,
    apply_rotate_multipliers: bool = False,
    apply_rotation_compensations: bool = False,
    apply_ik_correction: bool = False,
    add_unit: bool = False,
    only_additive: bool = False,
    only_non_additive: bool = False,
    threads: int = 1,
    use_processes: bool = False,
    preserve_hand_bend_frame: bool = True,
    preserve_source_key_times: bool = False,
    preserve_unmodified_channels: bool = False,
    source_arm_constraints: bool = False,
    preserve_playback_timing: bool = False,
    preserve_unchanged_bytes: bool = False,
    playback_reference_loader: Callable[[int], bytes] | None = None,
) -> BatchBuildResult:
    if isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 16:
        raise ValueError("threads must be an integer between 1 and 16")
    if not isinstance(use_processes, bool):
        raise ValueError("use_processes must be a boolean")
    result = BatchBuildResult()
    unit_entries: dict[tuple[int, int], TocEntry] = {}
    patched_units: dict[int, UnitData] = {}
    successful_unit_keys: set[tuple[int, int]] = set()

    def prepare_job(job):
        # ResourceIndex/PackageStore have mutable LRU caches. Resolve resources
        # and patch shared Units on the caller thread, in original job order.
        try:
            job_config = job.config or config
            _, animation_entry = resource_index.resolve(job.animation_id, ANIMATION_TYPE_ID)
            animation = AnimationData.parse(animation_entry.toc_data)
            if (only_additive and not animation.is_additive) or (only_non_additive and animation.is_additive):
                return None, None
            processing_unit = job.unit
            if add_unit and job.unit_id is not None:
                unit_key = (job.unit_id, UNIT_TYPE_ID)
                if unit_key not in unit_entries:
                    _, unit_entry = resource_index.resolve(job.unit_id, UNIT_TYPE_ID)
                    unit_resource = UnitData.parse(unit_entry.toc_data)
                    patched_unit_data = patch_unit_positions(
                        unit_entry.toc_data, unit_resource, job.bones,
                        job_config.offsets, job_config.distance_multipliers,
                    )
                    patched_unit_entry = copy.deepcopy(unit_entry)
                    patched_unit_entry.toc_data = bytearray(patched_unit_data)
                    patched_unit_entry.gpu_data = bytearray()
                    patched_unit_entry.stream_data = bytearray()
                    unit_entries[unit_key] = patched_unit_entry
                    patched_units[job.unit_id] = UnitData.parse(patched_unit_data)
                if animation.is_additive:
                    processing_unit = patched_units[job.unit_id]
            return (animation_entry, animation, processing_unit, job_config), None
        except Exception as error:
            return None, error

    def process_job(job, prepared):
        data, error = prepared
        if error is None and data is None:
            return None, None, None
        if error is None:
            try:
                animation_entry, animation, processing_unit, job_config = data
                playback_reference = job.playback_reference
                if playback_reference_loader is not None:
                    if playback_reference is not None:
                        raise ValueError('Use either a per-job reference or a lazy playback loader')
                    reference_bytes = playback_reference_loader(job.animation_id)
                    playback_reference = AnimationData.parse(reference_bytes)
                    if animation.is_additive != playback_reference.is_additive:
                        raise ValueError('Game/reference additive type differs')
                    if animation.is_additive and bytes(animation_entry.toc_data) != reference_bytes:
                        raise ValueError('Additive source differs from accepted normal reference')
                modification = modify_animation_with_world_compensation(
                    animation, job.bones, processing_unit, job_config,
                    allow_additive=allow_additive,
                    apply_offsets_to_additive=False,
                    apply_rotate_multipliers=apply_rotate_multipliers,
                    apply_rotation_compensations=apply_rotation_compensations,
                    apply_ik_correction=apply_ik_correction,
                    preserve_hand_bend_frame=preserve_hand_bend_frame,
                    preserve_source_key_times=preserve_source_key_times,
                    preserve_unmodified_channels=preserve_unmodified_channels,
                    source_arm_constraints=source_arm_constraints,
                    preserve_playback_timing=preserve_playback_timing,
                    playback_reference=playback_reference,
                )
                modified_entry = copy.deepcopy(animation_entry)
                modified_entry.toc_data = bytearray(animation_entry.toc_data if preserve_unchanged_bytes and modification.unchanged else animation.to_bytes())
                modified_entry.gpu_data = bytearray()
                modified_entry.stream_data = bytearray()
                return modified_entry, BatchAnimationResult(
                    animation_id=job.animation_id,
                    package_name=job.animation_package,
                    modification=modification,
                ), None
            except Exception as failure:
                error = failure
        return None, None, BatchIssue(
            f"animation {job.animation_id}", f"Failed to modify animation: {error}", True,
        )

    def collect(job_index, job, outcome):
        entry, animation_result, issue = outcome
        if issue is not None:
            result.issues.append(issue)
        if entry is not None:
            result.entries.append(entry)
            result.animations.append(animation_result)
            if add_unit and job.unit_id is not None:
                successful_unit_keys.add((job.unit_id, UNIT_TYPE_ID))
        if progress:
            progress("animation", job_index, len(jobs), str(job.animation_id))

    if threads == 1:
        for job_index, job in enumerate(jobs, start=1):
            collect(job_index, job, process_job(job, prepare_job(job)))
    elif jobs and use_processes:
        # Real processes: the single-skeleton route is pure-Python quaternion
        # math, so threads only contend for the GIL. Clips are parsed inside
        # the workers; resource resolution, patched Units, lazy reference
        # reads and collection stay on the caller to keep output deterministic.
        options = _ProcessOptions(
            allow_additive=allow_additive,
            apply_rotate_multipliers=apply_rotate_multipliers,
            apply_rotation_compensations=apply_rotation_compensations,
            apply_ik_correction=apply_ik_correction,
            only_additive=only_additive,
            only_non_additive=only_non_additive,
            preserve_hand_bend_frame=preserve_hand_bend_frame,
            preserve_source_key_times=preserve_source_key_times,
            preserve_unmodified_channels=preserve_unmodified_channels,
            source_arm_constraints=source_arm_constraints,
            preserve_playback_timing=preserve_playback_timing,
            preserve_unchanged_bytes=preserve_unchanged_bytes,
        )
        pending = deque()
        remaining = iter(enumerate(jobs, start=1))
        prepared_issues: dict[int, BatchIssue] = {}

        def additive_unit_for(job):
            if not add_unit or job.unit_id is None:
                return None
            unit_key = (job.unit_id, UNIT_TYPE_ID)
            if unit_key not in unit_entries:
                job_config = job.config or config
                _, unit_entry = resource_index.resolve(job.unit_id, UNIT_TYPE_ID)
                unit_resource = UnitData.parse(unit_entry.toc_data)
                patched_unit_data = patch_unit_positions(
                    unit_entry.toc_data, unit_resource, job.bones,
                    job_config.offsets, job_config.distance_multipliers,
                )
                patched_unit_entry = copy.deepcopy(unit_entry)
                patched_unit_entry.toc_data = bytearray(patched_unit_data)
                patched_unit_entry.gpu_data = bytearray()
                patched_unit_entry.stream_data = bytearray()
                unit_entries[unit_key] = patched_unit_entry
                patched_units[job.unit_id] = UnitData.parse(patched_unit_data)
            return patched_units[job.unit_id]

        def make_task(job):
            _, animation_entry = resource_index.resolve(job.animation_id, ANIMATION_TYPE_ID)
            playback_reference = job.playback_reference
            use_loader = playback_reference_loader is not None
            reference_bytes = None
            if use_loader:
                if playback_reference is not None:
                    raise ValueError('Use either a per-job reference or a lazy playback loader')
                reference_bytes = playback_reference_loader(job.animation_id)
            return _ProcessTask(
                animation_id=job.animation_id,
                package_name=job.animation_package,
                bones=job.bones,
                unit=job.unit,
                additive_unit=additive_unit_for(job),
                config=job.config or config,
                animation_entry=animation_entry,
                playback_reference=playback_reference,
                reference_bytes=reference_bytes,
                use_loader=use_loader,
                options=options,
            )

        with ProcessPoolExecutor(max_workers=threads) as executor:
            def submit_next():
                item = next(remaining, None)
                if item is None:
                    return False
                job_index, job = item
                try:
                    future = executor.submit(_run_batch_animation, make_task(job))
                except Exception as error:
                    prepared_issues[job_index] = BatchIssue(
                        f"animation {job.animation_id}",
                        f"Failed to modify animation: {error}",
                        True,
                    )
                    future = None
                pending.append((job_index, job, future))
                return True

            for _ in range(threads * 2):
                if not submit_next():
                    break
            while pending:
                job_index, job, future = pending.popleft()
                issue = prepared_issues.pop(job_index, None)
                if issue is not None:
                    outcome = (None, None, issue)
                else:
                    try:
                        outcome = future.result()
                    except Exception as error:
                        outcome = (None, None, BatchIssue(
                            f"animation {job.animation_id}",
                            f"Failed to modify animation: {error}",
                            True,
                        ))
                collect(job_index, job, outcome)
                submit_next()
    elif jobs:
        # Bound the prepared animations to 2x parallelism, instead of eagerly
        # parsing the entire game. Collect/write only on the caller thread so
        # output bytes, issue ordering and progress remain deterministic.
        with ThreadPoolExecutor(max_workers=threads, thread_name_prefix="hd2-animation") as executor:
            pending = deque()
            remaining = iter(enumerate(jobs, start=1))

            def submit_next():
                item = next(remaining, None)
                if item is None:
                    return False
                job_index, job = item
                pending.append((job_index, job, executor.submit(process_job, job, prepare_job(job))))
                return True

            for _ in range(threads * 2):
                if not submit_next():
                    break
            while pending:
                job_index, job, future = pending.popleft()
                collect(job_index, job, future.result())
                submit_next()
    result.entries = [
        unit_entries[key] for key in unit_entries if key in successful_unit_keys
    ] + result.entries
    return result


def unit_context_signature(unit: UnitData, bones: BonesData) -> str:
    digest = hashlib.sha256()
    digest.update(struct.pack("<Q", unit.bones_ref))
    digest.update(struct.pack("<I", len(bones.hashes)))
    for bone_hash in bones.hashes:
        digest.update(struct.pack("<I", bone_hash))
    digest.update(struct.pack("<I", len(unit.transforms)))
    for index, transform in enumerate(unit.transforms):
        parent = unit.parents[index]
        digest.update(struct.pack("<Ii", unit.name_hashes[index], -1 if parent is None else parent))
        digest.update(struct.pack("<3f", *transform.position))
        digest.update(struct.pack("<4f", *transform.rotation))
        digest.update(struct.pack("<3f", *transform.scale))
    return digest.hexdigest()
