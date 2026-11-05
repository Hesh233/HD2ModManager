"""Measure both native hands and weapon markers in a preserved B21 session.

This writes analysis artifacts only. It does not propose or deploy a pose edit.
All cross-Unit ownership remains unverified, and instance groups stay separate.
"""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path

from package_native_v12 import ROOT, load, save_json, digest
from analyze_native_b21_capture import (
    norm, rotation, angle, affine_relative, compose, summary,
)

IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
RESOURCES = dict(avatar='4d1c334d294dfa97', left_model='23a244c877843da3',
                 right_model='30204ad0fe720352', foregrip='f9df21c8e52cac95', weapon='186ea95de7306b1a')
PAIRS = {
    'r_mount_gun': ('avatar', 'attach_hand_r', 'weapon', 'boss'),
    'r_wrist_mount': ('avatar', 'r_hand', 'avatar', 'attach_hand_r'),
    'r_wrist_ik': ('avatar', 'r_hand', 'weapon', 'IK_right'),
    'r_twist_ik': ('avatar', 'r_hand_twist', 'weapon', 'IK_right'),
    'r_wrist_model': ('avatar', 'r_hand', 'right_model', 'r_hand'),
    'r_twist_model': ('avatar', 'r_hand_twist', 'right_model', 'r_hand_twist'),
    'r_mount_ik': ('avatar', 'attach_hand_r', 'weapon', 'IK_right'),
    'r_mount_aim': ('avatar', 'attach_hand_r', 'avatar', 'weapon_aim'),
    'l_wrist_mount': ('avatar', 'l_hand', 'avatar', 'attach_hand_l'),
    'l_wrist_foregrip': ('avatar', 'l_hand', 'foregrip', 'IK_left'),
    'l_twist_foregrip': ('avatar', 'l_hand_twist', 'foregrip', 'IK_left'),
    'l_wrist_gun_ik': ('avatar', 'l_hand', 'weapon', 'IK_left'),
    'l_mount_foregrip': ('avatar', 'attach_hand_l', 'foregrip', 'IK_left'),
    'l_wrist_model': ('avatar', 'l_hand', 'left_model', 'l_hand'),
    'l_twist_model': ('avatar', 'l_hand_twist', 'left_model', 'l_hand_twist'),
    'gun_right_ik': ('weapon', 'boss', 'weapon', 'IK_right'),
    'gun_muzzle': ('weapon', 'boss', 'weapon', 'attach_muzzle'),
    'gun_underbarrel': ('weapon', 'boss', 'weapon', 'attach_underbarrel'),
    'underbarrel_foregrip_root': ('weapon', 'attach_underbarrel', 'foregrip', 'skeleton'),
    'gun_left_ik_foregrip': ('weapon', 'IK_left', 'foregrip', 'IK_left'),
    'foregrip_local': ('foregrip', 'skeleton', 'foregrip', 'IK_left'),
    'gun_foregrip_ik': ('weapon', 'boss', 'foregrip', 'IK_left'),
    'right_ik_foregrip': ('weapon', 'IK_right', 'foregrip', 'IK_left'),
}
LOCALS = {
    'r_mount': ('avatar', 'attach_hand_r'),
    'l_mount': ('avatar', 'attach_hand_l'),
    'right_ik': ('weapon', 'IK_right'),
    'left_ik': ('weapon', 'IK_left'),
    'underbarrel': ('weapon', 'attach_underbarrel'),
    'foregrip_ik': ('foregrip', 'IK_left'),
}


def distance(a, b):
    return norm([b[i] - a[i] for i in range(9, 12)])


def pose_error(a, b):
    return dict(metres=distance(a, b), degrees=angle(rotation(a), rotation(b)),
                maxMatrixError=max(abs(x-y) for x, y in zip(a, b)))


def coincident(metric):
    return metric['metres'] < .001 and metric['degrees'] < .1


