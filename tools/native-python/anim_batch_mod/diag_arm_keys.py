"""Diagnostic: compare arm-bone rotation motion between game data and the Oct 26 pack.

The tool bakes sparse tracks to dense 30FPS keys, so the pack should never lose
motion. If a clip's arm-bone rotations are moving in the game data but constant
in the pack, processing dropped the arm motion - that would directly explain
"bolt-pull arms don't move".
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
from anim_batch_mod.formats import (
    AnimationData,
    BonesData,
    UnitData,
    parse_state_machine_animation_ids,
)
from anim_batch_mod.processor import ModConfig

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
PACK = Path(__file__).with_name("output") / "9ba626afa44a3aa3.patch_0"
CONFIG = Path(__file__).with_name("config.toml")

ARM_BONES = [
    "r_shoulder", "r_elbow", "r_hand", "r_hand_twist",
    "l_shoulder", "l_elbow", "l_hand", "l_hand_twist",
]


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def rotation_motion(animation: AnimationData, arm_indices: dict[int, str]):
    """Per arm bone: (distinct key count, max component spread across keys)."""
    values: dict[int, list[list[float]]] = {index: [] for index in arm_indices}
    for entry in animation.entries:
        if entry.is_rotation and entry.bone in values:
            values[entry.bone].append(entry.data2)
    stats = {}
    for index, name in arm_indices.items():
        keys = values[index]
        if not keys:
            stats[name] = (0, 0.0)
            continue
        spread = max(
            abs(keys[i][c] - keys[j][c])
            for i in range(len(keys))
            for j in range(len(keys))
            for c in range(4)
        )
        stats[name] = (len(keys), spread)
    return stats


def main() -> None:
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)
    config = ModConfig.load(CONFIG.resolve())

    # The compatible Unit and its 3180 clips.
    archive = TocArchive.load_toc_only(store, KEYWORD)
    anim_ids: set[int] = set()
    unit_bones: BonesData | None = None
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
        bones = BonesData.parse(bones_entry.toc_data)
        if config.required_bone not in bones.names:
            continue
        configured = set(config.offsets) | set(config.rotation_compensations)
        if [name for name in configured if name not in bones.names]:
            continue
        unit_bones = bones
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(unit.state_machine_ref), blob(STATE_MACHINE_TYPE_ID)),
        ).fetchone()
        state_entry = TocArchive.load_toc_only(store, row[0]).get_entry(
            unit.state_machine_ref, STATE_MACHINE_TYPE_ID
        )
        anim_ids.update(parse_state_machine_animation_ids(state_entry.toc_data))
    assert unit_bones is not None
    name_to_index = {name: i for i, name in enumerate(unit_bones.names)}
    arm_indices = {name_to_index[n]: n for n in ARM_BONES if n in name_to_index}
    print(f"discovery set: {len(anim_ids)}, arm bones: {list(arm_indices.values())}")

    game_cache: dict[str, TocArchive] = {}

    def game_entry(anim_id: int):
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ? LIMIT 1",
            (blob(anim_id), blob(ANIMATION_TYPE_ID)),
        ).fetchone()
        if not row:
            return None
        arch = game_cache.get(row[0])
        if arch is None:
            arch = TocArchive.load_toc_only(store, row[0])
            game_cache[row[0]] = arch
        return arch.get_entry(anim_id, ANIMATION_TYPE_ID)

    pack_index: dict[int, tuple[int, int]] = {}
    with PACK.open("rb") as handle:
        header = handle.read(72)
        magic, type_count, file_count = struct.unpack_from("<III", header, 0)
        type_counts = {}
        handle.seek(72)
        for _ in range(type_count):
            values = struct.unpack("<QQQII", handle.read(32))
            type_counts[values[1]] = values[2]
        print(f"pack TOC types: { {struct.unpack('<Q', struct.pack('<Q', k))[0]: v for k, v in type_counts.items()} }")
        handle.seek(72 + type_count * 32)
        for _ in range(file_count):
            entry = handle.read(80)
            file_id, type_id = struct.unpack_from("<QQ", entry, 0)
            if type_id != ANIMATION_TYPE_ID:
                continue
            toc_offset = struct.unpack_from("<Q", entry, 16)[0]
            toc_size = struct.unpack_from("<Q", entry, 40)[0]
            pack_index[file_id] = (toc_offset, toc_size)
    print(f"pack animations: {len(pack_index)}")

    additive_game = additive_pack = 0
    suspects = []
    missing = 0
    compared = 0
    for anim_id in sorted(anim_ids):
        game_e = game_entry(anim_id)
        loc = pack_index.get(anim_id)
        if game_e is None or loc is None:
            missing += 1
            continue
        game_anim = AnimationData.parse(game_e.toc_data)
        with PACK.open("rb") as handle:
            handle.seek(loc[0])
            pack_anim = AnimationData.parse(handle.read(loc[1]))
        compared += 1
        if game_anim.is_additive:
            additive_game += 1
        if pack_anim.is_additive:
            additive_pack += 1
        game_stats = rotation_motion(game_anim, arm_indices)
        pack_stats = rotation_motion(pack_anim, arm_indices)
        for name in ARM_BONES:
            g_count, g_spread = game_stats[name]
            p_count, p_spread = pack_stats[name]
            # Moving in game but essentially constant in the pack.
            if g_spread > 0.05 and p_spread < 0.01:
                suspects.append((anim_id, name, g_count, g_spread, p_count, p_spread))
    print(f"\ncompared: {compared}, missing: {missing}")
    print(f"additive clips (game/pack): {additive_game}/{additive_pack}")
    print(f"arm-motion-dropped suspects: {len(suspects)}")
    for item in suspects[:20]:
        anim_id, name, g_count, g_spread, p_count, p_spread = item
        print(f"  {anim_id} {name}: game keys={g_count} spread={g_spread:.3f} -> pack keys={p_count} spread={p_spread:.3f}")
    conn.close()


if __name__ == "__main__":
    main()
