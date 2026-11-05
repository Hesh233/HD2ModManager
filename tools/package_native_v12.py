"""Build mutually exclusive v12 runtime variants and a verified local delivery."""
import argparse,copy,hashlib,json,re,shutil,struct,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'outputs/native-v12-20261104';PROJECT=WORK/'project'
RELEASE=ROOT/'outputs/native-manual-20261103'
PROTECTED={'settings.json','config.toml','config','data','cache','logs'}
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive

def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def save_json(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def files(root):
    return [(p,p.relative_to(root)) for p in sorted(Path(root).rglob('*')) if p.is_file()
            and '__pycache__' not in p.parts and not p.name.startswith('resource-index.sqlite3')]
def archive(name,rows):
    path=WORK/name;path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,r in rows:z.write(p,str(r))
    with zipfile.ZipFile(path) as z:assert z.testzip() is None
    return dict(name=name,sha256=digest(path),bytes=path.stat().st_size)
def lua(v):
    if v is None:return 'nil'
    if isinstance(v,bool):return 'true' if v else 'false'
    if isinstance(v,(int,float)):return repr(v)
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
    return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'

def static():
    p=load(PROJECT/'attachment-profile.json');source=ROOT/'HD2PhysBoneCompat/src'
    exported=(WORK/'physics-export-delivery/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    profile_source=(source/'native_attachment_profile.lua').read_text(encoding='utf-8-sig').replace('\r\n','\n')
    for name in ('native_attachments.lua','native_attachment_profile.lua','physbone_runtime.lua'):
        assert (source/name).read_text(encoding='utf-8-sig').replace('\r\n','\n') in exported,name
    for name in ('processor.py','native_skeleton.py','test_native_v12.py'):
        assert digest(ROOT.parent/name)==digest(WORK/'manager/anim_batch_mod'/name),name
    info=load(WORK/'manager/anim_batch_mod/build-info.json')
    for row in info['files']:row['sha256']=digest(WORK/'manager/anim_batch_mod'/row['name'])
    info['sourceRevision']='test01-v12';save_json(WORK/'manager/anim_batch_mod/build-info.json',info)
    doc=ROOT/'docs/native-v12-20261104.md'
    shutil.copy2(doc,WORK/'manager/先读我-修复测试.txt')
    base=WORK/'physics-export-delivery/patch版'
    binary=(base/'9ba626afa44a3aa3.patch_0').read_bytes()
    offset=struct.unpack_from('<Q',binary,120)[0];assert offset==192
    base_body=exported.encode('utf-8');old=TocArchive.parse_parts(bytearray(binary),bytearray(),bytearray())
    entry=next(iter(old.entries.values()));assert bytes(entry.toc_data[8:]).decode('utf-8-sig').replace('\r\n','\n')==exported
    names={'A':'test01-物理运行时-v12-A.zip','B1':'AB测试/B1-旧持枪映射.zip',
           'B2':'AB测试/B2-原版收枪挂点.zip','B3':'AB测试/B3-停止挂点运行时.zip'}
    descriptions={'A':'修正版基线；原生瞄准父链，恢复头部挂点，补齐握把刷新。',
                  'B1':'仅关闭瞄准父链保护，恢复旧持枪映射；与 A 比较枪口和左手。',
                  'B2':'仅将 sling 保持原版；与 A 比较收枪位置和角度。',
                  'B3':'仅停止挂点适配器写入（含其手腕辅助骨）；头发物理继续。与 A 比较军械库预览。'}
    rows=[];matrix=[]
    sys.path.insert(0,str(ROOT/'outputs/native-v11-20261104/test-runtime'))
    from lupa.lua51 import LuaRuntime
    for key,name in names.items():
        variant=copy.deepcopy(p);variant['revision']='test01-v12-'+key
        if key=='B1':variant['protectControllerParents']=False
        if key=='B2':next(r for r in variant['vpk'] if r['standardName']=='sling')['policy']='original-world'
        if key=='B3':variant['diagnosticMode']='observe'
        code=exported.replace(profile_source,'-- Generated v12 '+key+' profile.\nreturn '+lua(variant)+'\n')
        assert code!=exported or key=='A'
        vm=LuaRuntime();assert vm.eval('function(s) return loadstring(s)~=nil end')(code),'Lua syntax: '+key
        dest=PROJECT/'ab-runtime'/key;dest.mkdir(parents=True,exist_ok=True)
        body=code.encode('utf-8');resource=struct.pack('<II',len(body),2)+body
        data=bytearray(binary[:offset])+resource;data.extend(bytes(-len(data)%16))
        struct.pack_into('<Q',data,32,len(data));struct.pack_into('<I',data,160,len(resource))
        patch=dest/'9ba626afa44a3aa3.patch_0';patch.write_bytes(data)
        for suffix in ('.stream','.gpu_resources'):Path(str(patch)+suffix).write_bytes(b'')
        parsed=next(iter(TocArchive.parse_parts(data,bytearray(),bytearray()).entries.values()))
        assert parsed.file_id==entry.file_id and parsed.type_id==entry.type_id
        assert parsed.toc_data==resource and struct.unpack_from('<I',parsed.toc_data)[0]==len(body)
        manifest=load(base/'manifest.json');manifest.update(Name='test01 v12 '+key,Description=descriptions[key]+' 同一时间仅启用一组 v12 运行时。')
        save_json(dest/'manifest.json',manifest)
        (dest/'测试说明.txt').write_text(descriptions[key]+'\n'+doc.read_text(encoding='utf-8'),encoding='utf-8')
        save_json(PROJECT/'ab-profiles'/f'{key}.json',variant)
        rows.append(archive(name,files(dest)))
        matrix.append(dict(group=key,package=name,description=descriptions[key],profileSha256=digest(PROJECT/'ab-profiles'/f'{key}.json'),
                           addonId=f'{entry.file_id:016x}',addonSha256=hashlib.sha256(resource).hexdigest()))
    # Give the standard project exporter its matching A package and bare Lua.
    shutil.copytree(WORK/'physics-export-delivery',PROJECT/'physics-runtime',dirs_exist_ok=True)
    shutil.copytree(PROJECT/'ab-runtime/A',PROJECT/'physics-runtime/patch版',dirs_exist_ok=True)
    save_json(WORK/'ab-matrix.json',dict(status='offline-verified',groups=matrix,gameTested=False))
    save_json(WORK/'static-packages.json',rows)
    print('Four runtime variants verified',flush=True)

def animation():
    build=load(PROJECT/'animations/build-report.json')
    assert build['status']=='complete' and len(build['animations'])==build['expected_animations']==3180
    for row in build['files']:
        path=PROJECT/'animations'/row['path'];assert path.stat().st_size==row['bytes'] and digest(path)==row['sha256']
    save_json(WORK/'animation-package.json',archive('test01-配套动画.zip',files(PROJECT/'animations/runtime')))
    print('Animation package verified',flush=True)

def finalize():
    required=['animation-final-audit.json','candidate-audit.json','attachment-runtime-audit.json',
              'chef-compatibility-audit.json','package-inspection.json','python-regression.json','ab-profile-audit.json','exporter-audit.json']
    for name in required:assert load(WORK/name)['status']=='PASS',name
    reports=PROJECT/'reports/current-v12';reports.mkdir(parents=True,exist_ok=True)
    for name in required+['ab-matrix.json','small-angle-diagnostic.json']:shutil.copy2(WORK/name,reports/name)
    code=PROJECT/'source-code'
    for file,relative in files(RELEASE/'project/source-code'):
        target=code/relative
        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    for file in ROOT.parent.glob('*.py'):
        target=code/'anim_batch_mod'/file.name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,target);shutil.copy2(file,code/file.name)
    for folder in ('HD2PhysBoneCompat/src','HD2PhysBoneCompat/test'):
        for file,relative in files(ROOT/folder):
            target=code/folder/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
            if file.suffix=='.lua' and folder.endswith('/src'):shutil.copy2(file,code/file.name)
    for file in (ROOT/'tools').glob('*native_v12*.py'):
        target=code/'tools'/file.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,target)
    # Update older duplicated production snapshots too: no stale processor or
    # runtime may masquerade as the source of this delivered build.
    current={f.name:f for f in ROOT.parent.glob('*.py')}
    current.update({f.name:f for f in (ROOT/'HD2PhysBoneCompat/src').glob('*.lua')})
    for file,_ in files(code):
        if file.name in current:shutil.copy2(current[file.name],file)
    (code/'README.txt').write_text('v12 production Python: anim_batch_mod/. Lua: HD2PhysBoneCompat/src/.\nBuild with ../Rebuild-Animations.ps1 and the adjacent matching manager. Version-specific audits require their original workspace fixtures.\n',encoding='utf-8')
    doc=ROOT/'docs/native-v12-20261104.md'
    for name in ('先读我.txt','修正说明.md','挂点配置.md','AB测试说明.md'):shutil.copy2(doc,PROJECT/name)
    script=(ROOT/'tools/Rebuild-Native-v10-Animations.ps1').read_text(encoding='utf-8-sig').replace('v10','v12')
    (PROJECT/'Rebuild-Animations.ps1').write_text(script,encoding='utf-8')
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md'):shutil.copy2(doc,WORK/name)
    packages=load(WORK/'static-packages.json')+[load(WORK/'animation-package.json')]
    packages.append(archive('HD2ModManager-原生骨架测试版.zip',[(p,Path('manager')/r) for p,r in files(WORK/'manager')]))
    packages.append(archive('test01-源工程.zip',[(p,r) for p,r in files(PROJECT) if r.parts[:2]!=('animations','runtime')]))
    save_json(WORK/'package-report.json',dict(status='offline-verified',revision='native-v12',gameTested=False,
        runtimeVersion='2.1.7',attachmentVersion='0.8.0',modelMaterialsWeightsUnchanged=True,
        modelPackageSha256=digest(RELEASE/'test01-模型材质.zip'),packages=packages,reports={n:digest(WORK/n) for n in required}))
    print('Final v12 packages verified',flush=True)

