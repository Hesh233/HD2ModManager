"""Diagnostic: find clips whose spine/chest/neck rotations differ between game data and pack.

Bone offsets only touch positions; rotate-multipliers config is empty and
rotation-compensations are disabled; IK chains cover shoulder/elbow/thigh/knee
only. Spine rotations should therefore be identical (rebaked but equal). Any
large angular difference is a processing bug - e.g. the reported 90-degree
waist twist.
"""
from __future__ import annotations

import sqlite3
import struct
import sys
from math import acos
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
from anim_batch_mod.processor import ModConfig, _build_tracks

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
PACK = Path(__file__).with_name("output") / "9ba626afa44a3aa3.patch_0"
CONFIG = Path(__file__).with_name("config.toml")

SPINE_BONES = ["spine1", "spine2", "chest", "neck", "head", "boss"]


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def quat_angle(a, b) -> float:
    dot = abs(sum(a[i] * b[i] for i in range(4)))
    dot = min(1.0, dot)
    return 2.0 * acos(dot)


def main() -> None:
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)
    config = ModConfig.load(CONFIG.resolve())

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
    name_to_index = {name: i for i, name in enumerate(unit_bones.names)}
    spine_indices = {name_to_index[n]: n for n in SPINE_BONES if n in name_to_index}
    print(f"spine bones: {list(spine_indices.values())}")

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
        handle.seek(72 + type_count * 32)
        for _ in range(file_count):
            entry = handle.read(80)
            file_id, type_id = struct.unpack_from("<QQ", entry, 0)
            if type_id != ANIMATION_TYPE_ID:
                continue
            pack_index[file_id] = (
                struct.unpack_from("<Q", entry, 16)[0],
                struct.unpack_from("<Q", entry, 40)[0],
            )

    flagged = []
    compared = 0
    for anim_id in sorted(anim_ids):
        game_e = game_entry(anim_id)
        loc = pack_index.get(anim_id)
        if game_e is None or loc is None:
            continue
        game_anim = AnimationData.parse(game_e.toc_data)
        with PACK.open("rb") as handle:
            handle.seek(loc[0])
            pack_anim = AnimationData.parse(handle.read(loc[1]))
        compared += 1
        game_rot, _, _ = _build_tracks(game_anim)
        pack_rot, _, _ = _build_tracks(pack_anim)
        length = min(game_anim.animation_length, pack_anim.animation_length)
        samples = [length * f / 10.0 for f in range(11)]
        worst = (0.0, None, 0.0)
        for index, name in spine_indices.items():
            for t in samples:
                try:
                    a = game_rot[index].evaluate(t)
                    b = pack_rot[index].evaluate(t)
                except Exception:
                    continue
                if not a or not b or len(a) != 4 or len(b) != 4:
                    continue
                angle = quat_angle(a, b)
                if angle > worst[0]:
                    worst = (angle, name, t)
        if worst[0] > 0.15:  # ~8.6 degrees
            flagged.append((anim_id, game_anim.animation_length, game_anim.is_additive, worst))
    print(f"compared: {compared}")
    print(f"clips with spine rotation deviation > 8.6 deg: {len(flagged)}")
    for anim_id, length, add, (angle, name, t) in sorted(flagged, key=lambda x: -x[3][0]):
        print(f"  {anim_id}: len={length:.2f}s additive={add} worst={name} {angle / 3.14159265 * 180:.1f} deg @ {t:.2f}s")
    conn.close()


if __name__ == "__main__":
    main()
