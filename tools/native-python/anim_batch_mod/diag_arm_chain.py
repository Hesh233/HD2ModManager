"""Check whether the whole arm chain is frozen in the pack for suspect clips."""
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

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
PACK = Path(__file__).with_name("output") / "9ba626afa44a3aa3.patch_0"
KEYWORD = "18235e0c9ec0e636"
CHARACTER_UNIT = 5556372446766824087

ARM_BONES = [
    "r_shoulder", "r_elbow", "r_hand", "r_hand_twist",
    "l_shoulder", "l_elbow", "l_hand",
]


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

    pack_index: dict[int, tuple[int, int]] = {}
    with PACK.open("rb") as handle:
        magic, tc, fc = struct.unpack_from("<III", handle.read(72), 0)
        handle.seek(72 + tc * 32)
        for _ in range(fc):
            entry = handle.read(80)
            fid, tid = struct.unpack_from("<QQ", entry, 0)
            if tid == ANIMATION_TYPE_ID:
                pack_index[fid] = (
                    struct.unpack_from("<Q", entry, 16)[0],
                    struct.unpack_from("<Q", entry, 40)[0],
                )

    for aid in (3542481557377973498, 11623262177752411465, 7487460257401496141, 2372646189065085873):
        row = conn.execute(
            "SELECT package_name FROM resources WHERE file_id=? AND type_id=?",
            (blob(aid), blob(ANIMATION_TYPE_ID)),
        ).fetchone()
        ge = TocArchive.load_toc_only(store, row[0]).get_entry(aid, ANIMATION_TYPE_ID)
        ga = AnimationData.parse(ge.toc_data)
        with PACK.open("rb") as handle:
            handle.seek(pack_index[aid][0])
            pa = AnimationData.parse(handle.read(pack_index[aid][1]))
        print(f"--- {aid} (len={ga.animation_length:.2f}s) ---")
        print(f"  {'bone':14} {'game keys':>10} {'spread':>9} {'pack keys':>10} {'spread':>9}")
        for n in ARM_BONES:
            g = spread(ga, n2i[n])
            p = spread(pa, n2i[n])
            print(f"  {n:14} {g[0]:>10} {g[1]:>9.4f} {p[0]:>10} {p[1]:>9.4f}")
    conn.close()


if __name__ == "__main__":
    main()
