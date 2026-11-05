"""Compare a standalone Avatar mesh with the composite-backed vanilla Unit."""
import copy
import argparse
import hashlib
import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID, TOC_MAGIC
from anim_batch_mod.formats import UnitData

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expanded',action='store_true');args=parser.parse_args()
    probe='C7' if args.expanded else 'C6'
    work=ROOT/'outputs/native-v13-20261104'
    source=ROOT.parent/'unit_anim/9ba626afa44a3aa3.patch_0'
    archive=TocArchive.parse_parts(source.read_bytes(),Path(str(source)+'.gpu_resources').read_bytes(),Path(str(source)+'.stream').read_bytes())
    entry=copy.deepcopy(archive.entries[0x4d1c334d294dfa97,UNIT_TYPE_ID])
    original=(work/'vanilla-avatar.toc').read_bytes()
    unit=UnitData.parse(original);standalone=UnitData.parse(entry.toc_data)
    assert len(unit.transforms)==len(standalone.transforms)==107
    assert unit.name_hashes==standalone.name_hashes and unit.parents==standalone.parents
    assert struct.unpack_from('<Q',entry.toc_data,16)[0]==0
    assert entry.gpu_data and not entry.stream_data
    old_offset=struct.unpack_from('<I',original,52)[0]
    at=struct.unpack_from('<I',entry.toc_data,52)[0]
    size=16+136*107
    # Make the original rest graph bit-identical, independent of SDK rounding.
    entry.toc_data[at:at+size]=original[old_offset:old_offset+size]
    assert UnitData.parse(entry.toc_data).transforms==unit.transforms
    (work/'standalone-avatar.toc').write_bytes(entry.toc_data)
    (work/'standalone-avatar.gpu').write_bytes(entry.gpu_data)
    if args.expanded:
        from anim_batch_mod.native_skeleton import append_unit, load_manifest
        entry.toc_data=bytearray(append_unit(entry.toc_data,load_manifest(work/'project/source-skeleton.json')))
        expanded=UnitData.parse(entry.toc_data)
        assert len(expanded.transforms)==255 and expanded.transforms[:107]==unit.transforms
        assert expanded.name_hashes[:107]==unit.name_hashes and expanded.parents[:107]==unit.parents
    entry.unknown1=entry.unknown2=0
    dest=work/'preview-probe'/probe;dest.mkdir(parents=True,exist_ok=True)
    data=bytearray(192)+entry.toc_data;data.extend(bytes(-len(data)%16))
    struct.pack_into('<III',data,0,TOC_MAGIC,1,1)
    struct.pack_into('<Q',data,32,len(data))
    struct.pack_into('<QQQII',data,72,0,UNIT_TYPE_ID,1,16,64)
    struct.pack_into('<QQQQQQQIIIIII',data,104,entry.file_id,UNIT_TYPE_ID,192,0,0,0,0,len(entry.toc_data),0,len(entry.gpu_data),16,64,1)
    patch=dest/'9ba626afa44a3aa3.patch_0';patch.write_bytes(data)
    Path(str(patch)+'.gpu_resources').write_bytes(entry.gpu_data)
    Path(str(patch)+'.stream').write_bytes(b'')
    parsed=TocArchive.parse_parts(data,entry.gpu_data)
    assert len(parsed.entries)==1 and parsed.entries[entry.file_id,entry.type_id].toc_data==entry.toc_data
    assert parsed.entries[entry.file_id,entry.type_id].gpu_data==entry.gpu_data
    (dest/'manifest.json').write_text(json.dumps(dict(Version=1,Guid=('c7747377-7c22-4760-bd79-4b9d666d1c07' if args.expanded else 'c6747377-7c22-4760-bd79-4b9d666d1c06'),
        Name=f'test01 {probe} 独立网格 Avatar 对照',Description=('扩展为255节点，独立网格；测试后停用。' if args.expanded else '仅原版107节点和独立网格；测试后停用。')),ensure_ascii=False,indent=2),encoding='utf-8')
    (dest/'测试说明.txt').write_text(f'保持 B3，停用配套动画及其他 C 系列，仅启用 {probe}，部署并重启，查看同一原版头盔和盔甲预览。\n'
        '本包沿用 unit_anim 的独立 Avatar 网格封装和 GPU 数据，107 个节点的绑定数据逐字节恢复为原版。\n'
        +('本 C7 在 C6 基础上仅扩展为255个节点。\n' if args.expanded else '')+
        f'不包含 Bones、状态机、动画和 Lua。完成后停用 {probe}。\n',encoding='utf-8')
    output=work/f'{probe}-独立网格Avatar预览对照.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for path in dest.iterdir():z.write(path,path.name)
    with zipfile.ZipFile(output) as z:assert z.testzip() is None
    delivery=ROOT/'outputs/native-manual-20261103/AB测试'/output.name
    if not args.expanded:shutil.copy2(output,delivery)
    report=dict(status='OFFLINE_VERIFIED',gameTested=False,resources=1,animations=0,nodes=255 if args.expanded else 107,
        originalTransformInfoByteIdentical=True,source=str(source),compositeRef=0,gpuBytes=len(entry.gpu_data),
        package=str(output if args.expanded else delivery),sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (work/f'preview-probe-{probe}-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
