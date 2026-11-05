"""Deliver verified L/R profiles and the completed B16 trial evidence locally."""
import argparse
import copy
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files
import package_native_v12 as pack
from repack_native_b17 import build as repack

W = ROOT / 'outputs/native-v25-b17-20261105'
R = ROOT / 'outputs/native-manual-20261103'
BACKUP = Path('backups/v25-b17-before-20261105')
REQUIRED = ['scope-audit.json', 'candidate-tree.json', 'attachment-probe-audit.json',
            'chef-compatibility-audit.json', 'package-inspection.json']
DOCUMENTS = ('先读我-人工测试.txt', '转换原理与验证.md', 'AB测试说明.md')


def check_baseline():
    baseline = load(W / 'baseline-delivery.json')
    assert baseline == load(R / 'delivery-verification.json') and baseline['revision'] == 'native-v24'
    for row in baseline['verified']:
        assert digest(R / row['path']) == row['sha256'], row['path']
    return baseline


def prepare():
    baseline = check_baseline()
    save_json(W / 'baseline-file-audit.json', dict(status='PASS', revision='native-v24', files=len(baseline['verified'])))
    for name in REQUIRED:
        assert load(W / name)['status'] == 'PASS', name
    scope = load(W / 'scope-audit.json')
    audit = load(W / 'attachment-probe-audit.json')
    chef = load(W / 'chef-compatibility-audit.json')
    tree = load(W / 'candidate-tree.json')
    assert tree['disjoint'] and tree['unionExactlyEqualsB16H'] and tree['rootFamiliesPerGroup'] == 1
    assert scope['sourceSha256'] == audit['sourceSha256'] == digest(ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua')
    assert scope['probeSha256'] == audit['probeSha256'] == digest(ROOT / 'HD2PhysBoneCompat/src/native_attachment_probe.lua')
    assert chef['embeddedSourceSha256'] == scope['baselineChefSourceSha256']
    for name, sha in chef['embeddedSourceSha256'].items():
        assert digest(ROOT / 'HD2PhysBoneCompat/src' / name) == sha
    assert digest(R / 'test01-配套动画.zip') == scope['animationSha256']
    comparison = load(W / 'evidence/B16-comparison.json')
    assert comparison['status'] == 'PASS'
    assert comparison['results']['H']['candidateSetPositive'] and not comparison['results']['W']['candidateSetPositive']
    packages = load(W / 'static-packages.json')
    assert len(packages) == 2
    imported = {row['package']: row['sha256'] for row in load(W / 'package-inspection.json')['packages']}
    for row in packages:
        assert digest(W / row['name']) == row['sha256'] == imported[row['name']]
        with zipfile.ZipFile(W / row['name']) as archive:
            assert archive.testzip() is None
    diag = W / 'diagnostics/B17'
    diag.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'docs/native-v25-B17-20261105.md', diag / '测试说明.txt')
    shutil.copy2(ROOT / 'docs/native-v24-B16-20261105.md', W / 'evidence/B16-feedback-and-context.md')
    shutil.copy2(ROOT / 'tools/repack_native_b17.py', diag / 'repack_native_b17.py')
    for variant in ('L', 'R'):
        folder = diag / 'variants' / variant
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(W / ('hd2physbone-B17-' + variant + '.lua'), folder / 'hd2physbone.lua')
        shutil.copy2(W / ('B17-' + variant + '.json'), folder / 'profile.json')
        shutil.copy2(W / 'runtime' / variant / 'manifest.json', folder / 'manifest.json')
        (folder / 'container-header.bin').write_bytes((W / 'runtime' / variant / '9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    rebuilt = repack(diag)
    for variant, row in rebuilt['variants'].items():
        assert row['patchSha256'] == digest(W / 'runtime' / variant / '9ba626afa44a3aa3.patch_0')
    save_json(W / 'repack-audit.json', dict(rebuilt, patchMatchesDelivered=True))
    pairs = [(ROOT / 'HD2PhysBoneCompat/src' / name, Path('src') / name) for name in chef['embeddedSourceSha256']]
    pairs.extend((ROOT / 'HD2PhysBoneCompat/test' / name, Path('test') / name) for name in
                 ('attachments_layout_harness.lua', 'attachment_probe_harness.lua', 'strict_id32_fixture.lua'))
    toolnames = ('analyze_native_b16_results.py', 'prepare_native_v25_b17.py', 'audit_native_v25_b17.py',
                 'audit_native_v25_b17_chef.py', 'audit_native_v25_b17_import.py', 'package_native_v25_b17.py',
                 'audit_native_v23_b15.py', 'audit_native_v20_b12.py', 'audit_native_v20_b12_chef.py',
                 'audit_native_v18_b9.py', 'audit_native_v15_chef.py', 'audit_native_v16_import.py',
                 'audit_native_attachment_layouts.py', 'native_attachment_layouts.py', 'analyze_native_b9_log.py',
                 'package_native_v12.py')
    pairs.extend((ROOT / 'tools' / name, Path('tools') / name) for name in toolnames)
    report_names = REQUIRED + ['repack-audit.json', 'baseline-file-audit.json']
    pairs.extend((W / name, Path('reports') / name) for name in report_names)
    pairs.extend((path, Path('evidence') / relative) for path, relative in files(W / 'evidence'))
    for source, relative in pairs:
        dest = diag / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    (diag / 'README.txt').write_text(
        'B17 partitions B16-H into L (attach_hand_l) and R (attach_hand_r/weapon_aim). Runtime is unchanged.\n'
        'Run python repack_native_b17.py here using standard Python to reproduce both patches.\n'
        'Other audits require the original workspace, historical fixtures and Python 3.11 with the existing lupa runtime.\n'
        'Workspace order: py -3.11 tools/analyze_native_b16_results.py; prepare_native_v25_b17.py; '
        'audit_native_v25_b17.py; audit_native_v25_b17_chef.py; audit_native_v25_b17_import.py; '
        'package_native_v25_b17.py prepare; package_native_v25_b17.py deliver (all in tools/).\n'
        'Historical delivery must still be native-v24 when rebuilding the full delivery. '
        'The standalone repacker has no such requirement.\n'
        'Test L, then R separately. Neither is game-tested. Individual driver and flash cause remain unconfirmed.\n'
        'The test harness injects a post-mutation fault at min(2, root count), covering one-root variants.\n', encoding='utf-8')
    pack.WORK = W
    increment = pack.archive('B17-增量排查工程.zip', [(p, r) for p, r in files(diag) if r.parts[0] != 'rebuilt'])
    save_json(W / 'incremental-source-package.json', increment)
    for name in DOCUMENTS:
        shutil.copy2(ROOT / 'docs/native-v25-B17-20261105.md', W / name)
    report = load(R / 'package-report.json')
    assert not any('B17-' in row['name'] for row in report['packages'])
    report['packages'].extend(packages + [increment])
    report.update(revision='native-v25', runtimeRevision='native-v25-B17', probe='B17-L/R', animationRevision='native-v15',
                  animationUserAccepted=True, gameTested=False, gameDeployed=False, incrementalDelivery=True,
                  validationStage='isolated-import-verified', incrementalReports={name: digest(W / name) for name in report_names},
                  sourcePackages={'base': 'test01-源工程.zip', 'previousIncrement': 'B16-增量排查工程.zip', 'increment': 'B17-增量排查工程.zip'})
    matrix = load(R / 'ab-matrix.json')
    matrix.update(revision='native-v25', gameTested=False, nextTest='B17-L')
    for variant in ('H', 'W'):
        key = 'B16-' + variant
        result = comparison['results'][variant]
        result_path = 'project/diagnostics/B17/evidence/' + key + '-game-result.json'
        assert result == load(W / 'evidence' / (key + '-game-result.json'))
        report.setdefault('priorUserResults', {})[key] = result['userFeedback']
        report.setdefault('gameResults', {})[key] = dict(
            status='candidate-set-positive' if variant == 'H' else 'no-observed-weapon-response',
            report=result_path, sha256=digest(W / 'evidence' / (key + '-game-result.json')),
            candidateDisplacementVerified=True, individualDriverConfirmed=False, flashCauseConfirmed=False)
        prior = next(row for row in matrix['groups'] if row['group'] == key)
        prior.update(status='tested-weapon-response-positive' if variant == 'H' else 'tested-no-observed-weapon-response',
                     gameTested=True, result=result['userFeedback'], resultReport=result_path,
                     appliedCycles=result['appliedCycles'], candidateDisplacementVerified=True)
    for variant, row in zip(('L', 'R'), packages):
        matrix['groups'].append(dict(group='B17-' + variant, package=row['name'], status='awaiting-game-test', gameTested=False,
            description='B16-H 的左手挂点。' if variant == 'L' else 'B16-H 的右手挂点及 weapon_aim 子节点。',
            profileSha256=digest(W / ('B17-' + variant + '.json'))))
    save_json(W / 'package-report.json', report)
    save_json(W / 'ab-matrix.json', matrix)
    print('B17 baseline, regressions, repack, isolated imports and B16 evidence verified; local delivery prepared.')


def deliver():
    baseline = check_baseline()
    expected = {row['path']: row['sha256'] for row in baseline['verified']}
    report = load(W / 'package-report.json')
    assert report['revision'] == 'native-v25' and report['validationStage'] == 'isolated-import-verified'
    assert load(W / 'package-inspection.json')['status'] == 'PASS'
    for name, sha in report['incrementalReports'].items():
        assert digest(W / name) == sha
    packages = load(W / 'static-packages.json') + [load(W / 'incremental-source-package.json')]
    for row in packages:
        assert digest(W / row['name']) == row['sha256']
    pairs = [(W / row['name'], Path(row['name'])) for row in packages]
    pairs.extend((p, Path('project/diagnostics/B17') / r) for p, r in files(W / 'diagnostics/B17') if r.parts[0] != 'rebuilt')
    pairs.extend((W / name, Path(name)) for name in ('package-report.json', 'ab-matrix.json', *DOCUMENTS))
    backup = (R / BACKUP).resolve()
    assert backup.is_relative_to(R.resolve()) and not backup.exists()
    prepared = []
    for source, relative in pairs:
        source, dest, saved = source.resolve(), (R / relative).resolve(), (backup / relative).resolve()
        assert source.is_relative_to(W.resolve()) and dest.is_relative_to(R.resolve()) and saved.is_relative_to(backup)
        old = digest(dest) if dest.exists() else None
        if old is not None:
            assert old == expected[relative.as_posix()]
        prepared.append((source, relative, dest, saved, old, digest(source)))
    backup.mkdir(parents=True)
    shutil.copy2(R / 'delivery-verification.json', backup / 'delivery-verification.json')
    expected[(BACKUP / 'delivery-verification.json').as_posix()] = digest(backup / 'delivery-verification.json')
    for source, relative, dest, saved, old, sha in prepared:
        if old is not None and old != sha:
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
            assert digest(saved) == old
            expected[(BACKUP / relative).as_posix()] = old
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        assert digest(dest) == sha
        expected[relative.as_posix()] = sha
    for name, sha in expected.items():
        assert digest(R / name) == sha, name
    result = copy.deepcopy(baseline)
    result.update(status='PASS', revision='native-v25', runtimeRevision='native-v25-B17', files=len(expected), backup=str(backup),
                  gameDeployed=False, gameTested=False, lastGameResult='project/diagnostics/B17/evidence/B16-comparison.json',
                  verified=[dict(path=p, sha256=s) for p, s in sorted(expected.items())])
    save_json(R / 'delivery-verification.json', result)
    print('Delivered B17;', len(expected), 'SHA-verified files. B16 controls and v15 animation retained; no game deployment.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'deliver'])
    if parser.parse_args().stage == 'deliver':
        deliver()
    else:
        prepare()
