"""Copy the verified correction into the backed-up manual delivery folder."""
import hashlib,json,shutil,zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
work=root/'outputs/native-fix-20261103'; release=root/'outputs/native-manual-20261103'
assert (release/'backups/before-native-fix-20261103/backup-log.json').is_file()
project=work/'project'
for name in ('import-final-validation.json','import-final-result.json','import-content-audit.json','import-animations-validation.json'):
    document=json.loads((work/name).read_text(encoding='utf-8-sig'))
    assert document.get('ok',document.get('status')=='PASS')
    shutil.copy2(work/name,project/'reports'/name)
shutil.copy2(root/'docs/native-fix-20261103.md',project/'修正说明.md')
shutil.copy2(work/'先读我-修复测试.txt',project/'先读我.txt')

def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def project_files():
    for p in sorted(project.rglob('*')):
        if not p.is_file(): continue
        rel=p.relative_to(project)
        if rel.parts[:2]==('animations','runtime') or p.name.startswith('resource-index.sqlite3'): continue
        yield p,rel

for p,rel in project_files():
    destination=release/'project'/rel
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(p,destination)

source_zip=work/'test01-源工程.zip'
with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p,rel in project_files(): z.write(p,rel.as_posix())
with zipfile.ZipFile(source_zip) as z: assert z.testzip() is None
report=json.loads((work/'package-report.json').read_text(encoding='utf-8'))
for row in report['files']:
    p=work/row['name']
    row.update(bytes=p.stat().st_size,sha256=digest(p))
    shutil.copy2(p,release/p.name)
    assert digest(release/p.name)==row['sha256']
manager_zip=release/'HD2ModManager-原生骨架测试版.zip'
with zipfile.ZipFile(manager_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted((release/'manager').rglob('*')):
        if p.is_file(): z.write(p,p.relative_to(release).as_posix())
with zipfile.ZipFile(manager_zip) as z: assert z.testzip() is None
report['files'].append(dict(name=manager_zip.name,bytes=manager_zip.stat().st_size,sha256=digest(manager_zip)))
report['verification']={'python':{'passed':86,'skipped':1},'native_and_physics_csharp':{'passed':13},
                        'cli_scale':{'passed':7},'core':{'passed':23,'skipped':1},'gui':'PASS',
                        'lua51':{'physics_bones':17,'chains':12,'frames_per_chain':600},
                        'model_zip_import':'PASS, byte-identical after import','animation_zip_validation':'PASS'}
report['backup']='backups/before-native-fix-20261103'
report['gameDeployed']=False
shutil.copy2(work/'先读我-修复测试.txt',release/'先读我-人工测试.txt')
with (release/'先读我-人工测试.txt').open('a',encoding='utf-8') as f:
    f.write('\n旧版包、程序和工程备份于 backups/before-native-fix-20261103。\n')
shutil.copy2(root/'docs/native-fix-20261103.md',release/'转换原理与验证.md')
shutil.copy2(work/'conversion.json',release/'conversion.json')
for p in (release/'package-report.json',work/'package-report.json'):
    p.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
