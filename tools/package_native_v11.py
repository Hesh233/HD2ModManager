"""Package verified v11 files and update the requested delivery with backups."""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-v11-20261104';PROJECT=WORK/'project'
RELEASE=ROOT/'outputs/native-manual-20261103'
PROTECTED={'settings.json','config.toml','config','data','cache','logs'}

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def save_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def files(root):
    return [(p,p.relative_to(root)) for p in sorted(Path(root).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and not p.name.startswith('resource-index.sqlite3')]
def archive(name,rows):
    path=WORK/name
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file,relative in rows:z.write(file,str(relative))
    with zipfile.ZipFile(path) as z:assert z.testzip() is None
    return dict(name=name,sha256=digest(path),bytes=path.stat().st_size)

def static():
    shutil.copy2(ROOT/'docs/native-v11-20261104.md',WORK/'manager/先读我-修复测试.txt')
    source=ROOT/'HD2PhysBoneCompat/src'
    lua=(WORK/'physics-export-delivery/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig')
    for name in ('native_attachments.lua','native_attachment_profile.lua','physbone_runtime.lua'):
        assert (source/name).read_text(encoding='utf-8-sig').replace('\r\n','\n') in lua.replace('\r\n','\n'),name
    for name in ('processor.py','native_skeleton.py'):
        assert digest(ROOT.parent/name)==digest(WORK/'manager/anim_batch_mod'/name),name
    metadata=WORK/'manager/anim_batch_mod/build-info.json'
    info=load(metadata)
    for row in info['files']:row['sha256']=digest(metadata.parent/row['name'])
    info['sourceRevision']='test01-v11';save_json(metadata,info)
    shutil.copytree(WORK/'physics-export-delivery',PROJECT/'physics-runtime',dirs_exist_ok=True)
    shutil.copy2(RELEASE/'test01-模型材质.zip',WORK/'test01-模型材质.zip')
    # No model/skin/rig changes are needed for the two existing wrist helpers.
    for file,relative in files(PROJECT/'models-o3'):
        assert digest(file)==digest(RELEASE/'project/models-o3'/relative),str(relative)
    rows=[dict(name='test01-模型材质.zip',sha256=digest(WORK/'test01-模型材质.zip'),bytes=(WORK/'test01-模型材质.zip').stat().st_size),
          archive('test01-物理运行时-v11.zip',files(PROJECT/'physics-runtime/patch版')),
          archive('HD2ModManager-原生骨架测试版.zip',[(p,Path('manager')/r) for p,r in files(WORK/'manager')])]
    save_json(WORK/'static-packages.json',rows)
    print('Static model/runtime/manager packages verified',flush=True)

def animation():
    build=load(PROJECT/'animations/build-report.json')
    assert build['status']=='complete' and len(build['animations'])==build['expected_animations']==3180
    for row in build['files']:
        file=PROJECT/'animations'/row['path'];assert file.stat().st_size==row['bytes'] and digest(file)==row['sha256']
    rows=files(PROJECT/'animations/runtime');assert len(rows)==3
    save_json(WORK/'animation-package.json',archive('test01-配套动画.zip',rows))
    print('Animation package verified',flush=True)

def finalize():
    required=['animation-final-audit.json','candidate-audit.json','attachment-runtime-audit.json',
              'wrist-head-sling-audit.json','chef-compatibility-audit.json','package-inspection.json','python-regression.json']
    for name in required:assert load(WORK/name)['status']=='PASS',name
    reports=PROJECT/'reports/current-v11';reports.mkdir(parents=True,exist_ok=True)
    for name in required+['source-weight-consumers.json','profile-changes.json','source-procedures.json']:
        shutil.copy2(WORK/name,reports/name)
    code=PROJECT/'source-code'
    # Preserve previously delivered supporting C# sources and historical
    # audits; overwrite only the current production files below.
    for file,relative in files(RELEASE/'project/source-code'):
        target=code/relative
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    for file in ROOT.parent.glob('*.py'):
        target=code/'anim_batch_mod'/file.name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,target);shutil.copy2(file,code/file.name)
    for folder in ('HD2PhysBoneCompat/src','HD2PhysBoneCompat/test'):
        for file,relative in files(ROOT/folder):
            target=code/folder/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
            if file.suffix=='.lua' and folder.endswith('/src'):shutil.copy2(file,code/file.name)
    for file in (ROOT/'tools').glob('*native_v11*.py'):
        target=code/'tools'/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    for name in ('audit_native_attachment_layouts.py','native_attachment_layouts.py'):
        shutil.copy2(ROOT/'tools'/name,code/'tools'/name)
    (code/'README.txt').write_text('v11 production animation source: anim_batch_mod/. Runtime source: HD2PhysBoneCompat/src/.\nRebuild animations with ../Rebuild-Animations.ps1 and the matching v11 manager. Version-named audit scripts describe the original workspace and its regression inputs.\n',encoding='utf-8')
    doc=ROOT/'docs/native-v11-20261104.md'
    for name in ('先读我.txt','修正说明.md','挂点配置.md'):shutil.copy2(doc,PROJECT/name)
    script=(ROOT/'tools/Rebuild-Native-v10-Animations.ps1').read_text(encoding='utf-8-sig').replace('v10','v11')
    (PROJECT/'Rebuild-Animations.ps1').write_text(script,encoding='utf-8')
    shutil.copy2(doc,WORK/'先读我-人工测试.txt');shutil.copy2(doc,WORK/'转换原理与验证.md')
    packages=load(WORK/'static-packages.json')+[load(WORK/'animation-package.json')]
    for row in packages:assert digest(WORK/row['name'])==row['sha256']
    rows=[(p,r) for p,r in files(PROJECT) if r.parts[:2]!=('animations','runtime')]
    packages.append(archive('test01-源工程.zip',rows))
    save_json(WORK/'package-report.json',dict(status='offline-verified',revision='native-v11',gameTested=False,
        headChildWrites=0,wristHelpers=2,runtimeVersion='2.1.6',attachmentVersion='0.7.0',
        modelMaterialsWeightsUnchanged=True,packages=packages,reports={n:digest(WORK/n) for n in required}))
    print('Final packages ready',flush=True)

