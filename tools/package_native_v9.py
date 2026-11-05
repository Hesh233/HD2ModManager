"""Package v9 from final serialized files, then deliver through verified backups.

All mutations are confined to this repository's outputs. This does not import,
deploy, launch the desktop manager, or bypass its ManagerProcessRunning guard.
"""
from __future__ import annotations

import argparse
import ast
import collections
import csv
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'outputs/native-v9-20261104'
PROJECT = WORK / 'project'
RELEASE = ROOT / 'outputs/native-manual-20261103'
BASE = ROOT / 'outputs/native-v6-20261104/project'
sys.path.insert(0, str(ROOT.parent.parent))
from anim_batch_mod.constants import ANIMATION_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID, UNIT_TYPE_ID
from anim_batch_mod.formats import BonesData, UnitData

PROTECTED = {'settings.json', 'config.toml', 'data', 'cache', 'logs', 'config'}
GENERATED_PATCH = re.compile(r'9ba626afa44a3aa3\.patch_\d+(?:\.(?:gpu_resources|stream))?$')
GENERATED_PATCH_FOLDERS = ('animations/runtime', 'models/test01', 'models-o3/test01-O3', 'physics-runtime/patch版')
DEFAULT_AUDITS = (
    'animation-final-audit.json', 'attachment-runtime-audit.json',
    'chef-compatibility-audit.json', 'published-generator-audit.json',
    'fusion-layer-audit.json', 'grip-validation-audit.json', 'model-final-audit.json',
)


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def files(root, prefix=None):
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Unexpected symlink in generated output: {path}')
        if path.is_file() and '__pycache__' not in path.parts:
            relative = path.relative_to(root)
            yield path, Path(prefix) / relative if prefix else relative


def project_files(include_animation_runtime=False):
    for path, relative in files(PROJECT):
        if (not include_animation_runtime and relative.parts[:2] == ('animations', 'runtime')) or path.name.startswith('resource-index.sqlite3'):
            continue
        yield path, relative


def records(path):
    with Path(path).open('rb') as f:
        header = f.read(72)
        if len(header) != 72:
            raise ValueError(f'Truncated patch: {path}')
        types, count = struct.unpack_from('<II', header, 4)
        f.seek(72 + types * 32)
        return [struct.unpack('<QQQQQQQIIIIII', f.read(80)) for _ in range(count)]


def payload(path, row):
    with Path(path).open('rb') as f:
        f.seek(row[2])
        result = f.read(row[7])
    assert len(result) == row[7], path
    return result


def main_patches(root):
    return sorted(p for p, _ in files(root) if re.fullmatch(r'[0-9a-f]{16}\.patch_\d+', p.name))


