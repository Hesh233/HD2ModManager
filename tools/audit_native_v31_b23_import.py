"""Import the B23-LR-M test packages into disposable manager roots; never deploy."""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, save_json, digest
from prepare_native_v31_b23 import W
import audit_native_v16_import as importer

importer.W = W


def audit_project_package(package, output, require_project_source=True):
    """Exercise the project ZIP itself, not just its separate runtime ZIP."""
    package, output = Path(package).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    patch_pattern = re.compile(r'[0-9a-f]{16}\.patch_\d+(?:\.(?:stream|gpu_resources))?$')
    expected = {f'9ba626afa44a3aa3.patch_{number}{suffix}'
                for number in (4, 5) for suffix in ('', '.stream', '.gpu_resources')}
    with zipfile.ZipFile(package) as archive:
        payload = {name for name in archive.namelist() if patch_pattern.fullmatch(Path(name).name)}
        assert payload == expected, 'Project must have both complete patch groups at its root'
        if require_project_source or 'hd2attachmentfix-B23.lua' in archive.namelist():
            assert archive.read('hd2attachmentfix-B23.lua') in archive.read('9ba626afa44a3aa3.patch_4')
        else:
            assert b'-- HD2-Addon: mods/hd2modmanager/attachment_fix' in archive.read('9ba626afa44a3aa3.patch_4')
    local_package = output / package.name
    if local_package != package:
        shutil.copy2(package, local_package)
    save_json(output / 'static-packages.json', [dict(name=local_package.name, sha256=digest(local_package))])
    previous = importer.W
    try:
        importer.W = output
        importer.main(exe=W/'manager-1.0.7/hd2mod.exe')
    finally:
        importer.W = previous
    inspection = json.loads((output / 'package-inspection.json').read_text(encoding='utf-8'))
    library = Path(inspection['sandbox']) / '0/library'
    mains = [p for p in library.rglob('*') if p.is_file() and re.fullmatch(r'[0-9a-f]{16}\.patch_\d+', p.name)]
    assert len(mains) == 2 and len({p.parent for p in mains}) == 1, 'Imported project split or empty'
    with zipfile.ZipFile(package) as archive:
        expected_hashes = {hashlib.sha256(archive.read(name)).hexdigest() for name in expected}
    actual_hashes = {digest(p) for p in library.rglob('*') if p.is_file() and patch_pattern.fullmatch(p.name)}
    assert expected_hashes == actual_hashes, 'Imported payload changed'
    result = dict(status='PASS', package=str(package), packageSha256=digest(package),
        topLevelPatchGroups=2, importedPayloadDirectories=1, allPayloadBytesPreserved=True,
        importedLuaSha256=next(digest(p) for p in mains if b'-- HD2-Addon: mods/hd2modmanager/attachment_fix' in p.read_bytes()),
        isolatedImportReport=str(output / 'package-inspection.json'), gameDeployed=False, gameTested=False)
    save_json(output / 'installable-project-audit.json', result)
    return result


if __name__ == '__main__':
    try:
        importer.main(exe=W/'manager-1.0.7/hd2mod.exe')
    except Exception as error:
        save_json(importer.W / 'package-inspection.json', dict(status='FAIL', error=str(error), gameDeployed=False))
        raise
