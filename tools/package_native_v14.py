"""Package the verified arm-reference update and deliver with checked backups."""
import argparse
import copy
import shutil
import struct
import sys
from pathlib import Path
import package_native_v12 as base
from package_native_v12 import digest,load,save_json,files,lua

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-v14-20261104';PROJECT=WORK/'project'
RELEASE=ROOT/'outputs/native-manual-20261103'
base.WORK=WORK;base.PROJECT=PROJECT;base.RELEASE=RELEASE
archive=base.archive
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive

REQUIRED=['animation-final-audit.json','candidate-audit.json','final-motion-audit.json',
    'preview-integration-audit.json','attachment-runtime-audit.json','arm-sync-audit.json',
    'chef-compatibility-audit.json','package-inspection.json','python-regression.json',
    'ab-profile-audit.json','exporter-audit.json','known-good-reference.json','runtime-activation-evidence.json']

def static():
    profile=load(PROJECT/'attachment-profile.json')
    exported=(WORK/'physics-export-delivery/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    source=ROOT/'HD2PhysBoneCompat/src'
    profile_source=(source/'native_attachment_profile.lua').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    for name in ('native_attachments.lua','native_attachment_profile.lua','physbone_runtime.lua'):
        assert (source/name).read_text(encoding='utf-8-sig').replace('\r\n','\n') in exported
    for name in ('processor.py','native_skeleton.py','native_arm_reference.py','archive.py','test_native_arm_reference.py'):
        assert digest(ROOT.parent/name)==digest(WORK/'manager/anim_batch_mod'/name)
    binary=(WORK/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0').read_bytes()
    original=next(iter(TocArchive.parse_parts(binary).entries.values()))
    assert original.toc_data[8:].decode('utf-8-sig').replace('\r\n','\n')==exported
    sys.path.insert(0,str(ROOT/'outputs/native-v11-20261104/test-runtime'))
    from lupa.lua51 import LuaRuntime
    packages=[];matrix=[]
    groups={'A':('test01-物理运行时-v14-A.zip','参考骨段方向及解剖次轴修正；实时握持关闭。'),
        'B5':('AB测试/B5-掌心握持校准.zip','掌心位置与朝向校准试验；原生挂点作为目标，仅驱动自定义角色手臂。')}
    for key,(name,description) in groups.items():
        p=load(PROJECT/'ab-profiles'/f'{key}.json')
        expected=copy.deepcopy(profile);expected.update(revision='test01-v14-'+key,armSync=key=='B5',armGripSync=key=='B5')
        assert p==expected
        code=exported.replace(profile_source,'-- Generated test01 v14 '+key+' profile.\nreturn '+lua(p)+'\n')
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
        manifest.update(Name='test01 v14 '+key,Description=description+' 每次只启用 A 或 B5。')
        save_json(dest/'manifest.json',manifest)
        (dest/'测试说明.txt').write_text(description+'\n'+(ROOT/'docs/native-v14-20261104.md').read_text(encoding='utf-8'),encoding='utf-8')
        packages.append(archive(name,files(dest)))
        matrix.append(dict(group=key,package=name,description=description,profileSha256=digest(PROJECT/'ab-profiles'/f'{key}.json')))
    a,b=load(PROJECT/'ab-profiles/A.json'),load(PROJECT/'ab-profiles/B5.json')
    assert {k for k in a if a[k]!=b[k]}=={'revision','armSync','armGripSync'}
    shutil.copytree(WORK/'physics-export-delivery',PROJECT/'physics-runtime',dirs_exist_ok=True)
    shutil.copytree(PROJECT/'ab-runtime/A',PROJECT/'physics-runtime/patch版',dirs_exist_ok=True)
    (PROJECT/'physics-runtime/lua版/hd2physbone.lua').write_bytes(
        bytes(next(iter(TocArchive.parse_parts((PROJECT/'ab-runtime/A/9ba626afa44a3aa3.patch_0').read_bytes()).entries.values())).toc_data[8:]))
    save_json(WORK/'static-packages.json',packages)
    save_json(WORK/'ab-matrix.json',dict(status='offline-verified',gameTested=False,groups=matrix))
    save_json(WORK/'ab-profile-audit.json',dict(status='PASS',groups=['A','B5'],changedFields=['revision','armSync','armGripSync'],sameAnimationPackage=True))
    print('A and B5 runtime packages verified',flush=True)

def animation():base.animation()

def prepare():
    reports=PROJECT/'reports/current-v14';reports.mkdir(parents=True,exist_ok=True)
    for name in REQUIRED+['ab-matrix.json','feedback.json','palm-calibration.json','reference-comparison.json',
        'python-regression.log','exporter-tests.log','build.log','final-motion-audit.log','chef-audit.log','attachment-audit.log','import-library-cleanup.json']:
        if (WORK/name).exists():shutil.copy2(WORK/name,reports/name)
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
    for file in (ROOT/'tools').glob('*native_v14*.py'):
        dest=code/'tools'/file.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
    shutil.copy2(ROOT/'tools/Cleanup-Native-V14Imports.ps1',code/'tools/Cleanup-Native-V14Imports.ps1')
    (code/'README.txt').write_text('v14 production Python: anim_batch_mod/. Lua: HD2PhysBoneCompat/src/.\nAudits use retained fixtures from the original workspace. Rebuild with ../Rebuild-Animations.ps1 and ../refs.\n',encoding='utf-8')
    script=(ROOT/'tools/Rebuild-Native-v10-Animations.ps1').read_text(encoding='utf-8-sig').replace('v10','v14')
    (PROJECT/'Rebuild-Animations.ps1').write_text(script,encoding='utf-8')
    doc=ROOT/'docs/native-v14-20261104.md'
    for name in ('先读我.txt','修正说明.md','挂点配置.md','AB测试说明.md'):shutil.copy2(doc,PROJECT/name)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md'):shutil.copy2(doc,WORK/name)
    shutil.copy2(doc,WORK/'manager/先读我-修复测试.txt')
    save_json(WORK/'manager-package.json',archive('HD2ModManager-原生骨架测试版.zip',[(p,Path('manager')/r) for p,r in files(WORK/'manager')]))
    print('Source project and manager package prepared; final import remains required',flush=True)

def finalize():
    for name in REQUIRED:assert load(WORK/name)['status']=='PASS',name
    imported={row['package']:row['sha256'] for row in load(WORK/'package-inspection.json')['packages']}
    for row in load(WORK/'static-packages.json')+[load(WORK/'animation-package.json')]:
        assert imported.get(row['name'])==row['sha256'],'Re-run isolated import for '+row['name']
    reports=PROJECT/'reports/current-v14'
    for name in REQUIRED+['import-library-cleanup.json']:
        if (WORK/name).exists():shutil.copy2(WORK/name,reports/name)
    manager=load(WORK/'manager-package.json');assert digest(WORK/manager['name'])==manager['sha256']
    packages=load(WORK/'static-packages.json')+[load(WORK/'animation-package.json'),manager]
    packages.append(archive('test01-源工程.zip',[(p,r) for p,r in files(PROJECT) if r.parts[:2]!=('animations','runtime')]))
    save_json(WORK/'package-report.json',dict(status='offline-verified',revision='native-v14',gameTested=False,
        runtimeVersion='2.1.9',attachmentVersion='0.10.0',modelMaterialsWeightsUnchanged=True,
        modelPackageSha256=digest(RELEASE/'test01-模型材质.zip'),packages=packages,reports={n:digest(WORK/n) for n in REQUIRED}))
    print('Final v14 packages verified',flush=True)

def baseline():
    report=load(RELEASE/'delivery-verification.json');assert report['status']=='PASS' and report['revision']=='native-v13'
    for row in report['verified']:assert digest(RELEASE/row['path'])==row['sha256'],'Existing delivery changed: '+row['path']
    save_json(WORK/'baseline-v13/delivery-verification.json',report)
    print('Previous v13 delivery hashes verified',flush=True)

def deliver():
    report=load(WORK/'package-report.json');assert report['revision']=='native-v14'
    backup=(RELEASE/'backups/v14-before-20261104').resolve()
    prior=load(WORK/'baseline-v13/delivery-verification.json')
    expected={row['path']:row['sha256'] for row in prior['verified']}
    pairs=[(WORK/r['name'],Path(r['name'])) for r in report['packages']]
    pairs.extend((p,Path('project')/r) for p,r in files(PROJECT))
    for folder in ('manager','test'):
        pairs.extend((p,Path(folder)/r) for p,r in files(WORK/'manager') if r.parts[0] not in base.PROTECTED)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md','package-report.json','ab-matrix.json'):
        pairs.append((WORK/name,Path(name)))
    assert digest(RELEASE/'test01-模型材质.zip')==report['modelPackageSha256']
    for row in report['packages']:assert digest(WORK/row['name'])==row['sha256']
    prepared=[]
    for source,relative in pairs:
        dest=(RELEASE/relative).resolve();saved=(backup/relative).resolve();source=source.resolve()
        assert source.is_relative_to(WORK.resolve()) and dest.is_relative_to(RELEASE.resolve()) and saved.is_relative_to(backup)
        sha=digest(source);previous=digest(dest) if dest.exists() else None
        if previous is not None and previous!=sha:
            assert expected.get(relative.as_posix())==previous,'Delivery changed since baseline: '+str(relative)
            assert not saved.exists() or digest(saved)==previous,'Conflicting backup: '+str(saved)
        prepared.append((source,relative,dest,saved,sha,previous))
    retired=['test01-物理运行时-v13-A.zip','AB测试/B4-实时原生手部同步.zip']
    for kind in ('ab-runtime','ab-profiles'):
        for label in ('B1','B2','B3','B4'):
            path=RELEASE/'project'/kind/(label+'.json' if kind=='ab-profiles' else label)
            if path.is_dir():retired.extend(str(p.relative_to(RELEASE)).replace('\\','/') for p,_ in files(path))
            elif path.is_file():retired.append(path.relative_to(RELEASE).as_posix())
    retire_pairs=[]
    for relative in retired:
        old=(RELEASE/relative).resolve();saved=(backup/relative).resolve()
        assert old.is_relative_to(RELEASE.resolve()) and saved.is_relative_to(backup)
        if old.exists():
            previous=digest(old)
            # Earlier internal B1/B2/B3 copies predate the v13 manifest. Keep
            # their actual bytes in backup instead of assuming a v13 identity.
            if relative in expected:assert expected[relative]==previous,relative
            assert not saved.exists(),relative
            retire_pairs.append((old,saved,previous,relative))
    backup.mkdir(parents=True,exist_ok=True)
    save_json(backup/'delivery-verification.json',prior)
    checked=[]
    for source,relative,dest,saved,sha,previous in prepared:
        if previous is not None and previous!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dest),str(saved))
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            if source.stat().st_size>100_000_000:shutil.move(str(source),str(dest))
            else:shutil.copy2(source,dest)
        assert digest(dest)==sha;checked.append(dict(path=relative.as_posix(),sha256=sha))
    retired_verified=[]
    for old,saved,sha,relative in retire_pairs:
        saved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(old),str(saved))
        assert digest(saved)==sha;retired_verified.append(dict(path=relative,sha256=sha))
    save_json(RELEASE/'delivery-verification.json',dict(status='PASS',revision='native-v14',files=len(checked),backup=str(backup),
        gameDeployed=False,gameTested=False,largeFilesMoved=True,retired=retired_verified,verified=checked))
    save_json(WORK/'delivery-location.json',dict(release=str(RELEASE),largeFilesMoved=True,verification=str(RELEASE/'delivery-verification.json')))
    print('Delivered',len(checked),'verified files',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['static','animation','prepare','finalize','baseline','deliver'])
    globals()[parser.parse_args().stage]()