def describe_matrices(matrices):
    first = matrices[0]
    first_rot = rotation(first)
    delta_p = [distance(first, m) for m in matrices]
    delta_r = [angle(first_rot, rotation(m)) for m in matrices]
    return dict(firstAffine=first,
                originDistanceMetres=summary([norm(m[9:]) for m in matrices]),
                rotationDegrees=summary([angle(rotation(m)) for m in matrices]),
                translationMetres={a: summary([m[9+i] for m in matrices]) for i, a in enumerate('XYZ')},
                translationChangeFromFirstMetres=summary(delta_p),
                rotationChangeFromFirstDegrees=summary(delta_r),
                stableWithinCoincidenceTolerance=max(delta_p) < .001 and max(delta_r) < .1,
                recordedExactUniqueCount=len({tuple(m) for m in matrices}))


def summarize(rows):
    if not rows:
        return dict(samples=0)
    metrics = {}
    for key in PAIRS:
        metrics[key] = dict(describe_matrices([r['relative'][key] for r in rows]),
                            worldDistanceMetres=summary([r['metrics'][key]['metres'] for r in rows]),
                            worldRotationDegrees=summary([r['metrics'][key]['degrees'] for r in rows]),
                            exactWorldMatrixMatches=sum(r['metrics'][key]['maxMatrixError'] == 0 for r in rows),
                            coincidentSamples=sum(coincident(r['metrics'][key]) for r in rows))
    return dict(samples=len(rows), firstSample=rows[0]['sample'], lastSample=rows[-1]['sample'],
                firstLogTime=rows[0]['logTime'], lastLogTime=rows[-1]['logTime'],
                relations=metrics,
                nativeLocalPoses={k: describe_matrices([r['locals'][k] for r in rows]) for k in LOCALS},
                chainResiduals={key: {axis: summary([r['closure'][key][axis] for r in rows])
                                     for axis in ('metres', 'degrees', 'maxMatrixError')}
                                for key in rows[0]['closure']})


