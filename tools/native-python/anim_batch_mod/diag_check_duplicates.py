"""Diagnostic: check whether the 3180 referenced animations have stale duplicate copies."""
from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from anim_batch_mod.archive import PackageStore, ResourceIndex, TocArchive
from anim_batch_mod.constants import (
    ANIMATION_TYPE_ID,
    BONE_TYPE_ID,
    STATE_MACHINE_TYPE_ID,
    UNIT_TYPE_ID,
)
from anim_batch_mod.formats import UnitData, parse_state_machine_animation_ids
from anim_batch_mod.cli import ModConfig  # noqa: F401  (config path check only)

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
CONFIG = Path(__file__).with_name("config.toml")


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def main() -> None:
    from anim_batch_mod.processor import ModConfig as _MC

    config = _MC.load(CONFIG.resolve())
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)

    # 1. Parse Units in the matched archive and collect StateMachine animation references.
    archive = TocArchive.load_toc_only(store, KEYWORD)
    units = archive.entries_of_type(UNIT_TYPE_ID)
    print(f"matched archive Units: {len(units)}")
    anim_ids: set[int] = set()
    matched_units = 0
    for unit_entry in units:
        unit = UnitData.parse(unit_entry.toc_data)
        if not unit.bones_ref or not unit.state_machine_ref:
            continue
        try:
            _, bones_entry = ResourceIndex(store).resolve(unit.bones_ref, BONE_TYPE_ID) if False else (None, None)
        except Exception:
            bones_entry = None
        # Resolve bones through the index (same as the tool does).
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.bones_ref), blob(BONE_TYPE_ID)),
        ).fetchone()
        if row is None:
            continue
        bones_archive = TocArchive.load_toc_only(store, row[0])
        bones_entry = bones_archive.get_entry(unit.bones_ref, BONE_TYPE_ID)
        if bones_entry is None:
            continue
        from anim_batch_mod.formats import BonesData

        bones = BonesData.parse(bones_entry.toc_data)
        if config.required_bone not in bones.names:
            continue
        configured = set(config.offsets) | set(config.rotation_compensations)
        if [name for name in configured if name not in bones.names]:
            continue
        matched_units += 1
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.state_machine_ref), blob(STATE_MACHINE_TYPE_ID)),
        ).fetchone()
        state_archive = TocArchive.load_toc_only(store, row[0])
        state_entry = state_archive.get_entry(unit.state_machine_ref, STATE_MACHINE_TYPE_ID)
        ids = parse_state_machine_animation_ids(state_entry.toc_data)
        anim_ids.update(ids)
    print(f"cape/config-compatible Units: {matched_units}")
    print(f"unique animation references (tool's discovery set): {len(anim_ids)}")

    # 2. For each referenced animation, how many package copies does the index know?
    copy_counts: dict[int, int] = {}
    multi: dict[int, list[str]] = {}
    for anim_id in anim_ids:
        rows = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ?",
            (blob(anim_id), blob(ANIMATION_TYPE_ID)),
        ).fetchall()
        packages = sorted(row[0] for row in rows)
        copy_counts[len(packages)] = copy_counts.get(len(packages), 0) + 1
        if len(packages) > 1:
            multi[anim_id] = packages
    print("\ncopies-per-animation distribution:")
    for count in sorted(copy_counts):
        print(f"  {count} copy(ies): {copy_counts[count]} animations")
    print(f"animations with multiple copies: {len(multi)}")

    # 3. For multi-copy animations, compare content between the lexicographic-first copy
    #    (what locate() resolves) and the highest-bundle-index copy (most recent update).
    def bundle_of(package: str) -> int:
        entries = store.packages.get(package)
        return entries.entries[0].bundle_index if entries and entries.entries else -1

    stale = 0
    checked = 0
    examples = []
    cache_archives: dict[str, TocArchive] = {}
    for anim_id, packages in sorted(multi.items()):
        newest = max(packages, key=bundle_of)
        if bundle_of(newest) == bundle_of(packages[0]):
            continue  # all copies in the same bundle generation
        checked += 1
        if checked > 60:
            break
        payloads = {}
        for package in dict.fromkeys([packages[0], newest]):
            arch = cache_archives.get(package)
            if arch is None:
                arch = TocArchive.load_toc_only(store, package)
                cache_archives[package] = arch
            entry = arch.get_entry(anim_id, ANIMATION_TYPE_ID)
            payloads[package] = bytes(entry.toc_data) if entry else b""
        first_bytes = payloads[packages[0]]
        newest_bytes = payloads[newest]
        if first_bytes != newest_bytes:
            stale += 1
            if len(examples) < 10:
                examples.append(
                    f"    anim {anim_id}: locate()->{packages[0]} (bundle{bundle_of(packages[0]):02d}, "
                    f"{len(first_bytes)}B) != newest {newest} (bundle{bundle_of(newest):02d}, {len(newest_bytes)}B)"
                )
    print(f"\nmulti-copy animations checked (different bundle generations): {checked}")
    print(f"  content differs between lexicographic-first and newest copy: {stale}")
    for line in examples:
        print(line)
    conn.close()


if __name__ == "__main__":
    main()
