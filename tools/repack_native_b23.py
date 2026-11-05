"""Rebuild the delivered B23 patch with standard Python after editing its Lua."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path

ADDON_RESOURCE = 0xcfdf231bc0803b9d


def parenting_file(root, item):
    # Installable projects keep both patch groups at the root so the manager
    # imports one complete node. Retain support for the archived source layout.
    candidates = [root / item['name'], root / 'native-parenting' / item['name']]
    existing = [path for path in candidates if path.is_file()]
    assert existing, 'Missing parenting companion: ' + item['name']
    for path in existing:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'Parenting companion changed'
    return existing[0]


def build(root):
    root = Path(root).resolve()
    output = root / 'rebuilt'
    output.mkdir(exist_ok=True)
    body = (root / 'hd2attachmentfix-B23.lua').read_bytes()
    header = (root / 'container-header.bin').read_bytes()
    assert body.startswith(b'-- HD2-Addon: mods/hd2modmanager/attachment_fix\n')
    assert len(header) == 192 and struct.unpack_from('<I', header)[0] == 0xf0000011
    assert struct.unpack_from('<Q', header, 120)[0] == 192
    assert struct.unpack_from('<Q', header, 104)[0] == ADDON_RESOURCE
    payload = struct.pack('<II', len(body), 2) + body
    patch = bytearray(header) + payload
    patch.extend(bytes(-len(patch) % 16))
    struct.pack_into('<Q', patch, 32, len(patch))
    struct.pack_into('<I', patch, 160, len(payload))
    name = '9ba626afa44a3aa3.patch_4'
    profile_path = root / 'B23-profile.json'
    profile = json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else None
    left = profile is not None and profile.get('leftGrip', {}).get('enabled')
    rig_path=root/'native-parenting.json'
    rig=json.loads(rig_path.read_text(encoding='utf-8')) if rig_path.exists() else None
    if profile is not None and profile.get('bodySync',{}).get('enabled'):
        assert rig is not None,'B23 native-parent outputs require their paired Avatar/Bones patch'
    multi = left and 'weaponTargets' in profile.get('leftGrip',{})
    companions = [parenting_file(root, item) for item in rig['files']] if rig else []
    package_name = (profile or {}).get('packageName') or ('B23LR-M-多武器动态原生握持测试.zip' if multi else
        'B23-LR-动态原生握持挂点测试.zip' if left else 'B23-R-动态原生握持挂点测试.zip')
    assert Path(package_name).name == package_name and package_name.endswith('.zip'), 'Invalid package filename'
    package = output / package_name
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(name, patch)
        archive.writestr(name + '.stream', b'')
        archive.writestr(name + '.gpu_resources', b'')
        archive.write(root / 'manifest.json', 'manifest.json')
        archive.write(root / '测试说明.md', '测试说明.md')
        for file in companions:
            archive.write(file,file.name)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
    installable_project = (root / name).is_file()
    if installable_project:
        # Reimporting an edited flat project must not silently use stale Lua.
        (root / name).write_bytes(patch)
        for suffix in ('.stream', '.gpu_resources'):
            (root / (name + suffix)).write_bytes(b'')
    result = dict(status='PASS', sourceSha256=hashlib.sha256(body).hexdigest(),
        patchSha256=hashlib.sha256(patch).hexdigest(), gameDeployed=False,
        installableProjectPayloadUpdated=installable_project,
        scope='Container rebuilt only; edited Lua requires its own syntax/runtime validation')
    (output / 'repack-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    print(json.dumps(build(Path(__file__).parent), indent=2))
