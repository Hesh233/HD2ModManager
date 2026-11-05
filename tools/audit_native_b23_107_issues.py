"""Audit the shipped B23 1.0.7 without changing packages, deployment or runtime.

Reuse the original harness and NumPy oracle. Synthetic assertions characterize
known defects; PASS does NOT mean those defects are fixed or game-verified.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from audit_native_v31_b23 import run_harness
from prepare_native_v31_b23 import ROOT, B22, SRC, load, lua, save
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import UnitData, BonesData
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import BONE_TYPE_ID
from anim_batch_mod.processor import _calculate_world_transforms

PACKAGE = ROOT / 'outputs/native-manual-20261103/B23LR-M-多武器握持测试工程-1.0.7.zip'
DEFAULT_LOG = Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2/hd2_grip_b23.log')
DEFAULT_OUTPUT = ROOT / 'outputs/native-b23-107-issue-audit-20261105'
DEFAULT_CHEF_LOG = DEFAULT_LOG.with_name('chef_loader.log')


def plain(value):
    if hasattr(value, 'items'):
        rows = dict(value.items())
        if rows and set(rows) == set(range(1, len(rows) + 1)):
            return [plain(rows[n]) for n in range(1, len(rows) + 1)]
        return {str(k): plain(v) for k, v in rows.items()}
    return value


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def audit_counterexamples():
    with zipfile.ZipFile(PACKAGE) as archive:
        source = archive.read('src/native_grip_transfer_test.lua')
        # Audit the archived runtime explicitly, even after incrementing the working source.
        profile = json.loads(archive.read('B23-profile.json').decode('utf-8-sig'))
        fixture = json.loads(archive.read('runtime-fixture.json').decode('utf-8-sig'))
        harness = archive.read('test/native_grip_transfer_harness.lua').decode('utf-8-sig')
        harness = harness.replace('-- STRICT_ID_FIXTURE', archive.read('test/strict_id32_fixture.lua').decode('utf-8-sig'))
    # Keep ALL original cases, replacing only their terminal summary return.
    tail = harness.rindex('\nreturn {integratedCases=')
    manifest = load(B22 / 'source-skeleton.json')
    finger_nodes = [fixture['avatar']['hashes'].index(native.bone_name_hash(row['name'])) + 1
                    for row in manifest['bones'] if row.get('driver') and 'finger' in row['driver']]
    component = UnitData.parse((ROOT / 'outputs/native-v26-b18-20261105/assets/52ff81fcba0c059d.toc').read_bytes())
    from prepare_native_v31_b23 import matrices
    epoch = dict(resource='52ff81fcba0c059d', hashes=component.name_hashes,
                 parents=component.parents, matrices=matrices(component))
    extension = (ROOT / 'HD2PhysBoneCompat/test/native_grip_transfer_107_issue_cases.lua').read_text(encoding='utf-8-sig')
    additions = '\nlocal issue_epoch_fixture=' + lua(epoch) + '\nlocal issue_finger_nodes=' + lua(finger_nodes) + '\n' + extension
    result = plain(run_harness(profile, fixture, harness[:tail] + additions, source.decode('utf-8-sig')))
    result.update(package=str(PACKAGE), packageSha256=sha256(PACKAGE.read_bytes()),
                  runtimeSha256=sha256(source), originalPackageUnmodified=True,
                  gameDeployed=False, gameTested=False,
                  scope='Original 1.0.7 runtime + original harness + explicit defect counterexamples; not a repair')
    return result


def new_session(row, wall_time):
    return dict(start=wall_time, loaded=row, counts=collections.Counter(), consumerKinds=collections.Counter(),
                linkedResources=collections.Counter(), seenResources=set(), scans=[], applied=[],
                leftContacts=[], leftSkipped=collections.Counter(), previewApplied=[], previewLeft=[],
                syncWorlds=collections.Counter(), syncFingerFields=0, errors=[], complete=None)


def audit_live_log(path):
    # Stream once; do not copy hundreds of MB or retain all JSON matrices.
    before = path.stat()
    current = None
    sessions = []
    full_hash = hashlib.sha256()
    latest_hash = None
    invalid = 0
    for raw in path.open('rb'):
        full_hash.update(raw)
        try:
            text = raw.decode('utf-8-sig')
            row = json.loads(text[text.index('{'):])
        except (UnicodeError, ValueError):
            invalid += 1
            continue
        event = row.get('event')
        if event == 'loaded':
            if current is not None:
                sessions.append(current)
            current = new_session(row, text[:19]) if row.get('version') == '1.0.7' else None
            latest_hash = hashlib.sha256() if current else None
        if not current:
            continue
        latest_hash.update(raw)
        current['counts'][event] += 1
        if event == 'scan':
            current['scans'].append({k: row.get(k) for k in ('time', 'worlds', 'actors', 'models', 'consumers')})
        elif event == 'consumer':
            current['consumerKinds'][row.get('kind')] += 1
            current['seenResources'].add(row.get('resource'))
            if row.get('kind') == 'linked_item':
                current['linkedResources'][row['resource']] += 1
        elif event == 'applied':
            small = {k: row.get(k) for k in ('frame', 'time', 'avatar', 'world', 'worldUnits', 'modelRefreshes', 'consumerRefreshes', 'leftWrite')}
            current['applied'].append(small)
            if row.get('world') != 1:
                current['previewApplied'].append(small)
        elif event == 'left_applied':
            current['leftContacts'].append(row.get('nativeContactDistance', 0))
            if any(x['avatar'] == row.get('avatar') for x in current['previewApplied'][-10:]):
                current['previewLeft'].append({k: row.get(k) for k in ('avatar', 'frame', 'weaponResource', 'nativeContactDistance', 'beforeDistance', 'afterDistance')})
        elif event == 'left_skipped':
            current['leftSkipped'][row.get('reason')] += 1
        elif event == 'sync':
            current['syncWorlds'][f"{row.get('world')}:{row.get('phase')}"] += 1
            current['syncFingerFields'] += sum('finger' in name for name in row.get('nodes', {}))
        elif event in ('disabled', 'rollback', 'callback_error', 'restore_failed'):
            current['errors'].append(row)
        elif event == 'complete':
            current['complete'] = row
            current['end'] = text[:19]
        if latest_hash:
            current['sessionSha256'] = latest_hash.hexdigest()
    if current is not None:
        sessions.append(current)
    after = path.stat()
    names = {}
    for line in (ROOT.parents[1] / 'hashlists/friendlynames.txt').read_text(encoding='utf-8-sig').splitlines():
        try:
            key, name = line.split(' ', 1)
            names[f'{int(key):016x}'] = name
        except ValueError:
            pass
    for session in sessions:
        scans, applied = session.pop('scans'), session.pop('applied')
        session['scanSamples'] = len(scans)
        session['consumerCandidatesMinMax'] = [min(r['consumers'] for r in scans), max(r['consumers'] for r in scans)] if scans else None
        session['lastScan'] = scans[-1] if scans else None
        session['largestScan'] = max(scans, key=lambda r: r['consumers']) if scans else None
        session['appliedSamples'] = len(applied)
        session['perAppliedRefreshMinMax'] = {k: [min(r[k] for r in applied), max(r[k] for r in applied)] for k in ('modelRefreshes', 'consumerRefreshes')} if applied else {}
        contact = session.pop('leftContacts')
        session['nativeLeftContactMetres'] = dict(samples=len(contact), min=min(contact) if contact else None,
            max=max(contact) if contact else None, fartherThan5cm=sum(x > .05 for x in contact))
        resources = session.pop('seenResources')
        session['epochGunLogged'] = 'e8d5f49ad7780e54' in resources
        session['epochComponentLogged'] = '52ff81fcba0c059d' in resources
        session['linkedResourceExamples'] = [dict(resource=key, samples=count, friendly=names.get(key)) for key, count in session.pop('linkedResources').most_common(12)]
        session['previewAppliedCount'] = len(session['previewApplied'])
        session['previewApplied'] = session['previewApplied'][:3] + session['previewApplied'][-3:]
        session['previewLeft'] = session['previewLeft'][:3]
        stats = (session.get('complete') or {}).get('stats', {})
        writes = stats.get('writes', 0)
        session['refreshesPerSuccessfulRenderAverage'] = {key: stats.get(key, 0) / writes for key in ('modelRefreshes', 'consumerRefreshes')} if writes else {}
    return dict(status='LIVE_LOG_OBSERVED_NOT_FPS_PROFILE', path=str(path), fileBytes=after.st_size,
        fileSha256=full_hash.hexdigest(), immutableDuringRead=before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns,
        invalidRows=invalid, sessions=sessions, timeZone='Asia/Shanghai',
        caveats=['World 11 is the preview in this session only, not a universal world-ID contract.',
                 'Refresh counters prove excess calls, not exact CPU time or the reported FPS ratio.',
                 'Native contact distance alone cannot reliably identify ADS, reload, or free-hand state.',
                 'Existing paired sync logs contain no finger joints, GPU skinning/LOD states or true ADS/reload state.'])


def audit_finger_bind():
    manifest = load(B22 / 'source-skeleton.json')
    with zipfile.ZipFile(PACKAGE) as archive:
        before = UnitData.parse(archive.read('v30-avatar.toc'))
        after = UnitData.parse(archive.read('runtime-avatar.toc'))
        patch = TocArchive.parse_parts(archive.read('9ba626afa44a3aa3.patch_5'),
            archive.read('9ba626afa44a3aa3.patch_5.gpu_resources'),
            archive.read('9ba626afa44a3aa3.patch_5.stream'))
        bone = BonesData.parse(next(entry.toc_data for entry in patch.entries.values() if entry.type_id == BONE_TYPE_ID))
        fixture = json.loads(archive.read('runtime-fixture.json').decode('utf-8-sig'))
        profile = json.loads(archive.read('B23-profile.json').decode('utf-8-sig'))
    old_world = _calculate_world_transforms(before.transforms, before.parents)
    new_world = _calculate_world_transforms(after.transforms, after.parents)
    rows = []
    for source in manifest['bones']:
        if not source.get('driver') or 'finger' not in source['driver']:
            continue
        hash_ = native.bone_name_hash(source['name'])
        old = before.name_hashes.index(hash_)
        new = after.name_hashes.index(hash_)
        a, b = before.transforms[old], after.transforms[new]
        local_error = max(abs(x-y) for x, y in zip(a.position+a.rotation+a.scale, b.position+b.rotation+b.scale))
        position_error = max(abs(x-y) for x, y in zip(old_world[old].position, new_world[new].position))
        assert local_error == 0 and position_error < 1e-5 and hash_ in bone.hashes
        rows.append(dict(driver=source['driver'], name=source['name'], index=new,
            oldParent=before.parents[old], newParent=after.parents[new],
            localPoseError=local_error, bindPositionError=position_error, localScale=b.scale,
            animationChannel=bone.hashes.index(hash_)))
    finger_hashes = {native.bone_name_hash(row['name']) for row in rows}
    models = {key: len(finger_hashes.intersection(value['hashes'])) for key, value in fixture['bodyModels'].items()}
    assert all(value == len(rows) for value in models.values())
    setters = {profile['target']['index']}
    setters.update(row['index'] for row in profile['leftGrip']['outputs'])
    setters.update(row['node']['index'] for row in profile['bodySync']['outputs'])
    setters.update(row['node']['index'] for row in profile['attachments'])
    assert not setters.intersection(row['index'] for row in rows)
    return dict(status='SERIALIZED_FINGER_BIND_AND_CHANNELS_PRESERVED', fingerNodes=len(rows),
        rows=rows, modelFingerNamesPresent=models, directFingerSetters=False,
        leftHandInput=profile['leftGrip']['nodes'][-1], leftHandOutput=profile['sourceLeft'],
        leftHandOutputAnimated=profile['sourceLeft']['hash'] in bone.hashes,
        scope='Exact packaged Avatar/Bones bind and model name signatures; not skin weights, runtime link indices or GPU/LOD verification')


def audit_chef_log(path):
    data = path.read_bytes()
    sessions = []
    active = None
    for line in data.decode('utf-8-sig').splitlines():
        if 'started mods/hd2modmanager/attachment_fix 1.0.7 ' in line:
            active = dict(start=line[:8], startLine=line, timing=[], otherAddons=[], evidence=[])
            sessions.append(active)
        if active is None:
            continue
        if 'started mods/' in line and '/attachment_fix ' not in line:
            active['otherAddons'].append(line)
        if any(key in line for key in ('status:', 'frame budget', 'shutdown', 'blocked:')):
            active['evidence'].append(line)
        match = re.search(r'attachment_fix on avg ([0-9.]+) ms max ([0-9.]+) ms', line)
        if match:
            active['timing'].append(dict(wallTime=line[:8], averageMs=float(match[1]), worstMs=float(match[2])))
        if 'shutdown (clean)' in line or 'starting' in line:
            active = None
    return dict(status='LIVE_CHEF_CALLBACK_TIMING_OBSERVED', path=str(path), fileSha256=sha256(data),
        sessions=sessions, scope='Chef addon callback timings, not GPU timing or an identical-scene FPS AB test')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, default=DEFAULT_LOG)
    parser.add_argument('--skip-live-log', action='store_true')
    parser.add_argument('--chef-log', type=Path, default=DEFAULT_CHEF_LOG)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError('Audit output must remain inside HD2ModManager workspace')
    output.mkdir(parents=True, exist_ok=True)
    counterexamples = audit_counterexamples()
    save(output / 'shipped-runtime-counterexamples.json', counterexamples)
    save(output / 'finger-bind-and-channel-audit.json', audit_finger_bind())
    live = audit_live_log(args.log) if not args.skip_live_log else None
    if live:
        save(output / 'live-1.0.7-analysis.json', live)
        if args.chef_log.exists():
            save(output / 'chef-1.0.7-callback-timing.json', audit_chef_log(args.chef_log))
    save(output / 'audit-summary.json', dict(status='INVESTIGATION_COMPLETE_REPAIRS_NOT_APPLIED',
        counterexampleChecks=counterexamples['checks'], baselineChecks=counterexamples['baselineChecks'],
        packageSha256=counterexamples['packageSha256'], runtimeUnchanged=True, gameDeploymentUnchanged=True,
        issues={'1': 'Broad discovery/refresh confirmed; Chef measures 8.883ms average on ship, exact FPS ratio still requires AB',
                '2': 'No reload/free-left-hand gate; separated-native-hand counterexample reproduced',
                '3': 'Exact Epoch non-skeletal component excluded; refresh-only visual repair remains unverified',
                '4': 'Preview runs body/attachment corrections but all 23 sampled preview frames skip left IK; real finger skin/LOD cause unresolved',
                '5': 'attach_hand_r is incorrectly treated as an ADS gate; non-contact aim_only sidearm still solved'},
        liveLogAnalysed=live is not None))
    print(json.dumps({'output': str(output), 'status': counterexamples['status'],
        'baselineChecks': counterexamples['baselineChecks'], 'checks': counterexamples['checks'],
        'issues': counterexamples['issues'], 'liveSessions': len(live['sessions']) if live else 0}, indent=2))


if __name__ == '__main__':
    main()
