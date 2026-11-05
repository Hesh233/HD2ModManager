"""Measure the observed B21 hand/weapon relationships, without changing runtime."""
from collections import Counter
import csv
import json
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest
from analyze_native_b21_capture import norm, rotation, angle, affine_relative, summary

W = ROOT / 'outputs/native-b21-observation-20261105/20261105-092343'
SOURCE_LEFT = 'hd2n_4e4fb4fa303d_anim_008_l_hand'
SOURCE_RIGHT = 'hd2n_4e4fb4fa303d_anim_031_r_hand'
IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
RESOURCES = dict(avatar='4d1c334d294dfa97', left_model='23a244c877843da3',
                 right_model='30204ad0fe720352', foregrip='f9df21c8e52cac95', weapon='186ea95de7306b1a')


def main():
    manifest = load(W / 'snapshot-manifest.json')
    capture = load(W / 'capture-analysis.json')
    assert capture['inputSha256'] == manifest['snapshotSha256'] == digest(W / 'native-grip-latest.log')
    assert capture['gamePoseCaptured'] and capture['completedSamplePairs'] == 1455
    units = {role: max((u for u in manifest['units'] if u['resource'] == resource),
                      key=lambda u:(u['firstSample'], u['id'])) for role, resource in RESOURCES.items()}
    ids = {u['id']: role for role, u in units.items()}
    phases, pending, observations, callbacks = {}, {}, [], []
    first_relative = {}
    identity_errors = Counter()
    parent_states = Counter()
    log_phase_counts = Counter()

    def evaluate(rows):
        if set(rows) != set(units):
            return
        a = rows['avatar']
        assert len({(r['sample'],r['frame'],r['phase'],r['world']) for r in rows.values()}) == 1
        nodes = {role: {n['name']: n for n in r['nodes']} for role, r in rows.items()}
        result = dict(sample=a['sample'], frame=a['frame'], phase=a['phase'],
                      time=a['time'], logTime=a['_stamp'])
        cache = {}

        def pose(role, name):
            key = role, name
            if key not in cache:
                m = nodes[role][name]['worldMatrix']
                cache[key] = (m, rotation(m))
            return cache[key]

        def pair(key, ar, an, br, bn):
            ma, ra = pose(ar, an)
            mb, rb = pose(br, bn)
            assert ra is not None and rb is not None
            result[key + '_m'] = norm([mb[j] - ma[j] for j in range(9,12)])
            result[key + '_deg'] = angle(ra, rb)
            if key not in first_relative:
                first_relative[key] = dict(sample=a['sample'], phase=a['phase'],
                    a=dict(role=ar, id=units[ar]['id'], name=an), b=dict(role=br, id=units[br]['id'], name=bn),
                    relativeAffine=affine_relative(ma, mb))

        for side, model in (('l', 'left_model'), ('r', 'right_model')):
            name = side + '_hand'
            pair(side + '_avatar_model', 'avatar', name, model, name)
            expected, _ = pose('avatar', name)
            actual, _ = pose(model, name)
            result[side + '_avatar_model_max_matrix_error'] = max(abs(x-y) for x,y in zip(expected, actual))
            n = nodes[model][name]
            identity_errors[model] += n['localMatrix'] != IDENTITY
            parent_states[(model, n['parentState'], n.get('runtimeParent'))] += 1
        pair('left_foregrip', 'avatar', 'l_hand', 'foregrip', 'IK_left')
        pair('left_gun_ik', 'avatar', 'l_hand', 'weapon', 'IK_left')
        pair('left_attachment_foregrip', 'avatar', 'attach_hand_l', 'foregrip', 'IK_left')
        pair('source_left_foregrip', 'avatar', SOURCE_LEFT, 'foregrip', 'IK_left')
        pair('native_source_left', 'avatar', 'l_hand', 'avatar', SOURCE_LEFT)
        pair('native_source_right', 'avatar', 'r_hand', 'avatar', SOURCE_RIGHT)
        pair('right_attachment_boss', 'avatar', 'attach_hand_r', 'weapon', 'boss')
        pair('right_hand_gun_ik', 'avatar', 'r_hand', 'weapon', 'IK_right')
        pair('foregrip_underbarrel', 'weapon', 'attach_underbarrel', 'foregrip', 'skeleton')
        pair('gun_foregrip_ik', 'weapon', 'IK_left', 'foregrip', 'IK_left')
        pair('right_attachment_aim', 'avatar', 'attach_hand_r', 'avatar', 'weapon_aim')
        result['rightAttachmentCoincident'] = result['right_attachment_boss_m'] < .001 and result['right_attachment_boss_deg'] < .1
        result['leftForegripCoincident'] = result['left_foregrip_m'] < .001 and result['left_foregrip_deg'] < .1
        result['leftGunIKCoincident'] = result['left_gun_ik_m'] < .001 and result['left_gun_ik_deg'] < .1
        observations.append(result)
        log_phase_counts[a['phase']] += 1
        if a['phase'] == 'update':
            pending[a['sample']] = (result, cache)
        elif a['sample'] in pending:
            previous, prior = pending.pop(a['sample'])
            cb = dict(sample=a['sample'], time=a['time'], callbackGapSeconds=a['time']-previous['time'])
            for label, ar, an in (('avatar_left', 'avatar', 'l_hand'), ('avatar_right', 'avatar', 'r_hand'),
                                  ('left_model', 'left_model', 'l_hand'), ('right_model', 'right_model', 'r_hand'),
                                  ('weapon', 'weapon', 'boss'), ('foregrip', 'foregrip', 'IK_left')):
                old, old_rot = prior[ar, an]
                new, new_rot = cache[ar, an]
                cb[label + '_world_delta_m'] = norm([new[j]-old[j] for j in range(9,12)])
                cb[label + '_world_delta_deg'] = angle(old_rot, new_rot)
            callbacks.append(cb)

    with (W / 'native-grip-latest.log').open(encoding='utf-8') as stream:
        for line in stream:
            stamp, body = line.split('[native_capture] ', 1)
            row = json.loads(body)
            if row['event'] == 'phase_begin':
                phases[row['phase']] = {}
            elif row['event'] == 'unit' and row['id'] in ids:
                row['_stamp'] = stamp.strip()
                phases.setdefault(row['phase'], {})[ids[row['id']]] = row
            elif row['event'] == 'phase_end':
                evaluate(phases.pop(row['phase'], {}))
    assert not pending
    assert log_phase_counts == Counter(update=1230, render=1230)
    assert len(callbacks) == 1230
    assert all(r['l_avatar_model_max_matrix_error'] == r['r_avatar_model_max_matrix_error'] == 0 for r in observations)
    rendered = [r for r in observations if r['phase'] == 'render']

    def summarize(rows):
        keys = [k for k, v in observations[0].items() if type(v) is float]
        return dict(samples=len(rows), firstSample=rows[0]['sample'] if rows else None,
            lastSample=rows[-1]['sample'] if rows else None,
            rightAttachmentCoincident=sum(r['rightAttachmentCoincident'] for r in rows),
            leftForegripCoincident=sum(r['leftForegripCoincident'] for r in rows),
            leftGunIKCoincident=sum(r['leftGunIKCoincident'] for r in rows),
            metrics={k:summary([r[k] for r in rows]) for k in keys})

    # This selection uses only right attachment/weapon geometry. It does not
    # select frames for matching the left hand to a favored IK candidate.
    right_aligned = [r for r in rendered if r['rightAttachmentCoincident']]
    both_aligned = [r for r in right_aligned if r['leftForegripCoincident']]

    def runs(key):
        found, current = [], []
        for r in rendered:
            if r[key] and (not current or (r['sample'] == current[-1]['sample']+1 and r['time']-current[-1]['time'] < .5)):
                current.append(r)
            else:
                if current:
                    found.append(current)
                current = [r] if r[key] else []
        if current:
            found.append(current)
        return [dict(firstSample=g[0]['sample'], lastSample=g[-1]['sample'], samples=len(g),
                     start=g[0]['logTime'], end=g[-1]['logTime'], elapsedSeconds=g[-1]['time']-g[0]['time'])
                for g in found]

    parent_rows = [dict(role=k[0], parentState=k[1], runtimeParent=k[2], observations=v) for k,v in parent_states.items()]
    unavailable = manifest['diagnostics']
    deployment = load(W / 'deployment-audit.json')
    conclusions = dict(status='ANALYZED', gamePoseCaptured=True, pureNativeBaseline=False,
        sessionStart=manifest['selected']['started'], sessionEnd=manifest['selected']['completed'],
        latestSessionOrdinal=manifest['latestSessionOrdinal'], rawCompletePairs=1455,
        completeMissionConsumerPairs=1230, observedAvatarLayout=units['avatar']['layout'],
        unitSelection=units, owner='unverified',
        allRender=summarize(rendered),
        rightAttachmentCoincidentRender=summarize(right_aligned),
        bothHandsCoincidentRender=summarize(both_aligned),
        bothHandsSubsetIsSelectedOnLeftCoincidence=True,
        callbackChanges={k:summary([r[k] for r in callbacks]) for k in callbacks[0] if k not in ('sample',)},
        exactNativeModelWorldMatrixMatches=dict(left=len(observations), right=len(observations)),
        modelNonIdentityLocalPoseCounts=dict(identity_errors), modelParentStates=parent_rows,
        coincidenceThresholds=dict(positionMetres=.001, rotationDegrees=.1),
        rightAttachmentCoincidenceRuns=runs('rightAttachmentCoincident'),
        leftForegripCoincidenceRuns=runs('leftForegripCoincident'),
        firstRelativeMatrices=first_relative,
        lifecycleDiagnostics=dict(count=len(unavailable),
            start=min(r['timestamp'] for r in unavailable), end=max(r['timestamp'] for r in unavailable),
            reasons=dict(Counter(r['event']['reason'] for r in unavailable))),
        effectiveAvatar=deployment['effectiveAvatar'],
        sourceSha256=manifest['snapshotSha256'], generalAnalysisSha256=digest(W / 'capture-analysis.json'),
        limits=[
            'The native glove models were observed under the v15 extended Avatar/animation override, not an unmodified native game baseline.',
            'Near-exact pose equality over time supports a relationship in this equipment configuration; it does not by itself prove engine IK callback order or a general weapon priority.',
            'The right-attachment subset is selected independently of left-hand matching. The both-hands subset explicitly selects left-hand coincidence and is not an independent test.',
            'Action names were not logged; unmatched intervals are not labeled as reload, switch or animation faults.',
            'No test01 Source hand mesh was observed in the selected session. Source-vs-native distances are bone readings inside the extended Avatar.',
            'World matrix equality does not identify the external parent Unit through scene_graph_parent; those API parent reads returned external/root for the gloves.',
        ])
    save_json(W / 'observed-correspondence.json', conclusions)
    with (W / 'pose-timeseries.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(observations[0]))
        writer.writeheader()
        writer.writerows(observations)
    with (W / 'callback-timeseries.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(callbacks[0]))
        writer.writeheader()
        writer.writerows(callbacks)
    print(json.dumps({key:conclusions[key] for key in ('completeMissionConsumerPairs','exactNativeModelWorldMatrixMatches',
        'modelNonIdentityLocalPoseCounts','modelParentStates')}, indent=2))
    for name in ('allRender','rightAttachmentCoincidentRender','bothHandsCoincidentRender'):
        group = conclusions[name]
        print(name, {k:group[k] for k in ('samples','rightAttachmentCoincident','leftForegripCoincident','leftGunIKCoincident')})
        for key in ('left_foregrip_m','left_foregrip_deg','left_gun_ik_m','left_gun_ik_deg',
                    'source_left_foregrip_m','native_source_left_m','native_source_right_m',
                    'right_attachment_boss_m','right_attachment_boss_deg','right_hand_gun_ik_m',
                    'foregrip_underbarrel_m','gun_foregrip_ik_m','gun_foregrip_ik_deg'):
            m = group['metrics'][key]
            print(' ', key, {k:round(m[k],9) for k in ('minimum','median','p95','maximum')})
    print('longest_left_contact_runs', sorted(conclusions['leftForegripCoincidenceRuns'], key=lambda r:r['samples'], reverse=True)[:8])


if __name__ == '__main__':
    main()
