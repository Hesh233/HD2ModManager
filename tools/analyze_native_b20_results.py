"""Archive B20 game evidence without treating successful writes as visual success."""
from collections import Counter, defaultdict
import hashlib
import math
import re
import statistics
from pathlib import Path
from package_native_v12 import ROOT, save_json

W = ROOT / 'outputs/native-v29-b21-20261105'
E = W / 'evidence/B20'
GAME = Path.home() / 'AppData/Roaming/Arrowhead/Helldivers2'
FEEDBACK = 'RAHT均无影响左手，右手只有位置正确，视觉平移还是有问题。'


def main():
    E.mkdir(parents=True, exist_ok=True)
    raw = (GAME / 'hd2physbone.log').read_bytes()
    text = raw.decode('utf-8', errors='replace')
    loader_raw = (GAME / 'chef_loader.log').read_bytes()
    loader = loader_raw.decode('utf-8', errors='replace').splitlines()
    starts = list(re.finditer(r'^.*?\[grip_align\] variant=(R|A|H|T) event=loaded version=1\.1\.0 .*$', text, re.M))
    assert starts, 'No B20 sessions in the game log'
    sessions = []
    for i, match in enumerate(starts):
        variant = match[1]
        chunk = text[match.start():starts[i+1].start() if i+1 < len(starts) else len(text)]
        lines = chunk.splitlines()
        start = lines[0][:8]
        begins = [j for j, line in enumerate(loader) if line[:8] == start and '==== Chef Shared Loader' in line]
        assert len(begins) == 1
        begin = begins[0]
        stop = next((j for j in range(begin+1, len(loader)) if 'shutdown (clean)' in loader[j]), None)
        assert stop is not None and not any('==== Chef Shared Loader' in s for s in loader[begin+1:stop])
        records = [dict(re.findall(r'(\w+)=([^ ]+)', line)) for line in lines if '[grip_align]' in line]
        assert all(r['variant'] == variant for r in records)
        counts = Counter(r['event'] for r in records)
        aligned = [r for r in records if r['event'] == 'aligned']
        targets = {}
        for target in sorted({r['target'] for r in aligned}):
            rows = [r for r in aligned if r['target'] == target]
            targets[target] = dict(samples=len(rows), maxPositionError=max(float(r['after_m']) for r in rows),
                                   maxMatrixError=max(float(r['matrix_error']) for r in rows),
                                   rotationModes=sorted({r['rotation'] for r in rows}))
        refreshed = [r for r in records if r['event'] == 'post_refresh']
        groups = defaultdict(list)
        for r in records:
            if r['event'] == 'consumer':
                groups[r['resource'], r['kind'], r['name']].append(r)
        consumers = []
        for (resource, kind, name), rows in sorted(groups.items()):
            summary = dict(resource=resource, kind=kind, name=name, samples=len(rows), owner='unverified')
            for field in ('source_l_m', 'source_r_m', 'wrist_l_m'):
                values = [float(r[field]) for r in rows]
                summary[field] = dict(min=min(values), median=statistics.median(values), max=max(values))
            summary['maxWithinCallbackDisplacement'] = max(math.sqrt(sum(float(r[k])**2 for k in ('dx', 'dy', 'dz'))) for r in rows)
            consumers.append(summary)
        errors = [line for line in lines if '[grip_align]' in line and any('event='+x in line for x in
                  ('disabled', 'rollback', 'restore_failed', 'validation_mismatch', 'consumer_unavailable'))]
        result = dict(variant='B20-'+variant, sessionStart=start, sessionEnd=loader[stop][:8],
            cleanShutdown=True, userFeedback=FEEDBACK, leftVisualResponse=False, rightMotionAccepted=False,
            rightPositionUserAccepted=True, targets=targets, eventCounts=dict(counts), consumers=consumers,
            errors=errors, sourceMaxMatrixChange=max((float(r['source_matrix_change']) for r in refreshed), default=None),
            aimMaxLocalChange=max((float(r['aim_local_change']) for r in refreshed), default=None),
            loaderBudgetWarnings=[s for s in loader[begin:stop+1] if 'over its frame budget' in s],
            loaderReadDenials=[s for s in loader[begin:stop+1] if 'blocked:' in s],
            causalityEstablished=False, rawSourceWeaponBonesAreNotCalibrated=True)
        name = 'B20-' + variant + '-' + start.replace(':', '')
        (E / (name+'-runtime.log')).write_text(chunk, encoding='utf-8')
        (E / (name+'-loader.log')).write_text('\n'.join(loader[begin:stop+1])+'\n', encoding='utf-8')
        save_json(E / (name+'-result.json'), result)
        sessions.append(result)
        print(variant, start, 'targets', {k:v['samples'] for k,v in targets.items()}, 'errors', len(errors), flush=True)
    save_json(E / 'B20-comparison.json', dict(status='CAPTURED', userFeedback=FEEDBACK, sessions=sessions,
        sourceLogs={'hd2physbone.log': dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()),
                    'chef_loader.log': dict(bytes=len(loader_raw), sha256=hashlib.sha256(loader_raw).hexdigest())},
        nextStep='Capture original armor, native Avatar and weapon/foregrip transforms without pose writes or forced refreshes.',
        limitation='Sampled consumer distances are not synchronized A/B poses and do not establish ownership or the cause of sliding.'))


if __name__ == '__main__':
    main()
