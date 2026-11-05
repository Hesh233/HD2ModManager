"""Deliver the small B7 increment and archive the failed B6 probe."""
import argparse
import copy
import shutil
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files
import package_native_v12 as pack
from repack_native_b7 import build as repack
W=ROOT/'outputs/native-v16-20261104'
R=ROOT/'outputs/native-manual-20261103'
REQUIRED=['skin-weights.json','consumer-coverage.json','runtime-evidence.json',
          'scope-audit.json','split-model-audit.json','chef-compatibility-audit.json','package-inspection.json']
B6=Path('AB测试/B6-update时机对照.zip')
BACKUP=Path('backups/v16-before-20261104')


def finalize():
    for name in REQUIRED:assert load(W/name)['status']=='PASS',name
    packages=load(W/'static-packages.json')
    imports={row['package']:row['sha256'] for row in load(W/'package-inspection.json')['packages']}
    for row in packages:assert imports.get(row['name'])==row['sha256']==digest(W/row['name'])
    assert digest(R/'test01-配套动画.zip')==load(W/'scope-audit.json')['animationSha256']
    diag=W/'diagnostics/B7';diag.mkdir(parents=True,exist_ok=True)
    for name in ('hd2physbone-B7.lua','B7.json'):shutil.copy2(W/name,diag/name)
    for name in ('manifest.json','测试说明.txt'):shutil.copy2(W/'runtime/B7'/name,diag/name)
    (diag/'container-header.bin').write_bytes((W/'runtime/B7/9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    shutil.copy2(ROOT/'tools/repack_native_b7.py',diag/'repack_native_b7.py')
    result=repack(diag)
    assert result['patchSha256']==digest(W/'runtime/B7/9ba626afa44a3aa3.patch_0')
    save_json(W/'repack-audit.json',dict(result,patchMatchesDelivered=True))
    reports=diag/'reports';reports.mkdir(exist_ok=True)
    for name in REQUIRED+['feedback.json','repack-audit.json','import-library-cleanup.json',
                          'test01-v15-B6-evidence.log','test01-v14-B5-evidence.log']:
        if (W/name).exists():shutil.copy2(W/name,reports/name)
    for source,relative in [
        (ROOT/'HD2PhysBoneCompat/src/native_attachments.lua',Path('src/native_attachments.lua')),
        (R/'project/source-code/HD2PhysBoneCompat/src/native_attachments.lua',Path('src/control/native_attachments-B5.lua')),
        (ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua',Path('test/attachments_layout_harness.lua')),
        (ROOT/'HD2PhysBoneCompat/test/split_model_refresh_harness.lua',Path('test/split_model_refresh_harness.lua')),
        *[(s,Path('tools')/s.name) for s in (ROOT/'tools').glob('*native_v16*.py')],
        (ROOT/'tools/native_attachment_layouts.py',Path('tools/native_attachment_layouts.py')),
        (ROOT/'tools/NativeArmSkinAudit/Program.cs',Path('tools/NativeArmSkinAudit/Program.cs')),
        (ROOT/'tools/NativeArmSkinAudit/NativeArmSkinAudit.csproj',Path('tools/NativeArmSkinAudit/NativeArmSkinAudit.csproj')),
    ]:
        target=diag/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (diag/'README.txt').write_text(
        'B7 increment for accepted v15 animations. Run python repack_native_b7.py here to reproduce the runtime patch. '
        'The resulting patch SHA256 is checked in reports/repack-audit.json. '
        'The tools/ and test/ files document workspace analysis; their full regression dependencies remain in the original project. '
        'Game visual acceptance is pending.\n',encoding='utf-8')
    pack.WORK=W
    source=pack.archive('B7-增量排查工程.zip',[(p,r) for p,r in files(diag) if r.parts[0]!='rebuilt'])
    packages.append(source)
    old=load(R/'package-report.json');report=copy.deepcopy(old)
    report.update(revision='native-v16',animationRevision='native-v15',animationUserAccepted=True,
                  runtimeRevision='native-v16-B7',gameTested=False,probe='v16-B7',
                  incrementalDelivery=True,incrementalReports={name:digest(W/name) for name in REQUIRED+['repack-audit.json']})
    for row in report['packages']:
        if row['name']==B6.as_posix():row.update(name=(BACKUP/B6).as_posix(),status='withdrawn-user-reported-regression')
    report['packages'].extend(packages)
    report['sourcePackages']={'base':'test01-源工程.zip','increment':'B7-增量排查工程.zip'}
    save_json(W/'package-report.json',report)
    matrix=load(R/'ab-matrix.json');matrix.update(revision='native-v16',animationRevision='native-v15',gameTested=False)
    for group in matrix['groups']:
        if group['group']=='B6':group.update(package=(BACKUP/B6).as_posix(),status='withdrawn',
            result='样本瓶闪烁、切分裂缝、握持无改善；停用。')
        if group['group']=='B5':group['result']='v15 动画下，握持与不装 Lua 一致。'
    assert not any(g['group']=='B7' for g in matrix['groups'])
    matrix['groups'].append(dict(group='B7',package=packages[0]['name'],status='awaiting-game-test',
        description='保持 B5 render 与算法，补齐六个切分部件刷新；选择门槛保持原躯干/头盔。',
        profileSha256=digest(W/'B7.json')))
    save_json(W/'ab-matrix.json',matrix)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md'):
        shutil.copy2(ROOT/'docs/native-v16-B7-20261104.md',W/name)
    print('B7 runtime, source increment and reports verified.')


def deliver():
    previous=load(W/'baseline-delivery.json');current=load(R/'delivery-verification.json')
    assert current==previous and current['revision']=='native-v15'
    expected={row['path']:row['sha256'] for row in current['verified']}
    for relative,sha in expected.items():assert digest(R/relative)==sha,'Existing delivery changed: '+relative
    backup=(R/BACKUP).resolve()
    assert backup.is_relative_to(R.resolve()) and not backup.exists()
    report=load(W/'package-report.json');assert report['revision']=='native-v16'
    additions=load(W/'static-packages.json')+[next(row for row in report['packages'] if row['name']=='B7-增量排查工程.zip')]
    pairs=[(W/row['name'],Path(row['name'])) for row in additions]
    pairs.extend((p,Path('project/diagnostics/B7')/r) for p,r in files(W/'diagnostics/B7') if r.parts[0]!='rebuilt')
    pairs.extend((W/name,Path(name)) for name in ('package-report.json','ab-matrix.json','先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md'))
    prepared=[]
    for source,relative in pairs:
        source=source.resolve();dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert source.is_relative_to(W.resolve()) and dest.is_relative_to(R.resolve()) and saved.is_relative_to(backup)
        sha=digest(source);old=digest(dest) if dest.exists() else None
        if old is not None:assert expected.get(relative.as_posix())==old,'Untracked destination edit: '+str(relative)
        prepared.append((source,relative,dest,saved,sha,old))
    b6=(R/B6).resolve();saved_b6=(backup/B6).resolve()
    assert b6.is_relative_to(R.resolve()) and saved_b6.is_relative_to(backup)
    assert digest(b6)==expected[B6.as_posix()]
    backup.mkdir(parents=True)
    save_json(backup/'delivery-verification.json',current)
    saved_b6.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(b6),str(saved_b6))
    expected[(BACKUP/B6).as_posix()]=expected.pop(B6.as_posix())
    for source,relative,dest,saved,sha,old in prepared:
        if old is not None and old!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dest),str(saved))
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(source,dest)
        assert digest(dest)==sha;expected[relative.as_posix()]=sha
    assert not b6.exists() and digest(saved_b6)==expected[(BACKUP/B6).as_posix()]
    save_json(R/'delivery-verification.json',dict(status='PASS',revision='native-v16',animationRevision='native-v15',
        animationUserAccepted=True,runtimeRevision='native-v16-B7',files=len(expected),backup=str(backup),
        gameDeployed=False,gameTested=False,incrementalDelivery=True,
        verified=[dict(path=p,sha256=s) for p,s in sorted(expected.items())]))
    print('Delivered B7 increment; retained v15 animation; B6 archived;',len(expected),'verified files.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['finalize','deliver'])
    globals()[parser.parse_args().stage]()
