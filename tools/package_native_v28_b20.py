"""Finalize B20 packages, evidence and reproducible sources without altering B19."""
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files
import package_native_v12 as pack
from repack_native_b20 import build as repack

W = ROOT / 'outputs/native-v28-b20-20261105'
OLD = ROOT / 'outputs/native-v27-b19-20261105'
R = ROOT / 'outputs/native-manual-20261103'
REQUIRED = ('scope-audit.json', 'mapping-audit.json', 'grip-alignment-audit.json',
            'chef-compatibility-audit.json', 'package-inspection.json')


def main():
    for name in REQUIRED:
        assert load(W / name)['status'] == 'PASS', name
    scope = load(W / 'scope-audit.json')
    audit = load(W / 'grip-alignment-audit.json')
    chef = load(W / 'chef-compatibility-audit.json')
    assert audit['sourceSha256'] == scope['sourceSha256']['native_attachments.lua']
    assert audit['moduleSha256'] == scope['sourceSha256']['native_grip_alignment.lua']
    assert chef['embeddedSourceSha256'] == scope['sourceSha256']
    for name, sha in scope['sourceSha256'].items():
        assert digest(ROOT / 'HD2PhysBoneCompat/src' / name) == sha, name
    for name, sha in audit['testSha256'].items():
        assert digest(ROOT / 'HD2PhysBoneCompat/test' / name) == sha, name
    for name, sha in scope['assetSha256'].items():
        assert digest(R / name) == sha, name
    for name, sha in scope['historicalB19Sha256'].items():
        assert digest(OLD / name) == sha, name
    assert load(W / 'evidence/B19-comparison.json')['status'] == 'PASS'
    assert load(W / 'evidence/B19-user-feedback.json')['orientationClarification'] == '枪口朝上，握把朝内，同时枪身大概有20度的倾斜'
    packages = load(W / 'static-packages.json')
    imported = {p['package']: p['sha256'] for p in load(W / 'package-inspection.json')['packages']}
    assert len(packages) == len(imported) == 4
    for row in packages:
        assert digest(W / row['name']) == row['sha256'] == imported[row['name']]
    diag = W / 'diagnostics/B20'
    diag.mkdir(parents=True, exist_ok=True)
    doc = ROOT / 'docs/native-v28-B20-20261105.md'
    shutil.copy2(doc, diag / '测试说明.txt')
    shutil.copy2(doc, W / '先读我-B20.md')
    shutil.copy2(ROOT / 'tools/repack_native_b20.py', diag / 'repack_native_b20.py')
    for variant in ('R', 'A', 'H', 'T'):
        folder = diag / 'variants' / variant
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(W / ('hd2physbone-B20-' + variant + '.lua'), folder / 'hd2physbone.lua')
        shutil.copy2(W / ('B20-' + variant + '.json'), folder / 'profile.json')
        shutil.copy2(W / 'runtime' / variant / 'manifest.json', folder / 'manifest.json')
        (folder / 'container-header.bin').write_bytes((W / 'runtime' / variant / '9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    rebuilt = repack(diag)
    for variant, data in rebuilt['variants'].items():
        assert data['patchSha256'] == digest(W / 'runtime' / variant / '9ba626afa44a3aa3.patch_0')
        assert data['sourceSha256'] == digest(W / ('hd2physbone-B20-' + variant + '.lua'))
    save_json(W / 'repack-audit.json', dict(rebuilt, patchMatchesDelivered=True))
    sources = [(ROOT / 'HD2PhysBoneCompat/src' / name, Path('src') / name) for name in scope['sourceSha256']]
    sources += [(ROOT / 'HD2PhysBoneCompat/test' / name, Path('test') / name) for name in audit['testSha256']]
    for name in ('prepare_native_v28_b20.py', 'audit_native_v28_b20.py', 'audit_native_v28_b20_chef.py',
                 'audit_native_v28_b20_import.py', 'package_native_v28_b20.py', 'sync_native_grip_alignment.py',
                 'analyze_native_b19_results.py', 'package_native_v12.py', 'audit_native_v15_chef.py',
                 'audit_native_v16_import.py', 'audit_native_attachment_layouts.py', 'audit_native_v20_b12.py',
                 'native_attachment_layouts.py'):
        sources.append((ROOT / 'tools' / name, Path('tools') / name))
    for name in (*REQUIRED, 'repack-audit.json'):
        sources.append((W / name, Path('reports') / name))
    for name in ('native-v25-B17-20261105.md', 'native-v27-B19-20261105.md'):
        sources.append((ROOT / 'docs' / name, Path('evidence') / name))
    sources.extend((p, Path('evidence') / rel) for p, rel in files(W / 'evidence'))
    sources.extend((p, Path('evidence/offline') / p.name) for p in W.glob('*.log'))
    for name in ('native_attachments.lua', 'native_grip_alignment.lua'):
        sources.append((W / 'baseline' / name, Path('baseline') / name))
    for path, relative in sources:
        target = diag / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    (diag / 'README.txt').write_text(
        'B20: native output positions follow read-only Source anchors; native world aiming basis and scale are preserved.\n'
        'R is the right baseline. A/H/T each add exactly one native left target: attachment/wrist/wrist-helper.\n'
        'Run python repack_native_b20.py here to reproduce the four patches with standard Python.\n'
        'Full regression needs the original workspace, historical Units/loader fixtures and its Python 3.11 lupa runtime.\n'
        'Workspace order (tools/): prepare_native_v28_b20.py, audit_native_v28_b20.py, '
        'audit_native_v28_b20_chef.py, audit_native_v28_b20_import.py, package_native_v28_b20.py.\n'
        'All use the accepted v15 animation and existing test01 model. B19 deliveries are unchanged.\n'
        'Weapon/foregrip IK telemetry is read-only; ownership and the real left driving chain are unverified.\n'
        'Offline fixtures simulate existing links; they do not prove game relationships or visual correction.\n'
        'B19 live evidence and the user orientation clarification are in evidence/. B20 game trial is pending.\n', encoding='utf-8')
    pack.WORK = W
    bundle = pack.archive('B20-增量排查工程.zip', [(p, rel) for p, rel in files(diag) if rel.parts[0] != 'rebuilt'])
    for row in packages + [bundle]:
        with zipfile.ZipFile(W / row['name']) as archive:
            assert archive.testzip() is None
    save_json(W / 'delivery-verification.json', dict(status='PASS', revision='native-v28-B20',
        animationRevision='native-v15', packages=packages + [bundle],
        reports={name: digest(W / name) for name in (*REQUIRED, 'repack-audit.json')},
        evidenceSha256={str(rel): digest(path) for path, rel in files(W / 'evidence')},
        sourceSha256=scope['sourceSha256'], testSha256=audit['testSha256'], assetSha256=scope['assetSha256'],
        readmeSha256=digest(W / '先读我-B20.md'), gameDeployed=False, gameTested=False,
        priorDeliveriesModified=False, recommendedOrder=['B20-R', 'B20-A', 'B20-H', 'B20-T']))
    print('B20 verified: four importable packages, reproducible source bundle, unchanged assets/B19; game trial pending.')


if __name__ == '__main__':
    main()
