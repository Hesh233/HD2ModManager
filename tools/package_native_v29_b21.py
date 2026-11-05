"""Finalize B21 evidence and reproducible reader sources without game deployment."""
from pathlib import Path
import shutil
import struct
import zipfile
from package_native_v12 import ROOT, load, save_json, digest, files
import package_native_v12 as pack
from anim_batch_mod.archive import TocArchive
from repack_native_b21 import build as repack

W = ROOT / 'outputs/native-v29-b21-20261105'
OLD = ROOT / 'outputs/native-v28-b20-20261105'
OLD19 = ROOT / 'outputs/native-v27-b19-20261105'
R = ROOT / 'outputs/native-manual-20261103'
REQUIRED = (
    'static-correspondence-audit.json', 'capture-runtime-audit.json', 'capture-analysis-audit.json',
    'chef-compatibility-audit.json', 'package-inspection.json',
)
TOOLS = (
    'prepare_native_v29_b21.py', 'audit_native_v29_b21.py', 'audit_native_v29_b21_chef.py',
    'audit_native_v29_b21_import.py', 'audit_native_b21_correspondence.py', 'audit_native_b21_analysis.py',
    'analyze_native_v29_b21_assets.py', 'analyze_native_b20_results.py',
    'analyze_native_b21_capture.py', 'package_native_v29_b21.py', 'package_native_v12.py', 'audit_native_v16_import.py',
)


