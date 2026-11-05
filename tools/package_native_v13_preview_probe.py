"""Create a single-resource control for wardrobe preview diagnosis."""
import copy
import argparse
import hashlib
import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive, TocEntry
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from package_native_v10 import records, payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--relocate-only', action='store_true')
    parser.add_argument('--inline-expanded', action='store_true')
    parser.add_argument('--vanilla-only', action='store_true')
    parser.add_argument('--clean-container', action='store_true')
    parser.add_argument('--source-archive', action='store_true')
    args = parser.parse_args()
    assert sum((args.relocate_only,args.inline_expanded,args.vanilla_only)) <= 1
    assert not args.clean_container or args.vanilla_only
    assert not args.source_archive or args.clean_container
    probe = 'C5' if args.source_archive else 'C4' if args.clean_container else 'C0' if args.vanilla_only else 'C3' if args.inline_expanded else 'C2' if args.relocate_only else 'C1'
    title = '原归档路径Avatar对照' if args.source_archive else '标准容器原版Avatar对照' if args.clean_container else '原版Avatar原样封包对照' if args.vanilla_only else '原位扩展Avatar预览对照' if args.inline_expanded else '仅搬移原Avatar节点预览对照' if args.relocate_only else '仅扩展Avatar预览对照'
    work = ROOT / 'outputs/native-v13-20261104'
    reference = ROOT / 'outputs/native-v12-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'
    if not reference.exists():
        reference = ROOT / 'outputs/native-manual-20261103/project/animations/runtime/9ba626afa44a3aa3.patch_2'
    row = next(r for r in records(reference) if r[1] == UNIT_TYPE_ID)
    data = payload(reference, row)
    original_bytes = (ROOT / 'outputs/native-fix-20261103/avatar.toc').read_bytes()
    original = UnitData.parse(original_bytes)
    if args.vanilla_only:
        data = (work / 'vanilla-avatar.toc').read_bytes()
        assert data == original_bytes
    if args.relocate_only:
        offset = struct.unpack_from('<I', original_bytes, 52)[0]
        size = 16 + 136 * len(original.transforms)
        data = bytearray(original_bytes)
        data.extend(b'\0' * (-len(data) % 16))
        new_offset = len(data)
        data.extend(original_bytes[offset:offset + size])
        struct.pack_into('<I', data, 52, new_offset)
        assert data[:52] == original_bytes[:52]
        assert data[56:len(original_bytes)] == original_bytes[56:]
        assert data[new_offset:] == original_bytes[offset:offset + size]
    if args.inline_expanded:
        old_start = struct.unpack_from('<I', original_bytes, 52)[0]
        old_end = (old_start + 16 + 136 * len(original.transforms) + 15) & ~15
        expanded_start = struct.unpack_from('<I', data, 52)[0]
        expanded_count = struct.unpack_from('<I', data, expanded_start)[0]
        block = bytearray(data[expanded_start:expanded_start + 16 + 136 * expanded_count])
        block.extend(bytes(-len(block) % 16))
        delta = len(block) - (old_end - old_start)
        data = bytearray(original_bytes[:old_start]) + block + original_bytes[old_end:]
        shifted = {}
        for at in (48, 56, 60, 64, 76, 80, 84, 88, 92, 96, 100, 112):
            value = struct.unpack_from('<I', data, at)[0]
            if value >= old_end:
                assert value <= len(original_bytes)
                struct.pack_into('<I', data, at, value + delta)
                shifted[at] = [value, value + delta]
            else:
                assert value == 0 or value < old_start
        assert struct.unpack_from('<I', data, 52)[0] == old_start
        assert data[old_end + delta:] == original_bytes[old_end:]
        assert len(data) == len(original_bytes) + delta
    expanded = UnitData.parse(data)
    assert expanded.transforms[:len(original.transforms)] == original.transforms
    assert expanded.parents[:len(original.parents)] == original.parents
    assert expanded.name_hashes[:len(original.name_hashes)] == original.name_hashes
    if args.relocate_only:
        assert len(expanded.transforms) == len(original.transforms) == 107
    with reference.open('rb') as src:
        header = src.read(72)
    archive = TocArchive(struct.unpack_from('<I', header, 12)[0], header[16:72], {})
    dest = work / 'preview-probe' / probe
    dest.mkdir(parents=True, exist_ok=True)
    patch_name = '18235e0c9ec0e636.patch_0' if args.source_archive else '9ba626afa44a3aa3.patch_0'
    files = archive.write_patch(dest / patch_name,
                                [TocEntry(row[0], UNIT_TYPE_ID, bytearray(data))])
    if args.clean_container:
        from anim_batch_mod.constants import TOC_MAGIC
        container = bytearray(192)
        container.extend(data)
        container.extend(bytes(-len(container) % 16))
        struct.pack_into('<III', container, 0, TOC_MAGIC, 1, 1)
        struct.pack_into('<Q', container, 32, len(container))
        struct.pack_into('<QQQII', container, 72, 0, UNIT_TYPE_ID, 1, 16, 64)
        struct.pack_into('<QQQQQQQIIIIII', container, 104, row[0], UNIT_TYPE_ID, 192, 0, 0, 0, 0,
                         len(data), 0, 0, 16, 64, 1)
        files[0].write_bytes(container)
    parsed = TocArchive.parse_parts(files[0].read_bytes())
    assert len(parsed.entries) == 1 and parsed.entries[row[0], UNIT_TYPE_ID].toc_data == data
    guide = ('C1：仅扩展 Avatar 场景骨架。\n'
             '保持 B3，停用 test01-配套动画，选择未替换的原版头盔和盔甲。\n'
             '在已确认原版预览正常的状态下，仅启用本 C1 包，重新部署并重启，比较同一军械库页面。\n'
             '本包只有 Avatar Unit，不含 Bones、状态机、动画或 Lua；原有 107 个节点逐项不变，新增节点保持绑定姿态。\n'
             '若预览再次异常，问题可收窄到 Avatar 节点扩展/预览图处理；若仍正常，继续查其余骨架资源和动画载荷。\n'
             '这不是角色成品包，自定义角色姿态不作为本项结果。完成后停用 C1，再恢复配套动画和 A。\n')
    if args.relocate_only:
        guide = ('C2：仅搬移原 Avatar 节点数据，不增加或修改节点。\n'
                 '保持 B3，停用 test01-配套动画、C1 及其他 C 系列对照包。\n'
                 '仅启用本 C2 包，重新部署并重启，查看此前同一未替换的原版头盔和盔甲。\n'
                 '本包只有 Avatar Unit。原有 107 个节点数据逐字节保持，仅将其原样追加到文件尾部并更新 TransformInfo 指针。\n'
                 '若再次倒置/放大，继续检查数据搬移和相关引用；若正常，继续检查新增节点及相关表。\n'
                 '仅报告军械库原版预览结果，自定义角色姿态不作为本项结果。完成后停用 C2。\n')
    if args.inline_expanded:
        guide = ('C3：原位扩展 Avatar 节点预览对照。\n'
                 '保持 B3，停用 test01-配套动画、C1、C2 及其他 C 系列对照包，仅启用 C3。\n'
                 '部署并重启，查看同一未替换的原版头盔和盔甲。\n'
                 '与 C1 同为 255 个节点，原有 107 节点数据不变；将最终节点表保留在原始位置，顺移后续数据并校正其头部偏移。\n'
                 '本包不含 Bones、状态机、动画或 Lua；仅报告原版军械库预览结果。完成后停用 C3。\n')
    if args.vanilla_only:
        guide = ('C0：原版 Avatar 原样封包对照。\n'
                 '保持 B3，停用配套动画和其他所有 C 系列对照，仅启用 C0，部署并重启。\n'
                 '查看同一原版头盔和盔甲的军械库预览。\n'
                 '唯一资源逐字节等于当前游戏原始归档中的 Avatar Unit，未改节点、偏移或文件长度。\n'
                 '此项确认原样封包替换是否也会触发异常；完成后停用 C0。\n')
    if args.clean_container:
        guide = ('C4：标准容器原版 Avatar 对照。\n'
                 '保持 B3，停用配套动画及 C0/C1/C2/C3，仅启用 C4，部署并重启。\n'
                 '查看同一原版头盔和盔甲军械库预览；完成后停用 C4。\n'
                 'Avatar 资源与 C0 完全相同；改用清零重建的独立归档头、正确的总长度和 16 字节对齐的资源起点。\n')
    if args.source_archive:
        guide = ('C5：原归档路径 Avatar 对照。\n'
                 '保持 B3，停用配套动画及其他 C 系列包，仅启用 C5，部署并重启。\n'
                 '查看同一原版头盔和盔甲预览，完成后停用 C5。\n'
                 '补丁字节与 C4 完全相同，唯一变量是归档文件名前缀改成 Avatar 所在的原始归档 18235e0c9ec0e636。\n')
    (dest / '测试说明.txt').write_text(guide, encoding='utf-8')
    (dest / 'manifest.json').write_text(json.dumps(dict(Version=1, Guid=('c5747377-7c22-4760-bd79-4b9d666d1c05' if args.source_archive else 'c4747377-7c22-4760-bd79-4b9d666d1c04' if args.clean_container else 'cb727377-7c22-4760-bd79-4b9d666d1c00' if args.vanilla_only else '0633a265-7c22-4760-bd79-4b9d666d1c03' if args.inline_expanded else '8663aa2b-7c22-4760-bd79-4b9d666d1c02' if args.relocate_only else '12d68d1f-9da7-4ee4-900e-408e77740f13'),
        Name=f'test01 {probe} {title}', Description='仅在配套动画停用时测试原版军械库预览；完成后停用。'),
        ensure_ascii=False, indent=2), encoding='utf-8')
    output = work / f'{probe}-{title}.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in dest.iterdir():
            z.write(f, f.name)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
    delivery = ROOT / 'outputs/native-manual-20261103/AB测试' / output.name
    shutil.copy2(output, delivery)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(delivery) == digest(output)
    report = dict(status='OFFLINE_VERIFIED', gameTested=False, resources=1, animations=0,
                  originalNodes=len(original.transforms), expandedNodes=len(expanded.transforms),
                  package=str(delivery), sha256=digest(output))
    if args.relocate_only:
        report.update(originalOffset=offset, relocatedOffset=new_offset, originalDataUnchanged=True)
    if args.inline_expanded:
        report.update(originalOffset=old_start, expandedOffset=old_start, shiftedHeaders=shifted, deltaBytes=delta,
                      tailBytesUnchanged=True)
    if args.vanilla_only:
        report.update(unitSha256=hashlib.sha256(data).hexdigest(),entireUnitUnchanged=True)
    if args.clean_container:
        report.update(cleanArchiveHeader=True,alignedPayloadOffset=192,archiveBytes=len(container))
    if args.source_archive:
        assert files[0].read_bytes() == (work/'preview-probe/C4/9ba626afa44a3aa3.patch_0').read_bytes()
        report.update(archivePrefix='18235e0c9ec0e636',samePatchBytesAsC4=True)
    (work / (f'preview-probe-{probe}-audit.json' if probe != 'C1' else 'preview-probe-audit.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
