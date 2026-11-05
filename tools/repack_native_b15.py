"""Reproduce the two B15 subset patches with standard Python."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path


def build(root):
    root=Path(root).resolve();reports={};out=root/'rebuilt';out.mkdir(exist_ok=True)
    for variant in ('A1','A2'):
        folder=root/'variants'/variant;body=(folder/'hd2physbone.lua').read_bytes()
        header=(folder/'container-header.bin').read_bytes()
        assert len(header)==192 and struct.unpack_from('<I',header)[0]==0xf0000011
        assert struct.unpack_from('<Q',header,120)[0]==192
        payload=struct.pack('<II',len(body),2)+body;data=bytearray(header)+payload;data.extend(bytes(-len(data)%16))
        struct.pack_into('<Q',data,32,len(data));struct.pack_into('<I',data,160,len(payload))
        name='9ba626afa44a3aa3.patch_0';package=out/('B15-'+variant+'.zip')
        with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
            z.writestr(name,data);z.writestr(name+'.stream',b'');z.writestr(name+'.gpu_resources',b'')
            z.write(folder/'manifest.json','manifest.json');z.write(root/'测试说明.txt','测试说明.txt')
        with zipfile.ZipFile(package)as z:assert z.testzip()is None
        reports[variant]=dict(patchSha256=hashlib.sha256(data).hexdigest(),sourceSha256=hashlib.sha256(body).hexdigest())
    result=dict(status='PASS',variants=reports)
    (out/'repack-report.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result


if __name__=='__main__':print(json.dumps(build(Path(__file__).parent),indent=2))