def facts():
    """Read counts from final Unit/Bones resources, never from expected constants."""
    manifests = [PROJECT / 'source-skeleton.json', PROJECT / 'models-o3/test01-O3/source-skeleton.json']
    manifest = load(manifests[0])
    for path in manifests:
        current = load(path)
        assert current['modelScale'] == 1.08 and current['scaleOrigin'] == 'source', path
    profile = load(PROJECT / 'attachment-profile.json')
    assert len(profile['native']) == len(profile['vpk']) == 29
    animation_paths = main_patches(PROJECT / 'animations/runtime')
    assert len(animation_paths) == 1, 'Exactly one companion patch is required'
    animation_path = animation_paths[0]
    rows = records(animation_path)
    avatar_row = [r for r in rows if r[1] == UNIT_TYPE_ID]
    bones_row = [r for r in rows if r[1] == BONE_TYPE_ID]
    state_row = [r for r in rows if r[1] == STATE_MACHINE_TYPE_ID]
    assert len(avatar_row) == len(bones_row) == len(state_row) == 1
    avatar = UnitData.parse(payload(animation_path, avatar_row[0]))
    bones = BonesData.parse(payload(animation_path, bones_row[0]))
    animation_ids = {r[0] for r in rows if r[1] == ANIMATION_TYPE_ID}
    build = load(PROJECT / 'animations/build-report.json')
    assert build['status'] == 'complete'
    options=tomllib.loads((PROJECT/'config.toml').read_text(encoding='utf-8-sig'))['native_skeleton']
    assert build['config_sha256']==digest(PROJECT/'config.toml')
    assert options['foot_y_degrees']=={'l_foot':20.,'r_foot':-20.}
    assert options['stable_grip_pole'] is True and options['grip_soft_distance']==.008
    assert animation_ids == {int(r['id']) for r in build['animations']}
    assert len(animation_ids) == build['expected_animations']
    assert len(avatar.transforms) == profile['expectedAvatarNodes']
    units = []
    for patch in main_patches(PROJECT / 'models-o3'):
        for row in records(patch):
            assert row[1] != STATE_MACHINE_TYPE_ID, 'Model patch contains StateMachine'
            if row[1] == UNIT_TYPE_ID:
                unit = UnitData.parse(payload(patch, row))
                units.append((f'{row[0]:016x}', unit))
    assert len(units) == 17, 'O-3 mapping must retain 11 replacements and 6 hidden Units'
    by_id = dict(units)
    layouts = profile['modelLayouts']
    for slot, targets in profile['targets'].items():
        for target in targets:
            unit, layout = by_id[target], layouts[target]
            assert len(unit.transforms) == layout['nodeCount'], (slot, target)
            for signature in layout['signature']:
                assert unit.name_hashes[signature['index']] == signature['hash'], target
    material = PROJECT / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_1'
    for suffix in ('', '.gpu_resources'):
        assert digest(str(material) + suffix) == digest(str(BASE / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_1') + suffix)
    return dict(avatarNodes=len(avatar.transforms), animationChannels=len(bones.names),
                animations=len(animation_ids), companionPatches=1, modelUnits=len(units),
                modelNodeCounts=dict(collections.Counter(len(u.transforms) for _, u in units)),
                sourceBones=len(manifest['bones']), modelStateMachineEntries=0,
                modelScale=manifest['modelScale'], scaleOrigin=manifest['scaleOrigin'],
                footLocalYDegrees=options['foot_y_degrees'],stableGripPole=True,gripSoftDistanceMetres=options['grip_soft_distance'],
                materialsUnchanged=True, physicsBones=sum(bool(b.get('physics')) for b in manifest['bones']),
                attachmentProfiles=dict(native=29, vpk=29,
                    sourceAnchored=sum(r['policy'] in ('source-reference', 'source-blended-reference') for r in profile['vpk']),
                    modelLayouts=len(layouts)))


def runtime_modules():
    """Find local Python dependencies of the shipped entry points via AST."""
    visited = set()
    pending = ['__init__', 'main', 'cli', 'native_skeleton']
    while pending:
        name = pending.pop()
        source = ROOT.parent / (name + '.py')
        if name in visited or not source.is_file():
            continue
        visited.add(name)
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ''
                if node.level or module.startswith('anim_batch_mod.'):
                    candidate = module.removeprefix('anim_batch_mod.').split('.')[0]
                    if candidate:
                        pending.append(candidate)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith('anim_batch_mod.'):
                        pending.append(alias.name.split('.')[1])
    return sorted(name + '.py' for name in visited)


def audit_runtime():
    manager = WORK / 'manager'
    required = ['HD2ModManager.exe', 'HD2ModManager.dll', 'HD2ModManager.deps.json',
                'HD2ModManager.runtimeconfig.json', 'hd2mod.exe', 'hd2mod.dll',
                'hd2mod.deps.json', 'hd2mod.runtimeconfig.json', 'HD2ModCore.dll',
                'HD2ModAdaptation.dll', 'HD2SourceMigration.dll',
                'anim_batch_mod/runtime/python.exe', 'anim_batch_mod/runtime/python311.zip']
    rows = []
    for relative in required:
        path = manager / relative
        assert path.is_file() and path.stat().st_size, relative
        if path.suffix in ('.exe', '.dll'):
            with path.open('rb') as f:
                assert f.read(2) == b'MZ', relative
        rows.append(dict(path=relative, bytes=path.stat().st_size, sha256=digest(path)))
    modules = runtime_modules()
    for name in modules:
        published, source = manager / 'anim_batch_mod' / name, ROOT.parent / name
        assert digest(published) == digest(source), f'Published Python differs: {name}'
        rows.append(dict(path='anim_batch_mod/' + name, bytes=published.stat().st_size, sha256=digest(published)))
    for args in ([str(manager / 'hd2mod.exe'), '--help'],
                 [str(manager / 'anim_batch_mod/runtime/python.exe'), '-X', 'utf8',
                  str(manager / 'anim_batch_mod/main.py'), 'native-project', '--help']):
        result = subprocess.run(args, cwd=manager, capture_output=True, timeout=60)
        assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    result = dict(status='PASS', files=rows, pythonModules=modules, cliHelp=True, nativeProjectHelp=True)
    save_json(WORK / 'runtime-layout-audit.json', result)
    return result


def archive(name, items):
    WORK.mkdir(parents=True, exist_ok=True)
    target = WORK / name
    temporary = target.with_suffix('.zip.tmp')
    seen = set()
    fingerprints = {}
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path, relative in items:
            key = relative.as_posix()
            assert not relative.is_absolute() and '..' not in relative.parts
            assert key.casefold() not in seen, key
            seen.add(key.casefold())
            fingerprints[key] = digest(path)
            z.write(path, key)
    assert seen, name
    with zipfile.ZipFile(temporary) as z:
        assert z.testzip() is None, name
    temporary.replace(target)
    row = dict(name=name, bytes=target.stat().st_size, sha256=digest(target), inputs=fingerprints)
    print('verified ZIP', name, row['bytes'], flush=True)
    return row


def unchanged_inputs(row, items):
    assert row['inputs'] == {relative.as_posix(): digest(path) for path, relative in items}, f"Package inputs changed: {row['name']}"


def static():
    audit_runtime()
    lua = (PROJECT / 'physics-runtime/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig')
    for name in ('physbone_compat.lua', 'physbone_runtime.lua', 'native_attachments.lua', 'native_attachment_profile.lua'):
        assert (ROOT / 'HD2PhysBoneCompat/src' / name).read_text(encoding='utf-8-sig') in lua, name
    rows = [archive('test01-模型材质.zip', files(PROJECT / 'models-o3')),
            archive('test01-物理运行时-v9.zip', files(PROJECT / 'physics-runtime/patch版')),
            archive('HD2ModManager-原生骨架测试版.zip', files(WORK / 'manager', 'manager'))]
    save_json(WORK / 'static-packages.json', rows)


def animation():
    build = load(PROJECT / 'animations/build-report.json')
    assert build['status'] == 'complete' and len(build['animations']) == build['expected_animations']
    assert len(main_patches(PROJECT / 'animations/runtime')) == 1
    for row in build['files']:
        path = PROJECT / 'animations' / row['path']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], row['path']
    row = archive('test01-配套动画.zip', files(PROJECT / 'animations/runtime'))
    save_json(WORK / 'animation-package.json', dict(file=row, buildFiles=build['files']))


def validate_animation_runtime():
    build = load(PROJECT / 'animations/build-report.json')
    assert build['status'] == 'complete'
    rows = [r for r in build['files'] if Path(r['path']).parts[0] == 'runtime']
    assert len(rows) == 3, 'Expected one animation patch and both companions'
    for row in rows:
        path = (PROJECT / 'animations' / row['path']).resolve()
        assert path.is_relative_to((PROJECT / 'animations/runtime').resolve())
        assert GENERATED_PATCH.fullmatch(path.name)
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], row['path']
    expected = {Path(r['path']).name for r in rows}
    main = [name for name in expected if re.fullmatch(r'9ba626afa44a3aa3\.patch_\d+', name)]
    assert len(main) == 1 and expected == {main[0], main[0]+'.gpu_resources', main[0]+'.stream'}
    assert {p.name for p in (PROJECT / 'animations/runtime').iterdir() if p.is_file() and GENERATED_PATCH.fullmatch(p.name)} == expected


