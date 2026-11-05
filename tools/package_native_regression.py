"""Package the verified second correction, then deliver with recoverable backups."""
import hashlib,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-regression-20261103'
RELEASE=ROOT/'outputs/native-manual-20261103'
PROJECT=WORK/'project'

def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def project_files():
    for p in sorted(PROJECT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(PROJECT)
        if rel.parts[:2]==('animations','runtime') or rel.parts[0]=='physics-runtime-v3' or p.name.startswith('resource-index.sqlite3'):continue
        yield p,rel

def archive(name,files):
    target=WORK/name
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,rel in files:z.write(p,rel.as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert not any('ModelScaleSmoke' in n for n in z.namelist())
    print(f'ZIP verified: {name} ({target.stat().st_size} bytes)',flush=True)
    return dict(name=name,bytes=target.stat().st_size,sha256=digest(target))

def files(directory,prefix=None):
    return [(p,(Path(prefix)/p.relative_to(directory) if prefix else p.relative_to(directory))) for p in sorted(directory.rglob('*')) if p.is_file()]

def prepare():
    assert json.loads((WORK/'reports/animation-physics-isolation.json').read_text())['status']=='PASS'
    assert json.loads((WORK/'reports/published-generator.json').read_text())['status']=='PASS'
    assert json.loads((WORK/'reports/model-scale-gui.json').read_text())['status']=='PASS'
    for p in (PROJECT/'physics-runtime-v3').rglob('*'):
        if p.is_file():
            rel=str(p.relative_to(PROJECT/'physics-runtime-v3')).replace('patch_0','patch_54')
            target=PROJECT/'physics-runtime'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    note=(ROOT/'docs/native-regression-20261103.md').read_text(encoding='utf-8')
    for name in ('修正说明.md','先读我.txt'): (PROJECT/name).write_text(note,encoding='utf-8-sig')
    (WORK/'先读我-本轮修复.txt').write_text(note,encoding='utf-8-sig')
    (PROJECT/'reports/current-regression').mkdir(exist_ok=True)
    for p in (WORK/'reports').iterdir():
        if p.is_file():shutil.copy2(p,PROJECT/'reports/current-regression'/p.name)
    for name in ('native_skeleton.py','native_animation.py'):
        dest=PROJECT/'source-code'/name;dest.parent.mkdir(exist_ok=True);shutil.copy2(ROOT.parent/name,dest)
    for name in ('physbone_runtime.lua','physbone_compat.lua'):
        shutil.copy2(ROOT/'HD2PhysBoneCompat/src'/name,PROJECT/'source-code'/name)
    packages=[archive('test01-模型材质.zip',files(PROJECT/'models-o3')),
              archive('test01-配套动画.zip',files(PROJECT/'animations/runtime')),
              archive('test01-物理运行时-v3.zip',files(PROJECT/'physics-runtime/patch版')),
              archive('test01-源工程.zip',project_files()),
              archive('HD2ModManager-原生骨架测试版.zip',files(WORK/'manager-final','manager'))]
    report=dict(status='PASS',revision='native-regression-v3',modelScale=1.2,armor='O-3 自由之魂',
                animations=3180,originalDriversPreserved=True,sourceAnimationBytesUnchanged=True,
                physicsBones=17,physicsChains=12,sharedAvatarPhysicsBones=0,luaVersion='2.0.1',
                modelPatchBytesUnchanged=True,files=packages,gameDeployed=False,gameTested=False)
    for p in (PROJECT/'models-o3/test01-O3').glob('*.patch_*'):
        assert digest(p)==digest(RELEASE/'project/models-o3/test01-O3'/p.name)
    (WORK/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

def deliver():
    report=json.loads((WORK/'package-report.json').read_text(encoding='utf-8'))
    validation=json.loads((WORK/'reports/import-validation.json').read_text(encoding='utf-8-sig'))
    assert validation['ok'] and validation['validation']['isValid']
    for p in (WORK/'reports').iterdir():
        if p.is_file():shutil.copy2(p,PROJECT/'reports/current-regression'/p.name)
    row=archive('test01-源工程.zip',project_files())
    report['files']=[row if r['name']==row['name'] else r for r in report['files']]
    backup=RELEASE/'backups/before-native-regression-20261103'
    if backup.exists() and '--resume' not in sys.argv:raise FileExistsError(backup)
    backup.mkdir(parents=True,exist_ok=True)
    records=[]
    def replace(source,target):
        target=target.resolve();assert target.is_relative_to(RELEASE.resolve())
        if target.exists():
            saved=backup/target.relative_to(RELEASE);saved.parent.mkdir(parents=True,exist_ok=True)
            if not saved.exists():
                shutil.copy2(target,saved);assert digest(saved)==digest(target)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        assert digest(source)==digest(target)
        records.append(str(target.relative_to(RELEASE)))
    for row in report['files']:
        assert digest(WORK/row['name'])==row['sha256']
        replace(WORK/row['name'],RELEASE/row['name'])
    for p,rel in project_files():replace(p,RELEASE/'project'/rel)
    preserved={}
    for name in ('settings.json','config.toml'):
        p=RELEASE/'test'/name
        if p.exists():preserved[name]=digest(p)
    for p,rel in files(WORK/'manager-final'):
        replace(p,RELEASE/'manager'/rel)
        if (RELEASE/'test').is_dir() and rel.parts[0] not in ('data','config','cache','logs','settings.json','config.toml'):
            replace(p,RELEASE/'test'/rel)
    assert all(digest(RELEASE/'test'/n)==h for n,h in preserved.items())
    for name in ('先读我-人工测试.txt','转换原理与验证.md'):
        replace(WORK/'先读我-本轮修复.txt',RELEASE/name)
    replace(WORK/'先读我-本轮修复.txt',RELEASE/'test/先读我-修复测试.txt')
    report.update(backup=str(backup.relative_to(RELEASE)),testSettingsPreserved=True,importValidation='PASS')
    (WORK/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    replace(WORK/'package-report.json',RELEASE/'package-report.json')
    (backup/'backup-log.json').write_text(json.dumps(dict(files=records,settings=preserved),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    (deliver if '--deliver' in sys.argv else prepare)()