def runs(rows, predicate):
    groups, current = [], []
    for r in rows:
        if predicate(r):
            if current and (r['sample'] != current[-1]['sample'] + 1 or r['time'] - current[-1]['time'] > .5):
                groups.append(current)
                current = []
            current.append(r)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [dict(firstSample=g[0]['sample'], lastSample=g[-1]['sample'], samples=len(g),
                 start=g[0]['logTime'], end=g[-1]['logTime'], elapsedSeconds=g[-1]['time'] - g[0]['time'])
            for g in groups]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observation', type=Path)
    args = parser.parse_args()
    output = args.observation.resolve()
    manifest = load(output / 'snapshot-manifest.json')
    general = load(output / 'capture-analysis.json')
    audit = load(output / 'deployment-audit.json')
    source = output / 'native-grip-latest.log'
    assert digest(source) == general['inputSha256'] == manifest['snapshotSha256']
    assert general['gamePoseCaptured'] and len(general['sessions']) == 1 and not general['parseErrors']
    assert general['sessions'][0]['layouts'] == ['native_107']
    assert set(general['sessions'][0]['issues']) <= {'unavailable'}
    assert audit['nativeSkeletonAndWatchedAssetBaselineConfirmed']
    assert general['completedSamplePairs'] == manifest['selected']['complete']['samples']
    observations, group_meta, choices, incomplete, block = [], {}, [], Counter(), None

    def evaluate(unit_rows):
        by_world = defaultdict(list)
        for row in unit_rows:
            by_world[row['world']].append(row)
        for world, candidates in by_world.items():
            role_rows = {role: [r for r in candidates if r['resource'] == rid] for role, rid in RESOURCES.items()}
            if any(len(role_rows[role]) != 1 for role in RESOURCES if role != 'foregrip') or not role_rows['foregrip']:
                incomplete['missing_or_ambiguous_complete_group'] += 1
                continue
            rows = {role: found[0] for role, found in role_rows.items() if role != 'foregrip'}
            for row in candidates:
                row['_nodes'] = {n['name']: n for n in row['nodes']}
            a = rows['avatar']
            assert a['owner'] == 'unverified' and a['layout'] == 'native_107' and a['nodeCount'] == 107
            grips = role_rows['foregrip']
            if len(grips) == 1:
                rows['foregrip'] = grips[0]
            else:
                ub = rows['weapon']['_nodes']['attach_underbarrel']['worldMatrix']
                scores = [(g, pose_error(ub, g['_nodes']['skeleton']['worldMatrix'])) for g in grips]
                eligible = [g for g, score in scores if coincident(score)]
                assert len(eligible) == 1, 'Foregrip ownership ambiguous even by mount geometry'
                rows['foregrip'] = eligible[0]
                choices.append(dict(sample=a['sample'], phase=a['phase'], world=world,
                                    selected=eligible[0]['id'], criterion='underbarrel_to_skeleton_only',
                                    candidates=[dict(id=g['id'], **s) for g, s in scores]))
            assert len({(r['sample'], r['phase'], r['frame'], r['world']) for r in rows.values()}) == 1
            identity = tuple((role, rows[role]['id']) for role in RESOURCES)
            group_key = (world, identity)
            if group_key not in group_meta:
                group_meta[group_key] = dict(group=f'group_{len(group_meta)+1}', world=world, owner='unverified',
                    units={role: {k: r[k] for k in ('id', 'resource', 'kind', 'layout', 'nodeCount')} for role, r in rows.items()},
                    nodes={role: [{k: n.get(k) for k in ('name', 'index', 'skinInput', 'serializedParent', 'runtimeParent', 'parentState')}
                                  for n in r['nodes']] for role, r in rows.items()})
            g = group_meta[group_key]
            result = dict(group=g['group'], sample=a['sample'], phase=a['phase'], frame=a['frame'],
                          time=a['time'], logTime=a['_stamp'], world=world, owner='unverified',
                          unitIds={role: r['id'] for role, r in rows.items()},
                          evidenceLines={role: r['_line'] for role, r in rows.items()},
                          metrics={}, relative={}, locals={}, closure={}, skinAgreement={})
            world_poses = {}

            def wp(role, name):
                key = role + ':' + name
                if key not in world_poses:
                    world_poses[key] = rows[role]['_nodes'][name]['worldMatrix']
                return world_poses[key]

            for key, (ar, an, br, bn) in PAIRS.items():
                ma, mb = wp(ar, an), wp(br, bn)
                result['metrics'][key] = pose_error(ma, mb)
                result['relative'][key] = affine_relative(ma, mb)
            for key, (role, name) in LOCALS.items():
                result['locals'][key] = rows[role]['_nodes'][name]['localMatrix']
            for side, role in (('l', 'left_model'), ('r', 'right_model')):
                detail = {}
                for name in (side + '_' + suffix for suffix in ('clavicle', 'shoulder', 'elbow', 'hand', 'hand_twist')):
                    node = rows[role]['_nodes'][name]
                    detail[name] = dict(maxMatrixError=max(abs(x-y) for x, y in zip(wp('avatar', name), wp(role, name))),
                                        skinInput=node['skinInput'], identityLocal=node['localMatrix'] == IDENTITY,
                                        runtimeParent=node.get('runtimeParent'), parentState=node['parentState'])
                result['skinAgreement'][role] = detail
            hr, ar = wp('avatar', 'r_hand'), wp('avatar', 'attach_hand_r')
            la = result['locals']['r_mount']
            result['closure']['wrist_local_to_mount'] = pose_error(compose(hr, la), ar)
            result['closure']['mount_to_right_ik'] = pose_error(compose(ar, result['locals']['right_ik']), wp('weapon', 'IK_right'))
            result['closure']['wrist_local_to_right_ik'] = pose_error(
                compose(compose(hr, la), result['locals']['right_ik']), wp('weapon', 'IK_right'))
            result['closure']['mount_to_foregrip_ik'] = pose_error(
                compose(compose(ar, result['locals']['underbarrel']), result['locals']['foregrip_ik']), wp('foregrip', 'IK_left'))
            result['worldPoses'] = world_poses
            observations.append(result)

    with source.open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            stamp, body = line.split('[native_capture] ', 1)
            row = json.loads(body)
            if row['event'] == 'phase_begin':
                assert block is None
                block = dict(key=(row['sample'], row['frame'], row['phase']), rows=[])
            elif row['event'] == 'unit':
                assert block is not None and block['key'] == (row['sample'], row['frame'], row['phase'])
                row.update(_line=number, _stamp=stamp.strip())
                block['rows'].append(row)
            elif row['event'] == 'phase_end':
                assert block is not None and block['key'] == (row['sample'], row['frame'], row['phase'])
                evaluate(block['rows'])
                block = None
    assert block is None and observations
    grouped = defaultdict(list)
    for row in observations:
        grouped[row['group']].append(row)
    reports, callbacks, examples = [], [], []
    for meta in group_meta.values():
        rows = grouped[meta['group']]
        phases = {phase: [r for r in rows if r['phase'] == phase] for phase in ('update', 'render')}
        u_by_sample = {r['sample']: r for r in phases['update']}
        assert set(u_by_sample) == {r['sample'] for r in phases['render']}
        for r in phases['render']:
            u = u_by_sample[r['sample']]
            cb = dict(group=r['group'], sample=r['sample'], time=r['time'], callbackGapSeconds=r['time']-u['time'])
            for key in ('avatar:r_hand', 'avatar:attach_hand_r', 'avatar:l_hand', 'weapon:boss',
                        'weapon:IK_right', 'foregrip:IK_left', 'left_model:l_hand', 'right_model:r_hand'):
                err = pose_error(u['worldPoses'][key], r['worldPoses'][key])
                cb[key + '_metres'], cb[key + '_degrees'] = err['metres'], err['degrees']
            for key in ('r_wrist_mount', 'r_wrist_ik', 'l_wrist_foregrip'):
                err = pose_error(u['relative'][key], r['relative'][key])
                cb[key + '_relative_metres'], cb[key + '_relative_degrees'] = err['metres'], err['degrees']
            callbacks.append(cb)
        rendered = phases['render']
        mounted = [r for r in rendered if coincident(r['metrics']['r_mount_gun'])]
        left_contact = [r for r in rendered if coincident(r['metrics']['l_wrist_foregrip'])]
        scoped_cb = [r for r in callbacks if r['group'] == meta['group']]
        skin = {role: {name: dict(observations=len(rows),
                    exactWorldMatrixMatches=sum(r['skinAgreement'][role][name]['maxMatrixError'] == 0 for r in rows),
                    maximumMatrixError=max(r['skinAgreement'][role][name]['maxMatrixError'] for r in rows),
                    nonIdentityLocalCount=sum(not r['skinAgreement'][role][name]['identityLocal'] for r in rows),
                    parentStates=dict(Counter(r['skinAgreement'][role][name]['parentState'] for r in rows)),
                    observedRuntimeParents=sorted({str(r['skinAgreement'][role][name]['runtimeParent']) for r in rows}))
                    for name in rows[0]['skinAgreement'][role]} for role in ('left_model', 'right_model')}
        reports.append(dict(meta, completedPairs=len(rendered),
            phases={p: summarize(v) for p, v in phases.items()},
            rightMountCoincidentRender=summarize(mounted),
            leftContactRender=summarize(left_contact), leftContactSubsetSelectedOnLeftCoincidence=True,
            leftContactRuns=runs(rendered, lambda r: coincident(r['metrics']['l_wrist_foregrip'])),
            leftNonContactRuns=runs(rendered, lambda r: not coincident(r['metrics']['l_wrist_foregrip'])),
            skinAgreement=skin,
            callbackDifferences={k: summary([r[k] for r in scoped_cb]) for k in scoped_cb[0] if k not in ('group', 'sample', 'time')}))
        for key, metric in (('r_wrist_ik', 'metres'), ('r_wrist_ik', 'degrees'), ('r_wrist_mount', 'metres')):
            for label, fn in (('minimum', min), ('maximum', max)):
                selected = fn(rendered, key=lambda r: r['metrics'][key][metric])
                examples.append(dict(criterion=f'{key}.{metric}.{label}', observation=selected))
    static = load(ROOT / 'outputs/native-v29-b21-20261105/native-capture-layouts.json')
    static_matrices = {}
    for key, (role, name) in LOCALS.items():
        resource = static['nativeAvatar'] if role == 'avatar' else static['resources'][RESOURCES[role]]
        node = next(n for n in resource['nodes'] if n['name'] == name)
        static_matrices[key] = dict(resource=resource['resource'], staticIndex=node['index'],
                                    runtimeIndex=node['index']+1, name=name, parentName=node['parentName'],
                                    localAffine=node['localMatrix'])
    report = dict(status='ANALYZED', gamePoseCaptured=True, sessionStart=manifest['selected']['started'],
        sessionEnd=manifest['selected']['completed'], latestSessionOrdinal=manifest['latestSessionOrdinal'],
        sourceSha256=manifest['snapshotSha256'], generalAnalysisSha256=digest(output / 'capture-analysis.json'),
        deploymentAuditSha256=digest(output / 'deployment-audit.json'), rawCompletePairs=general['completedSamplePairs'],
        completeFiveUnitPairs=sum(g['completedPairs'] for g in reports), nativeSkeletonAndWatchedAssetsConfirmed=True,
        owner='unverified', matrixConvention='inverse(A) * B; three basis columns, then translation in metres',
        indexBase=1, staticAssetIndexBase=0, coincidenceThresholds=dict(positionMetres=.001, rotationDegrees=.1),
        groups=reports, multiForegripSelections=choices, incompleteGroupCounts=dict(incomplete),
        nativeAssetLocalMatrices=static_matrices,
        conclusions=dict(rightGunMount='attach_hand_r equals weapon boss only in the explicitly verified mounted group(s)',
                         verifiedMountedGroups=[g['group'] for g in reports
                             if all(g['phases'][p]['relations']['r_mount_gun']['coincidentSamples'] == g['completedPairs']
                                    for p in ('update', 'render'))],
                         rightWristRelation='r_hand to attach_hand_r is a time-varying native local pose',
                         rightIKMarker='IK_right is a fixed marker in weapon boss space; wrist equality is not assumed',
                         leftGripCandidate='The observed vertical foregrip IK_left matches l_hand during contact intervals',
                         calibrationApplied=False),
        limits=[
            'Cross-Unit owner references are unverified. Unit IDs, world labels and session boundaries are preserved.',
            'World labels are collector enumeration values, not persistent engine world identifiers.',
            'The 503-pair later group begins during task loading; individual gameplay actions were not logged.',
            'Coincidence of a bone and a marker is not a measurement of palm/finger surface contact. Finger poses and weighted mesh vertices were not captured.',
            'The right IK marker is named by the asset. Its presence does not prove that the engine drives the right wrist to it.',
            'Callback timing relative to IK is unverified. Identical logged engine times do not establish simultaneous reads.',
            'Native relationships are scoped to SMG-203 with the observed vertical foregrip and original hand models.',
            'A fixed right-wrist correction is not inferred from a median offset or from the approximately 90-degree visual symptom.',
            'test01 calibration and runtime edits are outside this read-only observation analysis.',
        ])
    save_json(output / 'observed-native-grips.json', report)
    save_json(output / 'right-pose-examples.json', examples)
    with (output / 'relative-poses.jsonl').open('w', encoding='utf-8') as stream:
        for row in observations:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
    flat = []
    for r in observations:
        row = {k: r[k] for k in ('group', 'sample', 'frame', 'phase', 'time', 'logTime', 'world')}
        for key, m in r['metrics'].items():
            row[key + '_m'], row[key + '_deg'], row[key + '_coincident'] = m['metres'], m['degrees'], coincident(m)
        flat.append(row)
    for name, data in (('pose-timeseries.csv', flat), ('callback-timeseries.csv', callbacks)):
        with (output / name).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    for g in reports:
        print(g['group'], 'pairs', g['completedPairs'], 'ids', {r: u['id'] for r, u in g['units'].items()})
        for key in ('r_mount_gun', 'r_wrist_ik', 'r_twist_ik', 'r_wrist_mount', 'gun_right_ik',
                    'l_wrist_foregrip', 'l_wrist_gun_ik', 'l_twist_foregrip', 'underbarrel_foregrip_root'):
            m = g['phases']['render']['relations'][key]
            print(key, 'coincident', m['coincidentSamples'], 'mm min/med/max',
                  [round(m['worldDistanceMetres'][k]*1000, 6) for k in ('minimum', 'median', 'maximum')],
                  'deg min/med/max', [round(m['worldRotationDegrees'][k], 6) for k in ('minimum', 'median', 'maximum')])


if __name__ == '__main__':
    main()