def collect_sources():
    source = PROJECT / 'source-code'
    for path in ROOT.parent.glob('*.py'):
        target = source / 'anim_batch_mod' / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        # Older deliveries also exposed flat source files. Refresh those known
        # aliases so opening the established path cannot display stale v6 code.
        shutil.copy2(path, source / path.name)
    for folder in ('HD2PhysBoneCompat/src', 'HD2PhysBoneCompat/test'):
        for path, relative in files(ROOT / folder):
            target = source / folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if folder.endswith('/src') and path.suffix == '.lua':
                shutil.copy2(path, source / path.name)
    for path in (ROOT / 'tools').glob('*.py'):
        if 'native_v9' in path.name or path.name == 'native_attachment_layouts.py':
            target = source / 'tools' / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    relatives = ('HD2SourceMigration/Retarget/NativeSourceSkeleton.cs', 'HD2SourceMigration/VpkConversion/PhysBoneRigSidecar.cs',
        'HD2ModManager/Services/NativeSkeletonProjectService.cs', 'HD2ModAdaptation/PatchReconstruction/PatchTocScanner.cs',
        'HD2ModCore/Infrastructure/PatchTocScanner.cs', 'HD2ModAdaptation/PatchReconstruction/PatchArchiveWriter.cs',
        'HD2ModAdaptation/PatchReconstruction/PatchSubsetWriter.cs', 'HD2ModAdaptation/PatchReconstruction/PatchWorkspace/PatchWorkspaceReader.cs',
        'HD2ModCli/CliApplication.cs', 'HD2ModCore/Infrastructure/PhysBoneLuaSource.cs', 'HD2ModCore/HD2ModCore.csproj',
        'tools/BuildNativeRuntime.ps1', 'HD2ModManager/HD2ModManager.csproj', 'tools/NativeReleaseTools/Program.cs',
        'tools/NativeReleaseTools/NativeReleaseTools.csproj', 'HD2SourceMigration.Tests/NativeSourceSkeletonTests.cs',
        'HD2SourceMigration/VpkConversion/UnitTransformInfoAppender.cs', 'HD2SourceMigration.Tests/UnitTransformInfoAppenderTests.cs')
    for relative in relatives:
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        legacy = source / 'changed-files' / relative
        legacy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, legacy)
        if Path(relative).name in ('NativeSourceSkeleton.cs', 'NativeSkeletonProjectService.cs', 'PhysBoneRigSidecar.cs'):
            shutil.copy2(ROOT / relative, source / Path(relative).name)
    shutil.copy2(ROOT / 'HD2ModAdaptation/PatchReconstruction/PatchTocScanner.cs', source / 'PatchTocScanner.cs')
    (source / 'README.txt').write_text(
        'v9 production source is under anim_batch_mod/, HD2SourceMigration/, HD2ModCore/ and HD2PhysBoneCompat/.\n'
        'Known flat and changed-files aliases are refreshed to the same v9 source for compatibility.\n'
        'Older version-named audit/build scripts retained from earlier deliveries are historical; use the delivered manager and project/Rebuild-Animations.ps1 for rebuilding.\n'
        'v9 adds Source arm pole continuity, soft reach, configurable foot Y rotation, hidden-armor filtering and independent equipment graph refresh. Live grip acceptance remains pending. See ../reports/current-v9/grip-validation-summary.json.\n', encoding='utf-8')
    shutil.copy2(ROOT / 'tools/Rebuild-Native-v9-Animations.ps1', PROJECT / 'Rebuild-Animations.ps1')


