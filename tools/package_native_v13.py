"""Package verified v13 outputs, preserving prior delivery by checked moves."""
import argparse
import copy
import json
import shutil
import struct
import sys
from pathlib import Path
import package_native_v12 as base
from package_native_v12 import digest, load, save_json, files, lua

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-v13-20261104';PROJECT=WORK/'project'
RELEASE=ROOT/'outputs/native-manual-20261103'
base.WORK=WORK;base.PROJECT=PROJECT;base.RELEASE=RELEASE
archive=base.archive
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive


def static():
    profile=load(PROJECT/'attachment-profile.json')
    exported=(WORK/'physics-export-delivery/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    source=ROOT/'HD2PhysBoneCompat/src'
    profile_source=(source/'native_attachment_profile.lua').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    for name in ('native_attachments.lua','native_attachment_profile.lua','physbone_runtime.lua'):
        assert (source/name).read_text(encoding='utf-8-sig').replace('\r\n','\n') in exported
    for name in ('processor.py','native_skeleton.py','archive.py','test_native_v13.py'):
        assert digest(ROOT.parent/name)==digest(WORK/'manager/anim_batch_mod'/name)
    binary=(WORK/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0').read_bytes()
    original=next(iter(TocArchive.parse_parts(binary).entries.values()))
    assert original.toc_data[8:].decode('utf-8-sig').replace('\r\n','\n')==exported
    sys.path.insert(0,str(ROOT/'outputs/native-v11-20261104/test-runtime'))
    from lupa.lua51 import LuaRuntime
    packages=[];matrix=[]
    groups={'A':('test01-物理运行时-v13-A.zip','基线：固定解剖肘轴，原版收枪挂点，保留原生瞄准父链及前握把刷新。'),
            'B4':('AB测试/B4-实时原生手部同步.zip','仅开启原生手部同步。试验方案；臂长不足的目标仍可能无法贴合，日志记录残差。')}
    for key,(name,description) in groups.items():
        p=copy.deepcopy(profile);p.update(revision='test01-v13-'+key,armSync=key=='B4')
        code=exported.replace(profile_source,'-- Generated test01 v13 '+key+' profile.\nreturn '+lua(p)+'\n')
        vm=LuaRuntime();assert vm.eval('function(s) return loadstring(s)~=nil end')(code)
        dest=PROJECT/'ab-runtime'/key;dest.mkdir(parents=True,exist_ok=True)
        data=code.encode('utf-8');entry=struct.pack('<II',len(data),2)+data
        patch=bytearray(binary[:192])+entry;patch.extend(bytes(-len(patch)%16))
        struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(entry))
        name_=dest/'9ba626afa44a3aa3.patch_0';name_.write_bytes(patch)
        for suffix in ('.stream','.gpu_resources'):Path(str(name_)+suffix).write_bytes(b'')
        parsed=next(iter(TocArchive.parse_parts(patch).entries.values()))
        assert parsed.toc_data==entry and parsed.file_id==original.file_id
        manifest=load(WORK/'physics-export-delivery/patch版/manifest.json')
        manifest.update(Name='test01 v13 '+key,Description=description+' 每次只启用 A 或 B4。')
        save_json(dest/'manifest.json',manifest)
        (dest/'测试说明.txt').write_text(description+'\n'+(ROOT/'docs/native-v13-20261104.md').read_text(encoding='utf-8'),encoding='utf-8')
        save_json(PROJECT/'ab-profiles'/f'{key}.json',p)
        packages.append(archive(name,files(dest)))
        matrix.append(dict(group=key,package=name,description=description,profileSha256=digest(PROJECT/'ab-profiles'/f'{key}.json')))
    a,b=load(PROJECT/'ab-profiles/A.json'),load(PROJECT/'ab-profiles/B4.json')
    assert {k for k in a if a[k]!=b[k]}=={'revision','armSync'}
    shutil.copytree(WORK/'physics-export-delivery',PROJECT/'physics-runtime',dirs_exist_ok=True)
    shutil.copytree(PROJECT/'ab-runtime/A',PROJECT/'physics-runtime/patch版',dirs_exist_ok=True)
    # Both forms of the exporter must carry the actual A code, including revision text.
    (PROJECT/'physics-runtime/lua版/hd2physbone.lua').write_bytes(
        bytes(next(iter(TocArchive.parse_parts((PROJECT/'ab-runtime/A/9ba626afa44a3aa3.patch_0').read_bytes()).entries.values())).toc_data[8:]))
    save_json(WORK/'static-packages.json',packages)
    save_json(WORK/'ab-matrix.json',dict(status='offline-verified',gameTested=False,groups=matrix))
    save_json(WORK/'ab-profile-audit.json',dict(status='PASS',groups=['A','B4'],changedFields=['revision','armSync'],sameAnimationPackage=True))
    print('A and B4 runtime packages verified',flush=True)


def animation():
    base.animation()


def finalize():
    required=['animation-final-audit.json','candidate-audit.json','attachment-runtime-audit.json',
              'arm-sync-audit.json','chef-compatibility-audit.json','package-inspection.json',
              'python-regression.json','ab-profile-audit.json','exporter-audit.json','preview-integration-audit.json']
    for name in required:assert load(WORK/name)['status']=='PASS',name
    imported={row['package']:row['sha256'] for row in load(WORK/'package-inspection.json')['packages']}
    for row in load(WORK/'static-packages.json')+[load(WORK/'animation-package.json')]:
        assert imported.get(row['name'])==row['sha256'],'Re-run isolated import for '+row['name']
    reports=PROJECT/'reports/current-v13';reports.mkdir(parents=True,exist_ok=True)
    for name in required+['ab-matrix.json','feedback.json','elbow-plane-analysis.json','candidate-comparison.json','duplicate-cleanup.json','known-good-reference.json']:
        shutil.copy2(WORK/name,reports/name)
    for file in WORK.glob('preview-probe*-audit.json'):shutil.copy2(file,reports/file.name)
    for name in ('import-library-cleanup.json','python-preview-regression.log','preview-import.log'):
        if (WORK/name).exists():shutil.copy2(WORK/name,reports/name)
    baseline=reports/'baseline-v13';baseline.mkdir(exist_ok=True)
    for name in ('animation-final-audit.json','build-report.json'):
        shutil.copy2(WORK/'baseline-v13'/name,baseline/name)
    code=PROJECT/'source-code';code.mkdir(parents=True,exist_ok=True)
    for file,relative in files(RELEASE/'project/source-code'):
        dest=code/relative
        if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    current={f.name:f for f in ROOT.parent.glob('*.py')}
    current.update({f.name:f for f in (ROOT/'HD2PhysBoneCompat/src').glob('*.lua')})
    for folder in ('HD2PhysBoneCompat/src','HD2PhysBoneCompat/test'):
        for file,relative in files(ROOT/folder):
            dest=code/folder/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    for file in ROOT.parent.glob('*.py'):
        dest=code/'anim_batch_mod'/file.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
        shutil.copy2(file,code/file.name)
    for file,relative in files(code):
        if file.name in current:shutil.copy2(current[file.name],file)
    for file in (ROOT/'tools').glob('*native_v13*.py'):
        dest=code/'tools'/file.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    shutil.copy2(ROOT/'tools/Cleanup-Native-DuplicateArtifacts.ps1',code/'tools/Cleanup-Native-DuplicateArtifacts.ps1')
    shutil.copy2(ROOT/'tools/Cleanup-Native-V13Imports.ps1',code/'tools/Cleanup-Native-V13Imports.ps1')
    (code/'README.txt').write_text('v13 production Python: anim_batch_mod/. Lua: HD2PhysBoneCompat/src/.\nVersioned offline audits use retained fixtures from the original workspace. Rebuild with ../Rebuild-Animations.ps1.\n',encoding='utf-8')
    script=(ROOT/'tools/Rebuild-Native-v10-Animations.ps1').read_text(encoding='utf-8-sig').replace('v10','v13')
    (PROJECT/'Rebuild-Animations.ps1').write_text(script,encoding='utf-8')
    doc=ROOT/'docs/native-v13-20261104.md'
    for name in ('先读我.txt','修正说明.md','挂点配置.md','AB测试说明.md'):shutil.copy2(doc,PROJECT/name)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md'):shutil.copy2(doc,WORK/name)
    shutil.copy2(doc,WORK/'manager/先读我-修复测试.txt')
    packages=load(WORK/'static-packages.json')+[load(WORK/'animation-package.json')]
    packages.append(archive('HD2ModManager-原生骨架测试版.zip',[(p,Path('manager')/r) for p,r in files(WORK/'manager')]))
    packages.append(archive('test01-源工程.zip',[(p,r) for p,r in files(PROJECT) if r.parts[:2]!=('animations','runtime')]))
    save_json(WORK/'package-report.json',dict(status='offline-verified',revision='native-v13',gameTested=False,
        runtimeVersion='2.1.8',attachmentVersion='0.9.0',modelMaterialsWeightsUnchanged=True,
        modelPackageSha256=digest(RELEASE/'test01-模型材质.zip'),packages=packages,reports={n:digest(WORK/n) for n in required}))
    print('Final v13 packages verified',flush=True)


def deliver(preview_update=False):
    report=load(WORK/'package-report.json');assert report['revision']=='native-v13'
    backup=(RELEASE/('backups/v13-preview-before-20261104' if preview_update else 'backups/v13-before-20261104')).resolve()
    expected={row['path']:row['sha256'] for row in load(WORK/'baseline-v13/delivery-verification.json')['verified']} if preview_update else {}
    pairs=[(WORK/r['name'],Path(r['name'])) for r in report['packages']]
    pairs.extend((p,Path('project')/r) for p,r in files(PROJECT))
    for folder in ('manager','test'):
        pairs.extend((p,Path(folder)/r) for p,r in files(WORK/'manager') if r.parts[0] not in base.PROTECTED)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md','package-report.json','ab-matrix.json'):
        pairs.append((WORK/name,Path(name)))
    assert digest(RELEASE/'test01-模型材质.zip')==report['modelPackageSha256']
    for row in report['packages']:assert digest(WORK/row['name'])==row['sha256']
    # Validate all destinations before the first move. Existing v12 backups remain intact.
    prepared=[]
    for source,relative in pairs:
        dest=(RELEASE/relative).resolve();saved=(backup/relative).resolve();source=source.resolve()
        assert source.is_relative_to(WORK.resolve()) and dest.is_relative_to(RELEASE.resolve()) and saved.is_relative_to(backup)
        sha=digest(source)
        previous=digest(dest) if dest.exists() else None
        if previous is not None and previous!=sha:
            if preview_update:assert expected.get(relative.as_posix())==previous,'Delivery changed since baseline: '+str(relative)
            assert not saved.exists() or digest(saved)==previous,'Existing version backup: '+str(saved)
        prepared.append((source,relative,dest,saved,sha,previous))
    backup.mkdir(parents=True,exist_ok=True)
    checked=[]
    for source,relative,dest,saved,sha,previous in prepared:
        if previous is not None and previous!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dest),str(saved))
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            if source.stat().st_size>100_000_000:shutil.move(str(source),str(dest))
            else:shutil.copy2(source,dest)
        assert digest(dest)==sha;checked.append(dict(path=relative.as_posix(),sha256=sha))
    for relative in ('test01-物理运行时-v12-A.zip','AB测试/B1-旧持枪映射.zip','AB测试/B2-原版收枪挂点.zip','AB测试/B3-停止挂点运行时.zip'):
        old=(RELEASE/relative).resolve();saved=(backup/relative).resolve()
        assert old.is_relative_to(RELEASE.resolve()) and saved.is_relative_to(backup)
        if old.exists():
            assert not saved.exists();saved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(old),str(saved))
    save_json(RELEASE/'delivery-verification.json',dict(status='PASS',revision='native-v13',files=len(checked),backup=str(backup),
        gameDeployed=False,gameTested=False,largeFilesMoved=True,verified=checked))
    save_json(WORK/'delivery-location.json',dict(release=str(RELEASE),largeFilesMoved=True,verification=str(RELEASE/'delivery-verification.json')))
    print('Delivered',len(checked),'verified files',flush=True)


def deliver_preview():
    deliver(preview_update=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['static','animation','finalize','deliver','deliver_preview'])
    globals()[parser.parse_args().stage]()
