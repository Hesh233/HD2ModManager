"""Verify frozen project payloads, code contracts, cleanup evidence and archive layout."""
import hashlib,json,os,shutil,unittest,zipfile,tomllib
from pathlib import Path
from prepare_native_v31_b23 import ROOT,load,save
from anim_batch_mod.attachment_skeleton import validate_attachment_transfer_contract
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import BONE_TYPE_ID

P=ROOT/'projects/test01-native-grip';OUT=ROOT/'outputs/project-archive-cleanup-20261105'

def main():
    native_names=['test_attachment_swap','test_attachment_skeleton','test_native_skeleton','test_native_v9','test_native_v10','test_native_v11','test_native_v12','test_native_v13']
    native=unittest.defaultTestLoader.loadTestsFromNames(['anim_batch_mod.'+n for n in native_names])
    project=unittest.defaultTestLoader.discover(str(ROOT/'tools'),pattern='test_native_grip_project.py')
    counts=(native.countTestCases(),project.countTestCases())
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite([native,project]))
    if not result.wasSuccessful():raise RuntimeError('Archive/code contract regression failed')
    cleanup=load(OUT/'cleanup-result.json');spec=load(P/'project.json')
    assert cleanup['status']=='complete'
    assert all(not Path(r['path']).exists() and Path(r['keeper']).is_file() for r in cleanup['deleted'])
    assert all((ROOT/path).exists() for path in spec['dependencies'].values())
    assert hashlib.sha256((P/spec['baseline']).read_bytes()).hexdigest()==spec['baselineSha256']
    for row in spec['releases']:
        archived=P/row['path'];assert hashlib.sha256(archived.read_bytes()).hexdigest()==row['sha256']
        fresh=P/'.build/交付'/Path(row['path']).name.replace('.zip','-待测试.zip')
        with zipfile.ZipFile(archived) as old,zipfile.ZipFile(fresh) as new:
            for n in (4,5):
                for suffix in ('','.gpu_resources','.stream'):
                    name=f'9ba626afa44a3aa3.patch_{n}{suffix}';assert old.read(name)==new.read(name)
    files=[];total=0
    for current,dirs,names in os.walk(ROOT/'outputs',followlinks=False):
        dirs[:]=[d for d in dirs if not Path(current,d).is_symlink()]
        for name in names:
            path=Path(current,name)
            try:size=path.stat().st_size
            except OSError:continue
            total+=size;files.append(dict(path=str(path),bytes=size))
    save(OUT/'inventory-after.json',dict(fileCount=len(files),bytes=total,files=files))
    sources=['HD2PhysBoneCompat/src/native_grip_transfer_test.lua','HD2PhysBoneCompat/src/native_grip_transfer_test_entry.lua','HD2PhysBoneCompat/src/attachment_fix_runtime.lua',
        'tools/build_native_b23_108.py','tools/repack_native_b23.py','tools/test_native_grip_project.py','tools/verify_native_grip_archive.py',
        '../native_skeleton.py','../attachment_skeleton.py','../test_attachment_swap.py','../test_attachment_skeleton.py']
    save(P/'verification/source-manifest.json',[dict(path=path,sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),
        role='future-animation-converter-v2' if path.startswith('../') else 'runtime-or-archive-tool') for path in sources])
    with zipfile.ZipFile(P/spec['baseline']) as z:
        avatar=UnitData.parse(z.read('runtime-avatar.toc'))
        patch=TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_5'),z.read('9ba626afa44a3aa3.patch_5.gpu_resources'),b'')
    bones=BonesData.parse(next(e.toc_data for e in patch.entries.values() if e.type_id==BONE_TYPE_ID))
    contract=validate_attachment_transfer_contract(load(P/spec['profile']),avatar,bones,load(P/spec['sourceSkeleton']),
        tomllib.loads((P/spec['animationConfig']).read_text(encoding='utf-8-sig'))['attachment_swap'])
    contract.update(tested108PayloadUnchanged=True,futureBakeStage='after-final-arm-reference',testedAnimationBakeIsFrozenLegacyB22=True)
    save(P/'verification/attachment-contract-audit.json',contract)
    build=load(P/'.build/delivery-verification.json')
    validation=dict(status='ARCHIVED_SMOKE_TESTED_PAYLOAD_PRESERVED',userFeedback=spec['userFeedback'],
        releasePayloadByteIdentical=True,baseline107ByteIdentical=True,animationRebaked=False,gameDeploymentChanged=False,
        canonicalBuild=build['status'],freshImports=build['importStatus'],prior108Imports='PASS (original delivery reports retained)',
        nativePythonTests=counts[0],projectContractTests=counts[1],runtimeChecks=load(P/'.build/runtime-audit.json')['checks'],
        cleanupDeletedFiles=cleanup['deletedFiles'],cleanupReclaimedBytes=cleanup['deletedBytes'],cleanupReclaimedGiB=cleanup['reclaimedGiB'],
        outputsAfterGiB=round(total/1024**3,3),fullWeaponAcceptance=False)
    save(P/'verification/archive-validation.json',validation)
    shutil.copy2(OUT/'cleanup-result.json',P/'verification/cleanup-result.json')
    text=f'''# 工程归档与动作副本清理

2026-11-05（Asia/Shanghai）。用户反馈“暂无发现明显问题”，1.0.8 记录为本轮观察通过，不扩大到所有武器验收。

## 归档
`{P}`：固定配置、小型输入、共享源码、不可变 releases/1.0.8、verification、可重建 .build 分开。运行 projects/test01-native-grip/build.ps1 即可重打，不读当前游戏日志重新推导配置、不自动重烘、不部署、不覆盖已观察发布包。
原交付与规范发布包的六个有效补丁文件完全相同；1.0.7/1.0.4 基线保留。管理器运行时的新副库写入验证遵守保护而跳过，旧 1.0.8 的导入通过记录保留，没有关闭管理器或绕过保护。

## 挂点代码
动画生成和 GUI/运行时工程使用同一个配置归一化及契约检查。右通道 16↔137、原始参考203；左19↔114、原始参考202。通道与 Unit 节点不同；运行时由转换器手部轴/原生参考校准，不用旧 L4D2 武器骨世界位置当握点。
源代码已修正父级缩放逆变换，以及互换与最终手臂参考旋转的顺序；重叠通道、歧义短骨名、奇异缩放、错误原始参考通道拒绝生成。{counts[0]} 项动画/骨架回归和 {counts[1]} 项冻结工程/契约测试通过，归档重建运行时 {validation['runtimeChecks']:,} 项断言通过，Chef 验证通过。
**没有将后续生成修正偷偷应用到已测 B22 动作。** 已观察的 1.0.8 Lua、Avatar/Bones、模型/权重/动作不变；未来重烘需形成新待测动作版本，不能沿用旧包实机验收状态。

## 清理
删除 **{cleanup['deletedFiles']}** 个 SHA-256 验证的冗余动作文件，释放 **{cleanup['reclaimedGiB']:.3f} GiB（约 {cleanup['deletedBytes']/1e9:.2f} GB）**：
- 9 个历史转换备份的大动作解包副本：对应 ZIP/member 逐字节哈希相同，ZIP 保留。
- 一次 test02 隔离导入的临时动作副本：保留 animations-upgraded 金版。
保留当前 test01/B22 动作、test02 最新导出、原生手臂参考、模型/源码/配置/报告及基线。没有删除不同内容的历史 ZIP、数据库或当前游戏/日常 Mod 库。
删除路径、SHA-256、保留文件和 ZIP member 见 delete-plan.json / cleanup-result.json；需要恢复时从该 ZIP 解压回原目录，临时导入副本可从金版复制回来。
outputs 逻辑占用由约47.27 GiB降至 **{total/1024**3:.3f} GiB**。新规范工程不再另复制全量动作。
'''
    (OUT/'归档与清理报告.md').write_text(text,encoding='utf-8')
    print(json.dumps(validation,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
