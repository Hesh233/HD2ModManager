"""Diagnostic: compare the Oct 22 output patch's animation IDs with the current discovery set."""
from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import (
    ANIMATION_TYPE_ID,
    BONE_TYPE_ID,
    STATE_MACHINE_TYPE_ID,
    UNIT_TYPE_ID,
)
from anim_batch_mod.formats import UnitData, parse_state_machine_animation_ids
from anim_batch_mod.processor import ModConfig

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
OLD_PATCH = Path(__file__).with_name("output") / "9ba626afa44a3aa3.patch_0"
MISSING_IDS_TXT = Path(__file__).with_name("cache") / "first_person_missing_ids.txt"


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def patch_animation_ids(path: Path) -> set[int]:
    """Read only the TOC entry table of a patch file (no data copies)."""
    ids: set[int] = set()
    with path.open("rb") as handle:
        header = handle.read(72)
        magic, type_count, file_count = struct.unpack_from("<III", header, 0)
        if magic != 4026531857:
            raise RuntimeError(f"Not a TOC archive: {path}")
        handle.seek(72 + type_count * 32)
        for _ in range(file_count):
            entry = handle.read(80)
            if len(entry) < 80:
                break
            file_id, type_id = struct.unpack_from("<QQ", entry, 0)
            if type_id == ANIMATION_TYPE_ID:
                ids.add(file_id)
    return ids


def main() -> None:
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)
    config = ModConfig.load((Path(__file__).with_name("config.toml")).resolve())

    # Current discovery set (same logic as the tool).
    archive = TocArchive.load_toc_only(store, KEYWORD)
    anim_ids: set[int] = set()
    for unit_entry in archive.entries_of_type(UNIT_TYPE_ID):
        unit = UnitData.parse(unit_entry.toc_data)
        if not unit.bones_ref or not unit.state_machine_ref:
            continue
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.bones_ref), blob(BONE_TYPE_ID)),
        ).fetchone()
        if row is None:
            continue
        bones_entry = TocArchive.load_toc_only(store, row[0]).get_entry(unit.bones_ref, BONE_TYPE_ID)
        if bones_entry is None:
            continue
        from anim_batch_mod.formats import BonesData

        bones = BonesData.parse(bones_entry.toc_data)
        if config.required_bone not in bones.names:
            continue
        configured = set(config.offsets) | set(config.rotation_compensations)
        if [name for name in configured if name not in bones.names]:
            continue
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.state_machine_ref), blob(STATE_MACHINE_TYPE_ID)),
        ).fetchone()
        state_entry = TocArchive.load_toc_only(store, row[0]).get_entry(
            unit.state_machine_ref, STATE_MACHINE_TYPE_ID
        )
        anim_ids.update(parse_state_machine_animation_ids(state_entry.toc_data))
    print(f"current discovery set: {len(anim_ids)}")

    old_ids = patch_animation_ids(OLD_PATCH)
    print(f"Oct 22 19:25 output patch animations: {len(old_ids)}")
    print(f"  in patch but NOT referenced now (stale/removed): {len(old_ids - anim_ids)}")
    print(f"  referenced now but NOT in patch (new since Oct 22 19:25): {len(anim_ids - old_ids)}")
    if anim_ids - old_ids:
        print("  new IDs:", ", ".join(str(v) for v in sorted(anim_ids - old_ids)[:30]))

    # Where do the "missing ids" from the Oct 22 diagnostic live?
    requested = [
        int(line.strip())
        for line in MISSING_IDS_TXT.read_text().splitlines()
        if line.strip()
    ]
    print(f"\ndiagnostic file ids: {len(requested)}")
    for anim_id in requested:
        rows = conn.execute(
            "SELECT type_id, package_name FROM resources WHERE file_id = ?",
            (blob(anim_id),),
        ).fetchall()
        if not rows:
            print(f"  {anim_id}: NOT IN INDEX (type unknown / not present)")
            continue
        entries = store.packages
        for type_id, package in rows:
            known_type = {
                blob(ANIMATION_TYPE_ID): "animation",
                blob(UNIT_TYPE_ID): "unit",
                blob(STATE_MACHINE_TYPE_ID): "state_machine",
                blob(BONE_TYPE_ID): "bones",
            }.get(type_id, f"type{struct.unpack('<Q', type_id)[0]}")
            bundle = entries[package].entries[0].bundle_index if package in entries and entries[package].entries else -1
            print(f"  {anim_id}: {known_type} in {package} (bundle{bundle:02d}) referenced_now={anim_id in anim_ids}")

    # Animations that exist only in the newest bundles = content added by the update.
    newest = store.index_package_names()  # sorted by bundle index
    newest_set = set()
    for package in reversed(newest):
        entries = store.packages[package]
        if entries.entries and entries.entries[0].bundle_index >= 28:
            newest_set.add(package)
    rows = conn.execute(
        "SELECT file_id, package_name FROM resources WHERE type_id = ?",
        (blob(ANIMATION_TYPE_ID),),
    ).fetchall()
    by_anim: dict[int, set[str]] = {}
    for file_id_blob, package in rows:
        by_anim.setdefault(struct.unpack("<Q", file_id_blob)[0], set()).add(package)
    fresh = {
        anim_id: packages
        for anim_id, packages in by_anim.items()
        if packages <= newest_set
    }
    in_bundle29 = {anim_id: packages for anim_id, packages in fresh.items() if any(p.endswith("29") or True for p in packages)}
    print(f"\ntotal animation file_ids in index: {len(by_anim)}")
    print(f"animations existing ONLY in bundle28+ packages (update-era content): {len(fresh)}")
    referenced_fresh = sorted(set(fresh) & anim_ids)
    print(f"  ...of those, referenced by the compatible Unit's StateMachine: {len(referenced_fresh)}")
    if fresh:
        sample = sorted(fresh)[:10]
        for anim_id in sample:
            packages = sorted(fresh[anim_id])
            bundles = ", ".join(
                f"{p[:8]}..(b{store.packages[p].entries[0].bundle_index:02d})" for p in packages
            )
            print(f"    {anim_id}: {bundles} referenced={anim_id in anim_ids}")
    conn.close()


if __name__ == "__main__":
    main()
