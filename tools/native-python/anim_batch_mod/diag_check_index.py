"""Diagnostic: inspect the resource index for duplicate package versions."""
from __future__ import annotations

import sqlite3
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from anim_batch_mod.archive import PackageStore, ResourceIndex
from anim_batch_mod.constants import (
    ANIMATION_TYPE_ID,
    BONE_TYPE_ID,
    STATE_MACHINE_TYPE_ID,
    UNIT_TYPE_ID,
)

GAME_DATA = Path(r"E:\Steam\steamapps\common\Helldivers 2\data")
CACHE = Path(__file__).with_name("cache") / "resource_index.sqlite3"
KEYWORD = "18235e0c9ec0e636"
TYPES = [BONE_TYPE_ID, UNIT_TYPE_ID, STATE_MACHINE_TYPE_ID, ANIMATION_TYPE_ID]


def blob(value: int) -> bytes:
    return struct.pack("<Q", value)


def main() -> None:
    store = PackageStore(GAME_DATA)
    print(f"bundled={store.is_bundled}, packages listed in bundles.nxa: {len(store.packages)}")

    fingerprint = store.index_fingerprint()
    conn = sqlite3.connect(CACHE)
    meta = dict(conn.execute("SELECT key, value FROM metadata"))
    print(f"cache fingerprint matches current store: {meta.get('game_fingerprint') == fingerprint}")
    print(f"cache built with indexed types: {meta.get('indexed_types')}")

    for type_id, label in ((UNIT_TYPE_ID, "Unit"), (STATE_MACHINE_TYPE_ID, "StateMachine")):
        rows = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT file_id) FROM resources WHERE type_id = ?",
            (blob(type_id),),
        ).fetchone()
        print(f"{label}: {rows[0]} (file_id, package) rows, {rows[1]} distinct file_ids")

    # How many file_ids are recorded in more than one package (duplicate versions)?
    dup_rows = conn.execute(
        """
        SELECT type_name, duplicates, COUNT(*) AS file_ids
        FROM (
            SELECT r.type_id, COUNT(DISTINCT r.package_name) AS duplicates
            FROM resources r
            WHERE r.type_id IN (?, ?, ?, ?)
            GROUP BY r.file_id, r.type_id
        )
        JOIN (SELECT ? AS type_name, ? AS type_id
              UNION SELECT 'unit', ?
              UNION SELECT 'state_machine', ?
              UNION SELECT 'animation', ?) names
              USING (type_id)
        GROUP BY type_name, duplicates
        ORDER BY type_name, duplicates
        """,
        (
            blob(BONE_TYPE_ID), blob(UNIT_TYPE_ID), blob(STATE_MACHINE_TYPE_ID), blob(ANIMATION_TYPE_ID),
            "bones", blob(BONE_TYPE_ID),
            blob(UNIT_TYPE_ID),
            blob(STATE_MACHINE_TYPE_ID),
            blob(ANIMATION_TYPE_ID),
        ),
    ).fetchall()
    print("\nfile_id copies per package count (bones/unit/state_machine/animation):")
    for type_name, duplicates, file_ids in dup_rows:
        print(f"  {type_name}: {duplicates} package(s) -> {file_ids} file_ids")

    # Which packages does the keyword match?
    matched = [
        name for name in store.packages
        if KEYWORD in name.lower()
    ]
    print(f"\npackages in bundles.nxa whose name contains keyword: {matched}")

    for package in matched:
        rows = conn.execute(
            "SELECT COUNT(*) FROM resources WHERE package_name = ? AND type_id = ?",
            (package, blob(STATE_MACHINE_TYPE_ID)),
        ).fetchone()
        units = conn.execute(
            "SELECT COUNT(*) FROM resources WHERE package_name = ? AND type_id = ?",
            (package, blob(UNIT_TYPE_ID)),
        ).fetchone()
        first = store.packages[package].entries[0] if store.packages[package].entries else None
        print(f"  {package}: Units={units[0]}, StateMachines={rows[0]}, first bundle={first.bundle_index if first else '-'}")

    # For each StateMachine file_id found in the matched package(s), list every package copy.
    matched_set = set(matched)
    if matched_set:
        sm_ids = [
            struct.unpack("<Q", row[0])[0]
            for row in conn.execute(
                "SELECT DISTINCT file_id FROM resources WHERE type_id = ? AND package_name IN (%s)"
                % ",".join("?" * len(matched)),
                (blob(STATE_MACHINE_TYPE_ID), *matched),
            )
        ]
        print(f"\nStateMachines in matched package(s): {len(sm_ids)}")
        copies = {}
        for sm_id in sm_ids:
            rows = conn.execute(
                "SELECT package_name FROM resources WHERE file_id = ? AND type_id = ?",
                (blob(sm_id), blob(STATE_MACHINE_TYPE_ID)),
            ).fetchall()
            packages = sorted(row[0] for row in rows)
            copies.setdefault(tuple(packages), []).append(sm_id)
        for packages, ids in sorted(copies.items(), key=lambda item: -len(item[1])):
            marker = " <- matched by keyword" if any(p in matched_set for p in packages) else ""
            bundle_info = []
            for p in packages:
                entries = store.packages.get(p)
                b = entries.entries[0].bundle_index if entries and entries.entries else -1
                bundle_info.append(f"{p}(bundle{b:02d})")
            print(f"  {len(ids)} StateMachine(s) also in: {', '.join(bundle_info)}{marker}")
    conn.close()


if __name__ == "__main__":
    main()