def bone_names():
    manifest = load(PROJECT / 'source-skeleton.json')
    rows = manifest['bones']
    names = PROJECT / 'bone-names'
    names.mkdir(exist_ok=True)
    (names / 'test01-custom-bonehash.txt').write_text(''.join(f"{b['hash']} {b['name']}\n" for b in rows), encoding='utf-8')
    with (names / 'source-bone-map.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['SourceIndex', 'VPKName', 'NormalizedName', 'HashDecimal', 'ParentSourceIndex', 'Driver', 'Physics'])
        for b in rows:
            parent_source = None if b['parent'] is None else rows[b['parent']]['sourceIndex']
            writer.writerow([b['sourceIndex'], b['sourceName'], b['name'], b['hash'], parent_source, b['driver'], b.get('physics', False)])
    assert len(rows) == 89
    shutil.copy2(ROOT / 'tools/blender_native_v9_bone_names.py', names / 'blender_native_v9_bone_names.py')


def prepare():
    validation = WORK / 'release-validation.json'
    required = load(validation)['requiredReports'] if validation.exists() else DEFAULT_AUDITS
    audits = {}
    grip_status = None
    for name in required:
        path = (WORK / name).resolve()
        assert path.is_relative_to(WORK.resolve()), name
        report = load(path)
        if name == 'grip-validation-audit.json':
            assert report.get('validationStatus') == 'COMPLETE', name
            grip_status = report.get('gripStatus')
            assert isinstance(grip_status, str) and grip_status, 'Missing explicit grip validation outcome'
        else:
            assert report['status'] == 'PASS', name
        audits[name] = digest(path)
    assert 'fusion-layer-audit.json' in required or any('fusion' in n or 'motion' in n or 'mask' in n for n in required), 'Missing fusion validation'
    structure = facts()
    runtime = audit_runtime()
    reports = PROJECT / 'reports/current-v9'
    reports.mkdir(parents=True, exist_ok=True)
    for path in WORK.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log', '.trx') and path.name not in ('package-report.json', 'delivery-verification.json'):
            shutil.copy2(path, reports / path.name)
    for relative in ('armor-audit/layout-runtime-final.json', 'armor-audit/avatar-final.toc', 'deployment-readonly-recheck.json', 'unit-anim-reference.toc', 'native-skeleton-v9.diff'):
        source = WORK / relative
        assert source.is_file(), f'Missing final audit evidence: {relative}'
        target = reports / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    collect_sources()
    bone_names()
    doc = ROOT / 'docs/native-v9-20261104.md'
    if not doc.exists():
        doc = ROOT / 'docs/native-v9-delivery-guide.md'
    for name in ('先读我.txt', '修正说明.md', '挂点配置.md'):
        shutil.copy2(doc, PROJECT / name)
    rows = load(WORK / 'static-packages.json')
    for row in rows:
        assert digest(WORK / row['name']) == row['sha256'], row['name']
    unchanged_inputs(rows[0], files(PROJECT / 'models-o3'))
    unchanged_inputs(rows[1], files(PROJECT / 'physics-runtime/patch版'))
    unchanged_inputs(rows[2], files(WORK / 'manager', 'manager'))
    cached = load(WORK / 'animation-package.json')
    assert cached['buildFiles'] == load(PROJECT / 'animations/build-report.json')['files']
    assert digest(WORK / cached['file']['name']) == cached['file']['sha256']
    unchanged_inputs(cached['file'], files(PROJECT / 'animations/runtime'))
    rows.extend([cached['file'], archive('test01-源工程.zip', project_files())])
    chef = load(WORK / 'chef-compatibility-audit.json')
    report = dict(status='offline-verified', revision='native-v9', armor='O-3 自由之魂',
                  luaVersion=chef['runtimeVersion'], gameDeployed=False, gameTested=False,
                  audits=audits, runtimeLayout=runtime, **structure, files=rows,
                  gripStatus=grip_status or 'NOT_INCLUDED_IN_REQUIRED_REPORTS',
                  gripValidationStatus='COMPLETE' if grip_status else 'NOT_INCLUDED_IN_REQUIRED_REPORTS',
                  gripGameValidation='Procedural aim and attachment consumer timing require in-game validation')
    save_json(WORK / 'package-report.json', report)


def deliver():
    from verify_native_v9_delivery import snapshot, verify_preserved
    report = load(WORK / 'package-report.json')
    assert report['revision'] == 'native-v9' and not report['gameDeployed'] and not report['gameTested']
    assert load(WORK / 'package-inspection.json')['status'] == 'PASS'
    for name, expected in report['audits'].items():
        assert digest(WORK / name) == expected, f'Validation report changed: {name}'
    validate_animation_runtime()
    backup = RELEASE / 'backups/before-native-v9-20261104'
    backup.mkdir(parents=True, exist_ok=True)
    snapshot()
    changed, obsolete, preserved = [], [], []

    def back_up(target):
        target = target.resolve()
        assert target.is_relative_to(RELEASE.resolve()) and not target.is_relative_to(backup.resolve())
        if target.exists():
            assert target.is_file(), target
            stored = backup / target.relative_to(RELEASE)
            if not stored.exists():
                stored.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, stored)
                assert digest(stored) == digest(target)
        return target

    def replace(source, target):
        target = back_up(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        assert digest(source) == digest(target)
        changed.append(target.relative_to(RELEASE).as_posix())

    for row in report['files']:
        source = WORK / row['name']
        assert digest(source) == row['sha256'], row['name']
        replace(source, RELEASE / row['name'])
    if (WORK / 'conversion.json').exists():
        replace(WORK / 'conversion.json', RELEASE / 'conversion.json')
    for path, relative in project_files(include_animation_runtime=True):
        replace(path, RELEASE / 'project' / relative)
    for path, relative in files(WORK / 'manager'):
        for folder in ('manager', 'test'):
            target = RELEASE / folder / relative
            if relative.parts[0] in PROTECTED and target.exists():
                preserved.append(target.relative_to(RELEASE).as_posix())
                continue
            replace(path, target)
    generated_patch_sets = {}
    for folder in GENERATED_PATCH_FOLDERS:
        expected = {p.name for p, _ in files(PROJECT / folder) if GENERATED_PATCH.fullmatch(p.name)}
        assert expected, f'Missing generated patch input: {folder}'
        generated_patch_sets[folder] = sorted(expected)
        for path in (RELEASE / 'project' / folder).iterdir():
            if path.is_file() and GENERATED_PATCH.fullmatch(path.name) and path.name not in expected:
                back_up(path).unlink()
                obsolete.append(path.relative_to(RELEASE).as_posix())
    for path in RELEASE.glob('test01-物理运行时*.zip'):
        if path.name != 'test01-物理运行时-v9.zip':
            back_up(path).unlink()
            obsolete.append(path.relative_to(RELEASE).as_posix())
    doc = PROJECT / '修正说明.md'
    for relative in ('先读我-人工测试.txt', '转换原理与验证.md', 'test/先读我-修复测试.txt'):
        replace(doc, RELEASE / relative)
    report.update(backup=str(backup), updatedFiles=len(changed), removedObsoleteFiles=obsolete,
                  preservedLocalFiles=preserved,
                  deliveredProjectFiles={r.as_posix(): digest(p) for p, r in project_files(include_animation_runtime=True)},
                  generatedPatchFiles=generated_patch_sets,
                  deliveredManagerFiles={r.as_posix(): digest(p) for p, r in files(WORK / 'manager')})
    save_json(WORK / 'package-report.json', report)
    replace(WORK / 'package-report.json', RELEASE / 'package-report.json')
    save_json(backup / 'backup-log.json', dict(replaced=changed, obsolete=obsolete, preserved=preserved))
    verify_preserved()
    print('Delivered v9 with verified backup:', backup, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['--static', '--animation', '--prepare', '--deliver', '--facts', '--runtime'])
    # Preserve the established --phase invocation while retaining useful --help.
    if len(sys.argv) == 2 and sys.argv[1] in ('--static', '--animation', '--prepare', '--deliver', '--facts', '--runtime'):
        {'--static': static, '--animation': animation, '--prepare': prepare, '--deliver': deliver,
         '--facts': lambda: print(json.dumps(facts(), ensure_ascii=False, indent=2)), '--runtime': audit_runtime}[sys.argv[1]]()
    else:
        parser.parse_args()