def deliver():
    report=load(WORK/'package-report.json');assert report['revision']=='native-v12'
    pairs=[(WORK/r['name'],Path(r['name'])) for r in report['packages']]
    pairs.extend((p,Path('project')/r) for p,r in files(PROJECT))
    for folder in ('manager','test'):
        pairs.extend((p,Path(folder)/r) for p,r in files(WORK/'manager') if r.parts[0] not in PROTECTED)
    for name in ('先读我-人工测试.txt','转换原理与验证.md','AB测试说明.md','package-report.json','ab-matrix.json'):
        pairs.append((WORK/name,Path(name)))
    backup=RELEASE/'backups/v12-before-20261104';backup.mkdir(parents=True,exist_ok=True)
    checked=[]
    for source,relative in pairs:
        dest=(RELEASE/relative).resolve();saved=(backup/relative).resolve()
        assert dest.is_relative_to(RELEASE.resolve()) and saved.is_relative_to(backup.resolve())
        sha=digest(source)
        if dest.exists() and digest(dest)!=sha:
            if saved.exists():assert digest(saved)==digest(dest),'Conflicting backup: '+str(relative)
            else:saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or digest(dest)!=sha:shutil.copy2(source,dest)
        assert digest(dest)==sha;checked.append(dict(path=relative.as_posix(),sha256=sha))
    for old in RELEASE.glob('test01-物理运行时-v11.zip'):
        saved=(backup/old.name).resolve();assert old.resolve().parent==RELEASE.resolve() and saved.is_relative_to(backup.resolve())
        if not saved.exists():shutil.copy2(old,saved)
        assert digest(old)==digest(saved);old.unlink()
    assert digest(RELEASE/'test01-模型材质.zip')==report['modelPackageSha256']
    save_json(RELEASE/'delivery-verification.json',dict(status='PASS',revision='native-v12',files=len(checked),backup=str(backup),
        gameDeployed=False,gameTested=False,verified=checked))
    print('Delivered',len(checked),'verified files',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['static','animation','finalize','deliver'])
    globals()[parser.parse_args().stage]()
