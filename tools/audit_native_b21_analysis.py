"""Verify B21 analysis numerics and identity boundaries with simulated data."""
import copy
import json
import math
from pathlib import Path
import tempfile
from package_native_v12 import ROOT, digest, save_json
from analyze_native_b21_capture import analyze, affine_relative, basis, compose, inverse, mul, rotation, angle, markdown

W = ROOT / 'outputs/native-v29-b21-20261105'
IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def main():
    checks = []

    def check(value, label):
        assert value, label
        checks.append(label)

    # Nonuniform scale, shear, nonzero translation and known rotations catch
    # row/column order errors that a test of inverse(identity) would miss.
    a = [0, 2, 0, -3, 0, 0, 0, 0, 4, 4, -2, 1]
    local = [0, 0, -1, 0, 1, 0, 1, 0, 0, .2, -.3, .5]
    b = compose(a, local)
    check(max(abs(x-y) for x, y in zip(affine_relative(a, b), local)) < 1e-12, 'affine nonuniform-scale round trip')
    sheared = [[1, .25, -.1], [.2, 2, .3], [.1, -.2, 3]]
    product = mul(sheared, inverse(sheared))
    check(max(abs(product[r][c] - (r == c)) for r in range(3) for c in range(3)) < 1e-12, 'full 3x3 inverse with shear')
    r = rotation(a)
    check(abs(angle(r) - 90) < 1e-9, '90 degree rotation separated from scale')
    rz = [.6, .8, 0, -.8, .6, 0, 0, 0, 1, 100, -30, 12]
    check(max(abs(x-y) for x, y in zip(affine_relative(compose(rz, a), compose(rz, b)), local)) < 1e-12,
          'relative pose independent of common rigid world motion')
    reflected = IDENTITY.copy()
    reflected[0] = -1
    check(rotation(reflected) is None and rotation([0]*12) is None, 'reflection and singular basis excluded from rotation')
    shear_spd = [2, .2, 0, .2, 1, .1, 0, .1, 1.5, 0, 0, 0]
    shear_rotated = compose(rz, shear_spd)
    check(angle(rotation(shear_rotated), rotation(rz)) < 1e-5, 'polar rotation ignores symmetric shear')

    path = W / 'fixture-native-capture.log'
    report = analyze(path, 'simulated_fixture')
    check(report['status'] == 'ANALYZED' and report['completedSamplePairs'] == 14, '14 complete native callback pairs')
    session = report['sessions'][0]
    check(session['layouts'] == ['native_107'] and len(session['units']) == 10, 'native Avatar and nine observed consumers')
    callbacks = session['callbackDifferences']
    left = next(x for x in callbacks if x['node']['kind'] == 'avatar' and x['node']['name'] == 'l_hand')
    check(left['pairs'] == 14 and abs(left['metrics']['worldPositionDistanceMetres']['mean'] - .01) < 1e-7,
          'intentional 1 cm Avatar left-hand world change recovered')
    check(left['metrics']['localPositionDistanceMetres']['maximum'] == 0, 'world-only Avatar movement is not a local-pose change')
    consumers = [x for x in callbacks if x['node']['kind'] != 'avatar']
    check(all(x['metrics']['worldPositionDistanceMetres']['maximum'] == 0 for x in consumers),
          'independent cached model and weapon graphs remain stationary between callbacks')
    check(all(x['metrics']['worldRotationDeltaDegrees']['maximum'] < 1e-5 for x in callbacks),
          'no spurious rotation change in fixture callbacks')
    static_pairs = [x for x in session['relations'] if x['phase'] == 'update']
    check(all(x['metrics']['offsetChangeFromFirstMetres']['maximum'] < 2e-6 for x in static_pairs),
          'common world motion does not become relative offset drift')
    check(all(x['metrics']['rotationChangeFromFirstDegrees']['maximum'] < 1e-5 for x in static_pairs),
          'common world rotation does not become relative twist')
    check(any(x['category'] == 'avatar_to_foregrip_candidate' for x in static_pairs)
          and any(x['category'] == 'weapon_to_foregrip_candidate' for x in static_pairs)
          and any(x['category'] == 'avatar_to_skin_input' for x in static_pairs),
          'native armor, weapon and separate foregrip relationships analyzed')
    check(all(x['owner'] == 'unverified' for x in session['relations'] if x['a']['id'] != x['b']['id']),
          'cross-unit ownership never inferred')
    check(not report['gamePoseCaptured'] and '模拟数据' in markdown(report), 'fixture provenance remains explicit')

    rows = [json.loads(line.split('[native_capture] ', 1)[1]) for line in path.read_text(encoding='utf-8').splitlines()]
    first = [row for row in rows if row['event'] == 'loaded' or row.get('sample') == 1]
    with tempfile.TemporaryDirectory(prefix='analysis-fixture-', dir=W) as tmp:
        assert Path(tmp).resolve().is_relative_to(W.resolve())
        test_path = Path(tmp) / 'boundary-fixture.log'

        def trial(events):
            test_path.write_text(''.join('2000-01-01 [native_capture] '+json.dumps(row)+'\n' for row in events), encoding='utf-8')
            return analyze(test_path, 'simulated_fixture')

        separate = trial(first + copy.deepcopy(first))
        check(len(separate['sessions']) == 2 and all(s['completedSamplePairs'] == 1 for s in separate['sessions']),
              'reused IDs and samples after loaded remain separate sessions')
        cross_world = copy.deepcopy(first)
        for row in cross_world:
            if row['event'] == 'unit' and row['kind'] == 'weapon':
                row['world'] = 2
        unrelated = trial(cross_world)['sessions'][0]
        check(not any(r['category'] in ('avatar_to_weapon_candidate', 'weapon_to_foregrip_candidate',
                                       'skin_input_to_weapon_candidate') for r in unrelated['relations']),
              'nearby coordinates in different worlds never form candidate pairs')
        replaced = copy.deepcopy(first)
        for row in replaced:
            if row['event'] == 'unit' and row['phase'] == 'render' and row['kind'] == 'avatar':
                row['id'] = 1001
        rebuilt = trial(replaced)['sessions'][0]
        check(not any(r['node']['kind'] == 'avatar' for r in rebuilt['callbackDifferences'])
              and rebuilt['issues']['unpaired_unit_snapshots'] == 2,
              'same resource with different instances is not a callback pair')
        truncated = trial([r for r in first if r.get('phase') != 'render'])['sessions'][0]
        check(truncated['completedSamplePairs'] == 0 and truncated['issues']['sample_without_render'] == 1,
              'missing render is reported without fabricating pose changes')
        partial = trial([r for r in first if not (r['event'] == 'phase_end' and r['phase'] == 'render')])['sessions'][0]
        check(partial['completedSamplePairs'] == 0 and partial['issues']['partial_phase_excluded'] == 1,
              'truncated phase is excluded')
        duplicated = copy.deepcopy(first)
        duplicate = next(r for r in duplicated if r['event'] == 'unit' and r['kind'] == 'avatar')
        duplicated.insert(duplicated.index(duplicate)+1, copy.deepcopy(duplicate))
        ambiguous = trial(duplicated)['sessions'][0]
        check(ambiguous['issues']['duplicate_unit_sample'] == 1
              and not any(r['node']['kind'] == 'avatar' for r in ambiguous['callbackDifferences']),
              'duplicate unit records are excluded instead of silently overwritten')
        trial(first)
        with test_path.open('a', encoding='utf-8') as stream:
            stream.write('[native_capture] {"event":')
        damaged = analyze(test_path, 'simulated_fixture')
        check(len(damaged['parseErrors']) == 1 and damaged['completedSamplePairs'] == 1,
              'damaged append tail does not erase completed samples')
        try:
            analyze(test_path, 'game_log')
        except ValueError:
            fixture_guard = True
        else:
            fixture_guard = False
        check(fixture_guard, 'fixture input cannot be marked as an actual game log')
    filtered = analyze(path, 'simulated_fixture', 4, 6)
    check(filtered['completedSamplePairs'] == 3
          and all(x['firstSample'] == 4 and x['lastSample'] == 6 for x in filtered['sessions'][0]['relations']),
          'sample interval can isolate an action without combining other phases')
    save_json(W / 'fixture-capture-analysis.json', report)
    (W / 'fixture-capture-analysis.md').write_text(markdown(report), encoding='utf-8')
    save_json(W / 'capture-analysis-audit.json', dict(status='PASS', checks=checks,
        analyzerSha256=digest(ROOT / 'tools/analyze_native_b21_capture.py'),
        testSha256=digest(Path(__file__)), fixtureSha256=digest(path),
        fixtureReportSha256=digest(W / 'fixture-capture-analysis.json'), gamePoseCaptured=False))
    print('PASS:', len(checks), 'analysis checks; 14 callback pairs; Avatar-only 0.01 m movement recovered.')


if __name__ == '__main__':
    main()
