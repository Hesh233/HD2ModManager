"""Remove StateMachine entries from a skeleton/skin mod patch.

Shipping a StateMachine copy inside the skeleton mod freezes it at build
time: every game update that adds character animation states (new weapon
moves etc.) then plays without those states (e.g. 7.2's weapon bolt-pull
leaving the right arm frozen). With the entry removed the patched Unit's
state_machine_ref resolves against the vanilla StateMachine instead, which
the game always keeps current.

Usage:
    python remove_state_machine.py <patch_file> [-o OUTPUT]

<patch_file> is the skeleton mod's TOC file (e.g. 9ba626afa44a3aa3.patch_1);
its .gpu_resources / .stream sidecars must sit beside it. The output is a
three-file patch set; the input files are never modified.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root))

from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import STATE_MACHINE_TYPE_ID


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete StateMachine entries from a Helldivers 2 patch so "
        "the game uses the vanilla StateMachine."
    )
    parser.add_argument("patch", type=Path, help="Skeleton mod TOC patch file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output patch file (default: <input name>_noSM beside the input)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    patch_path = args.patch.resolve()
    gpu_path = Path(f"{patch_path}.gpu_resources")
    stream_path = Path(f"{patch_path}.stream")
    for required in (patch_path, gpu_path, stream_path):
        if not required.is_file():
            print(f"Error: missing patch part: {required}", file=sys.stderr)
            return 1

    archive = TocArchive.parse_parts(
        patch_path.read_bytes(), gpu_path.read_bytes(), stream_path.read_bytes()
    )

    machines = archive.entries_of_type(STATE_MACHINE_TYPE_ID)
    if not machines:
        print("No StateMachine entries in this patch - nothing to do.")
        return 0
    for entry in machines:
        print(f"removing StateMachine {entry.file_id} ({len(entry.toc_data)} bytes)")
    for entry in machines:
        del archive.entries[(entry.file_id, STATE_MACHINE_TYPE_ID)]

    output_path = args.output.resolve() if args.output else patch_path.with_name(
        f"{patch_path.stem}_noSM{patch_path.suffix}"
    )
    written = archive.write_patch(output_path, list(archive.entries.values()))

    verify = TocArchive.parse_parts(
        written[0].read_bytes(), written[1].read_bytes(), written[2].read_bytes()
    )
    remaining = len(verify.entries)
    leftover = verify.entries_of_type(STATE_MACHINE_TYPE_ID)
    if leftover:
        print(
            f"Error: verification failed, {len(leftover)} StateMachine entries remain",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: wrote {remaining} entries "
        f"({len(machines)} StateMachine removed) -> {written[0]}"
    )
    print("Copy the three output files over the mod's files in the game data folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
