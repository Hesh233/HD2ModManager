"""Reproduce the standalone B21 patch using only standard Python."""
import hashlib
import json
import struct
from pathlib import Path
import zipfile

ADDON_RESOURCE = 0xaf6cc767304a995d


def build(root):
    root = Path(root).resolve()
    output = root / 'rebuilt'
    output.mkdir(exist_ok=True)
    body = (root / 'native-grip-capture.lua').read_bytes()
    header = (root / 'container-header.bin').read_bytes()
    assert body.startswith(b'-- HD2-Addon: mods/hd2modmanager/native_grip_capture\n')
    assert len(header) == 192 and struct.unpack_from('<I', header)[0] == 0xf0000011
    assert struct.unpack_from('<Q', header, 120)[0] == 192
    assert struct.unpack_from('<Q', header, 104)[0] == ADDON_RESOURCE
    payload = struct.pack('<II', len(body), 2) + body
    data = bytearray(header) + payload
    data.extend(bytes(-len(data) % 16))
    struct.pack_into('<Q', data, 32, len(data))
    struct.pack_into('<I', data, 160, len(payload))
    name = '9ba626afa44a3aa3.patch_0'
    package = output / 'B21-原生握持只读采集.zip'
    with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(name, data)
        archive.writestr(name + '.stream', b'')
        archive.writestr(name + '.gpu_resources', b'')
        archive.write(root / 'manifest.json', 'manifest.json')
        archive.write(root / '测试说明.txt', '测试说明.txt')
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
    result = dict(status='PASS', addonResource=f'{ADDON_RESOURCE:016x}',
        patchSha256=hashlib.sha256(data).hexdigest(), sourceSha256=hashlib.sha256(body).hexdigest(),
        gameDeployed=False, gamePoseCaptured=False)
    (output / 'repack-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    print(json.dumps(build(Path(__file__).parent), indent=2))
