"""Verify the fixed O-3 variant against the original native-rig payload and game index."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import row_pose, validate_manifest
from anim_batch_mod.processor import _calculate_world_transforms


def read_patch(path):
    def sidecar(suffix):
        side = Path(str(path) + suffix)
        return side.read_bytes() if side.exists() else b""
    return TocArchive.parse_parts(path.read_bytes(), sidecar('.gpu_resources'), sidecar('.stream'))


def verify(work, release):
    result = json.loads((work / 'rekey-result.json').read_text(encoding='utf-8-sig'))
    assert result['ok'] and result['headMerge'] == 'off'
    targets = {'f9ced2d898787705', 'a2999407862595df'}
    assert set(result['targets']) == targets
    source_dir = release / 'project/models/test01'
    manifest = json.loads((source_dir / 'source-skeleton.json').read_text(encoding='utf-8-sig'))
    validate_manifest(manifest)
    source = {e.file_id: e for e in read_patch(source_dir / '9ba626afa44a3aa3.patch_0').entries_of_type(UNIT_TYPE_ID)}
    output = {e.file_id: e for e in read_patch(Path(result['outputPatch'])).entries_of_type(UNIT_TYPE_ID)}
    mappings = []
    max_bind_error = 0.0
    for line in result['mappings']:
        match = re.fullmatch(r'(.+) ← 0x([0-9a-f]+) → 0x([0-9a-f]+)', line)
        assert match, line
        description, source_id, target_id = match.groups()
        original, converted = source[int(source_id, 16)], output[int(target_id, 16)]
        for field in ('toc_data', 'gpu_data', 'stream_data'):
            assert getattr(original, field) == getattr(converted, field), (target_id, field)
        unit = UnitData.parse(converted.toc_data)
        positions = {value: i for i, value in enumerate(unit.name_hashes)}
        fk = _calculate_world_transforms(unit.transforms, unit.parents)
        for bone in manifest['bones']:
            i = positions[bone['hash']]
            parent = manifest['driverHashes'][0] if bone['parent'] is None else manifest['bones'][bone['parent']]['hash']
            assert unit.name_hashes[unit.parents[i]] == parent
            expected = row_pose(bone['world'])
            error = math.dist(fk[i].position, expected.position)
            assert error < 1e-5
            assert abs(sum(a*b for a, b in zip(fk[i].rotation, expected.rotation))) > 1 - 1e-5
            max_bind_error = max(max_bind_error, error)
        mappings.append(dict(part=description, sourceUnit=source_id, targetUnit=target_id, payload='byte-identical'))
    assert {int(m['sourceUnit'], 16) for m in mappings} == set(source)
    db = sqlite3.connect((work / 'data/indexes/asset-index.sqlite').as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    kits = [dict(row) for row in db.execute('SELECT * FROM game_data_authority_kits WHERE archive_id IN (?,?)', sorted(targets))]
    assert len(kits) == 2
    authority_units = {row[0] % (1 << 64) for row in db.execute('SELECT DISTINCT unit_file_id FROM game_data_authority_pieces WHERE archive_id IN (?,?) AND slot<>1', sorted(targets))}
    assert set(output) == authority_units, 'O-3 armor/helmet coverage mismatch (cape excluded)'
    mapped = {int(m['targetUnit'], 16) for m in mappings}
    shared = []
    for file_id in output:
        signed = file_id if file_id < (1 << 63) else file_id - (1 << 64)
        rows = db.execute('SELECT DISTINCT k.item_id,k.archive_id,k.display_name FROM game_data_authority_pieces p JOIN game_data_authority_kits k USING(item_id) WHERE p.unit_file_id=? AND k.archive_id NOT IN (?,?)', (signed, *sorted(targets))).fetchall()
        if rows:
            shared.append(dict(unit=f'{file_id:016x}', role='model' if file_id in mapped else 'hidden', otherKits=[dict(row) for row in rows]))
    db.close()
    report = dict(status='PASS', gameTested=False, targets=kits, capeModified=False,
                  sourceBodyParts=len(source), mappedUnits=len(mapped), totalOutputUnits=len(output),
                  sourceBonesPerMappedUnit=len(manifest['bones']), maxBindErrorMetres=max_bind_error,
                  mappings=mappings, sharedUnits=shared, warnings=result['warnings'])
    destination = release / 'project/reports/native-o3-audit.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--release', type=Path, required=True)
    args = parser.parse_args()
    verify(args.work.resolve(), args.release.resolve())
