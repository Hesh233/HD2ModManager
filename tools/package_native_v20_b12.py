"""Deliver B12 diagnostics with exact baseline checks and isolated import."""
import argparse
import copy
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files
import package_native_v12 as pack
from repack_native_b12 import build as repack
W=ROOT/'outputs/native-v20-b12-20261104';R=ROOT/'outputs/native-manual-20261103'
REQUIRED=['B10-game-findings.json','scope-audit.json','candidate-tree.json','scene-observer-audit.json','attachment-probe-audit.json','chef-compatibility-audit.json']
DOCUMENTS=('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md')
BACKUP=Path('backups/v20-b12-before-20261104')


def prepare():
    for name in REQUIRED:assert load(W/name)['status']=='PASS',name
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua';module=ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'
    scope=load(W/'scope-audit.json');audit=load(W/'attachment-probe-audit.json');chef=load(W/'chef-compatibility-audit.json')
    assert digest(source)==scope['sourceSha256']==audit['sourceSha256']==chef['embeddedSourceSha256']['native_attachments.lua']
    assert digest(module)==scope['probeSha256']==audit['probeSha256']==chef['embeddedSourceSha256']['native_attachment_probe.lua']
    assert digest(source)==load(W/'scene-observer-audit.json')['sourceSha256']
    for name,sha in chef['embeddedSourceSha256'].items():assert digest(ROOT/'HD2PhysBoneCompat/src'/name)==sha,name
    assert digest(R/'test01-配套动画.zip')==scope['animationSha256']
    diag=W/'diagnostics/B12';diag.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'docs/native-v20-B12-20261104.md',diag/'测试说明.txt')
    shutil.copy2(ROOT/'tools/repack_native_b12.py',diag/'repack_native_b12.py')
    for variant in ('A','B','ALL'):
        folder=diag/'variants'/variant;folder.mkdir(parents=True,exist_ok=True)
        shutil.copy2(W/('hd2physbone-B12-'+variant+'.lua'),folder/'hd2physbone.lua')
        shutil.copy2(W/('B12-'+variant+'.json'),folder/'profile.json')
        shutil.copy2(W/'runtime'/variant/'manifest.json',folder/'manifest.json')
        (folder/'container-header.bin').write_bytes((W/'runtime'/variant/'9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    result=repack(diag)
    for variant,row in result['variants'].items():assert row['patchSha256']==digest(W/'runtime'/variant/'9ba626afa44a3aa3.patch_0')
    save_json(W/'repack-audit.json',dict(result,patchMatchesDelivered=True))
    reports=diag/'reports';reports.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'outputs/native-b10-observation-20261104/分析报告.md',reports/'B10-实机分析报告.md')
    for name in REQUIRED+['feedback.json','repack-audit.json','package-inspection.json','import-library-cleanup.json']:
        if (W/name).exists():shutil.copy2(W/name,reports/name)
    pairs=[(ROOT/'HD2PhysBoneCompat/src'/name,Path('src')/name)for name in chef['embeddedSourceSha256']]
    pairs.append((R/'project/diagnostics/B10/src/native_attachments.lua',Path('src/control/native_attachments-B10.lua')))
    pairs.extend((ROOT/'HD2PhysBoneCompat/test'/name,Path('test')/name)for name in
        ('attachments_layout_harness.lua','split_model_refresh_harness.lua','scene_observer_harness.lua','attachment_probe_harness.lua'))
    pairs.extend((p,Path('tools')/p.name)for p in (ROOT/'tools').glob('*native_v20_b12*.py'))
    pairs.extend((ROOT/'tools'/name,Path('tools')/name)for name in
        ('audit_native_v18_b9.py','audit_native_v15_chef.py','audit_native_v16_import.py','audit_native_attachment_layouts.py','analyze_native_b9_log.py','Cleanup-Native-V20B12Imports.ps1'))
    for original,relative in pairs:
        dest=diag/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
    (diag/'README.txt').write_text('B12: explicit Avatar attachment bisection, test01 body selection only. Run python repack_native_b12.py here with standard Python to reproduce all three runtime patches. Other audits require the original workspace. A/B game results and actual weapon driver are pending. Do not deploy multiple variants together.\n',encoding='utf-8')
    pack.WORK=W
    save_json(W/'incremental-source-package.json',pack.archive('B12-增量排查工程.zip',[(p,r)for p,r in files(diag)if r.parts[0]!='rebuilt']))
    for name in DOCUMENTS:shutil.copy2(ROOT/'docs/native-v20-B12-20261104.md',W/name)
    baseline=load(W/'baseline-delivery.json')
    for row in baseline['verified']:assert digest(R/row['path'])==row['sha256'],'Existing delivery changed: '+row['path']
    save_json(W/'baseline-file-audit.json',dict(status='PASS',files=len(baseline['verified']),revision=baseline['revision']))
    print('B12 source, standalone repack, instructions and existing delivery bytes verified.')


def finalize():
    inspection=load(W/'package-inspection.json');assert inspection['status']=='PASS'
    packages=load(W/'static-packages.json');imported={r['package']:r['sha256']for r in inspection['packages']}
    for row in packages:
        assert imported.get(row['name'])==row['sha256']==digest(W/row['name'])
        with zipfile.ZipFile(W/row['name'])as z:assert z.testzip()is None
    prepare();packages.append(load(W/'incremental-source-package.json'))
    report=copy.deepcopy(load(R/'package-report.json'))
    report.update(revision='native-v20',animationRevision='native-v15',animationUserAccepted=True,
        runtimeRevision='native-v20-B12',gameTested=False,probe='v20-B12',incrementalDelivery=True,
        incrementalReports={n:digest(W/n)for n in REQUIRED+['repack-audit.json','package-inspection.json','baseline-file-audit.json']})
    assert not set(r['name']for r in packages)&set(r['name']for r in report['packages'])
    report['packages'].extend(packages)
    report['sourcePackages']={'base':'test01-源工程.zip','previousIncrement':'B10-增量排查工程.zip','increment':'B12-增量排查工程.zip'}
    report['priorUserResults']={'B10':load(W/'feedback.json')['B10'],'hellpad':load(W/'feedback.json')['hellpadUserConfirmed']}
    save_json(W/'package-report.json',report)
    matrix=load(R/'ab-matrix.json');matrix.update(revision='native-v20',animationRevision='native-v15',gameTested=False)
    for group in matrix['groups']:
        if group['group']=='B10':group.update(status='tested-roundtrip-pass-grip-unchanged',gameTested=True,
            result='64轮4096次原样回写通过；握持未改善；手形、样本瓶、接缝正常。')
    for variant,row in zip(('A','B','ALL'),packages):
        matrix['groups'].append(dict(group='B12-'+variant,package=row['name'],status='awaiting-game-bisection',gameTested=False,
            description='仅 test01 匹配时，4秒原位/4秒上移60厘米；父级分组，不叠加。',profileSha256=digest(W/('B12-'+variant+'.json'))))
    save_json(W/'ab-matrix.json',matrix)
    print('B12 finalized after isolated imports; game driver remains unconfirmed.')


def deliver():
    current=load(R/'delivery-verification.json');assert current==load(W/'baseline-delivery.json')and current['revision']=='native-v19'
    expected={r['path']:r['sha256']for r in current['verified']}
    for relative,sha in expected.items():assert digest(R/relative)==sha,relative
    report=load(W/'package-report.json');assert report['revision']=='native-v20'
    for name,sha in report['incrementalReports'].items():assert digest(W/name)==sha
    assert load(W/'package-inspection.json')['status']=='PASS'
    packages=load(W/'static-packages.json')+[load(W/'incremental-source-package.json')]
    for row in packages:assert digest(W/row['name'])==row['sha256']
    pairs=[(W/r['name'],Path(r['name']))for r in packages]
    pairs.extend((p,Path('project/diagnostics/B12')/r)for p,r in files(W/'diagnostics/B12')if r.parts[0]!='rebuilt')
    pairs.extend((W/name,Path(name))for name in ('package-report.json','ab-matrix.json',*DOCUMENTS))
    backup=(R/BACKUP).resolve();assert backup.is_relative_to(R.resolve())and not backup.exists()
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
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved);assert digest(saved)==old
            expected[(BACKUP/relative).as_posix()]=old
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
        assert digest(dest)==sha;expected[relative.as_posix()]=sha
    for relative,sha in expected.items():assert digest(R/relative)==sha,relative
    save_json(R/'delivery-verification.json',dict(status='PASS',revision='native-v20',animationRevision='native-v15',
        animationUserAccepted=True,runtimeRevision='native-v20-B12',files=len(expected),backup=str(backup),
        gameDeployed=False,gameTested=False,incrementalDelivery=True,
        verified=[dict(path=p,sha256=s)for p,s in sorted(expected.items())]))
    print('Delivered B12;',len(expected),'verified files; v15 retained; game not deployed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','finalize','deliver'])
    globals()[parser.parse_args().stage]()