def deliver(backup_tag='v11-before-20261104'):
    report=load(WORK/'package-report.json');assert report['revision']=='native-v11'
    pairs=[]
    for row in report['packages']:
        file=WORK/row['name'];assert digest(file)==row['sha256'];pairs.append((file,Path(row['name'])))
    pairs.extend((p,Path('project')/r) for p,r in files(PROJECT))
    for folder in ('manager','test'):
        pairs.extend((p,Path(folder)/r) for p,r in files(WORK/'manager') if r.parts[0] not in PROTECTED)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','package-report.json'):
        pairs.append((WORK/name,Path(name)))
    doc=ROOT/'docs/native-v11-20261104.md'
    pairs.extend([(doc,Path('manager/先读我-修复测试.txt')),(doc,Path('test/先读我-修复测试.txt'))])
    assert Path(backup_tag).name==backup_tag and backup_tag.startswith('v11-')
    backup=RELEASE/'backups'/backup_tag;backup.mkdir(parents=True,exist_ok=True)
    checked=[]
    for source,relative in pairs:
        dest=(RELEASE/relative).resolve();saved=(backup/relative).resolve()
        assert dest.is_relative_to(RELEASE.resolve()) and saved.is_relative_to(backup.resolve())
        sha=digest(source)
        if dest.exists() and digest(dest)!=sha:
            if saved.exists():assert digest(saved)==digest(dest),'Existing backup differs: '+str(relative)
            else:
                saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
                assert digest(saved)==digest(dest)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or digest(dest)!=sha:shutil.copy2(source,dest)
        assert digest(dest)==sha
        checked.append(dict(path=relative.as_posix(),sha256=sha))
    old=RELEASE/'test01-物理运行时-v10.zip'
    if old.exists():
        saved=backup/old.name
        if not saved.exists():shutil.copy2(old,saved)
        assert digest(old)==digest(saved) and old.resolve().parent==RELEASE.resolve()
        old.unlink() # backed-up obsolete single file only
    save_json(RELEASE/'delivery-verification.json',dict(status='PASS',revision='native-v11',files=len(checked),
        backup=str(backup),gameDeployed=False,gameTested=False,verified=checked))
    print('Delivered',len(checked),'verified files to',RELEASE,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['static','animation','finalize','deliver'])
    parser.add_argument('--backup-tag',default='v11-before-20261104')
    args=parser.parse_args()
    if args.stage=='deliver':deliver(args.backup_tag)
    else:globals()[args.stage]()
