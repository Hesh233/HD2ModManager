"""Incremental B9 delivery with B8 retirement, byte checks and guarded import."""
import argparse
import copy
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files
import package_native_v12 as pack
from repack_native_b9 import build as repack
W=ROOT/'outputs/native-v18-20261104';R=ROOT/'outputs/native-manual-20261103'
REQUIRED=['model-arm-topology.json','scope-audit.json','scene-observer-audit.json','chef-compatibility-audit.json']
BACKUP=Path('backups/v18-before-20261104')
DOCUMENTS=('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md')
RETIRED='AB测试/B8-模型骨骼直接写入.zip'
RETIRED_DEST=BACKUP/'retired/B8-模型骨骼直接写入.zip'


def prepare():
    for name in REQUIRED:assert load(W/name)['status']=='PASS',name
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    assert digest(source)==load(W/'scope-audit.json')['sourceSha256']==load(W/'scene-observer-audit.json')['sourceSha256']
    assert digest(source)==load(W/'chef-compatibility-audit.json')['embeddedSourceSha256']['native_attachments.lua']
    observer=ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua'
    assert digest(observer)==load(W/'scope-audit.json')['observerSha256']==load(W/'scene-observer-audit.json')['observerSha256']
    assert digest(observer)==load(W/'chef-compatibility-audit.json')['embeddedSourceSha256']['native_scene_observer.lua']
    assert digest(R/'test01-配套动画.zip')==load(W/'scope-audit.json')['animationSha256']
    diag=W/'diagnostics/B9';diag.mkdir(parents=True,exist_ok=True)
    for name in ('hd2physbone-B9.lua','B9.json'):shutil.copy2(W/name,diag/name)
    for name in ('manifest.json','测试说明.txt'):shutil.copy2(W/'runtime/B9'/name,diag/name)
    (diag/'container-header.bin').write_bytes((W/'runtime/B9/9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    shutil.copy2(ROOT/'tools/repack_native_b9.py',diag/'repack_native_b9.py')
    result=repack(diag);assert result['patchSha256']==digest(W/'runtime/B9/9ba626afa44a3aa3.patch_0')
    save_json(W/'repack-audit.json',dict(result,patchMatchesDelivered=True))
    reports=diag/'reports';reports.mkdir(exist_ok=True)
    for name in REQUIRED+['feedback.json','repack-audit.json','package-inspection.json','import-library-cleanup.json']:
        if (W/name).exists():shutil.copy2(W/name,reports/name)
    pairs=[(source,Path('src/native_attachments.lua')),(observer,Path('src/native_scene_observer.lua')),
        (R/'project/diagnostics/B7/src/native_attachments.lua',Path('src/control/native_attachments-B7.lua')),
        *[(ROOT/'HD2PhysBoneCompat/test'/name,Path('test')/name)for name in
            ('attachments_layout_harness.lua','split_model_refresh_harness.lua','scene_observer_harness.lua')],
        *[(s,Path('tools')/s.name)for s in (ROOT/'tools').glob('*native_v18*.py')],
        *[(ROOT/'tools'/name,Path('tools')/name)for name in
            ('analyze_native_b9_log.py','native_model_arm_locals.py','audit_native_attachment_layouts.py',
             'audit_native_v15_chef.py','audit_native_v16_import.py','Cleanup-Native-V18Imports.ps1')]]
    for original,relative in pairs:
        dest=diag/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
    (diag/'README.txt').write_text(
        'B9 = accepted B7 behavior plus bounded read-only scene telemetry. No B8 model-local writes. '
        'Run python repack_native_b9.py here to reproduce the runtime patch using standard Python. '
        'tools/analyze_native_b9_log.py --log <log> --output <folder> needs numpy; analysis is offline. '
        'Other audit tools require the original workspace, real Unit inputs, Chef fixture, and prior reports. '
        'Synthetic parent captures are not game evidence. Model roundtrip and contact correction remain pending.\n',encoding='utf-8')
    pack.WORK=W
    save_json(W/'incremental-source-package.json',pack.archive('B9-增量排查工程.zip',[(p,r)for p,r in files(diag)if r.parts[0]!='rebuilt']))
    for name in DOCUMENTS:shutil.copy2(ROOT/'docs/native-v18-B9-20261104.md',W/name)
    baseline=load(W/'baseline-delivery.json')
    for row in baseline['verified']:assert digest(R/row['path'])==row['sha256'],'Existing delivery changed: '+row['path']
    save_json(W/'baseline-file-audit.json',dict(status='PASS',files=len(baseline['verified']),revision=baseline['revision']))
    print('B9 standalone repack, source increment and documentation ready; baseline bytes verified.')


def finalize():
    inspection=load(W/'package-inspection.json');assert inspection['status']=='PASS'
    packages=load(W/'static-packages.json');imported={row['package']:row['sha256']for row in inspection['packages']}
    for row in packages:
        assert imported.get(row['name'])==row['sha256']==digest(W/row['name'])
        with zipfile.ZipFile(W/row['name'])as z:assert z.testzip()is None
    prepare();packages.append(load(W/'incremental-source-package.json'))
    report=copy.deepcopy(load(R/'package-report.json'))
    report.update(revision='native-v18',animationRevision='native-v15',animationUserAccepted=True,
        runtimeRevision='native-v18-B9',gameTested=False,probe='v18-B9',incrementalDelivery=True,
        incrementalReports={n:digest(W/n)for n in REQUIRED+['repack-audit.json','package-inspection.json','baseline-file-audit.json']})
    assert not any(row['name']==packages[0]['name']for row in report['packages'])
    for row in report['packages']:
        if row['name']==RETIRED:row.update(name=RETIRED_DEST.as_posix(),status='retired-game-test-failed')
    report['packages'].extend(packages)
    report['sourcePackages']={'base':'test01-源工程.zip','previousIncrement':'B8-增量排查工程.zip','increment':'B9-增量排查工程.zip'}
    report['priorUserResults']={k:load(W/'feedback.json')[k]for k in ('B7','B8')}
    save_json(W/'package-report.json',report)
    matrix=load(R/'ab-matrix.json');matrix.update(revision='native-v18',animationRevision='native-v15',gameTested=False)
    for group in matrix['groups']:
        if group['group']=='B8':group.update(status='retired-game-test-failed',gameTested=True,package=RETIRED_DEST.as_posix(),
            result='手部拉伸变细，握持无改善。归档停用；B9 回到 B7 基准。')
    assert not any(g['group']=='B9'for g in matrix['groups'])
    matrix['groups'].append(dict(group='B9',package=packages[0]['name'],status='awaiting-game-observation',gameTested=False,
        description='B7 稳定基准，只读采集真实父节点、完整局部/世界矩阵和缩放。',profileSha256=digest(W/'B9.json')))
    save_json(W/'ab-matrix.json',matrix)
    print('B9 finalized after isolated import; actual scene observation remains pending.')


def deliver():
    current=load(R/'delivery-verification.json')
    assert current==load(W/'baseline-delivery.json')and current['revision']=='native-v17'
    expected={r['path']:r['sha256']for r in current['verified']}
    for relative,sha in expected.items():assert digest(R/relative)==sha,'Existing delivery changed: '+relative
    report=load(W/'package-report.json');assert report['revision']=='native-v18'
    for name,sha in report['incrementalReports'].items():assert digest(W/name)==sha
    assert load(W/'package-inspection.json')['status']=='PASS'
    packages=load(W/'static-packages.json')+[load(W/'incremental-source-package.json')]
    for row in packages:assert digest(W/row['name'])==row['sha256']
    pairs=[(W/row['name'],Path(row['name']))for row in packages]
    pairs.extend((p,Path('project/diagnostics/B9')/r)for p,r in files(W/'diagnostics/B9')if r.parts[0]!='rebuilt')
    pairs.extend((W/name,Path(name))for name in ('package-report.json','ab-matrix.json',*DOCUMENTS))
    backup=(R/BACKUP).resolve();assert backup.is_relative_to(R.resolve())and not backup.exists()
    retired=(R/RETIRED).resolve();saved_retired=(R/RETIRED_DEST).resolve()
    assert retired.is_relative_to(R.resolve())and saved_retired.is_relative_to(backup)
    assert digest(retired)==expected[RETIRED]and not saved_retired.exists()
    prepared=[]
    for original,relative in pairs:
        original=original.resolve();dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert original.is_relative_to(W.resolve())and dest.is_relative_to(R.resolve())and saved.is_relative_to(backup)
        sha=digest(original);old=digest(dest)if dest.exists()else None
        if old is not None:assert expected.get(relative.as_posix())==old,'Untracked destination change: '+str(relative)
        prepared.append((original,relative,dest,saved,sha,old))
    backup.mkdir(parents=True);save_json(backup/'delivery-verification.json',current)
    expected[(BACKUP/'delivery-verification.json').as_posix()]=digest(backup/'delivery-verification.json')
    for original,relative,dest,saved,sha,old in prepared:
        if old is not None and old!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
            assert digest(saved)==old;expected[(BACKUP/relative).as_posix()]=old
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
        assert digest(dest)==sha;expected[relative.as_posix()]=sha
    # Single verified file retirement; never delete historical packages.
    saved_retired.parent.mkdir(parents=True,exist_ok=True);retired.rename(saved_retired)
    assert digest(saved_retired)==expected[RETIRED]
    expected[RETIRED_DEST.as_posix()]=expected.pop(RETIRED)
    for relative,sha in expected.items():assert digest(R/relative)==sha,relative
    save_json(R/'delivery-verification.json',dict(status='PASS',revision='native-v18',animationRevision='native-v15',
        animationUserAccepted=True,runtimeRevision='native-v18-B9',files=len(expected),backup=str(backup),
        gameDeployed=False,gameTested=False,incrementalDelivery=True,
        verified=[dict(path=p,sha256=s)for p,s in sorted(expected.items())]))
    print('Delivered B9;',len(expected),'verified files; v15 and B7 retained, B8 archived, game not deployed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','finalize','deliver'])
    globals()[parser.parse_args().stage]()
