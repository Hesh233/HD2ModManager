"""Finalize a self-contained local B19 delivery, without altering B17/B18."""
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files
import package_native_v12 as pack
from repack_native_b19 import build as repack

W = ROOT / 'outputs/native-v27-b19-20261105'
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
    for name, sha in scope['assetSha256'].items():
        assert digest(R / name) == sha, name
    packages = load(W / 'static-packages.json')
    imported = {p['package']: p['sha256'] for p in load(W / 'package-inspection.json')['packages']}
    for row in packages:
        assert digest(W / row['name']) == row['sha256'] == imported[row['name']]
    diag = W / 'diagnostics/B19'
    diag.mkdir(parents=True, exist_ok=True)
    doc = ROOT / 'docs/native-v27-B19-20261105.md'
    shutil.copy2(doc, diag / '测试说明.txt')
    shutil.copy2(doc, W / '先读我-B19.md')
    shutil.copy2(ROOT / 'tools/repack_native_b19.py', diag / 'repack_native_b19.py')
    for variant in ('0', 'R', 'LR'):
        folder = diag / 'variants' / variant
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(W / ('hd2physbone-B19-' + variant + '.lua'), folder / 'hd2physbone.lua')
        shutil.copy2(W / ('B19-' + variant + '.json'), folder / 'profile.json')
        shutil.copy2(W / 'runtime' / variant / 'manifest.json', folder / 'manifest.json')
        (folder / 'container-header.bin').write_bytes((W / 'runtime' / variant / '9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    rebuilt = repack(diag)
    for variant, data in rebuilt['variants'].items():
        assert data['patchSha256'] == digest(W / 'runtime' / variant / '9ba626afa44a3aa3.patch_0')
        assert data['sourceSha256'] == digest(W / ('hd2physbone-B19-' + variant + '.lua'))
    save_json(W / 'repack-audit.json', dict(rebuilt, patchMatchesDelivered=True))
    sources = [(ROOT / 'HD2PhysBoneCompat/src' / name, Path('src') / name) for name in scope['sourceSha256']]
    for name in ('native_grip_alignment_harness.lua', 'native_grip_alignment_adapter_harness.lua',
                 'attachments_layout_harness.lua', 'strict_id32_fixture.lua'):
        sources.append((ROOT / 'HD2PhysBoneCompat/test' / name, Path('test') / name))
    for name in ('prepare_native_v27_b19.py', 'audit_native_v27_b19.py', 'audit_native_v27_b19_chef.py',
                 'audit_native_v27_b19_import.py', 'package_native_v27_b19.py', 'sync_native_grip_alignment.py',
                 'package_native_v12.py', 'audit_native_v15_chef.py', 'audit_native_v16_import.py',
                 'audit_native_attachment_layouts.py', 'native_attachment_layouts.py'):
        sources.append((ROOT / 'tools' / name, Path('tools') / name))
    for name in (*REQUIRED, 'prior-conflict-analysis.json', 'repack-audit.json'):
        sources.append((W / name, Path('reports') / name))
    for name in ('native-v25-B17-20261105.md', 'native-v26-B18-20261105.md'):
        sources.append((ROOT / 'docs' / name, Path('evidence') / name))
    sources.extend((p, Path('evidence') / p.name) for p in W.glob('*.log'))
    sources.append((W / 'baseline/native_attachments.lua', Path('baseline/native_attachments.lua')))
    for path, relative in sources:
        target = diag / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    (diag / 'README.txt').write_text(
        'B19: existing Source weapon bones are read-only inputs; native attachment bones are the only outputs.\n'
        'Run python repack_native_b19.py here to reproduce the three patches with standard Python.\n'
        'Full regression needs the original workspace, historical Units/loader fixtures and its Python 3.11 lupa runtime.\n'
        'Workspace order (tools/): prepare_native_v27_b19.py, audit_native_v27_b19.py, '
        'audit_native_v27_b19_chef.py, audit_native_v27_b19_import.py, package_native_v27_b19.py.\n'
        '0 is a legacy-writes-off control; R adds right alignment; LR adds left alignment to R.\n'
        'All use the same accepted v15 animation and existing model. No game deployment or game test performed.\n'
        'Raw Source attachment orientation is deliberate; in-game grip-axis calibration is not yet verified.\n', encoding='utf-8')
    pack.WORK = W
    bundle = pack.archive('B19-增量排查工程.zip', [(p, rel) for p, rel in files(diag) if rel.parts[0] != 'rebuilt'])
    for row in packages + [bundle]:
        with zipfile.ZipFile(W / row['name']) as archive:
            assert archive.testzip() is None
    save_json(W / 'delivery-verification.json', dict(status='PASS', revision='native-v27-B19',
        animationRevision='native-v15', packages=packages + [bundle],
        reports={name: digest(W / name) for name in (*REQUIRED, 'repack-audit.json', 'prior-conflict-analysis.json')},
        sourceSha256=scope['sourceSha256'], assetSha256=scope['assetSha256'],
        readmeSha256=digest(W / '先读我-B19.md'), gameDeployed=False, gameTested=False,
        priorDeliveriesModified=False, recommendedOrder=['B19-0', 'B19-R', 'B19-LR']))
    print('B19 local delivery verified: three importable packages, reproducible source bundle, unchanged assets; game trial pending.')


if __name__ == '__main__':
    main()
