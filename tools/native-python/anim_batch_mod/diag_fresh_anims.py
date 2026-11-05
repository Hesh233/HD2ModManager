"""Enumerate the update's new-layer animations (bundle28+ only, outside the
character's 3180) and map them to the StateMachines that reference them."""
from __future__ import annotations

import sqlite3
import struct
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID, STATE_MACHINE_TYPE_ID, UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData, parse_state_machine_animation_ids

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def bundle_of(store: PackageStore, pkg: str) -> int:
    e = store.packages.get(pkg)
    return e.entries[0].bundle_index if e and e.entries else -1


def main() -> None:
    store = PackageStore(GAME_DATA)
    conn = sqlite3.connect(CACHE)

    rows = conn.execute(
        "SELECT file_id, package_name FROM resources WHERE type_id = ?",
        (blob(ANIMATION_TYPE_ID),),
    ).fetchall()
    by_anim: dict[int, set[str]] = defaultdict(set)
    for fid_blob, pkg in rows:
        by_anim[struct.unpack("<Q", fid_blob)[0]].add(pkg)

    def generation(pkg: str) -> int:
        b = bundle_of(store, pkg)
        return 1 if b >= 28 else 0

    # Animations that exist only in the newest bundle generation (28+).
    fresh = {
        anim_id: sorted(pkgs)
        for anim_id, pkgs in by_anim.items()
        if all(generation(p) == 1 for p in pkgs)
    }
    # The character's 3180 come from the compatible Unit's StateMachine; exclude
    # them by checking against the known animation archive's own Unit SM.
    char_ids: set[int] = set()
    arch = TocArchive.load_toc_only(store, "18235e0c9ec0e636")
    for ue in arch.entries_of_type(UNIT_TYPE_ID):
        unit = UnitData.parse(ue.toc_data)
        if ue.file_id != 5556372446766824087:
            continue
        srow = conn.execute(
            "SELECT package_name FROM resources WHERE file_id=? AND type_id=?",
            (blob(unit.state_machine_ref), blob(STATE_MACHINE_TYPE_ID)),
        ).fetchone()
        se = TocArchive.load_toc_only(store, srow[0]).get_entry(
            unit.state_machine_ref, STATE_MACHINE_TYPE_ID
        )
        char_ids = set(parse_state_machine_animation_ids(se.toc_data))
    print(f"fresh(new-layer) animations: {len(fresh)}, character refs: {len(char_ids)}")

    others = {aid: pkgs for aid, pkgs in fresh.items() if aid not in char_ids}
    print(f"fresh animations outside the character set: {len(others)}")

    # Group by package.
    by_pkg: dict[str, list[int]] = defaultdict(list)
    for aid, pkgs in others.items():
        for p in pkgs:
            by_pkg[p].append(aid)
    print("packages holding fresh non-character animations:")
    for pkg, ids in sorted(by_pkg.items(), key=lambda kv: -len(kv[1])):
        print(f"  {pkg} (b{bundle_of(store, pkg):02d}): {len(ids)} clips")

    # For the top packages, find which Units/StateMachines reference their clips.
    sm_cache: dict[str, TocArchive] = {}
    for pkg, ids in sorted(by_pkg.items(), key=lambda kv: -len(kv[1]))[:8]:
        idset = set(ids)
        arch = TocArchive.load_toc_only(store, pkg)
        found = []
        for ue in arch.entries_of_type(UNIT_TYPE_ID):
            try:
                unit = UnitData.parse(ue.toc_data)
            except Exception:
                continue
            if not unit.state_machine_ref:
                continue
            srow = conn.execute(
                "SELECT package_name FROM resources WHERE file_id=? AND type_id=?",
                (blob(unit.state_machine_ref), blob(STATE_MACHINE_TYPE_ID)),
            ).fetchall()
            for (spkg,) in srow:
                if spkg not in sm_cache:
                    sm_cache[spkg] = TocArchive.load_toc_only(store, spkg)
                se = sm_cache[spkg].get_entry(unit.state_machine_ref, STATE_MACHINE_TYPE_ID)
                if se is None:
                    continue
                try:
                    refs = set(parse_state_machine_animation_ids(se.toc_data))
                except Exception:
                    continue
                hit = len(refs & idset)
                if hit:
                    found.append((ue.file_id, unit.state_machine_ref, hit, len(refs)))
        print(f"  pkg {pkg} (b{bundle_of(store, pkg):02d}) referencing Units:")
        for uid, sm, hit, total in found[:6]:
            print(f"    Unit {uid} SM {sm}: {hit}/{total} clips in this pkg")
    conn.close()


if __name__ == "__main__":
    main()
