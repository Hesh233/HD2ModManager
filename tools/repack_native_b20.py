"""Reproduce B20 patches using only standard Python, from this source bundle."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path


def build(root):
    root = Path(root).resolve()
    output = root / 'rebuilt'
    output.mkdir(exist_ok=True)
    variants = {}
    for variant in ('R', 'A', 'H', 'T'):
        folder = root / 'variants' / variant
        body = (folder / 'hd2physbone.lua').read_bytes()
        header = (folder / 'container-header.bin').read_bytes()
        assert len(header) == 192 and struct.unpack_from('<I', header)[0] == 0xf0000011
        assert struct.unpack_from('<Q', header, 120)[0] == 192
        payload = struct.pack('<II', len(body), 2) + body
        data = bytearray(header) + payload
        data.extend(bytes(-len(data) % 16))
        struct.pack_into('<Q', data, 32, len(data))
        struct.pack_into('<I', data, 160, len(payload))
        name = '9ba626afa44a3aa3.patch_0'
        package = output / ('B20-' + variant + '.zip')
        with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(name, data)
            archive.writestr(name + '.stream', b'')
            archive.writestr(name + '.gpu_resources', b'')
            archive.write(folder / 'manifest.json', 'manifest.json')
            archive.write(root / '测试说明.txt', '测试说明.txt')
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None
        variants[variant] = dict(patchSha256=hashlib.sha256(data).hexdigest(), sourceSha256=hashlib.sha256(body).hexdigest())
    result = dict(status='PASS', variants=variants)
    (output / 'repack-report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    print(json.dumps(build(Path(__file__).parent), indent=2))
