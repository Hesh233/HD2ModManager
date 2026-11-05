"""Archive B19 sessions and separate game observations from matrix evidence."""
from collections import Counter, defaultdict
import hashlib
import re
from pathlib import Path
from package_native_v12 import ROOT, load, save_json

W = ROOT / 'outputs/native-v28-b20-20261105'
E = W / 'evidence'
GAME = Path.home() / 'AppData/Roaming/Arrowhead/Helldivers2'
FEEDBACK = {
    '0': '19-0 没有效果',
    'LR': '19-lr 右手成功握住武器，上下摆动视觉也正常，武器大概扭转了90度，需要纠正，左手无变化',
    'R': '19-r 右手成功握住武器，上下摆动视觉也正常，武器大概扭转了90度，需要纠正，左手无变化',
}


def main():
    E.mkdir(parents=True, exist_ok=True)
    snapshots = {}
    for name in ('hd2physbone.log', 'chef_loader.log'):
        path = GAME / name
        raw = path.read_bytes()
        snapshots[name] = dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                               text=raw.decode('utf-8', errors='replace'))
    text = snapshots['hd2physbone.log']['text']
    matches = list(re.finditer(r'^.*?\[grip_align\] variant=(0|LR|R) event=loaded version=1\.0\.0 .*$', text, re.M))
    assert matches, 'No B19 game sessions found'
    loader = snapshots['chef_loader.log']['text'].splitlines()
    results = []
    for i, match in enumerate(matches):
        variant = match[1]
        chunk = text[match.start():matches[i+1].start() if i+1 < len(matches) else len(text)]
        all_lines = chunk.splitlines()
        lines = [s for s in all_lines if '[grip_align]' in s]
        records = [dict(re.findall(r'(\w+)=([^ ]+)', s)) for s in lines]
        assert all(r['variant'] == variant for r in records)
        expected = {'attach_hand_r'} | ({'attach_hand_l'} if variant == 'LR' else set())
        aligned = [r for r in records if r['event'] == 'aligned']
        refreshed = [r for r in records if r['event'] == 'post_refresh']
        counts = Counter(r['event'] for r in records)
        assert not any(counts[e] for e in ('disabled', 'rollback', 'validation_mismatch', 'restore_failed'))
        if variant == '0':
            assert not aligned and not refreshed
        else:
            assert aligned and refreshed
            assert {r['target'] for r in aligned} == expected
            for r in aligned:
                assert float(r['after_m']) < .002 and float(r['matrix_error']) < .002
            assert all(float(r['source_matrix_change']) < .002 and float(r['aim_local_change']) < 2e-5 for r in refreshed)
        start = all_lines[0][:8]
        begins = [j for j, line in enumerate(loader) if line[:8] == start and '==== Chef Shared Loader' in line]
        assert len(begins) == 1
        j = begins[0]
        finish = next(k for k in range(j, len(loader)) if 'shutdown (clean)' in loader[k])
        assert not any('==== Chef Shared Loader' in line for line in loader[j+1:finish])
        key = 'B19-' + variant + '-' + start.replace(':', '')
        (E / (key + '-runtime.log')).write_text(chunk, encoding='utf-8')
        (E / (key + '-loader.log')).write_text('\n'.join(loader[j:finish+1]) + '\n', encoding='utf-8')
        ik = [dict(re.findall(r'(\w+)=([^ ]+)', line)) for line in all_lines if 'weapon_ik_observation' in line]
        per_target = {}
        for target in expected:
            rows = [r for r in aligned if r['target'] == target]
            per_target[target] = dict(samples=len(rows), maxPositionError=max((float(r['after_m']) for r in rows), default=None),
                                      maxMatrixError=max((float(r['matrix_error']) for r in rows), default=None))
        result = dict(variant='B19-' + variant, status='LOGGED_EXECUTION_VERIFIED', userFeedback=FEEDBACK[variant],
            sessionStart=start, sessionEnd=loader[finish][:8], cleanShutdown=True, eventCounts=dict(counts), targets=per_target,
            sourceMaxMatrixChange=max((float(r['source_matrix_change']) for r in refreshed), default=None),
            aimMaxLocalChange=max((float(r['aim_local_change']) for r in refreshed), default=None),
            postRefreshMaxTargetError=max((float(r['target_matrix_error']) for r in refreshed), default=None),
            rightGripUserAccepted=variant != '0', upDownVisualUserAccepted=variant != '0',
            weaponTwistDegreesUserEstimate=90 if variant != '0' else None, leftVisualChangeObserved=False,
            twistAxisConfirmed=False, flickerCauseConfirmed=False, weaponIkObservations=ik,
            skippedRestores=[s for s in lines if 'event=restore_skipped' in s])
        save_json(E / (key + '-result.json'), result)
        results.append(result)
    assert {r['variant'] for r in results} == {'B19-0', 'B19-R', 'B19-LR'}
    save_json(E / 'B19-comparison.json', dict(status='PASS', sessions=results,
        sources={name: {k: v for k, v in data.items() if k != 'text'} for name, data in snapshots.items()},
        conclusion='R/LR have verified target readbacks and user-confirmed right grip response. Left target readback succeeded in LR without visible left change. Rotation axes and left driving chain remain to be tested.'))
    for r in results:
        print(r['variant'], r['sessionStart'], r['sessionEnd'], r['eventCounts'], r['targets'])


if __name__ == '__main__':
    main()
