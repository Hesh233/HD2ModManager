"""Deliver the verified A1/A2 subsets and retain B14-A as a positive control."""
import argparse
import copy
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files
import package_native_v12 as pack
from repack_native_b15 import build as repack

W=ROOT/'outputs/native-v23-b15-20261105';R=ROOT/'outputs/native-manual-20261103'
BACKUP=Path('backups/v23-b15-before-20261105')
REQUIRED=['scope-audit.json','candidate-tree.json','attachment-probe-audit.json','chef-compatibility-audit.json']
DOCUMENTS=('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md')


def prepare(offline=False):
    baseline=load(W/'baseline-delivery.json');assert baseline==load(R/'delivery-verification.json')and baseline['revision']=='native-v22'
    for row in baseline['verified']:assert digest(R/row['path'])==row['sha256'],row['path']
    save_json(W/'baseline-file-audit.json',dict(status='PASS',revision='native-v22',files=len(baseline['verified'])))
    required=REQUIRED+([]if offline else ['package-inspection.json'])
    for name in required:assert load(W/name)['status']=='PASS',name
    scope=load(W/'scope-audit.json');audit=load(W/'attachment-probe-audit.json');chef=load(W/'chef-compatibility-audit.json')
    assert scope['sourceSha256']==audit['sourceSha256']==digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua')
    assert scope['probeSha256']==audit['probeSha256']==digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua')
    assert chef['embeddedSourceSha256']==scope['baselineChefSourceSha256']
    for name,sha in chef['embeddedSourceSha256'].items():assert digest(ROOT/'HD2PhysBoneCompat/src'/name)==sha
    assert digest(R/'test01-配套动画.zip')==scope['animationSha256']
    packages=load(W/'static-packages.json')
    imported={}if offline else {r['package']:r['sha256']for r in load(W/'package-inspection.json')['packages']}
    for row in packages:
        assert digest(W/row['name'])==row['sha256']
        if not offline:assert imported[row['name']]==row['sha256']
        with zipfile.ZipFile(W/row['name'])as z:assert z.testzip()is None
    diag=W/'diagnostics/B15';diag.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'docs/native-v23-B15-20261105.md',diag/'测试说明.txt')
    shutil.copy2(ROOT/'tools/repack_native_b15.py',diag/'repack_native_b15.py')
    for variant in ('A1','A2'):
        folder=diag/'variants'/variant;folder.mkdir(parents=True,exist_ok=True)
        shutil.copy2(W/('hd2physbone-B15-'+variant+'.lua'),folder/'hd2physbone.lua')
        shutil.copy2(W/('B15-'+variant+'.json'),folder/'profile.json')
        shutil.copy2(W/'runtime'/variant/'manifest.json',folder/'manifest.json')
        (folder/'container-header.bin').write_bytes((W/'runtime'/variant/'9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    rebuilt=repack(diag)
    for variant,row in rebuilt['variants'].items():assert row['patchSha256']==digest(W/'runtime'/variant/'9ba626afa44a3aa3.patch_0')
    save_json(W/'repack-audit.json',dict(rebuilt,patchMatchesDelivered=True))
    pairs=[(ROOT/'HD2PhysBoneCompat/src'/name,Path('src')/name)for name in chef['embeddedSourceSha256']]
    pairs.extend((ROOT/'HD2PhysBoneCompat/test'/name,Path('test')/name)for name in
        ('attachments_layout_harness.lua','attachment_probe_harness.lua','strict_id32_fixture.lua'))
    toolnames=('analyze_native_b14_a.py','prepare_native_v23_b15.py','audit_native_v23_b15.py','audit_native_v23_b15_chef.py',
        'audit_native_v23_b15_import.py','package_native_v23_b15.py','audit_native_v20_b12.py','audit_native_v20_b12_chef.py',
        'audit_native_v18_b9.py','audit_native_v15_chef.py','audit_native_v16_import.py','audit_native_attachment_layouts.py','analyze_native_b9_log.py','package_native_v12.py')
    pairs.extend((ROOT/'tools'/name,Path('tools')/name)for name in toolnames)
    pairs.extend((W/name,Path('reports')/name)for name in required+['repack-audit.json','baseline-file-audit.json'])
    pairs.extend((p,Path('evidence')/r)for p,r in files(W/'evidence'))
    for source,relative in pairs:
        dest=diag/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
    (diag/'README.txt').write_text('B15 contains the exact B14 runtime with two disjoint candidate subsets. Run python repack_native_b15.py here using standard Python to reproduce both patches. Other audits require the original workspace and baseline. Test A1, then A2 separately. Individual driver and final grip correction remain unconfirmed.\n',encoding='utf-8')
    pack.WORK=W;increment=pack.archive('B15-增量排查工程.zip',[(p,r)for p,r in files(diag)if r.parts[0]!='rebuilt'])
    save_json(W/'incremental-source-package.json',increment)
    for name in DOCUMENTS:shutil.copy2(ROOT/'docs/native-v23-B15-20261105.md',W/name)
    report=load(R/'package-report.json');assert not any('B15-'in r['name']for r in report['packages'])
    report['packages'].extend(packages+[increment])
    report.update(revision='native-v23',runtimeRevision='native-v23-B15',probe='B15-A1/A2',animationRevision='native-v15',
        animationUserAccepted=True,gameTested=False,gameDeployed=False,incrementalDelivery=True,
        validationStage='offline-ready-import-pending'if offline else 'isolated-import-verified',
        incrementalReports={n:digest(W/n)for n in required+['repack-audit.json','baseline-file-audit.json']},
        sourcePackages={'base':'test01-源工程.zip','previousIncrement':'B14-增量排查工程.zip','increment':'B15-增量排查工程.zip'})
    report.setdefault('priorUserResults',{})['B14-A']='左右手位置未变，武器整体上移。'
    result_path='project/diagnostics/B15/evidence/B14-A-game-result.json'
    report.setdefault('gameResults',{})['B14-A']=dict(status='candidate-set-positive',report=result_path,
        sha256=digest(W/'evidence/B14-A-game-result.json'),individualDriverConfirmed=False)
    save_json(W/'package-report.json',report)
    matrix=load(R/'ab-matrix.json');matrix.update(revision='native-v23',gameTested=False,nextTest='B15-A1')
    prior=next(g for g in matrix['groups']if g['group']=='B14-A')
    prior.update(status='tested-weapon-response-positive',gameTested=True,result='武器整体上移，左右手未变；15次17节点位移回读通过，具体驱动节点待二分。',resultReport=result_path)
    for variant,row in zip(('A1','A2'),packages):
        matrix['groups'].append(dict(group='B15-'+variant,package=row['name'],status='awaiting-game-test',gameTested=False,
            description='B14-A的四个父级组；运行代码、位移、时机保持不变。',profileSha256=digest(W/('B15-'+variant+'.json'))))
    save_json(W/'ab-matrix.json',matrix)
    print('B15 source, subset regressions, repack and baseline verified; imports '+('pending.'if offline else 'PASS.'))


def deliver():
    baseline=load(R/'delivery-verification.json');assert baseline==load(W/'baseline-delivery.json')and baseline['revision']=='native-v22'
    expected={r['path']:r['sha256']for r in baseline['verified']}
    for name,sha in expected.items():assert digest(R/name)==sha,name
    report=load(W/'package-report.json');assert report['revision']=='native-v23'and report['validationStage']=='isolated-import-verified'
    assert load(W/'package-inspection.json')['status']=='PASS'
    for name,sha in report['incrementalReports'].items():assert digest(W/name)==sha
    packages=load(W/'static-packages.json')+[load(W/'incremental-source-package.json')]
    for row in packages:assert digest(W/row['name'])==row['sha256']
    pairs=[(W/r['name'],Path(r['name']))for r in packages]
    pairs.extend((p,Path('project/diagnostics/B15')/r)for p,r in files(W/'diagnostics/B15')if r.parts[0]!='rebuilt')
    pairs.extend((W/name,Path(name))for name in ('package-report.json','ab-matrix.json',*DOCUMENTS))
    backup=(R/BACKUP).resolve();assert backup.is_relative_to(R.resolve())and not backup.exists()
    prepared=[]
    for source,relative in pairs:
        source=source.resolve();dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert source.is_relative_to(W.resolve())and dest.is_relative_to(R.resolve())and saved.is_relative_to(backup)
        old=digest(dest)if dest.exists()else None
        if old is not None:assert old==expected[relative.as_posix()]
        prepared.append((source,relative,dest,saved,old,digest(source)))
    backup.mkdir(parents=True);shutil.copy2(R/'delivery-verification.json',backup/'delivery-verification.json')
    expected[(BACKUP/'delivery-verification.json').as_posix()]=digest(backup/'delivery-verification.json')
    for source,relative,dest,saved,old,sha in prepared:
        if old is not None and old!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
            assert digest(saved)==old;expected[(BACKUP/relative).as_posix()]=old
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        assert digest(dest)==sha;expected[relative.as_posix()]=sha
    for name,sha in expected.items():assert digest(R/name)==sha,name
    result=copy.deepcopy(baseline)
    result.update(status='PASS',revision='native-v23',runtimeRevision='native-v23-B15',files=len(expected),backup=str(backup),
        gameDeployed=False,gameTested=False,lastGameResult='project/diagnostics/B15/evidence/B14-A-game-result.json',
        verified=[dict(path=p,sha256=s)for p,s in sorted(expected.items())])
    save_json(R/'delivery-verification.json',result)
    print('Delivered B15;',len(expected),'SHA-verified files; B14 controls and v15 animation retained; no deployment.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','prepare-offline','deliver']);stage=parser.parse_args().stage
    if stage=='deliver':deliver()
    else:prepare(offline=stage=='prepare-offline')