def main():
    reports = {name: load(W / name) for name in REQUIRED}
    assert all(r['status'] == 'PASS' for r in reports.values())
    scope = load(W / 'capture-scope.json')
    runtime = reports['capture-runtime-audit.json']
    analysis = reports['capture-analysis-audit.json']
    chef = reports['chef-compatibility-audit.json']
    source = ROOT / 'HD2PhysBoneCompat/src'
    for name, sha in scope['sourceSha256'].items():
        assert digest(source / name) == sha == runtime['sourceSha256'][name], name
    assert runtime['mutationCalls'] == 0 and runtime['sourceEmbedsCurrent']
    assert digest(ROOT / 'HD2PhysBoneCompat/test/native_reference_capture_harness.lua') == runtime['testSha256']
    assert digest(W / 'native-grip-capture.lua') == scope['assembledSha256'] == chef['assembledSha256']
    assert digest(W / 'capture-profile.json') == scope['profileSha256']
    assert digest(source / 'native_reference_capture.lua') == chef['moduleSha256']
    for name, key in (('analyze_native_b21_capture.py', 'analyzerSha256'), ('audit_native_b21_analysis.py', 'testSha256')):
        assert digest(ROOT / 'tools' / name) == analysis[key]
    assert digest(W / 'fixture-native-capture.log') == analysis['fixtureSha256']
    assert digest(W / 'fixture-capture-analysis.json') == analysis['fixtureReportSha256']
    fixture_report = load(W / 'fixture-capture-analysis.json')
    assert fixture_report['provenance'] == 'simulated_fixture' and not fixture_report['gamePoseCaptured']
    static = reports['static-correspondence-audit.json']
    assert digest(W / 'native-reference-assets.json') == static['sourceAssetReportSha256']
    assert digest(W / 'native-capture-layouts.json') == static['layoutReportSha256']

    # These baselines predate B21. A changed historical input must be investigated
    # instead of silently recording its new hash as "unchanged".
    prior_scope = load(OLD / 'scope-audit.json')
    for name, sha in scope['legacySourceSha256'].items():
        assert digest(source / name) == sha, 'Legacy runtime changed: ' + name
    for name, sha in scope['legacyPackageSha256'].items():
        assert digest(OLD / name) == sha, 'B20 delivery changed: ' + name
    for name, sha in prior_scope['historicalB19Sha256'].items():
        assert digest(OLD19 / name) == sha, 'B19 delivery changed: ' + name
    for name, sha in prior_scope['assetSha256'].items():
        assert digest(R / name) == sha, 'Existing model/animation changed: ' + name
    for row in load(W / 'native-reference-assets.json')['resources']:
        assert digest(W / row['path']) == row['sha256']
    b20 = load(W / 'evidence/B20/B20-comparison.json')
    assert b20['status'] == 'CAPTURED'
    assert {r['variant'] for r in b20['sessions']} == {'B20-R', 'B20-A', 'B20-H', 'B20-T'}
    assert all(not r['errors'] and not r['leftVisualResponse'] and not r['rightMotionAccepted'] for r in b20['sessions'])

    packages = load(W / 'static-packages.json')
    imported = {r['package']: r['sha256'] for r in reports['package-inspection.json']['packages']}
    assert len(packages) == len(imported) == 1
    for row in packages:
        assert digest(W / row['name']) == row['sha256'] == imported[row['name']]
    patch = W / 'runtime/9ba626afa44a3aa3.patch_0'
    assert digest(patch) == chef['patchSha256']
    archive = TocArchive.parse_parts(bytearray(patch.read_bytes()))
    assert len(archive.entries) == 1
    entry = next(iter(archive.entries.values()))
    assert entry.file_id == int(scope['addonResource'], 16)
    body = (W / 'native-grip-capture.lua').read_bytes()
    assert entry.toc_data == struct.pack('<II', len(body), 2) + body
    assert all((W / 'runtime' / (patch.name + suffix)).stat().st_size == 0 for suffix in ('.stream', '.gpu_resources'))
    doc = ROOT / 'docs/native-v29-B21-20261105.md'
    assert digest(doc) == digest(W / '先读我-B21.md') == digest(W / 'runtime/测试说明.txt')

    dest = W / 'diagnostics/B21'
    dest.mkdir(parents=True, exist_ok=True)

    def copy(path, relative):
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    copy(doc, '测试说明.txt')
    copy(W / 'native-grip-capture.lua', 'native-grip-capture.lua')
    copy(W / 'capture-profile.json', 'capture-profile.json')
    copy(W / 'runtime/manifest.json', 'manifest.json')
    copy(ROOT / 'tools/repack_native_b21.py', 'repack_native_b21.py')
    copy(ROOT / 'tools/analyze_native_b21_capture.py', 'analyze_native_b21_capture.py')
    (dest / 'container-header.bin').write_bytes(patch.read_bytes()[:192])
    rebuilt = repack(dest)
    assert rebuilt['patchSha256'] == digest(patch)
    assert rebuilt['sourceSha256'] == digest(W / 'native-grip-capture.lua')
    save_json(W / 'repack-audit.json', dict(rebuilt, patchMatchesDelivered=True))

    for name in scope['sourceSha256']:
        copy(source / name, Path('src') / name)
    for name in ('native_reference_capture_harness.lua', 'strict_id32_fixture.lua'):
        copy(ROOT / 'HD2PhysBoneCompat/test' / name, Path('test') / name)
    for name in TOOLS:
        copy(ROOT / 'tools' / name, Path('tools') / name)
    for name in (*REQUIRED, 'repack-audit.json', 'capture-scope.json', 'static-packages.json'):
        copy(W / name, Path('reports') / name)
    for name in ('native-reference-assets.json', 'native-capture-layouts.json', 'native-hand-correspondence.csv'):
        copy(W / name, Path('reference') / name)
    for path, relative in files(W / 'assets'):
        copy(path, Path('reference/assets') / relative)
    for path, relative in files(W / 'evidence'):
        copy(path, Path('evidence') / relative)
    for name in ('collector-regression.log', 'fixture-native-capture.log', 'chef-fixture.log',
                 'fixture-capture-analysis.json', 'fixture-capture-analysis.md'):
        copy(W / name, Path('evidence/fixtures') / name)
    for name in ('native-v25-B17-20261105.md', 'native-v28-B20-20261105.md', 'test01-grip-memory.md'):
        copy(ROOT / 'docs' / name, Path('evidence/history') / name)
    (dest / 'README.txt').write_text(
        'B21: original armor correspondence and a standalone read-only native grip collector.\n'
        'Read 测试说明.txt first. The importable Lua-only package is delivered separately.\n'
        'python repack_native_b21.py reproduces the exact delivered patch using standard Python.\n'
        'The assembled native-grip-capture.lua, profile, original header and source modules are included.\n'
        'analyze_native_b21_capture.py runs offline with standard Python 3.11+.\n'
        'For bundled fixtures, explicitly use --provenance simulated_fixture. No B21 game capture is bundled.\n'
        'reference/ contains the extracted original Units and serialized bind/skin evidence.\n'
        'evidence/B20 contains previous real-game logs. evidence/fixtures is simulated, not game data.\n'
        'Full extraction/runtime/Chef/import audits require the original SDK workspace, game data, Chef source and manager.\n'
        'On this host, Python 3.13 plus outputs/native-fix-20261103/test-runtime provides lupa.lua51;\n'
        'Python 3.11 remains suitable for extraction, preparation, log analysis and packaging.\n'
        'Workspace order: analyze_native_b20_results.py; analyze_native_v29_b21_assets.py; prepare_native_v29_b21.py;\n'
        'audit_native_b21_correspondence.py; audit_native_v29_b21.py; audit_native_b21_analysis.py;\n'
        'audit_native_v29_b21_chef.py; audit_native_v29_b21_import.py; package_native_v29_b21.py.\n'
        'No pose writes, forced graph refreshes, alignment solvers or model/animation assets in the runtime package.\n'
        'Original mesh remaps prove eligible skin inputs, not nonzero weights on every vertex or live IK priorities.\n'
        'All cross-unit relationships retain unverified ownership. Update/render are not identified as before/after IK.\n',
        encoding='utf-8')
    bundle_files = [(path, relative) for path, relative in files(dest)
                    if relative.parts[0] != 'rebuilt' and relative.as_posix() != 'bundle-file-hashes.json']
    save_json(dest / 'bundle-file-hashes.json', {relative.as_posix(): digest(path) for path, relative in bundle_files})
    bundle_files.append((dest / 'bundle-file-hashes.json', Path('bundle-file-hashes.json')))
    pack.WORK = W
    bundle = pack.archive('B21-原生握持采集工程.zip', bundle_files)
    for row in packages + [bundle]:
        with zipfile.ZipFile(W / row['name']) as z:
            assert z.testzip() is None
    save_json(W / 'delivery-verification.json', dict(status='PASS', revision='native-v29-B21',
        packages=packages + [bundle], reports={n: digest(W / n) for n in (*REQUIRED, 'repack-audit.json')},
        sourceSha256=scope['sourceSha256'], legacySourceSha256=scope['legacySourceSha256'],
        protectedAssetSha256=prior_scope['assetSha256'], legacyPackageSha256=scope['legacyPackageSha256'],
        historicalB19Sha256=prior_scope['historicalB19Sha256'],
        readmeSha256=digest(doc), bundleFileHashesSha256=digest(dest / 'bundle-file-hashes.json'),
        addonResource=scope['addonResource'], runtimeResourceCount=1, modelOrAnimationResourceCount=0,
        patchSha256=digest(patch), originalArmorUnitCount=static['originalArmorUnitCount'],
        modelAndAnimationFilesUnchanged=True, historicalDeliveriesUnchanged=True,
        runtimeMutationCalls=runtime['mutationCalls'], gameDeployed=False, gamePoseCaptured=False,
        nextStep='Capture native B-01 with SMG-203 and a vertical foregrip after disabling test01 experiments and restarting.'))
    print('B21 verified: standalone reader, original data, source bundle, byte-identical rebuild; native game capture pending.')


if __name__ == '__main__':
    main()
