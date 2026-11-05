"""Verify the IK unreachable-target fix restores elbow motion in the frozen clips."""
from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID, BONE_TYPE_ID, UNIT_TYPE_ID
from anim_batch_mod.formats import AnimationData, BonesData, UnitData
from anim_batch_mod.processor import ModConfig, modify_animation_with_world_compensation

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
CHARACTER_UNIT = 5556372446766824087
CONFIG = Path(__file__).with_name("config.toml")

CASES = [
    (3542481557377973498, "r_elbow"),
    (11623262177752411465, "r_elbow"),
    (2372646189065085873, "l_elbow"),
    (7487460257401496141, "r_elbow"),
    (2079987957316695397, "l_elbow"),
]
ARM_BONES = ["r_shoulder", "r_elbow", "r_hand", "l_shoulder", "l_elbow", "l_hand"]


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def spread(animation: AnimationData, index: int) -> tuple[int, float]:
    keys = [entry.data2 for entry in animation.entries if entry.is_rotation and entry.bone == index]
    if not keys:
        return 0, 0.0
    sp = max(abs(a[c] - b[c]) for a in keys for b in keys for c in range(4))
    return len(keys), sp


def main() -> None:
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)
    config = ModConfig.load(CONFIG.resolve())
    arch = TocArchive.load_toc_only(store, KEYWORD)
    ue = next(e for e in arch.entries_of_type(UNIT_TYPE_ID) if e.file_id == CHARACTER_UNIT)
    unit = UnitData.parse(ue.toc_data)
    brow = conn.execute(
        "SELECT package_name FROM resources WHERE file_id=? AND type_id=?",
        (blob(unit.bones_ref), blob(BONE_TYPE_ID)),
    ).fetchone()
    bones = BonesData.parse(
        TocArchive.load_toc_only(store, brow[0]).get_entry(unit.bones_ref, BONE_TYPE_ID).toc_data
    )
    n2i = {n: i for i, n in enumerate(bones.names)}

    for anim_id, frozen_bone in CASES:
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id=? AND type_id=?",
            (blob(anim_id), blob(ANIMATION_TYPE_ID)),
        ).fetchone()
        entry = TocArchive.load_toc_only(store, row[0]).get_entry(anim_id, ANIMATION_TYPE_ID)
        game = AnimationData.parse(entry.toc_data)
        fixed = AnimationData.parse(entry.toc_data)
        result = modify_animation_with_world_compensation(
            fixed,
            bones,
            unit,
            config,
            allow_additive=True,
            apply_offsets_to_additive=False,
            apply_rotate_multipliers=True,
            apply_ik_correction=True,
        )
        print(f"--- {anim_id} (len={game.animation_length:.2f}s, frozen: {frozen_bone}) ---")
        for n in ARM_BONES:
            g = spread(game, n2i[n])
            f = spread(fixed, n2i[n])
            flag = " <- restored" if n == frozen_bone and f[1] > 0.03 else ""
            print(
                f"  {n:12} game k={g[0]:>3} sp={g[1]:.4f} | fixed k={f[0]:>3} sp={f[1]:.4f}{flag}"
            )
    conn.close()


if __name__ == "__main__":
    main()
