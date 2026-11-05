from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from .archive import PackageStore, ResourceIndex, TocArchive, flatten_archive_catalog
from .batch import build_batch_entries, discover_batch_jobs
from .constants import (
    ANIMATION_TYPE_ID,
    BASE_ARCHIVE_ID,
    BONE_TYPE_ID,
    STATE_MACHINE_TYPE_ID,
    UNIT_TYPE_ID,
)
from .formats import (
    AnimationData,
    BonesData,
    UnitData,
    parse_state_machine_animation_ids,
    patch_unit_positions,
)
from .processor import (
    ModConfig,
    _calculate_world_transforms,
    measure_bone_distance,
    modify_animation_with_world_compensation,
)
from .math3d import quat_inverse, quat_multiply, quat_normalize


DEFAULT_GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
DEFAULT_INDEX_CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
DEFAULT_BASE_ANIM = Path(__file__).with_name("base_anim")
DEFAULT_CONFIG = Path(__file__).with_name("config.toml")
CONFIG_OFFSET_TOLERANCE = 1e-6


def parse_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Modify one or many HD2 animations and build one patch."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("single", "batch", "generate-config", "generate-config-type2", "test_dis", "anim-filter", "unit-filter"),
        default="single",
        help=(
            "single (default) selects one animation; batch processes every match; "
            "generate-config derives offsets from base_anim; "
            "generate-config-type2 derives unit_anim - base_anim offsets"
        ),
    )
    parser.add_argument(
        "--game-data",
        type=Path,
        default=DEFAULT_GAME_DATA,
        help=f"Helldivers 2 data directory (default: {DEFAULT_GAME_DATA})",
    )
    parser.add_argument("--keyword", help="Archive name/ID search keyword")
    parser.add_argument("--file", type=Path, help="Resource patch file used by test_dis")
    parser.add_argument("--unit-id", help="Unit resource ID (decimal or 0x-prefixed hex)")
    parser.add_argument("--unitid", dest="unit_id", help=argparse.SUPPRESS)
    parser.add_argument("--name", help="Bone name used by unit-filter")
    parser.add_argument(
        "--unit-id-file",
        type=Path,
        help="Text file containing Unit resource IDs, one per line (batch/generate-config)",
    )
    animation_selector = parser.add_mutually_exclusive_group()
    animation_selector.add_argument(
        "--animation-id",
        help="Animation resource ID (decimal or 0x-prefixed hex)",
    )
    animation_selector.add_argument(
        "--animation-id-file",
        type=Path,
        help="Text file containing animation resource IDs, one per line",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Bone offset, distance multiplier, and rotation multiplier TOML config",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        help="Directory containing per-Unit TOML configs named <unit_id>.toml (batch)",
    )
    parser.add_argument(
        "--base-anim",
        type=Path,
        default=DEFAULT_BASE_ANIM,
        help="base_anim patch file or directory used by generate-config",
    )
    parser.add_argument(
        "--unit-skeleton",
        type=Path,
        help="Resource patch file or directory of patch files with Unit-specific original skeletons",
    )
    parser.add_argument(
        "--output-config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Output TOML path used by generate-config",
    )
    parser.add_argument(
        "--output-config-dir",
        type=Path,
        help="Output directory for per-Unit configs (generate-config)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=CONFIG_OFFSET_TOLERANCE,
        help="Position-difference tolerance used by generate-config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("output"),
        help="Directory for the three patch files",
    )
    parser.add_argument("--patch-index", type=int, default=0)
    parser.add_argument("--frame", type=int, default=0, help="Animation frame at 30 FPS (test_dis)")
    parser.add_argument("--first-bone", help="First bone name (test_dis)")
    parser.add_argument("--last-bone", help="Second bone name (test_dis)")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing output files"
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Discard and rebuild the local resource index cache",
    )
    parser.add_argument(
        "--build-index-only",
        action="store_true",
        help="Build or validate the local resource index, then exit",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Batch only: omit failed or ambiguous animations and write the rest",
    )
    parser.add_argument(
        "--add-unit",
        type=parse_bool,
        default=False,
        help="Batch only: include patched Unit resources in the output (default: false)",
    )
    parser.add_argument(
        "--allow-additive",
        "--process-additive",
        dest="allow_additive",
        action="store_true",
        help="Enable the additive-animation composition path",
    )
    additive_filter = parser.add_mutually_exclusive_group()
    additive_filter.add_argument(
        "--only-additive",
        action="store_true",
        help="Batch only: process and package only additive animations",
    )
    additive_filter.add_argument(
        "--only-non-additive",
        action="store_true",
        help="Batch only: process and package only non-additive animations",
    )
    parser.add_argument(
        "--rotate-multipliers",
        nargs="?",
        const=True,
        default=False,
        type=parse_bool,
        help="Apply per-bone rotation angle multipliers from config.toml",
    )
    parser.add_argument(
        "--rotation-compensation",
        nargs="?",
        const=True,
        default=False,
        type=parse_bool,
        help="Batch only: apply per-bone full rotation compensation from config.toml",
    )
    parser.add_argument(
        "--ik-correction",
        nargs="?",
        const=True,
        default=False,
        type=parse_bool,
        help="Batch only: validate and correct configured two-bone IK chains",
    )
    parser.add_argument(
        "--sort-patch-anim-id",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="Batch only: process animations numbered START through END after sorting IDs",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args)
        return 0
    except (FileNotFoundError, FileExistsError, LookupError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def run(args) -> None:
    if args.unit_id_file is not None and args.unit_id is not None:
        raise ValueError("--unit-id and --unit-id-file are mutually exclusive")
    if args.unit_id_file is not None and args.command not in {"batch", "generate-config", "generate-config-type2"}:
        raise ValueError(
            "--unit-id-file is only supported by batch and generate-config commands"
        )
    if args.config_dir is not None and args.config != DEFAULT_CONFIG:
        raise ValueError("--config and --config-dir are mutually exclusive")
    if args.config_dir is not None and args.command != "batch":
        raise ValueError("--config-dir is only supported by batch")
    if args.output_config_dir is not None and args.command not in {"generate-config", "generate-config-type2"}:
        raise ValueError("--output-config-dir is only supported by generate-config")
    if (
        getattr(args, "animation_id_file", None) is not None
        and args.command != "batch"
    ):
        raise ValueError("--animation-id-file is only supported by batch")
    if args.add_unit and args.command != "batch":
        raise ValueError("--add-unit is only supported by batch")
    if args.rotation_compensation and args.command != "batch":
        raise ValueError("--rotation-compensation is only supported by batch")
    if args.ik_correction and args.command != "batch":
        raise ValueError("--ik-correction is only supported by batch")
    if getattr(args, "only_additive", False) and args.command != "batch":
        raise ValueError("--only-additive is only supported by batch")
    if getattr(args, "only_non_additive", False) and args.command != "batch":
        raise ValueError("--only-non-additive is only supported by batch")
    if getattr(args, "sort_patch_anim_id", None) is not None and args.command != "batch":
        raise ValueError("--sort-patch-anim-id is only supported by batch")
    if getattr(args, "sort_patch_anim_id", None) is not None:
        start, end = args.sort_patch_anim_id
        if start < 1 or end < start:
            raise ValueError("--sort-patch-anim-id requires 1 <= START <= END")

    store = PackageStore(args.game_data)
    print(f"Resource layout: {'bundled/DSAR' if store.is_bundled else 'legacy archive'}")

    resource_index = load_resource_index(store, args.rebuild_index)
    try:
        if args.build_index_only:
            print(f"Index path: {DEFAULT_INDEX_CACHE.resolve()}")
            return

        if args.command in {"generate-config", "generate-config-type2"}:
            run_generate_config(args, store, resource_index)
            return
        if args.command == "test_dis":
            run_test_dis(args, store, resource_index)
            return
        if args.command == "anim-filter":
            unit_id = parse_optional_id(args.unit_id)
            if unit_id is None:
                raise ValueError("anim-filter requires --unitid")
            for animation_id in find_animation_ids_for_unit(resource_index, unit_id):
                print(animation_id)
            return
        if args.command == "unit-filter":
            if not args.name:
                raise ValueError("unit-filter requires --name")
            for unit_id in find_units_with_bone(resource_index, args.name):
                print(unit_id)
            return

        config = None if args.config_dir is not None else ModConfig.load(args.config.resolve())
        keyword = args.keyword or input("Archive name/ID keyword: ").strip()
        if args.command == "batch":
            run_batch(args, store, resource_index, config, keyword)
        else:
            run_single(args, store, resource_index, config, keyword)
    finally:
        resource_index.close()


def run_test_dis(args, store, resource_index) -> None:
    if args.file is None:
        raise ValueError("test_dis requires --file")
    unit_id = parse_optional_id(args.unit_id)
    if unit_id is None:
        raise ValueError("test_dis requires --unit-id")
    if not args.first_bone or not args.last_bone:
        raise ValueError("test_dis requires --first-bone and --last-bone")
    if args.frame < 0:
        raise ValueError("--frame must be non-negative")

    source = load_resource_patch(args.file)
    unit_entry = source.get_entry(unit_id, UNIT_TYPE_ID)
    if unit_entry is None:
        _, unit_entry = resource_index.resolve(unit_id, UNIT_TYPE_ID)
    unit = UnitData.parse(unit_entry.toc_data)
    bones_entry = source.get_entry(unit.bones_ref, BONE_TYPE_ID)
    if bones_entry is None:
        _, bones_entry = resource_index.resolve(unit.bones_ref, BONE_TYPE_ID)
    bones = BonesData.parse(bones_entry.toc_data)

    animation = None
    animation_id = parse_optional_id(args.animation_id)
    if animation_id is not None:
        animation_entry = source.get_entry(animation_id, ANIMATION_TYPE_ID)
        if animation_entry is None:
            _, animation_entry = resource_index.resolve(animation_id, ANIMATION_TYPE_ID)
        animation = AnimationData.parse(animation_entry.toc_data)

    result = measure_bone_distance(
        animation, bones, unit, args.frame, args.first_bone, args.last_bone
    )
    print(f"Frame: {args.frame} ({args.frame / 30.0:.6f}s)")
    print(f"First bone: {args.first_bone}")
    print(f"  World position: {format_vector(result.first_position)}")
    print(f"  World rotation: {format_vector(result.first_rotation)}")
    print(f"Last bone: {args.last_bone}")
    print(f"  World position: {format_vector(result.last_position)}")
    print(f"  World rotation: {format_vector(result.last_rotation)}")
    print(f"Distance: {result.distance:.9f}")


def load_resource_patch(path: Path) -> TocArchive:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Resource patch does not exist: {path}")
    gpu_path = Path(f"{path}.gpu_resources")
    stream_path = Path(f"{path}.stream")
    if not gpu_path.is_file() or not stream_path.is_file():
        raise FileNotFoundError(
            f"Resource patch requires sidecar files: {gpu_path} and {stream_path}"
        )
    return TocArchive.parse_parts(
        path.read_bytes(), gpu_path.read_bytes(), stream_path.read_bytes()
    )


def load_unit_skeletons(path: Path | None) -> dict[int, BonesData] | None:
    if path is None:
        return None
    path = path.resolve()
    if path.is_dir():
        patch_paths = sorted(
            item
            for item in path.iterdir()
            if item.is_file()
            and ".patch_" in item.name
            and not item.name.endswith((".gpu_resources", ".stream"))
        )
        if not patch_paths:
            raise FileNotFoundError(f"Unit skeleton directory contains no patch files: {path}")
    elif path.is_file():
        patch_paths = [path]
    else:
        raise FileNotFoundError(f"Unit skeleton path does not exist: {path}")

    archives = [load_resource_patch(patch_path) for patch_path in patch_paths]
    return build_unit_skeleton_overrides(archives)


def load_unit_anim_overrides(path: Path | None):
    if path is None:
        return None
    path = path.resolve()
    if path.is_dir():
        patch_paths = sorted(
            item
            for item in path.iterdir()
            if item.is_file()
            and ".patch_" in item.name
            and not item.name.endswith((".gpu_resources", ".stream"))
        )
        if not patch_paths:
            raise FileNotFoundError(f"Unit animation directory contains no patch files: {path}")
    elif path.is_file():
        patch_paths = [path]
    else:
        raise FileNotFoundError(f"Unit animation path does not exist: {path}")

    return build_unit_anim_overrides(
        [load_resource_patch(patch_path) for patch_path in patch_paths]
    )


def build_unit_skeleton_overrides(archives: list[TocArchive]) -> dict[int, BonesData]:
    overrides: dict[int, BonesData] = {}
    for archive in archives:
        bones_entries = archive.entries_of_type(BONE_TYPE_ID)
        for unit_entry in archive.entries_of_type(UNIT_TYPE_ID):
            unit = UnitData.parse(unit_entry.toc_data)
            bones_entry = archive.get_entry(unit.bones_ref, BONE_TYPE_ID)
            if bones_entry is None:
                bones_entry = archive.get_entry(unit_entry.file_id, BONE_TYPE_ID)
            if bones_entry is None and len(bones_entries) == 1:
                bones_entry = bones_entries[0]
            if bones_entry is None:
                raise LookupError(
                    f"Unit skeleton patch does not contain Bones for Unit {unit_entry.file_id}"
                )
            if unit_entry.file_id in overrides:
                raise ValueError(
                    f"Duplicate Unit {unit_entry.file_id} in --unit-skeleton patches"
                )
            overrides[unit_entry.file_id] = BonesData.parse(bones_entry.toc_data)
    if not overrides:
        raise LookupError("Unit skeleton patches contain no Unit resources")
    return overrides


def build_unit_anim_overrides(archives: list[TocArchive]):
    overrides = {}
    for archive in archives:
        bones_entries = archive.entries_of_type(BONE_TYPE_ID)
        for unit_entry in archive.entries_of_type(UNIT_TYPE_ID):
            unit = UnitData.parse(unit_entry.toc_data)
            bones_entry = archive.get_entry(unit.bones_ref, BONE_TYPE_ID)
            if bones_entry is None:
                bones_entry = archive.get_entry(unit_entry.file_id, BONE_TYPE_ID)
            if bones_entry is None and len(bones_entries) == 1:
                bones_entry = bones_entries[0]
            if bones_entry is None:
                raise LookupError(
                    f"Unit animation patch does not contain Bones for Unit {unit_entry.file_id}"
                )
            if unit_entry.file_id in overrides:
                raise ValueError(
                    f"Duplicate Unit {unit_entry.file_id} in --unit-skeleton patches"
                )
            overrides[unit_entry.file_id] = (
                unit,
                BonesData.parse(bones_entry.toc_data),
            )
    if not overrides:
        raise LookupError("Unit animation patches contain no Unit resources")
    return overrides


def resolve_unit_bones(
    unit: UnitData,
    unit_id: int,
    resource_index,
    skeleton_overrides: dict[int, BonesData] | None = None,
) -> tuple[str, BonesData]:
    if skeleton_overrides is not None and unit_id in skeleton_overrides:
        return "unit-skeleton", skeleton_overrides[unit_id]
    package, entry = resource_index.resolve(unit.bones_ref, BONE_TYPE_ID)
    return package, BonesData.parse(entry.toc_data)


def run_single(args, store, resource_index, config, keyword) -> None:
    archive_name = select_archive(store, keyword)
    archive = TocArchive.load_toc_only(store, archive_name)
    unit_entries = archive.entries_of_type(UNIT_TYPE_ID)
    if not unit_entries:
        raise LookupError(f"Archive {archive_name} contains no Unit resources")
    unit_entry = select_entry(unit_entries, args.unit_id, "Unit")
    unit = UnitData.parse(unit_entry.toc_data)
    if not unit.bones_ref or not unit.state_machine_ref:
        raise ValueError(
            f"Unit {unit_entry.file_id} has no BonesRef or StateMachineRef"
        )

    skeleton_overrides = (
        load_unit_skeletons(getattr(args, "unit_skeleton", None))
        if args.command == "generate-config"
        else None
    )
    bones_package, bones = resolve_unit_bones(
        unit, unit_entry.file_id, resource_index, skeleton_overrides
    )
    state_package, state_entry = resource_index.resolve(
        unit.state_machine_ref, STATE_MACHINE_TYPE_ID
    )
    if config.required_bone not in bones.names:
        raise ValueError(
            f"Unit {unit_entry.file_id} does not contain required bone "
            f"'{config.required_bone}'"
        )
    animation_ids = parse_state_machine_animation_ids(state_entry.toc_data)
    if not animation_ids:
        raise ValueError(f"StateMachine {unit.state_machine_ref} has no animation IDs")
    print(
        f"Unit {unit_entry.file_id}: Bones={unit.bones_ref} ({bones_package}), "
        f"StateMachine={unit.state_machine_ref} ({state_package})"
    )

    resolved_animations = []
    for animation_id in animation_ids:
        try:
            package_name = resource_index.locate(animation_id, ANIMATION_TYPE_ID)
            resolved_animations.append((animation_id, package_name))
        except LookupError:
            continue
    if not resolved_animations:
        raise LookupError("No StateMachine animation could be resolved in the resource index")
    animation_id = parse_optional_id(args.animation_id)
    if animation_id is None:
        print("Available animations:")
        for index, (file_id, package_name) in enumerate(resolved_animations, start=1):
            print(f"  {index}. {file_id}  [{package_name}]")
        selected = prompt_index(len(resolved_animations), "Select animation number: ")
        animation_id, animation_package = resolved_animations[selected]
    else:
        match = next(
            (item for item in resolved_animations if item[0] == animation_id), None
        )
        if match is None:
            raise LookupError(
                f"Animation {animation_id} is not in the selected Unit's StateMachine "
                "or the resource is missing"
            )
        animation_id, animation_package = match

    _, animation_entry = resource_index.resolve(animation_id, ANIMATION_TYPE_ID)

    animation = AnimationData.parse(animation_entry.toc_data)
    result = modify_animation_with_world_compensation(
        animation,
        bones,
        unit,
        config,
        allow_additive=args.allow_additive,
        apply_offsets_to_additive=False,
        apply_rotate_multipliers=getattr(args, "rotate_multipliers", False),
        apply_rotation_compensations=getattr(args, "rotation_compensation", False),
    )
    modified_entry = copy.deepcopy(animation_entry)
    modified_entry.toc_data = bytearray(animation.to_bytes())
    modified_entry.gpu_data = bytearray()
    modified_entry.stream_data = bytearray()

    patched_unit_entry = copy.deepcopy(unit_entry)
    patched_unit_entry.toc_data = patch_unit_positions(
        unit_entry.toc_data,
        unit,
        bones,
        config.offsets,
        config.distance_multipliers,
    )
    patched_unit_entry.gpu_data = bytearray()
    patched_unit_entry.stream_data = bytearray()

    written = write_output_patch(store, args, [patched_unit_entry, modified_entry])
    verify_patch(written[0], [animation_id])

    print("Complete:")
    print(f"  Archive: {archive_name}")
    print(f"  Unit: {unit_entry.file_id}")
    print(f"  Animation: {animation_id} [{animation_package}]")
    print(f"  Modified/compensated bones: {', '.join(result.changed_bones)}")
    print(f"  Sample count: {result.sample_count}")
    print(f"  Generated position keys: {result.generated_position_keys}")
    for path in written:
        print(f"  Output: {path}")


def run_batch(args, store, resource_index, config, keyword) -> None:
    archive_matches = find_archive_matches(store, keyword)
    print(f"Matched archives: {len(archive_matches)}")
    for archive_id, name in archive_matches:
        print(f"  {archive_id}  {name}")

    def discovery_progress(stage, current, total, label):
        if current == 1 or current == total or current % 25 == 0:
            print(f"Discovering {stage}s: [{current}/{total}] {label}")

    animation_id_file = getattr(args, "animation_id_file", None)
    requested_animation_ids = (
        load_animation_ids(animation_id_file) if animation_id_file is not None else None
    )
    if requested_animation_ids is not None:
        print(
            f"Requested animation IDs: {len(requested_animation_ids)} "
            f"(from {animation_id_file})"
        )
    requested_unit_ids = (
        load_unit_ids(args.unit_id_file) if args.unit_id_file is not None else None
    )
    config_by_unit = (
        load_unit_configs(args.config_dir, requested_unit_ids)
        if args.config_dir is not None
        else None
    )

    discovery = discover_batch_jobs(
        store=store,
        resource_index=resource_index,
        archive_names=[archive_id for archive_id, _ in archive_matches],
        config=config,
        requested_unit_id=parse_optional_id(args.unit_id),
        requested_unit_ids=requested_unit_ids,
        requested_animation_id=parse_optional_id(args.animation_id),
        requested_animation_ids=requested_animation_ids,
        include_ik_bones=getattr(args, "ik_correction", False),
        progress=discovery_progress,
        skeleton_overrides=load_unit_skeletons(getattr(args, "unit_skeleton", None)),
        config_by_unit=config_by_unit,
    )
    print("Discovery summary:")
    print(f"  Archives: {discovery.archive_count}")
    print(f"  Unit entries scanned: {discovery.unit_count}")
    print(f"  Cape/config-compatible Units: {discovery.matched_unit_count}")
    print(
        "  Units without required bone: "
        f"{discovery.filtered_missing_required_bone}"
    )
    print(
        "  Units missing configured bones: "
        f"{discovery.filtered_missing_config_bones}"
    )
    print(f"  Unique animation jobs: {len(discovery.jobs)}")
    print_issues(discovery.issues)
    if discovery.fatal_issues and not args.skip_errors:
        raise RuntimeError(
            f"Batch discovery found {len(discovery.fatal_issues)} fatal issues; "
            "nothing was written. Review the issue list or pass --skip-errors."
        )

    sort_patch_anim_id = getattr(args, "sort_patch_anim_id", None)
    if sort_patch_anim_id is not None:
        total_jobs = len(discovery.jobs)
        discovery.jobs = select_batch_jobs_by_number(discovery.jobs, sort_patch_anim_id)
        start, end = sort_patch_anim_id
        print(
            f"  Selected sorted animation range: {start}-{end} "
            f"({len(discovery.jobs)}/{total_jobs})"
        )
        if not discovery.jobs:
            raise RuntimeError(
                f"No animations fall within sorted animation range {start}-{end}"
            )
        if len(discovery.jobs) < 10:
            print(
                "  Selected animation IDs: "
                + ", ".join(str(job.animation_id) for job in discovery.jobs)
            )

    def build_progress(stage, current, total, label):
        if current == 1 or current == total or current % 25 == 0:
            print(f"Processing {stage}s: [{current}/{total}] {label}")

    build = build_batch_entries(
        resource_index,
        discovery.jobs,
        config,
        allow_additive=args.allow_additive or getattr(args, "only_additive", False),
        apply_rotate_multipliers=getattr(args, "rotate_multipliers", False),
        apply_rotation_compensations=getattr(args, "rotation_compensation", False),
        apply_ik_correction=getattr(args, "ik_correction", False),
        add_unit=args.add_unit,
        only_additive=getattr(args, "only_additive", False),
        only_non_additive=getattr(args, "only_non_additive", False),
        progress=build_progress,
    )
    print_issues(build.issues)
    if build.fatal_issues and not args.skip_errors:
        raise RuntimeError(
            f"Batch processing failed for {len(build.fatal_issues)} animations; "
            "nothing was written. Review the issue list or pass --skip-errors."
        )
    if not build.entries:
        raise RuntimeError("No successfully modified animations remain to package")

    written = write_output_patch(store, args, build.entries)
    animation_ids = [
        entry.file_id for entry in build.entries if entry.type_id == ANIMATION_TYPE_ID
    ]
    unit_count = sum(entry.type_id == UNIT_TYPE_ID for entry in build.entries)
    verify_patch(written[0], animation_ids)
    print("Batch complete:")
    print(f"  Animations packaged: {len(animation_ids)}")
    if len(animation_ids) < 10:
        print("  Animation IDs: " + ", ".join(str(value) for value in sorted(animation_ids)))
    print(f"  Units packaged: {unit_count}")
    print(
        "  Failed/skipped animations: "
        f"{len(discovery.fatal_issues) + len(build.fatal_issues)}"
    )
    print(
        "  Generated position keys: "
        f"{sum(item.modification.generated_position_keys for item in build.animations)}"
    )
    if getattr(args, "ik_correction", False):
        print(
            "  IK corrections: "
            f"{sum(item.modification.ik_corrections for item in build.animations)}"
        )
        print(
            "  IK max error before/after: "
            f"{max((item.modification.ik_max_error_before for item in build.animations), default=0.0):.6f}/"
            f"{max((item.modification.ik_max_error_after for item in build.animations), default=0.0):.6f}"
        )
    for path in written:
        print(f"  Output: {path}")


def select_batch_jobs_by_number(jobs, number_range):
    """Select an inclusive 1-based range after sorting jobs by animation ID."""
    start, end = number_range
    ordered_jobs = sorted(jobs, key=lambda job: job.animation_id)
    return ordered_jobs[start - 1 : end]


def load_resource_index(store: PackageStore, rebuild: bool) -> ResourceIndex:
    if rebuild:
        DEFAULT_INDEX_CACHE.unlink(missing_ok=True)
    print("Loading the resource index for Unit dependencies...")
    resource_index = ResourceIndex(
        store,
        cache_path=DEFAULT_INDEX_CACHE,
        indexed_type_ids={
            BONE_TYPE_ID,
            STATE_MACHINE_TYPE_ID,
            ANIMATION_TYPE_ID,
            UNIT_TYPE_ID,
        },
    )

    def progress(current, total, package_name):
        if current == 1 or current == total or current % 250 == 0:
            print(f"  [{current}/{total}] {package_name}")

    reused_cache = resource_index.load_or_build(progress)
    print("  Reused index cache" if reused_cache else "  Built and cached the index")
    return resource_index


def find_animation_ids_for_unit(resource_index, unit_id: int) -> list[int]:
    """Return unique animation IDs referenced by one Unit's StateMachine."""
    _, unit_entry = resource_index.resolve(unit_id, UNIT_TYPE_ID)
    unit = UnitData.parse(unit_entry.toc_data)
    if not unit.state_machine_ref:
        raise LookupError(f"Unit {unit_id} has no StateMachineRef")
    _, state_entry = resource_index.resolve(unit.state_machine_ref, STATE_MACHINE_TYPE_ID)
    return parse_state_machine_animation_ids(state_entry.toc_data)


def find_units_with_bone(resource_index, bone_name: str) -> list[int]:
    """Return Unit IDs whose referenced Bones resource contains ``bone_name``."""
    matches = []
    for unit_id in resource_index.resource_ids(UNIT_TYPE_ID):
        try:
            _, unit_entry = resource_index.resolve(unit_id, UNIT_TYPE_ID)
            unit = UnitData.parse(unit_entry.toc_data)
            if not unit.bones_ref:
                continue
            _, bones_entry = resource_index.resolve(unit.bones_ref, BONE_TYPE_ID)
            bones = BonesData.parse(bones_entry.toc_data)
        except (LookupError, ValueError):
            continue
        if bone_name in bones.names:
            matches.append(unit_id)
    return matches


def select_archive(store: PackageStore, keyword: str) -> str:
    matches = find_archive_matches(store, keyword)
    if len(matches) == 1:
        print(f"Selected Archive: {matches[0][0]}  {matches[0][1]}")
        return matches[0][0]
    print("Matching archives:")
    for index, (archive_id, name) in enumerate(matches, start=1):
        print(f"  {index}. {archive_id}  {name}")
    return matches[prompt_index(len(matches), "Select archive number: ")][0]


def find_archive_matches(store: PackageStore, keyword: str) -> list[tuple[str, str]]:
    catalog_path = Path(__file__).parents[1] / "hashlists" / "archivehashes.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    keyword_lower = keyword.lower()
    matches = [
        (archive_id, name)
        for archive_id, name in flatten_archive_catalog(catalog)
        if store.has_package(archive_id)
        and (keyword_lower in archive_id.lower() or keyword_lower in name.lower())
    ]
    if store.has_package(keyword) and all(item[0] != keyword for item in matches):
        matches.insert(0, (keyword, "Direct Archive ID"))
    if not matches:
        raise LookupError(f"No installed archive matches: {keyword}")
    return matches


def select_entry(entries, requested_id: str | None, label: str):
    parsed_id = parse_optional_id(requested_id)
    if parsed_id is not None:
        entry = next((item for item in entries if item.file_id == parsed_id), None)
        if entry is None:
            raise LookupError(f"The selected Archive does not contain {label} {parsed_id}")
        return entry
    if len(entries) == 1:
        print(f"Selected {label}: {entries[0].file_id}")
        return entries[0]
    print(f"Available {label} resources:")
    for index, entry in enumerate(entries, start=1):
        print(f"  {index}. {entry.file_id}")
    return entries[prompt_index(len(entries), f"Select {label} number: ")]


def prompt_index(count: int, prompt: str) -> int:
    while True:
        value = input(prompt).strip()
        try:
            index = int(value) - 1
        except ValueError:
            index = -1
        if 0 <= index < count:
            return index
        print(f"Enter a number from 1 to {count}")


def parse_optional_id(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value, 0)


def load_animation_ids(path: Path) -> set[int]:
    """Read one decimal or 0x-prefixed hexadecimal animation ID per line."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise ValueError(f"Could not read animation ID file {path}: {error}") from error

    animation_ids: set[int] = set()
    for line_number, line in enumerate(lines, start=1):
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        try:
            animation_id = parse_optional_id(value)
        except ValueError as error:
            raise ValueError(
                f"Invalid animation ID in {path} on line {line_number}: {value!r}"
            ) from error
        if animation_id is None or animation_id < 0:
            raise ValueError(
                f"Invalid animation ID in {path} on line {line_number}: {value!r}"
            )
        animation_ids.add(animation_id)

    if not animation_ids:
        raise ValueError(f"Animation ID file is empty: {path}")
    return animation_ids


def load_unit_ids(path: Path) -> set[int]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as error:
        raise ValueError(f"Could not read Unit ID file {path}: {error}") from error
    unit_ids = set()
    for line_number, line in enumerate(lines, start=1):
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        try:
            unit_id = parse_optional_id(value)
        except ValueError as error:
            raise ValueError(
                f"Invalid Unit ID in {path} on line {line_number}: {value!r}"
            ) from error
        if unit_id is None or unit_id < 0:
            raise ValueError(
                f"Invalid Unit ID in {path} on line {line_number}: {value!r}"
            )
        unit_ids.add(unit_id)
    if not unit_ids:
        raise ValueError(f"Unit ID file is empty: {path}")
    return unit_ids


def load_unit_configs(path: Path, unit_ids: set[int] | None = None) -> dict[int, ModConfig]:
    path = path.resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Config directory does not exist: {path}")
    if unit_ids is None:
        unit_ids = set()
        for config_path in path.glob("*.toml"):
            try:
                unit_ids.add(int(config_path.stem, 0))
            except ValueError:
                continue
    configs = {}
    for unit_id in unit_ids:
        config_path = path / f"{unit_id}.toml"
        if not config_path.is_file():
            raise FileNotFoundError(f"Config for Unit {unit_id} does not exist: {config_path}")
        configs[unit_id] = ModConfig.load(config_path)
    return configs


def run_generate_config(args, store, resource_index) -> None:
    unit_ids = (
        load_unit_ids(args.unit_id_file)
        if args.unit_id_file is not None
        else {parse_optional_id(args.unit_id)}
    )
    unit_ids.discard(None)
    if not unit_ids:
        raise ValueError(
            f"{args.command} requires --unit-id or --unit-id-file"
        )
    if len(unit_ids) > 1 and args.output_config_dir is None:
        raise ValueError("Multiple Units require --output-config-dir")
    if args.tolerance < 0:
        raise ValueError("--tolerance must be non-negative")

    skeleton_overrides = (
        load_unit_skeletons(getattr(args, "unit_skeleton", None))
        if args.command == "generate-config"
        else None
    )
    unit_anim_overrides = (
        load_unit_anim_overrides(getattr(args, "unit_skeleton", None))
        if args.command == "generate-config-type2"
        else None
    )
    if args.command == "generate-config-type2" and unit_anim_overrides is None:
        raise ValueError("generate-config-type2 requires --unit-skeleton")
    for unit_id in sorted(unit_ids):
        output_path = (
            args.output_config_dir.resolve() / f"{unit_id}.toml"
            if args.output_config_dir is not None
            else args.output_config.resolve()
        )
        if args.command == "generate-config-type2":
            generate_unit_config_type2(unit_id, args, unit_anim_overrides, output_path)
        else:
            generate_unit_config(
                unit_id, args, resource_index, skeleton_overrides, output_path
            )


def generate_unit_config(
    unit_id, args, resource_index, skeleton_overrides, output_path: Path
) -> None:

    base_overrides = load_base_anim_overrides(args.base_anim)
    if unit_id not in base_overrides:
        raise LookupError(f"base_anim does not contain Unit {unit_id}")
    base_unit_entry, base_bones_entry = base_overrides[unit_id]

    original_unit_package, original_unit_entry = resource_index.resolve(
        unit_id, UNIT_TYPE_ID
    )
    original_unit = UnitData.parse(original_unit_entry.toc_data)
    if skeleton_overrides is None or unit_id not in skeleton_overrides:
        original_bones_package, original_bones_entry = resource_index.resolve(
            unit_id, BONE_TYPE_ID
        )
    else:
        original_bones_package = "unit-skeleton"
        original_bones = skeleton_overrides[unit_id]
        original_bones_entry = None
    base_unit = UnitData.parse(base_unit_entry.toc_data)
    base_bones = BonesData.parse(base_bones_entry.toc_data)
    if original_bones_entry is not None:
        original_bones = BonesData.parse(original_bones_entry.toc_data)

    offsets, world_deltas = calculate_bone_offsets(
        base_unit,
        base_bones,
        original_unit,
        original_bones,
        args.tolerance,
    )
    rotation_compensations = calculate_bone_rotation_compensations(
        base_unit, base_bones, original_unit, original_bones, args.tolerance
    )
    if output_path.exists() and not args.force:
        raise FileExistsError(
            f"Output config already exists; use --force to overwrite: {output_path}"
        )
    write_generated_config(
        output_path,
        offsets,
        world_deltas,
        rotation_compensations=rotation_compensations,
    )

    print("Config generation complete:")
    print(f"  Unit: {unit_id}")
    print(f"  Base Unit: {base_unit_entry.file_id} [{args.base_anim.resolve()}]")
    print(f"  Original Unit: {unit_id} [{original_unit_package}]")
    print(f"  Original Bones: {unit_id} [{original_bones_package}]")
    print(f"  Direction: base_anim - original")
    print(f"  Tolerance: {args.tolerance:g}")
    print(f"  Bones written: {len(offsets)}")
    print(f"  Rotation compensations written: {len(rotation_compensations)}")
    for name, local_delta in offsets.items():
        world_delta = world_deltas[name]
        print(
            f"  {name}: local={format_vector(local_delta)} "
            f"world={format_vector(world_delta)}"
        )
    print(f"  Output: {output_path}")


def generate_unit_config_type2(
    unit_id, args, unit_anim_overrides, output_path: Path
) -> None:
    base_overrides = load_base_anim_overrides(args.base_anim)
    if unit_id not in base_overrides:
        raise LookupError(f"base_anim does not contain Unit {unit_id}")
    if unit_id not in unit_anim_overrides:
        raise LookupError(f"unit_anim does not contain Unit {unit_id}")

    base_unit_entry, base_bones_entry = base_overrides[unit_id]
    unit_anim, unit_anim_bones = unit_anim_overrides[unit_id]
    base_unit = UnitData.parse(base_unit_entry.toc_data)
    base_bones = BonesData.parse(base_bones_entry.toc_data)
    offsets, world_deltas = calculate_bone_offsets(
        unit_anim, unit_anim_bones, base_unit, base_bones, args.tolerance
    )
    rotation_compensations = calculate_bone_rotation_compensations(
        unit_anim, unit_anim_bones, base_unit, base_bones, args.tolerance
    )
    if output_path.exists() and not args.force:
        raise FileExistsError(
            f"Output config already exists; use --force to overwrite: {output_path}"
        )
    write_generated_config(
        output_path,
        offsets,
        world_deltas,
        rotation_compensations=rotation_compensations,
        direction="unit_anim - base_anim",
    )

    print("Config generation complete:")
    print(f"  Unit: {unit_id}")
    print(f"  Unit Anim: {args.unit_skeleton.resolve()}")
    print(f"  Base Unit: {base_unit_entry.file_id} [{args.base_anim.resolve()}]")
    print("  Direction: unit_anim - base_anim")
    print(f"  Tolerance: {args.tolerance:g}")
    print(f"  Bones written: {len(offsets)}")
    print(f"  Rotation compensations written: {len(rotation_compensations)}")
    for name, local_delta in offsets.items():
        print(
            f"  {name}: local={format_vector(local_delta)} "
            f"world={format_vector(world_deltas[name])}"
        )
    print(f"  Output: {output_path}")


def load_base_anim_archive(path: Path) -> TocArchive:
    path = path.resolve()
    if path.is_dir():
        path = path / f"{BASE_ARCHIVE_ID}.patch_0"
    if not path.is_file():
        raise FileNotFoundError(f"base_anim patch does not exist: {path}")
    gpu_path = Path(f"{path}.gpu_resources")
    stream_path = Path(f"{path}.stream")
    if not gpu_path.is_file():
        raise FileNotFoundError(f"base_anim GPU resource file does not exist: {gpu_path}")
    if not stream_path.is_file():
        raise FileNotFoundError(f"base_anim stream file does not exist: {stream_path}")
    return TocArchive.parse_parts(
        path.read_bytes(), gpu_path.read_bytes(), stream_path.read_bytes()
    )


def build_base_anim_overrides(archives: list[TocArchive]):
    overrides = {}
    for archive in archives:
        for unit_entry in archive.entries_of_type(UNIT_TYPE_ID):
            unit = UnitData.parse(unit_entry.toc_data)
            bones_entry = archive.get_entry(unit.bones_ref, BONE_TYPE_ID)
            if bones_entry is None:
                bones_entry = archive.get_entry(unit_entry.file_id, BONE_TYPE_ID)
            if bones_entry is None:
                raise LookupError(
                    f"base_anim patch does not contain Bones for Unit {unit_entry.file_id}"
                )
            if unit_entry.file_id in overrides:
                raise ValueError(
                    f"Duplicate Unit {unit_entry.file_id} in base_anim patches"
                )
            overrides[unit_entry.file_id] = (unit_entry, bones_entry)
    if not overrides:
        raise LookupError("base_anim patches contain no Unit resources")
    return overrides


def load_base_anim_overrides(path: Path):
    path = path.resolve()
    if path.is_file():
        return build_base_anim_overrides([load_base_anim_archive(path)])
    if not path.is_dir():
        raise FileNotFoundError(f"base_anim path does not exist: {path}")
    patch_paths = sorted(
        item for item in path.iterdir()
        if item.is_file() and ".patch_" in item.name
        and not item.name.endswith((".gpu_resources", ".stream"))
    )
    if not patch_paths:
        raise FileNotFoundError(f"base_anim directory contains no patch files: {path}")
    return build_base_anim_overrides([load_base_anim_archive(item) for item in patch_paths])


def calculate_bone_offsets(
    base_unit: UnitData,
    base_bones: BonesData,
    original_unit: UnitData,
    original_bones: BonesData,
    tolerance: float = CONFIG_OFFSET_TOLERANCE,
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    if tolerance < 0:
        raise ValueError("Position-difference tolerance must be non-negative")
    if base_bones.names != original_bones.names or base_bones.hashes != original_bones.hashes:
        raise ValueError("base_anim and original Bones resources do not match")
    if len(base_unit.transforms) != len(original_unit.transforms):
        raise ValueError(
            "base_anim and original Unit transform counts do not match: "
            f"base={len(base_unit.transforms)}, original={len(original_unit.transforms)}"
        )

    base_indices = _unique_hash_indices(base_unit.name_hashes, "base_anim Unit")
    original_indices = _unique_hash_indices(original_unit.name_hashes, "original Unit")
    missing_base = [name for name, bone_hash in zip(base_bones.names, base_bones.hashes) if bone_hash not in base_indices]
    missing_original = [name for name, bone_hash in zip(original_bones.names, original_bones.hashes) if bone_hash not in original_indices]
    if missing_base or missing_original:
        details = []
        if missing_base:
            details.append("base_anim=" + ", ".join(missing_base))
        if missing_original:
            details.append("original=" + ", ".join(missing_original))
        raise ValueError("Bones are missing from Unit TransformInfo: " + "; ".join(details))

    base_world = _calculate_world_transforms(base_unit.transforms, base_unit.parents)
    original_world = _calculate_world_transforms(
        original_unit.transforms, original_unit.parents
    )
    offsets = {}
    world_deltas = {}
    for name, bone_hash in zip(base_bones.names, base_bones.hashes):
        base_index = base_indices[bone_hash]
        original_index = original_indices[bone_hash]
        local_delta = [
            base_unit.transforms[base_index].position[index]
            - original_unit.transforms[original_index].position[index]
            for index in range(3)
        ]
        world_delta = [
            base_world[base_index].position[index]
            - original_world[original_index].position[index]
            for index in range(3)
        ]
        world_deltas[name] = world_delta
        if max(abs(value) for value in local_delta) > tolerance:
            offsets[name] = local_delta
    return offsets, {name: world_deltas[name] for name in offsets}


def calculate_bone_rotation_compensations(
    base_unit: UnitData,
    base_bones: BonesData,
    original_unit: UnitData,
    original_bones: BonesData,
    tolerance: float = CONFIG_OFFSET_TOLERANCE,
) -> dict[str, list[float]]:
    if tolerance < 0:
        raise ValueError("Rotation-difference tolerance must be non-negative")
    if base_bones.names != original_bones.names or base_bones.hashes != original_bones.hashes:
        raise ValueError("base_anim and original Bones resources do not match")
    if len(base_unit.transforms) != len(original_unit.transforms):
        raise ValueError("base_anim and original Unit transform counts do not match")

    base_indices = _unique_hash_indices(base_unit.name_hashes, "base_anim Unit")
    original_indices = _unique_hash_indices(original_unit.name_hashes, "original Unit")
    compensations = {}
    for name, bone_hash in zip(base_bones.names, base_bones.hashes):
        base_index = base_indices.get(bone_hash)
        original_index = original_indices.get(bone_hash)
        if base_index is None or original_index is None:
            raise ValueError(f"Bone '{name}' is missing from Unit TransformInfo")
        correction = quat_normalize(
            quat_multiply(
                quat_inverse(original_unit.transforms[original_index].rotation),
                base_unit.transforms[base_index].rotation,
            )
        )
        if correction[3] < 0.0:
            correction = [-component for component in correction]
        identity = [0.0, 0.0, 0.0, 1.0]
        if max(abs(correction[index] - identity[index]) for index in range(4)) > tolerance:
            compensations[name] = correction
    return compensations


def _unique_hash_indices(values: list[int], label: str) -> dict[int, int]:
    result = {}
    duplicates = set()
    for index, value in enumerate(values):
        if value in result:
            duplicates.add(value)
        result[value] = index
    if duplicates:
        raise ValueError(f"{label} contains duplicate bone hashes: {sorted(duplicates)}")
    return result


def write_generated_config(
    path: Path,
    offsets: dict[str, list[float]],
    world_deltas: dict[str, list[float]],
    distance_multipliers: dict[str, float] | None = None,
    rotation_compensations: dict[str, list[float]] | None = None,
    direction: str = "base_anim - original",
) -> None:
    if not offsets and not rotation_compensations:
        raise ValueError(
            "No bone offsets or rotation compensations exceeded the configured tolerance"
        )
    lines = [
        "# Generated by anim_batch_mod generate-config",
        f"# Offsets are local position deltas: {direction}.",
        "# World-space deltas are included as comments for verification.",
        "[filter]",
        'required_bone = "cape4"',
        "",
        "[bone_offsets]",
    ]
    for name, local_delta in offsets.items():
        world_delta = world_deltas[name]
        lines.append(
            f"{name} = {format_vector(local_delta)} "
            f"# world_delta = {format_vector(world_delta)}"
        )
    lines.extend(["", "[bone_distance_multipliers]"])
    multipliers = distance_multipliers or {}
    for name in offsets:
        lines.append(f"{name} = {format_float(multipliers.get(name, 1.0))}")
    lines.extend(["", "[bone_rotation_compensations]"])
    for name, rotation in (rotation_compensations or {}).items():
        lines.append(f"{name} = {format_vector(rotation)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_vector(values: list[float]) -> str:
    return "[" + ", ".join(format_float(value) for value in values) + "]"


def format_float(value: float) -> str:
    return repr(float(value))


def write_output_patch(store, args, entries):
    if not store.has_package(BASE_ARCHIVE_ID):
        raise LookupError(f"Base archive {BASE_ARCHIVE_ID} was not found")
    base_archive = TocArchive.load_toc_only(store, BASE_ARCHIVE_ID)
    output_path = args.output.resolve() / f"{BASE_ARCHIVE_ID}.patch_{args.patch_index}"
    output_paths = (
        output_path,
        Path(f"{output_path}.gpu_resources"),
        Path(f"{output_path}.stream"),
    )
    existing = [path for path in output_paths if path.exists()]
    if existing and not args.force:
        raise FileExistsError(
            "Output already exists; use --force to overwrite: "
            + ", ".join(str(path) for path in existing)
        )
    return base_archive.write_patch(output_path, entries)


def print_issues(issues, limit: int = 20) -> None:
    if not issues:
        return
    fatal_count = sum(issue.fatal for issue in issues)
    print(f"Issues: {len(issues)} total, {fatal_count} fatal")
    for issue in issues[:limit]:
        level = "FATAL" if issue.fatal else "WARN"
        print(f"  [{level}] {issue.scope}: {issue.message}")
    if len(issues) > limit:
        print(f"  ... {len(issues) - limit} more issues not shown")


def verify_patch(path: Path, animation_ids) -> None:
    archive = TocArchive.parse_parts(
        path.read_bytes(),
        Path(f"{path}.gpu_resources").read_bytes(),
        Path(f"{path}.stream").read_bytes(),
    )
    expected_ids = set(animation_ids)
    entries = archive.entries_of_type(ANIMATION_TYPE_ID)
    actual_ids = {entry.file_id for entry in entries}
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        unexpected = sorted(actual_ids - expected_ids)
        raise RuntimeError(
            "Patch verification failed: "
            f"missing={missing}, unexpected={unexpected}"
        )
    for entry in entries:
        AnimationData.parse(entry.toc_data)
