"""Repack the delivered B7 Lua using its saved container header and manifest.

Copy this script with hd2physbone-B7.lua, container-header.bin, manifest.json
and 测试说明.txt. Uses only Python's standard library; writes under rebuilt/.
"""
import hashlib
import json
import struct
import zipfile
from pathlib import Path


def build(root):
    root=Path(root).resolve()
    body=(root/'hd2physbone-B7.lua').read_bytes()
    header=(root/'container-header.bin').read_bytes()
    assert len(header)==192 and struct.unpack_from('<I',header)[0]==0xf0000011
    assert struct.unpack_from('<Q',header,120)[0]==192
    payload=struct.pack('<II',len(body),2)+body
    data=bytearray(header)+payload;data.extend(bytes(-len(data)%16))
    struct.pack_into('<Q',data,32,len(data));struct.pack_into('<I',data,160,len(payload))
    out=root/'rebuilt';out.mkdir(exist_ok=True)
    name='9ba626afa44a3aa3.patch_0'
    with zipfile.ZipFile(out/'B7-补齐切分部位刷新.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr(name,data)
        z.writestr(name+'.stream',b'');z.writestr(name+'.gpu_resources',b'')
        z.write(root/'manifest.json','manifest.json');z.write(root/'测试说明.txt','测试说明.txt')
    with zipfile.ZipFile(out/'B7-补齐切分部位刷新.zip') as z:assert z.testzip() is None
    result=dict(status='PASS',patchSha256=hashlib.sha256(data).hexdigest(),sourceSha256=hashlib.sha256(body).hexdigest())
    (out/'repack-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':print(json.dumps(build(Path(__file__).parent),indent=2))
