"""Deliver verified shoulder animation repair and the isolated B6 timing probe."""
import argparse
import shutil
from pathlib import Path
import package_native_v12 as base
from package_native_v12 import load,save_json,digest,files

ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v15-20261104'
P=W/'project';R=ROOT/'outputs/native-manual-20261103'
base.WORK=W;base.PROJECT=P;base.RELEASE=R
REQUIRED=['animation-final-audit.json','motion-audit.json','runtime-evidence.json','chef-compatibility-audit.json',
    'ab-profile-audit.json','python-regression.json','package-inspection.json']

def prepare():
    test=(W/'python-regression.log').read_text(encoding='utf-8-sig')
    assert 'Ran 118 tests' in test and 'OK (skipped=1)' in test
    save_json(W/'python-regression.json',dict(status='PASS',tests=118,skipped=1,sha256=digest(W/'python-regression.log')))
    manager=W/'manager'
    for source,relative in files(ROOT/'outputs/native-v14-20261104/manager'):
        target=manager/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    bundled=ROOT/'tools/native-python/anim_batch_mod'
    for source in ROOT.parent.glob('*.py'):
        for folder in (bundled,manager/'anim_batch_mod',manager/'third_party/anim_batch_mod'):
            if folder.exists():shutil.copy2(source,folder/source.name)
    for folder in (bundled,manager/'anim_batch_mod',manager/'third_party/anim_batch_mod'):
        info=folder/'build-info.json'
        if info.exists():
            data=load(info)
            for row in data['files']:row['sha256']=digest(folder/row['name'])
            data['sourceRevision']='test01-v15-preserved-clavicles';save_json(info,data)
    code=P/'source-code'
    for source,relative in files(R/'project/source-code'):
        target=code/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    current={p.name:p for p in ROOT.parent.glob('*.py')}
    for source in current.values():
        for folder in (code,code/'anim_batch_mod'):
            folder.mkdir(parents=True,exist_ok=True);shutil.copy2(source,folder/source.name)
    for target,relative in files(code):
        if target.name in current:shutil.copy2(current[target.name],target)
    for source in (ROOT/'tools').glob('*native_v15*.py'):
        target=code/'tools'/source.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (code/'README.txt').write_text('v15 production sources: anim_batch_mod/. Rebuild via ../Rebuild-Animations.ps1. B6 changes only the Chef callback phase; its construction and validation are in tools/.\n',encoding='utf-8')
    script=(R/'project/Rebuild-Animations.ps1').read_text(encoding='utf-8-sig').replace('v14','v15')
    (P/'Rebuild-Animations.ps1').write_text(script,encoding='utf-8')
    doc=ROOT/'docs/native-v15-20261104.md'
    for name in ('先读我.txt','修正说明.md','挂点配置.md','AB测试说明.md'):shutil.copy2(doc,P/name)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md'):shutil.copy2(doc,W/name)
    shutil.copy2(doc,manager/'先读我-修复测试.txt')
    save_json(W/'manager-package.json',base.archive('HD2ModManager-原生骨架测试版.zip',[(p,Path('manager')/r) for p,r in files(manager)]))
    print('v15 source and manager Python synchronized; Lua baseline remains v14-A.',flush=True)

def animation():base.animation()

def finalize():
    for name in REQUIRED:assert load(W/name)['status']=='PASS',name
    packages=load(W/'static-packages.json')+[load(W/'animation-package.json')]
    imported={r['package']:r['sha256'] for r in load(W/'package-inspection.json')['packages']}
    for row in packages:assert imported.get(row['name'])==row['sha256']
    reports=P/'reports/current-v15';reports.mkdir(parents=True,exist_ok=True)
    for name in REQUIRED+['feedback.json','shoulder-analysis.json','python-regression.log','build.log','chef-audit.log','import-library-cleanup.json']:
        if (W/name).exists():shutil.copy2(W/name,reports/name)
    matrix=load(R/'ab-matrix.json')
    matrix.update(revision='native-v15',gameTested=False)
    matrix['groups'].append(dict(group='B6',package='AB测试/B6-update时机对照.zip',
        description='与 v14-B5 相同握持算法，仅改为 Chef update 回调。',profileSha256=digest(P/'ab-profiles/B6.json')))
    save_json(W/'ab-matrix.json',matrix);save_json(reports/'ab-matrix.json',matrix)
    for source in (ROOT/'tools').glob('*native_v15*.py'):shutil.copy2(source,P/'source-code/tools'/source.name)
    manager=load(W/'manager-package.json');assert digest(W/manager['name'])==manager['sha256']
    packages.append(manager)
    packages.append(base.archive('test01-源工程.zip',[(p,r) for p,r in files(P) if r.parts[:2]!=('animations','runtime')]))
    save_json(W/'package-report.json',dict(status='offline-verified',revision='native-v15',gameTested=False,
        modelPackageSha256=digest(R/'test01-模型材质.zip'),packages=packages,
        reports={n:digest(W/n) for n in REQUIRED},controlsRetained=['v14-A','v14-B5'],probe='v15-B6'))
    print('v15 final packages verified',flush=True)

def deliver():
    report=load(W/'package-report.json');assert report['revision']=='native-v15'
    prior=load(R/'delivery-verification.json');assert prior['status']=='PASS' and prior['revision']=='native-v14'
    expected={row['path']:row['sha256'] for row in prior['verified']}
    for relative,sha in expected.items():assert digest(R/relative)==sha,'Existing v14 delivery changed: '+relative
    assert digest(R/'test01-模型材质.zip')==report['modelPackageSha256']
    backup=(R/'backups/v15-before-20261104').resolve()
    pairs=[(W/row['name'],Path(row['name'])) for row in report['packages']]
    pairs.extend((p,Path('project')/r) for p,r in files(P))
    for folder in ('manager','test'):
        pairs.extend((p,Path(folder)/r) for p,r in files(W/'manager') if r.parts[0] not in base.PROTECTED)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md','package-report.json','ab-matrix.json'):pairs.append((W/name,Path(name)))
    prepared=[]
    for source,relative in pairs:
        source=source.resolve();dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert source.is_relative_to(W.resolve()) and dest.is_relative_to(R.resolve()) and saved.is_relative_to(backup)
        sha=digest(source);old=digest(dest) if dest.exists() else None
        if old is not None and old!=sha:
            assert expected.get(relative.as_posix())==old,'Unknown destination modification: '+str(relative)
            assert not saved.exists()
        prepared.append((source,relative,dest,saved,sha,old))
    backup.mkdir(parents=True,exist_ok=True);save_json(backup/'delivery-verification.json',prior)
    checked=[]
    for source,relative,dest,saved,sha,old in prepared:
        if old is not None and old!=sha:saved.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dest),str(saved))
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():
            if source.stat().st_size>100_000_000:shutil.move(str(source),str(dest))
            else:shutil.copy2(source,dest)
        assert digest(dest)==sha;checked.append(dict(path=relative.as_posix(),sha256=sha))
    save_json(R/'delivery-verification.json',dict(status='PASS',revision='native-v15',files=len(checked),backup=str(backup),
        gameDeployed=False,gameTested=False,largeFilesMoved=True,verified=checked))
    print('Delivered',len(checked),'verified v15 files',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','animation','finalize','deliver'])
    globals()[parser.parse_args().stage]()
