"""Deliver B8 as a small increment; preserve the accepted v15 animation and B7."""
import argparse
import copy
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files
import package_native_v12 as pack
from repack_native_b8 import build as repack
W=ROOT/'outputs/native-v17-20261104'
R=ROOT/'outputs/native-manual-20261103'
REQUIRED=['model-arm-topology.json','runtime-evidence.json','scope-audit.json',
          'model-arm-local-audit.json','chef-compatibility-audit.json']
BACKUP=Path('backups/v17-before-20261104')
DOCUMENTS=('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md')


def prepare():
    for name in REQUIRED:assert load(W/name)['status']=='PASS',name
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    assert digest(source)==load(W/'scope-audit.json')['sourceSha256']==load(W/'model-arm-local-audit.json')['sourceSha256']
    assert digest(source)==load(W/'chef-compatibility-audit.json')['embeddedSourceSha256']['native_attachments.lua']
    assert digest(R/'test01-配套动画.zip')==load(W/'scope-audit.json')['animationSha256']
    diag=W/'diagnostics/B8';diag.mkdir(parents=True,exist_ok=True)
    for name in ('hd2physbone-B8.lua','B8.json'):shutil.copy2(W/name,diag/name)
    for name in ('manifest.json','测试说明.txt'):shutil.copy2(W/'runtime/B8'/name,diag/name)
    (diag/'container-header.bin').write_bytes((W/'runtime/B8/9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    shutil.copy2(ROOT/'tools/repack_native_b8.py',diag/'repack_native_b8.py')
    result=repack(diag)
    assert result['patchSha256']==digest(W/'runtime/B8/9ba626afa44a3aa3.patch_0')
    save_json(W/'repack-audit.json',dict(result,patchMatchesDelivered=True))
    reports=diag/'reports';reports.mkdir(exist_ok=True)
    for name in REQUIRED+['feedback.json','repack-audit.json','B7-game-evidence.log','package-inspection.json','import-library-cleanup.json']:
        if (W/name).exists():shutil.copy2(W/name,reports/name)
    pairs=[(source,Path('src/native_attachments.lua')),
        (ROOT/'tools/Cleanup-Native-V17Imports.ps1',Path('tools/Cleanup-Native-V17Imports.ps1')),
        (R/'project/diagnostics/B7/src/native_attachments.lua',Path('src/control/native_attachments-B7.lua')),
        *[(ROOT/'HD2PhysBoneCompat/test'/name,Path('test')/name)for name in
            ('attachments_layout_harness.lua','split_model_refresh_harness.lua','model_arm_local_harness.lua')],
        *[(s,Path('tools')/s.name)for s in (ROOT/'tools').glob('*native_v17*.py')],
        *[(ROOT/'tools'/name,Path('tools')/name)for name in
            ('native_model_arm_locals.py','audit_native_attachment_layouts.py','audit_native_v15_chef.py','audit_native_v16_import.py')]]
    for source,relative in pairs:
        dest=diag/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    (diag/'README.txt').write_text(
        'B8 is an opt-in direct model-local copy probe for accepted v15 animation. '
        'Run python repack_native_b8.py in this directory to reproduce the exact runtime patch. '
        'The tools/ and test/ folders document workspace checks; they require the original project and B7 increment. '
        'Synthetic skin invalidation tests do not establish real GPU behavior. Game visual acceptance is pending.\n',encoding='utf-8')
    pack.WORK=W
    source_package=pack.archive('B8-增量排查工程.zip',[(p,r)for p,r in files(diag)if r.parts[0]!='rebuilt'])
    save_json(W/'incremental-source-package.json',source_package)
    for name in DOCUMENTS:shutil.copy2(ROOT/'docs/native-v17-B8-20261104.md',W/name)
    print('B8 source, standalone repack and test instructions prepared.')


def finalize():
    inspection=load(W/'package-inspection.json');assert inspection['status']=='PASS'
    packages=load(W/'static-packages.json')
    imported={row['package']:row['sha256']for row in inspection['packages']}
    for row in packages:
        assert imported.get(row['name'])==row['sha256']==digest(W/row['name'])
        with zipfile.ZipFile(W/row['name'])as z:assert z.testzip()is None
    prepare()
    packages.append(load(W/'incremental-source-package.json'))
    report=copy.deepcopy(load(R/'package-report.json'))
    report.update(revision='native-v17',animationRevision='native-v15',animationUserAccepted=True,
        runtimeRevision='native-v17-B8',gameTested=False,probe='v17-B8',incrementalDelivery=True,
        incrementalReports={n:digest(W/n)for n in REQUIRED+['repack-audit.json','package-inspection.json']})
    assert not any(row['name']==packages[0]['name']for row in report['packages'])
    report['packages'].extend(packages)
    report['sourcePackages']={'base':'test01-源工程.zip','previousIncrement':'B7-增量排查工程.zip','increment':'B8-增量排查工程.zip'}
    report['priorUserResults']={'B7':load(W/'feedback.json')['B7']}
    save_json(W/'package-report.json',report)
    matrix=load(R/'ab-matrix.json');matrix.update(revision='native-v17',animationRevision='native-v15',gameTested=False)
    for group in matrix['groups']:
        if group['group']=='B7':group.update(status='tested-no-grip-improvement',gameTested=True,
            result='握持与无 Lua 一致；样本瓶稳定，切分处无裂缝。保留为稳定对照。')
    assert not any(g['group']=='B8'for g in matrix['groups'])
    matrix['groups'].append(dict(group='B8',package=packages[0]['name'],status='awaiting-game-test',
        description='保持 B7 算法、目标和回调，仅将相同的八个手臂本地姿态直接复制到匹配模型。',
        profileSha256=digest(W/'B8.json')))
    save_json(W/'ab-matrix.json',matrix)
    print('B8 runtime and source packages finalized after isolated import.')


def deliver():
    current=load(R/'delivery-verification.json')
    assert current==load(W/'baseline-delivery.json')and current['revision']=='native-v16'
    expected={r['path']:r['sha256']for r in current['verified']}
    for relative,sha in expected.items():assert digest(R/relative)==sha,'Existing delivery changed: '+relative
    report=load(W/'package-report.json');assert report['revision']=='native-v17'
    for name,sha in report['incrementalReports'].items():assert digest(W/name)==sha
    assert load(W/'package-inspection.json')['status']=='PASS'
    packages=load(W/'static-packages.json')+[load(W/'incremental-source-package.json')]
    for row in packages:assert digest(W/row['name'])==row['sha256']
    pairs=[(W/row['name'],Path(row['name']))for row in packages]
    pairs.extend((p,Path('project/diagnostics/B8')/r)for p,r in files(W/'diagnostics/B8')if r.parts[0]!='rebuilt')
    pairs.extend((W/name,Path(name))for name in ('package-report.json','ab-matrix.json',*DOCUMENTS))
    backup=(R/BACKUP).resolve();assert backup.is_relative_to(R.resolve())and not backup.exists()
    prepared=[]
    for source,relative in pairs:
        source=source.resolve();dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert source.is_relative_to(W.resolve())and dest.is_relative_to(R.resolve())and saved.is_relative_to(backup)
        sha=digest(source);old=digest(dest)if dest.exists()else None
        if old is not None:assert expected.get(relative.as_posix())==old,'Untracked destination change: '+str(relative)
        prepared.append((source,relative,dest,saved,sha,old))
    backup.mkdir(parents=True)
    save_json(backup/'delivery-verification.json',current)
    expected[(BACKUP/'delivery-verification.json').as_posix()]=digest(backup/'delivery-verification.json')
    for source,relative,dest,saved,sha,old in prepared:
        if old is not None and old!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
            assert digest(saved)==old;expected[(BACKUP/relative).as_posix()]=old
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        assert digest(dest)==sha;expected[relative.as_posix()]=sha
    save_json(R/'delivery-verification.json',dict(status='PASS',revision='native-v17',animationRevision='native-v15',
        animationUserAccepted=True,runtimeRevision='native-v17-B8',files=len(expected),backup=str(backup),
        gameDeployed=False,gameTested=False,incrementalDelivery=True,
        verified=[dict(path=p,sha256=s)for p,s in sorted(expected.items())]))
    print('Delivered B8; v15 animation and B7 retained;',len(expected),'verified files.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','finalize','deliver'])
    globals()[parser.parse_args().stage]()
