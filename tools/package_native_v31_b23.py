"""Deliver the verified B23 experiment into the user's existing tool directory."""
import json
import shutil
import zipfile
import sys
import uuid
from pathlib import Path

from prepare_native_v31_b23 import ROOT, W, R, B22, SRC, PACKAGE, PROJECT_PACKAGE, DOC, PHYSICS_PACKAGE, load, save, digest, compose_source
from repack_native_b23 import build as rebuild
from audit_native_v31_b23_import import audit_project_package


def copy_verified(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and digest(source) != digest(target):
        raise RuntimeError('Refusing to overwrite a different existing delivery: ' + str(target))
    if not target.exists():
        shutil.copy2(source, target)
    assert digest(source) == digest(target)


def main():
    for name in ('build-audit.json','runtime-audit.json','chef-audit.json',
                 'packaged-animation-axis-audit.json','package-inspection.json','native-parenting-audit.json'):
        assert load(W / name)['status'] == 'PASS', name
    body = (W / 'hd2attachmentfix-B23.lua').read_text(encoding='utf-8')
    expected = compose_source(load(W / 'B23-profile.json'))
    assert body == expected
    assert load(W / 'runtime-audit.json')['sourceSha256'] == digest(SRC / 'native_grip_transfer_test.lua')
    assert load(W / 'chef-audit.json')['sourceSha256'] == digest(W / 'hd2attachmentfix-B23.lua')
    assert load(W / 'chef-audit.json')['patchSha256'] == digest(W / 'runtime/9ba626afa44a3aa3.patch_4')
    shutil.copy2(ROOT / 'tools/repack_native_b23.py', W / 'repack_native_b23.py')
    repacked = rebuild(W)
    assert repacked['patchSha256'] == load(W / 'build-audit.json')['patchSha256']
    save(W / 'repack-audit.json', dict(status='PASS', standardPythonOnly=True,
        patchByteIdentical=True, patchSha256=repacked['patchSha256']))

    diagnostic = R / 'project/diagnostics/B23LR-M-1.0.7'
    artifacts = []
    for package in load(W / 'static-packages.json'):
        source = W / package['name']
        assert digest(source) == package['sha256']
        target = R / 'AB测试' / source.name
        copy_verified(source,target)
        artifacts.append(dict(path=str(target),sha256=digest(target),bytes=target.stat().st_size))

    direct = ['hd2attachmentfix-B23.lua','container-header.bin','manifest.json','测试说明.md',
        'repack_native_b23.py','B23-profile.json','wrist-registration.json','runtime-fixture.json','v30-avatar.toc','legacy-arm-math.lua',
        'native-parenting.json','runtime-avatar.toc','weapon-targets.json']
    reports = ['build-audit.json','runtime-audit.json','chef-audit.json','repack-audit.json',
        'packaged-animation-axis-audit.json','package-inspection.json','runtime-fixture.log','chef-fixture.log',
        'native-parenting-audit.json','weapon-coverage-live-analysis.json','coverage-status.json']
    for name in direct:
        copy_verified(W / name, diagnostic / name)
    for name in reports:
        copy_verified(W / name, diagnostic / 'reports' / name)
    for item in load(W/'native-parenting.json')['files']:
        copy_verified(W/'native-parenting'/item['name'],diagnostic/item['name'])
    for suffix in ('', '.stream', '.gpu_resources'):
        name = '9ba626afa44a3aa3.patch_4' + suffix
        copy_verified(W/'runtime'/name, diagnostic/name)
    for name in ('native_grip_transfer_test.lua','native_grip_transfer_test_entry.lua','attachment_fix_runtime.lua'):
        copy_verified(SRC / name,diagnostic / 'src' / name)
    for name in ('native_grip_transfer_harness.lua','strict_id32_fixture.lua'):
        copy_verified(ROOT / 'HD2PhysBoneCompat/test' / name,diagnostic / 'test' / name)
    for name in ('prepare_native_v31_b23.py','audit_native_v31_b23.py','audit_native_v31_b23_chef.py',
                 'audit_native_v31_b23_import.py','package_native_v31_b23.py','survey_native_weapon_grips.py'):
        copy_verified(ROOT / 'tools' / name,diagnostic / 'tools' / name)
    readme = ('B23-LR-M 1.0.7 多武器与持物挂点整合工程（可直接安装）\n\n'
        '本 ZIP 可直接导入管理器并启用；应识别一个模组、两个补丁组。停用旧 B23-R/LR 和旧多武器工程空节点。\n'
        '根目录同时含 Lua patch_4 和 Avatar/Bones patch_5（各带 stream/gpu_resources），必须作为整包启用。\n'
        '修改 hd2attachmentfix-B23.lua 后，运行 python repack_native_b23.py；仅需标准 Python。\n'
        '输出位于 rebuilt/；本目录已有的 Lua patch_4 也同步更新，重封包保留根目录骨架补丁。\n'
        '本版必须加载完整 ZIP；单独的 Lua 不包含新增输出节点。重封包不自动验证修改后的 Lua 行为。\n'
        '左手目标=本枪 IK_left；GP-20 持续双手，其他副武器仅瞄准路径双手；左右手单持物品独立更新。\n'
        '整合 21 个非头部挂点，含臂板与手枪收纳；保护头部子节点和原生控制器输入。\n\n'
        '完整离线回归需原工作区的 Lua 5.1/Lupa、NumPy、B21 原生资源、B22 动画、武器清单和 Chef 源码。\n'
        '保留的 tools/ 是审计源码快照；在 HD2ModManager 原工作区运行 tools/audit_native_v31_b23.py\n'
        '和 tools/audit_native_v31_b23_chef.py。reports/*fixture.log 是模拟数据，不是游戏日志。\n')
    (diagnostic / 'README.txt').write_text(readme,encoding='utf-8')
    instructions = R / '先读我-B23LR-M-1.0.7-覆盖修正.md'
    copy_verified(DOC, instructions)
    copy_verified(instructions, diagnostic / '安装与验证.md')
    checked = rebuild(diagnostic)
    assert checked['patchSha256'] == repacked['patchSha256']
    # Keep the editable project and a compact archive; omit rebuilt duplicates.
    project_zip=R / PROJECT_PACKAGE
    assert not project_zip.exists(), 'Existing project archive must be preserved'
    with zipfile.ZipFile(project_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for file in sorted(diagnostic.rglob('*')):
            if file.is_file() and 'rebuilt' not in file.relative_to(diagnostic).parts:
                archive.write(file,str(file.relative_to(diagnostic)))
    with zipfile.ZipFile(project_zip) as archive:
        assert archive.testzip() is None
    project_import = audit_project_package(project_zip, W / 'project-import')
    save(diagnostic / 'reports/installable-project-audit.json', project_import)
    artifacts.append(dict(path=str(project_zip),sha256=digest(project_zip),bytes=project_zip.stat().st_size))
    report=dict(status='PASS',artifacts=artifacts,editableLua=str(diagnostic / 'hd2attachmentfix-B23.lua'),
        instructions=str(instructions),
        repackInDeliveredDirectoryByteIdentical=True,
        projectDirectlyInstallable=True, projectImportAudit=project_import,
        onlyNewB23FilesAddedToToolDirectory=True,gameDeployed=False,gameTested=False,
        productionAdapterSha256=digest(SRC / 'attachment_fix_runtime.lua'),
        purePhysicsSourceSha256=digest(B22 / 'physics-runtime/lua版/hd2physbone.lua'),
        note='Use B22 animations and the complete B23-LR-M ZIP with its paired native-parenting patch; disable the older B23-R/LR packages. Left targets use weapon-self IK_left under the configured sidearm/hold policy; both carrying mounts and non-head attachments are integrated.')
    save(W / 'delivery-verification.json',report)
    save(diagnostic / 'delivery-verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


def package_test02():
    """Deliver the existing test02 model with its upgraded animation and GUI output."""
    import audit_native_v16_import as importer
    import audit_native_v31_b23_chef as chef
    project=ROOT/'outputs/native-test02-integrated-20261105'
    previous=ROOT/'outputs/native-test02-20261105'
    delivery=project/'交付'
    delivery.mkdir(exist_ok=True)
    audit=load(project/'runtime-audit.json')
    animation=load(project/'animations-upgraded/build-report.json')
    assert audit['status']=='PASS' and audit['publishedGuiServiceExportVerified']
    assert animation['status']=='complete' and len(animation['animations'])==3180
    assert animation['existingRetargetSwapAndEventsPreserved'] and animation['allOriginalReferenceKeysChecked']
    for row in animation['files']:
        assert digest(project/'animations-upgraded'/row['path'])==row['sha256']
    exported=project/'gui-attachment-fix-runtime/attachment-fix'
    assert digest(exported/'lua版/hd2attachmentfix.lua')==audit['luaSourceSha256']
    # Reuse the actual Chef parser/sandbox audit with this model's composed bytes.
    check=project/'chef-validation'
    check.mkdir(exist_ok=True)
    copy_verified(exported/'lua版/hd2attachmentfix.lua',check/'hd2attachmentfix-B23.lua')
    for folder,source,number in (
        ('runtime',exported/'patch版',4),('native-parenting',exported/'patch版',5),
        ('physics-companion',previous/'physics-runtime/patch版',3)):
        for suffix in ('','.stream','.gpu_resources'):
            name=f'9ba626afa44a3aa3.patch_{number}{suffix}'
            copy_verified(source/name,check/folder/name)
    chef.W=check;chef.B22=previous;chef.main()
    records=[]
    plans=[
        ('test02-独立护甲模型.zip',previous/'models/test02','[原骨架模型]test02'),
        ('test02-原比例动画-3180.zip',project/'animations-upgraded/runtime','[原比例动画]test02'),
        ('[骨骼挂点修正]test02-1.0.7.zip',exported/'patch版',None),
        ('test02-独立物理运行时.zip',previous/'physics-runtime/patch版',None)]
    for name,source,title in plans:
        target=delivery/name
        assert not target.exists(),'Existing test02 delivery must be preserved: '+str(target)
        print('Packaging test02:',name,flush=True)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for file in sorted(source.iterdir()):
                if file.is_file():archive.write(file,file.name)
            if title:
                archive.writestr('manifest.json',json.dumps(dict(Version=1,
                    Guid=str(uuid.uuid5(uuid.NAMESPACE_URL,'hd2-native-test02:'+title)),Name=title,
                    Description='test02 独立骨架配套，2026-11-05；与 1.0.7 挂点修正配套使用。'),ensure_ascii=False,indent=2))
            for file in source.glob('*.patch_*'):
                if not file.suffix[1:].startswith('patch_'):continue
                for suffix in ('.stream','.gpu_resources'):
                    if not (source/(file.name+suffix)).exists():archive.writestr(file.name+suffix,b'')
        records.append(dict(name=name,sha256=digest(target),bytes=target.stat().st_size))
    save(delivery/'static-packages.json',records)
    importer.W=delivery;importer.main(exe=W/'manager-1.0.7/hd2mod.exe',sandbox_root=project)
    inspection=load(delivery/'package-inspection.json')
    grip=inspection['packages'][2]
    mains=[row for row in grip['verifiedPatchFiles'] if row['name'].endswith(('.patch_4','.patch_5'))]
    parents={str(Path(path).parent) for row in mains for path in row['imported']}
    assert len(mains)==2 and len(parents)==1, 'test02 Lua/skeleton were split into separate nodes'
    reports=delivery/'reports'
    for source,name in (
        (project/'runtime-audit.json','runtime-audit.json'),
        (check/'chef-audit.json','chef-audit.json'),
        (project/'gui-attachment-fix-runtime/calibration/attachment-build-report.json','attachment-build-report.json'),
        (project/'animations-upgraded/build-report.json','animation-build-report.json')):
        copy_verified(source,reports/name)
    text=('test02 独立骨架与挂点修正 1.0.7\n\n'
        '把此目录四个 ZIP 分别导入管理器。模型、3180 条动画和挂点修正必须配套启用；物理运行时独立启用。\n'
        '挂点 ZIP 应识别一个模组、两个补丁组（Lua patch_4 和 Avatar/Bones patch_5）。需要 Chef Shared Loader。\n'
        '测试 test02 时停用 test01/B23 及旧 test02 的模型、动画和挂点修正，避免共用 Avatar 资源冲突。\n'
        'LAS-44、左右手单持物品、21 个非头部挂点已补充；GP-20 全程双手，其他副武器仅瞄准路径双手。\n'
        '原模型字节保持；新增两个原生手部参考动画通道；全部旧重定向、互换和事件保持。\n'
        '已通过离线运行时、实际 Chef 解析/沙箱和隔离库导入。GR-8/P-4 部件及所有画面结果仍待游戏验证。\n'
        '交付目录仅含最终包。上层 animations/、upgrade-attempt-* 等是构建历史，不用于安装。\n')
    (delivery/'安装说明.txt').write_text(text,encoding='utf8')
    result=dict(status='PASS',artifacts=records,modelBytesPreserved=True,animations=3180,
        importedGripPayloadDirectories=len(parents),publishedGuiExportVerified=True,
        gameDeployed=False,gameTested=False,dailyLibraryModified=False)
    save(delivery/'delivery-verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    if '--test02' in sys.argv:package_test02()
    else:main()
