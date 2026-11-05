"""Diagnostic: map every Unit in the keyword archive to its StateMachine animation references."""
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
from anim_batch_mod.formats import BonesData, UnitData, parse_state_machine_animation_ids

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
MISSING_IDS_TXT = Path(__file__).with_name("cache") / "first_person_missing_ids.txt"
CONFIG = Path(__file__).with_name("config.toml")


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def main() -> None:
    from anim_batch_mod.processor import ModConfig

    config = ModConfig.load(CONFIG.resolve())
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)

    archive = TocArchive.load_toc_only(store, KEYWORD)
    diag_ids = {
        int(line.strip())
        for line in MISSING_IDS_TXT.read_text().splitlines()
        if line.strip()
    }

    referenced_all: dict[int, set[int]] = {}
    unit_info: list[tuple[int, str, int]] = []
    for unit_entry in archive.entries_of_type(UNIT_TYPE_ID):
        unit_id = unit_entry.file_id
        try:
            unit = UnitData.parse(unit_entry.toc_data)
        except Exception as error:
            print(f"Unit {unit_id}: parse failed: {error}")
            continue
        if not unit.state_machine_ref:
            continue
        # bones names (may fail)
        bone_names: set[str] = set()
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.bones_ref), blob(BONE_TYPE_ID)),
        ).fetchone()
        if row:
            bones_entry = TocArchive.load_toc_only(store, row[0]).get_entry(unit.bones_ref, BONE_TYPE_ID)
            if bones_entry:
                bone_names = set(BonesData.parse(bones_entry.toc_data).names)
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.state_machine_ref), blob(STATE_MACHINE_TYPE_ID)),
        ).fetchone()
        if not row:
            print(f"Unit {unit_id}: StateMachine {unit.state_machine_ref} not in index")
            continue
        state_entry = TocArchive.load_toc_only(store, row[0]).get_entry(
            unit.state_machine_ref, STATE_MACHINE_TYPE_ID
        )
        if state_entry is None:
            print(f"Unit {unit_id}: StateMachine entry missing in {row[0]}")
            continue
        ids = set(parse_state_machine_animation_ids(state_entry.toc_data))
        referenced_all[unit_id] = ids
        cape = "cape4" in bone_names
        compat = cape and all(name in bone_names for name in set(config.offsets) | set(config.rotation_compensations))
        unit_info.append((unit_id, unit.state_machine_ref, len(ids)))
        hits = diag_ids & ids
        print(
            f"Unit {unit_id}: bones={len(bone_names)} cape4={cape} compat={compat} "
            f"anims={len(ids)} diag_ids_referenced={len(hits)}"
        )

    union = set()
    for ids in referenced_all.values():
        union |= ids
    print(f"\nunion of all StateMachine references in archive: {len(union)}")
    print(f"diag ids referenced by SOME unit in this archive: {len(diag_ids & union)}")
    orphan = diag_ids - union
    print(f"diag ids referenced by NO unit in this archive: {len(orphan)}")
    for anim_id in sorted(orphan):
        print(f"   {anim_id}")
    conn.close()


if __name__ == "__main__":
    main()
