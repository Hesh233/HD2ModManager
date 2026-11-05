"""Verify all delivered bytes and preserve both managers' local state exactly."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from package_native_v7 import WORK, RELEASE, PROTECTED, GENERATED_PATCH, digest, files, load, save_json

SNAPSHOT = WORK / 'delivery-settings-before.json'


def local_files():
    for folder in ('manager', 'test'):
        root = RELEASE / folder
        if not root.exists():
            continue
        for path, relative in files(root):
            if relative.parts[0] in PROTECTED:
                yield path, (Path(folder) / relative).as_posix()


def snapshot():
    current = {relative: digest(path) for path, relative in local_files()}
    if SNAPSHOT.exists():
        before = load(SNAPSHOT)
        for relative, expected in before.items():
            assert current.get(relative) == expected, f'Local setting changed since snapshot: {relative}'
    else:
        save_json(SNAPSHOT, current)
    print(f'Preserving {len(current)} existing manager/test local files', flush=True)


def verify_preserved():
    before = load(SNAPSHOT)
    for relative, expected in before.items():
        assert digest(RELEASE / relative) == expected, f'Local setting was changed: {relative}'
    return len(before)


def verify():
    report = load(RELEASE / 'package-report.json')
    assert report['revision'] == 'native-v7' and not report['gameDeployed'] and not report['gameTested']
    for row in report['files']:
        path = RELEASE / row['name']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], row['name']
    count = 0
    for relative, expected in report['deliveredProjectFiles'].items():
        assert digest(RELEASE / 'project' / relative) == expected, relative
        count += 1
    build = load(RELEASE / 'project/animations/build-report.json')
    runtime_files = [r for r in build['files'] if Path(r['path']).parts[0] == 'runtime']
    assert len(runtime_files) == 3, 'Expected the final animation patch and both companions'
    for row in runtime_files:
        relative = Path('animations') / row['path']
        path = RELEASE / 'project' / relative
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], relative
        assert report['deliveredProjectFiles'][relative.as_posix()] == row['sha256'], relative
    for folder, expected in report['generatedPatchFiles'].items():
        actual = {p.name for p in (RELEASE / 'project' / folder).iterdir() if p.is_file() and GENERATED_PATCH.fullmatch(p.name)}
        assert actual == set(expected), f'Stale or missing generated patch: {folder}'
    backup = Path(report['backup'])
    for relative in report['removedObsoleteFiles']:
        assert not (RELEASE / relative).exists() and (backup / relative).is_file(), relative
    preserved = set(report['preservedLocalFiles'])
    for relative, expected in report['deliveredManagerFiles'].items():
        for folder in ('manager', 'test'):
            if folder + '/' + relative not in preserved:
                assert digest(RELEASE / folder / relative) == expected, folder + '/' + relative
                count += 1
    local_count = verify_preserved()
    for path in RELEASE.glob('test01-物理运行时*.zip'):
        assert path.name == 'test01-物理运行时-v7.zip', path
    result = dict(status='PASS', revision='native-v7', zipCount=len(report['files']),
                  verifiedProjectAndManagerFiles=count, preservedLocalFiles=local_count,
                  managerSettingsPreserved=True, testSettingsPreserved=True,
                  finalAnimationRuntimeMatchesBuildReport=True, obsoleteGeneratedPatchesRemoved=True,
                  gameDeployed=False, gameTested=False)
    for path in (WORK / 'delivery-verification.json', RELEASE / 'delivery-verification.json'):
        save_json(path, result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('--snapshot', '--verify'):
        raise SystemExit('Usage: python verify_native_v7_delivery.py --snapshot|--verify')
    {'--snapshot': snapshot, '--verify': verify}[sys.argv[1]]()
