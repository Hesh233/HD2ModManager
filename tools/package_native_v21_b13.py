"""Verify and deliver B13; quarantine the three crashing B12 runtime packages."""
import argparse
import copy
import shutil
import zipfile
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files
import package_native_v12 as pack
from repack_native_b13 import build as repack

W=ROOT/'outputs/native-v21-b13-20261104';R=ROOT/'outputs/native-manual-20261103'
BACKUP=Path('backups/v21-b13-before-20261104')
REQUIRED=['scope-audit.json','candidate-tree.json','scene-observer-audit.json','attachment-probe-audit.json',
          'id32-contract-audit.json','chef-compatibility-audit.json','package-inspection.json']
DOCUMENTS=('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md')


def prepare():
    baseline=load(W/'baseline-delivery.json')
    assert baseline==load(R/'delivery-verification.json') and baseline['revision']=='native-v20'
    for row in baseline['verified']:assert digest(R/row['path'])==row['sha256'],row['path']
    save_json(W/'baseline-file-audit.json',dict(status='PASS',revision='native-v20',files=len(baseline['verified'])))
    for name in REQUIRED:assert load(W/name)['status']=='PASS',name
    scope=load(W/'scope-audit.json');audit=load(W/'attachment-probe-audit.json');chef=load(W/'chef-compatibility-audit.json')
    assert digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua')==scope['sourceSha256']==audit['sourceSha256']==load(W/'scene-observer-audit.json')['sourceSha256']
    assert digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua')==scope['probeSha256']==audit['probeSha256']==load(W/'id32-contract-audit.json')['sourceSha256']
    for name,sha in chef['embeddedSourceSha256'].items():assert digest(ROOT/'HD2PhysBoneCompat/src'/name)==sha
    assert digest(R/'test01-配套动画.zip')==scope['animationSha256']
    imported={r['package']:r['sha256'] for r in load(W/'package-inspection.json')['packages']}
    packages=load(W/'static-packages.json')
    for row in packages:
        assert digest(W/row['name'])==row['sha256']==imported[row['name']]
        with zipfile.ZipFile(W/row['name'])as z:assert z.testzip()is None
    diag=W/'diagnostics/B13';diag.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'docs/native-v21-B13-20261104.md',diag/'测试说明.txt')
    shutil.copy2(ROOT/'tools/repack_native_b13.py',diag/'repack_native_b13.py')
    for variant in ('0','A','B','ALL'):
        folder=diag/'variants'/variant;folder.mkdir(parents=True,exist_ok=True)
        shutil.copy2(W/('hd2physbone-B13-'+variant+'.lua'),folder/'hd2physbone.lua')
        shutil.copy2(W/('B13-'+variant+'.json'),folder/'profile.json')
        shutil.copy2(W/'runtime'/variant/'manifest.json',folder/'manifest.json')
        (folder/'container-header.bin').write_bytes((W/'runtime'/variant/'9ba626afa44a3aa3.patch_0').read_bytes()[:192])
    rebuilt=repack(diag)
    for variant,row in rebuilt['variants'].items():assert row['patchSha256']==digest(W/'runtime'/variant/'9ba626afa44a3aa3.patch_0')
    save_json(W/'repack-audit.json',dict(rebuilt,patchMatchesDelivered=True))
    pairs=[(ROOT/'HD2PhysBoneCompat/src'/name,Path('src')/name)for name in chef['embeddedSourceSha256']]
    pairs.extend((R/'project/diagnostics/B12/src'/name,Path('src/retired-B12')/name)
                 for name in ('native_attachments.lua','native_attachment_probe.lua'))
    pairs.extend((ROOT/'HD2PhysBoneCompat/test'/name,Path('test')/name)for name in
                 ('attachments_layout_harness.lua','split_model_refresh_harness.lua','scene_observer_harness.lua','attachment_probe_harness.lua','strict_id32_fixture.lua'))
    toolnames=['analyze_native_b12_crashes.py','prepare_native_v21_b13.py','audit_native_v21_b13.py','audit_native_v21_b13_chef.py',
               'audit_native_v21_b13_import.py','package_native_v21_b13.py','audit_native_v20_b12.py','audit_native_v20_b12_chef.py',
               'audit_native_v18_b9.py','audit_native_v15_chef.py','audit_native_v16_import.py','audit_native_attachment_layouts.py',
               'analyze_native_b9_log.py','package_native_v12.py']
    pairs.extend((ROOT/'tools'/name,Path('tools')/name)for name in toolnames)
    pairs.extend((W/name,Path('reports')/name)for name in REQUIRED+['repack-audit.json','baseline-file-audit.json','feedback.json'])
    pairs.extend((p,Path('evidence')/r)for p,r in files(W/'evidence'))
    for original,relative in pairs:
        dest=diag/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
    (diag/'README.txt').write_text('B13 replaces retired B12. Run python repack_native_b13.py here with standard Python to reproduce all four patches. Other audits require the original workspace and recorded baseline. Test 0 first; then A/B. Game stability and weapon driver are pending. Retired B12 sources are regression evidence only.\n',encoding='utf-8')
    pack.WORK=W
    increment=pack.archive('B13-增量排查工程.zip',[(p,r)for p,r in files(diag)if r.parts[0]!='rebuilt'])
    save_json(W/'incremental-source-package.json',increment)
    for name in DOCUMENTS:shutil.copy2(ROOT/'docs/native-v21-B13-20261104.md',W/name)
    report=load(R/'package-report.json')
    retired=[r for r in report['packages'] if Path(r['name']).name.startswith('B12-')]
    assert len(retired)==4
    report['packages']=[r for r in report['packages'] if r not in retired]+packages+[increment]
    retired_rows=[dict(row,previousName=row['name'],name=(BACKUP/'retired'/row['name']).as_posix(),status='retired-native-crash')for row in retired]
    report.setdefault('retiredPackages',[]).extend(retired_rows)
    report.update(revision='native-v21',runtimeRevision='native-v21-B13',probe='v21-B13',animationRevision='native-v15',
        animationUserAccepted=True,gameTested=False,gameDeployed=False,incrementalDelivery=True,
        incrementalReports={n:digest(W/n)for n in REQUIRED+['repack-audit.json','baseline-file-audit.json']},
        sourcePackages={'base':'test01-源工程.zip','previousIncrement':'B10-增量排查工程.zip','increment':'B13-增量排查工程.zip'})
    report['priorUserResults']['B12']='A and B crashed; three matching native AVs before displacement.'
    save_json(W/'package-report.json',report)
    matrix=load(R/'ab-matrix.json');matrix.update(revision='native-v21',animationRevision='native-v15',gameTested=False)
    for group in matrix['groups']:
        if group['group'].startswith('B12-'):
            group.update(status='retired-native-crash',gameTested=group['group']!='B12-ALL',
                result='A/B crashed before displacement; ALL shares defective numeric-ID path and is withdrawn.',
                package=(BACKUP/'retired'/group['package']).as_posix())
    for variant,row in zip(('0','A','B','ALL'),packages):
        matrix['groups'].append(dict(group='B13-'+variant,package=row['name'],status='awaiting-game-test',gameTested=False,
            description='First validate 23 known names with 0; A/B/ALL then displace selected attachments only.',
            profileSha256=digest(W/('B13-'+variant+'.json'))))
    save_json(W/'ab-matrix.json',matrix)
    save_json(W/'retirement-plan.json',dict(status='PREPARED',packages=retired_rows))
    print('B13 prepared for delivery: strict ID regression, four imports, reproducible patches, source and retirement plan verified.')


