"""Archive and validate the completed L/R trials without changing the logs."""
from collections import Counter, defaultdict
import hashlib
import re
from pathlib import Path
from package_native_v12 import ROOT, load, save_json

W = ROOT / 'outputs/native-v26-b18-20261105'
E = W / 'evidence'
GAME = Path.home() / 'AppData/Roaming/Arrowhead/Helldivers2'
FEEDBACK = {
    'L': '没有效果',
    'R': '武器周期向上移动，上移还是回落无发现闪烁，左手没有变化；火焰喷射器弹夹和纪元弹药的部件没有周期向上移动。',
}


def main():
    E.mkdir(parents=True, exist_ok=True)
    path = GAME / 'hd2physbone.log'
    data = path.read_bytes()
    text = data.decode('utf-8', errors='replace')
    marks = [m.start() for m in re.finditer(r'\[attach_probe\] variant=\S+ event=loaded', text)]
    loader_path = GAME / 'chef_loader.log'
    loader_data = loader_path.read_bytes()
    loader = loader_data.decode('utf-8', errors='replace').splitlines()
    results = {}
    for variant in ('L', 'R'):
        starts = list(re.finditer(r'\[attach_probe\] variant=' + variant + r' event=loaded version=1\.2\.0 ', text))
        assert len(starts) == 1, 'Ambiguous/missing B17 session; select a session explicitly before analysis.'
        start = starts[0].start()
        stop = next((i for i in marks if i > start), len(text))
        lines = [s for s in text[text.rfind('\n', 0, start) + 1:stop].splitlines() if '[attach_probe]' in s]
        records = [dict(re.findall(r'(\w+)=([^ ]+)', s)) for s in lines]
        assert all(r['variant'] == variant for r in records)
        loaded = records[0]
        assert loaded['event'] == 'loaded' and loaded['nodes'] == ('1' if variant == 'L' else '2')
        assert loaded['phase_seconds'] == '4' and loaded['shift_z'] == '0.600' and loaded['validation_only'] == 'false'
        counts = Counter(r['event'] for r in records)
        assert not any(counts[k] for k in ('disabled', 'validation_mismatch', 'rollback', 'restore_failed'))
        profile_path = ROOT / f'outputs/native-manual-20261103/project/diagnostics/B17/variants/{variant}/profile.json'
        profile = load(profile_path)
        assert profile['revision'] == 'test01-v25-B17-' + variant
        expected = {(r['name'], str(r['index'] + 1)) for r in profile['attachmentProbe']['nodes']}
        selected = {r['index'] for r in profile['attachmentProbe']['nodes']}
        roots = sum(r['parentIndex'] not in selected for r in profile['attachmentProbe']['nodes'])
        groups, consumers = defaultdict(list), defaultdict(list)
        applied_rows = [r for r in records if r['event'] == 'applied']
        applied = {(r['avatar'], r['frame']): r for r in applied_rows}
        assert len(applied) == len(applied_rows)
        for row in records:
            if row['event'] == 'node':
                groups[row['avatar'], row['frame']].append(row)
            elif row['event'] == 'consumer':
                assert row['owner'] == 'unverified'
                assert (row['avatar'], row['frame']) in applied
                consumers[row['resource']].append(row)
        assert applied and set(groups) == set(applied)
        for key, rows in groups.items():
            assert len(rows) == len(expected) and {(r['name'], r['index']) for r in rows} == expected
            assert int(applied[key]['nodes']) == len(expected) and int(applied[key]['roots']) == roots
            assert all(max(abs(float(r['dx'])), abs(float(r['dy'])), abs(float(r['dz']) - .6)) < .002 for r in rows)
        summary = {k: dict(kind=rs[0]['kind'], samples=len(rs),
                          upwardSamples=sum(abs(float(r['dz']) - .6) < .002 for r in rs),
                          maxAbsDelta=max(abs(float(r[q])) for r in rs for q in ('dx', 'dy', 'dz')),
                          owner='unverified') for k, rs in consumers.items()}
        assert summary
        if variant == 'R':
            assert any(v['upwardSamples'] for v in summary.values() if v['kind'] == 'weapon')
            assert any(v['upwardSamples'] for v in summary.values() if v['kind'] == 'weapon_grip')
        else:
            assert all(v['maxAbsDelta'] < 1e-6 for v in summary.values())
        begins = [i for i, s in enumerate(loader) if s[:8] == lines[0][:8] and '==== Chef Shared Loader' in s]
        assert len(begins) == 1
        begin = begins[0]
        finish = next(i for i in range(begin, len(loader)) if 'shutdown (clean)' in loader[i])
        assert not any('==== Chef Shared Loader' in s for s in loader[begin + 1:finish])
        loader_rows = loader[begin:finish + 1]
        # These existing messages occur in both trials; they do not establish a cause of the flash.
        observations = [s for s in loader_rows if 'over its frame budget:' in s or '| blocked:' in s]
        excerpt = E / f'B17-{variant}-probe-excerpt.log'
        excerpt.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        loader_excerpt = E / f'B17-{variant}-loader-excerpt.log'
        loader_excerpt.write_text('\n'.join(loader_rows) + '\n', encoding='utf-8')
        result = dict(status='PASS', validationMeaning='Logged execution and readback verified; not a grip-fix acceptance.',
                      variant='B17-' + variant, candidateSetPositive=variant == 'R', userFeedback=FEEDBACK[variant],
                      flashObserved=False if variant == 'R' else None, flashFixedConfirmed=False,
                      userClarification='在武器周期向上移动时出现部件不跟随。' if variant == 'R' else None,
                      reloadStateConfirmed=False,
                      unshiftedComponentsReported=['火焰喷射器弹夹', '纪元弹药部件'] if variant == 'R' else [],
                      flashFrequencyMeasured=False, flashExactFrameKnown=False, flashCauseConfirmed=False,
                      individualDriverConfirmed=False, appliedCycles=len(applied), nodesPerCycle=len(expected),
                      rootFamilies=roots, eventCounts=dict(counts),
                      maxNodeReadbackError=max(float(r['error']) for rs in groups.values() for r in rs),
                      consumers=summary, cleanShutdown=True, sessionStart=lines[0][:8], sessionEnd=loader_rows[-1][:8],
                      skippedRestores=[s for s in lines if 'event=restore_skipped' in s],
                      loaderObservations=observations, loaderObservationCausalityEstablished=False,
                      scope='Applies only to tested states and sampled markers. Consumer ownership is unverified. '
                            'Consumer samples occur at UP transitions; hand flashing and return-phase behavior are user observations, '
                            'not measurements of later animation/IK/solver updates. L cannot be excluded in every possible state.',
                      sources=[dict(path=str(p), bytes=len(d), sha256=hashlib.sha256(d).hexdigest())
                               for p, d in ((path, data), (loader_path, loader_data), (profile_path, profile_path.read_bytes()))])
        save_json(E / f'B17-{variant}-game-result.json', result)
        results[variant] = result
    save_json(E / 'B17-comparison.json', dict(status='PASS', results=results,
              next='AIM: test weapon_aim alone with legacy component discovery. PARTS: keep B17-R displacement and '
                   'enable exact-layout component refresh for the statically verified canister and Epoch candidate.'))
    for variant, result in results.items():
        print('B17-' + variant, 'verified cycles:', result['appliedCycles'],
              'node readback error:', result['maxNodeReadbackError'], 'clean shutdown:', result['cleanShutdown'])


if __name__ == '__main__':
    main()
