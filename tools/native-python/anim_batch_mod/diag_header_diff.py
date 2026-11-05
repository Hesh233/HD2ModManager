"""Diagnostic: compare animation headers between the Oct 22 patch and current game data.

animation_length / bone_count / hash counts are invariant under the tool's
compensation processing, so any difference means the game update changed the
animation content while keeping the same file_id.
"""
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
CONFIG = Path(__file__).with_name("config.toml")


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def read_header(data: bytes) -> tuple | None:
    if len(data) < 24:
        return None
    unk, bone_count, length, file_size, hash_count, hash2_count = struct.unpack_from(
        "<IIfIII", data, 0
    )
    return (unk, bone_count, round(length, 4), file_size, hash_count, hash2_count)


def main() -> None:
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)
    config = ModConfig.load(CONFIG.resolve())

    # Current discovery set.
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
        if not row:
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
    print(f"discovery set: {len(anim_ids)}")

    # Current game animation entries (TOC only).
    game_entries: dict[int, bytes] = {}
    for anim_id in anim_ids:
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(anim_id), blob(ANIMATION_TYPE_ID)),
        ).fetchone()
        if not row:
            continue
        entry = TocArchive.load_toc_only(store, row[0]).get_entry(anim_id, ANIMATION_TYPE_ID)
        if entry is not None:
            game_entries[anim_id] = bytes(entry.toc_data)
    print(f"current game entries loaded: {len(game_entries)}")

    # Old patch animation entries via TOC offsets (no big copies).
    old_entries: dict[int, bytes] = {}
    with OLD_PATCH.open("rb") as handle:
        header = handle.read(72)
        magic, type_count, file_count = struct.unpack_from("<III", header, 0)
        handle.seek(72 + type_count * 32)
        for _ in range(file_count):
            entry = handle.read(80)
            file_id, type_id = struct.unpack_from("<QQ", entry, 0)
            if type_id != ANIMATION_TYPE_ID:
                continue
            toc_offset, _stream, _gpu, _u1, _u2, toc_size = struct.unpack_from(
                "<QQQQQQ", entry, 16
            )[:6]
            handle.seek(toc_offset)
            old_entries[file_id] = handle.read(min(toc_size, 24))
    print(f"old patch animations: {len(old_entries)}")

    same = changed = missing_in_patch = missing_in_game = 0
    changed_samples = []
    for anim_id in sorted(anim_ids):
        old = old_entries.get(anim_id)
        new = game_entries.get(anim_id)
        if old is None:
            missing_in_patch += 1
            continue
        if new is None:
            missing_in_game += 1
            continue
        old_h, new_h = read_header(old), read_header(new)
        if old_h == new_h:
            same += 1
        else:
            changed += 1
            if len(changed_samples) < 15:
                changed_samples.append((anim_id, old_h, new_h))
    print(f"\nheader identical: {same}")
    print(f"header CHANGED since Oct 22 patch: {changed}")
    print(f"missing in old patch: {missing_in_patch}, missing in game: {missing_in_game}")
    for anim_id, old_h, new_h in changed_samples:
        print(f"  {anim_id}\n    old={old_h}\n    new={new_h}")
    conn.close()


if __name__ == "__main__":
    main()
