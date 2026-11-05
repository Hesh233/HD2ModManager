"""Package the verified v4 files and deliver with per-file recoverable backups."""
import hashlib,json,shutil,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-v4-20261103';PROJECT=WORK/'project';RELEASE=ROOT/'outputs/native-manual-20261103'
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def files(root,prefix=None):
    for p in sorted(root.rglob('*')):
        if p.is_file():yield p,(Path(prefix)/p.relative_to(root) if prefix else p.relative_to(root))
def project_files():
    for p,rel in files(PROJECT):
        if rel.parts[:2]==('animations','runtime') or p.name.startswith('resource-index.sqlite3'):continue
        yield p,rel
def archive(name,items):
    target=WORK/name
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,rel in items:z.write(p,rel.as_posix())
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    row=dict(name=name,bytes=target.stat().st_size,sha256=digest(target))
    print('verified ZIP',name,row['bytes'],flush=True);return row
def static():
    lua=(PROJECT/'physics-runtime/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig')
    for name in ('physbone_compat.lua','physbone_runtime.lua'):
        assert (ROOT/'HD2PhysBoneCompat/src'/name).read_text(encoding='utf-8-sig') in lua
    rows=[archive('test01-模型材质.zip',files(PROJECT/'models-o3')),
          archive('test01-物理运行时-v4.zip',files(PROJECT/'physics-runtime/patch版')),
          archive('HD2ModManager-原生骨架测试版.zip',files(WORK/'manager-release','manager'))]
    (WORK/'static-packages.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
def prepare():
    for name in ('animation-final-audit.json','physics-audit.json','serialized-floor-audit.json','published-generator-audit.json','attachment-profile-audit.json'):
        assert json.loads((WORK/name).read_text())['status']=='PASS'
    reports=PROJECT/'reports/current-v4';reports.mkdir(parents=True,exist_ok=True)
    for p in WORK.iterdir():
        if p.is_file() and p.suffix in ('.json','.log') and p.name!='package-report.json':shutil.copy2(p,reports/p.name)
    source=PROJECT/'source-code';source.mkdir(exist_ok=True)
    for p in (ROOT.parent).glob('*.py'):
        if p.name in ('__init__.py','main.py','archive.py','binary.py','constants.py','formats.py','math3d.py','native_animation.py','native_skeleton.py','processor.py','cli.py','batch.py'):
            shutil.copy2(p,source/p.name)
    for relative in ('HD2SourceMigration/Retarget/NativeSourceSkeleton.cs','HD2SourceMigration/VpkConversion/PhysBoneRigSidecar.cs',
        'HD2PhysBoneCompat/src/physbone_compat.lua','HD2PhysBoneCompat/src/physbone_runtime.lua',
        'HD2ModManager/Services/NativeSkeletonProjectService.cs','HD2ModAdaptation/PatchReconstruction/PatchTocScanner.cs'):
        p=ROOT/relative;shutil.copy2(p,source/p.name)
    for p in (ROOT/'tools').glob('*native_v4*.py'):shutil.copy2(p,source/p.name)
    for relative in ('HD2ModCore/Infrastructure/PatchTocScanner.cs','HD2ModAdaptation/PatchReconstruction/PatchArchiveWriter.cs',
        'HD2ModAdaptation/PatchReconstruction/PatchSubsetWriter.cs','HD2ModAdaptation/PatchReconstruction/PatchWorkspace/PatchWorkspaceReader.cs',
        'HD2ModCli/CliApplication.cs'):
        target=source/'changed-files'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
    research=PROJECT/'research';research.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'HD2PhysBoneCompat/research/attachment_profiles.lua',research/'attachment_profiles.lua')
    for name in ('先读我.txt','修正说明.md'):shutil.copy2(ROOT/'docs/native-v4-20261103.md',PROJECT/name)
    rows=json.loads((WORK/'static-packages.json').read_text())
    assert all(digest(WORK/r['name'])==r['sha256'] for r in rows)
    rows.extend([archive('test01-配套动画.zip',files(PROJECT/'animations/runtime')),
                 archive('test01-源工程.zip',project_files())])
    anim=json.loads((WORK/'animation-final-audit.json').read_text())
    report=dict(status='offline-verified',revision='native-v4',modelScale=1.05,scaleOrigin='ground',
        armor='O-3 自由之魂',companionPatches=1,animations=3180,physicsBones=17,physicsChains=12,luaVersion='2.0.2',
        materialsUnchanged=True,modelStateMachineEntries=0,gripStatus='IK corrected; unreachable poses require game validation',
        maxStandardGripResidualMetres=anim['maxStandardGripResidualMetres'],
        attachmentProfiles=dict(native=29,vpk=29,sourceAnchored=26,controllerFallbacks=3,
            status='offline prototype; not emitted to scene graph or enabled in runtime'),
        gameDeployed=False,gameTested=False,files=rows)
    (WORK/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def deliver():
    report=json.loads((WORK/'package-report.json').read_text())
    assert json.loads((WORK/'package-inspection.json').read_text())['status']=='PASS'
    backup=RELEASE/'backups/before-native-v4-20261103';backup.mkdir(parents=True,exist_ok=True)
    changed=[];obsolete=[]
    def save(target):
        target=target.resolve();assert target.is_relative_to(RELEASE.resolve())
        if target.exists():
            stored=backup/target.relative_to(RELEASE)
            if not stored.exists():
                stored.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,stored)
                assert digest(stored)==digest(target)
        return target
    def replace(source,target):
        target=save(target);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target);assert digest(source)==digest(target)
        changed.append(str(target.relative_to(RELEASE)))
    for row in report['files']:
        assert digest(WORK/row['name'])==row['sha256']
        replace(WORK/row['name'],RELEASE/row['name'])
    replace(WORK/'conversion.json',RELEASE/'conversion.json')
    for p,rel in project_files():replace(p,RELEASE/'project'/rel)
    # The external addon changed from patch_54 to patch_3. Remove only obsolete
    # files of this generated addon, after copying them to the backup.
    old_physics=RELEASE/'project/physics-runtime/patch版'
    expected={p.name for p in (PROJECT/'physics-runtime/patch版').iterdir() if p.is_file()}
    if old_physics.exists():
        for p in old_physics.glob('9ba626afa44a3aa3.patch_*'):
            if p.name not in expected:save(p).unlink();obsolete.append(str(p.relative_to(RELEASE)))
    for p,rel in files(WORK/'manager-release'):
        replace(p,RELEASE/'manager'/rel)
        if (RELEASE/'test').is_dir() and rel.parts[0] not in ('data','cache','logs','config','settings.json','config.toml'):
            replace(p,RELEASE/'test'/rel)
    for name in ('先读我-人工测试.txt','转换原理与验证.md'):
        replace(ROOT/'docs/native-v4-20261103.md',RELEASE/name)
    replace(ROOT/'docs/native-v4-20261103.md',RELEASE/'test/先读我-修复测试.txt')
    # The user's current model scale is explicitly 1.05; preserve other test settings.
    cfg=RELEASE/'test/config.toml'
    if cfg.exists():
        import re
        text=cfg.read_text(encoding='utf-8-sig')
        updated=re.sub(r'(?m)^(model_scale\s*=\s*)1\.2\s*$',r'\g<1>1.05',text)
        if text!=updated:save(cfg);cfg.write_text(updated,encoding='utf-8-sig');changed.append('test/config.toml')
    for name in ('test01-物理运行时.zip','test01-物理运行时-v3.zip'):
        p=RELEASE/name
        if p.exists():
            try:save(p).unlink();obsolete.append(name)
            except PermissionError:report.setdefault('lockedObsoleteFiles',[]).append(name)
    report.update(backup=str(backup),updatedFiles=len(changed),removedObsoleteFiles=obsolete)
    (WORK/'package-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    replace(WORK/'package-report.json',RELEASE/'package-report.json')
    (backup/'backup-log.json').write_text(json.dumps(dict(replaced=changed,obsolete=obsolete),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':
    {'--static':static,'--prepare':prepare,'--deliver':deliver}[sys.argv[1]]()