def deliver():
    current=load(R/'delivery-verification.json');assert current==load(W/'baseline-delivery.json')and current['revision']=='native-v20'
    expected={r['path']:r['sha256']for r in current['verified']}
    for relative,sha in expected.items():assert digest(R/relative)==sha,relative
    report=load(W/'package-report.json');assert report['revision']=='native-v21'
    for name,sha in report['incrementalReports'].items():assert digest(W/name)==sha,name
    packages=load(W/'static-packages.json')+[load(W/'incremental-source-package.json')]
    for row in packages:assert digest(W/row['name'])==row['sha256']
    pairs=[(W/r['name'],Path(r['name']))for r in packages]
    pairs.extend((p,Path('project/diagnostics/B13')/r)for p,r in files(W/'diagnostics/B13')if r.parts[0]!='rebuilt')
    pairs.extend((W/name,Path(name))for name in ('package-report.json','ab-matrix.json',*DOCUMENTS))
    backup=(R/BACKUP).resolve();assert backup.is_relative_to(R.resolve())and not backup.exists()
    prepared=[]
    for original,relative in pairs:
        original=original.resolve();dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert original.is_relative_to(W.resolve())and dest.is_relative_to(R.resolve())and saved.is_relative_to(backup)
        sha=digest(original);old=digest(dest)if dest.exists()else None
        if old is not None:assert expected.get(relative.as_posix())==old,relative
        prepared.append((original,relative,dest,saved,sha,old))
    retiring=[]
    for row in load(W/'retirement-plan.json')['packages']:
        old=(R/row['previousName']).resolve();new=(R/row['name']).resolve()
        assert old.is_relative_to(R.resolve())and new.is_relative_to(backup)and old.is_file()and not new.exists()
        assert expected[row['previousName']]==row['sha256']==digest(old)
        retiring.append((row,old,new))
    backup.mkdir(parents=True);save_json(backup/'delivery-verification.json',current)
    expected[(BACKUP/'delivery-verification.json').as_posix()]=digest(backup/'delivery-verification.json')
    for original,relative,dest,saved,sha,old in prepared:
        if old is not None and old!=sha:
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved);assert digest(saved)==old
            expected[(BACKUP/relative).as_posix()]=old
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
        assert digest(dest)==sha;expected[relative.as_posix()]=sha
    for row,old,new in retiring:
        new.parent.mkdir(parents=True,exist_ok=True);old.rename(new);assert digest(new)==row['sha256']and not old.exists()
        expected.pop(row['previousName']);expected[row['name']]=row['sha256']
    for relative,sha in expected.items():assert digest(R/relative)==sha,relative
    save_json(R/'delivery-verification.json',dict(status='PASS',revision='native-v21',animationRevision='native-v15',
        animationUserAccepted=True,runtimeRevision='native-v21-B13',files=len(expected),backup=str(backup),
        gameDeployed=False,gameTested=False,incrementalDelivery=True,retired='B12 A/B/ALL and source archive moved intact to backup',
        verified=[dict(path=p,sha256=s)for p,s in sorted(expected.items())]))
    print('Delivered B13;',len(expected),'SHA-verified files; B12 retired; v15 retained; game not deployed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','deliver'])
    globals()[parser.parse_args().stage]()
