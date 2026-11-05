"""Independently verify B21 affine/angle results with NumPy and raw log lines."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from analyze_native_b21_native_grips import PAIRS, LOCALS


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def mat(values):
    result = np.eye(4)
    result[:3, :3] = np.asarray(values[:9]).reshape(3, 3, order='F')
    result[:3, 3] = values[9:]
    return result


def proper(m):
    u, _, vt = np.linalg.svd(m[:3, :3])
    result = u @ vt
    assert np.linalg.det(result) > 0
    return result


def degrees(a, b):
    relative = proper(a).T @ proper(b)
    sine = np.linalg.norm([relative[2, 1]-relative[1, 2], relative[0, 2]-relative[2, 0], relative[1, 0]-relative[0, 1]]) / 2
    cosine = (np.trace(relative) - 1) / 2
    return float(np.degrees(np.arctan2(sine, cosine)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observation', type=Path)
    args = parser.parse_args()
    output = args.observation.resolve()
    manifest = load(output / 'snapshot-manifest.json')
    report = load(output / 'observed-native-grips.json')
    audit = load(output / 'deployment-audit.json')
    expected = {}
    for line in (output / 'relative-poses.jsonl').open(encoding='utf-8'):
        row = json.loads(line)
        key = row['sample'], row['phase']
        assert key not in expected
        expected[key] = row
    counts, exact, errors, closures = Counter(), Counter(), defaultdict(float), defaultdict(float)
    verified, relations, raw_units, captured_poses = 0, 0, 0, 0
    units = {}
    for line_no, line in enumerate((output / 'native-grip-latest.log').open(encoding='utf-8'), 1):
        row = json.loads(line.split('[native_capture] ', 1)[1])
        if row['event'] == 'phase_begin':
            units = {}
        elif row['event'] == 'unit':
            units[row['id']] = (line_no, row, {n['name']: n for n in row['nodes']})
            raw_units += 1
        elif row['event'] == 'phase_end' and (row['sample'], row['phase']) in expected:
            item = expected.pop((row['sample'], row['phase']))
            poses = {}
            for key, values in item['worldPoses'].items():
                role, name = key.split(':', 1)
                no, raw, nodes = units[item['unitIds'][role]]
                assert no == item['evidenceLines'][role]
                assert (raw['world'], raw['frame'], raw['sample'], raw['phase']) == (item['world'], item['frame'], item['sample'], item['phase'])
                assert raw['owner'] == 'unverified' and values == nodes[name]['worldMatrix']
                poses[key] = mat(values)
                captured_poses += 1
            for name, (ar, an, br, bn) in PAIRS.items():
                a, b = poses[ar + ':' + an], poses[br + ':' + bn]
                relative = np.linalg.inv(a) @ b
                err = float(np.max(np.abs(relative - mat(item['relative'][name]))))
                errors['affineMaximumElementDifference'] = max(errors['affineMaximumElementDifference'], err)
                assert err < 1e-9
                d = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
                deg = degrees(a, b)
                metric = item['metrics'][name]
                errors['worldDistanceMaximumDifferenceMetres'] = max(errors['worldDistanceMaximumDifferenceMetres'], abs(d-metric['metres']))
                errors['rotationMaximumDifferenceDegrees'] = max(errors['rotationMaximumDifferenceDegrees'], abs(deg-metric['degrees']))
                assert abs(d-metric['metres']) < 1e-10 and abs(deg-metric['degrees']) < 1e-5
                counts[(item['group'], item['phase'], name)] += int(d < .001 and deg < .1)
                exact[(item['group'], item['phase'], name)] += int(np.array_equal(a, b))
                relations += 1
            for name, (role, node) in LOCALS.items():
                assert item['locals'][name] == units[item['unitIds'][role]][2][node]['localMatrix']
            hr, ar = poses['avatar:r_hand'], poses['avatar:attach_hand_r']
            local = {k: mat(v) for k, v in item['locals'].items()}
            predicted = {
                'wrist_local_to_mount': (hr @ local['r_mount'], ar),
                'mount_to_right_ik': (ar @ local['right_ik'], poses['weapon:IK_right']),
                'wrist_local_to_right_ik': (hr @ local['r_mount'] @ local['right_ik'], poses['weapon:IK_right']),
                'mount_to_foregrip_ik': (ar @ local['underbarrel'] @ local['foregrip_ik'], poses['foregrip:IK_left']),
            }
            for key, (a, b) in predicted.items():
                distance = float(np.linalg.norm(a[:3, 3] - b[:3, 3]))
                assert abs(distance-item['closure'][key]['metres']) < 1e-10
                closure_key = item['group'] + ':' + item['phase'] + ':' + key
                closures[closure_key] = max(closures[closure_key], distance)
            verified += 1
    assert not expected and raw_units == manifest['eventCounts']['unit']
    assert verified == report['completeFiveUnitPairs'] * 2
    for group in report['groups']:
        for phase in ('update', 'render'):
            for key, value in group['phases'][phase]['relations'].items():
                assert counts[group['group'], phase, key] == value['coincidentSamples']
                assert exact[group['group'], phase, key] == value['exactWorldMatrixMatches']
    assert sha(output / 'native-grip-latest.log') == report['sourceSha256'] == manifest['snapshotSha256']
    assert sha(Path(manifest['source'])) == manifest['sourceSha256'], 'Original append log changed during analysis'
    assert sha(output / 'deployment-audit.json') == report['deploymentAuditSha256']
    assert all(sha(Path(p['path'])) == p['sha256'] for p in audit['patches']), 'Current patch bytes changed during analysis'
    result = dict(status='PASSED', independentMethod='NumPy 4x4 inverse/composition; SVD proper rotations; atan2 angular distance',
                  numpyVersion=np.__version__, verifiedSnapshots=verified, verifiedRelations=relations,
                  verifiedWorldPoseCopies=captured_poses, rawUnitRecords=raw_units,
                  numericalMaximumDifferences=dict(errors), maximumClosureMetres=dict(closures),
                  sourceAppendLogUnchanged=True, deployedPatchBytesUnchanged=True,
                  summaryCountsIndependentlyRecomputed=True,
                  checkedReportSha256=sha(output / 'observed-native-grips.json'),
                  checkedRelativePoseSha256=sha(output / 'relative-poses.jsonl'))
    (output / 'analysis-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
