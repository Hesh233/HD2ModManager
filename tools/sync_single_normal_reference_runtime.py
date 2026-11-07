"""Narrow R2 synchronization. Never publishes Core/CLI/Lua/physics or rewrites a library.

Run after verify_single_normal_reference_integration.py and the installed-dependency
WPF build. All targets are explicit descendants of this repository. Preflight all
locks before writes; back up changed files and roll back on a copy/hash failure.
"""
from pathlib import Path
import argparse, ctypes, datetime, hashlib, json, os, shutil
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1]
ANIMATION=ROOT.parent
AUDIT=ROOT/'outputs/single-normal-reference-integrated-20261107'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
STAGING=ROOT/'outputs/single-hd2-fix-20261106/manager'
BUNDLE=ROOT/'tools/native-python/anim_batch_mod'
MODULES=('processor.py','batch.py','single_skeleton.py','playback_reference.py')
REFERENCE='presets/single-normal-reference/playback.zip'
SOURCE_SHA='4030765f8066141df8ecd0440322d128a4827d2cf9f5064a3a918b34eaefbf18'
PACK_SHA='5df2f22b11bba8b30ffa4a231c6c56949ada67b66d56b429482e260e052ddc5a'

def safe(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise ValueError(f'Outside repository: {path}')
    return path

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def lock_preflight(path):
    # FILE_SHARE_NONE catches a running mapped WPF DLL; do not kill the manager.
    if os.name!='nt':return
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    api.CreateFileW.restype=wintypes.HANDLE
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=api.CreateFileW(str(path),0x80000000|0x40000000,0,None,3,0,None)
    if handle==wintypes.HANDLE(-1).value:raise OSError(ctypes.get_last_error(),f'Locked/read-only target; close manager or approve access: {path}')
    api.CloseHandle(handle)

def protected():
    paths=set()
    for folder in ('test-library','data','config'):
        paths.update(p for p in (INSTALL/folder).rglob('*') if p.is_file())
    paths.update(p for p in INSTALL.glob('*.dll') if p.name!='HD2ModManager.dll')
    paths.update(p for p in (INSTALL/'anim_batch_mod/presets/native-v15').rglob('*') if p.is_file())
    paths.update(p for p in (INSTALL/'anim_batch_mod').glob('*.py') if p.name not in MODULES)
    paths.update(p for p in INSTALL.glob('*.json') if p.name not in ('更新记录.json',))
    paths.add(INSTALL/'config.toml')
    paths.add(BUNDLE/'native_config.py')
    paths.update((ROOT/'HD2PhysBoneCompat/src').glob('*.lua'))
    paths.add(ROOT/'HD2ModCore/Infrastructure/PhysBoneLuaSource.cs')
    return {str(p):digest(p) for p in sorted(paths) if p.is_file()}

def make_plan():
    plan=[];now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    source_pack=ANIMATION/REFERENCE
    if digest(source_pack)!=PACK_SHA:raise ValueError('Uncertified playback bundle')
    binaries=AUDIT/'wpf-build/bin/Release/net10.0-windows'
    for label,runtime in (('bundle',BUNDLE),('staging',STAGING/'anim_batch_mod'),('installed',INSTALL/'anim_batch_mod')):
        info_path=safe(runtime/'build-info.json');info=json.loads(info_path.read_text(encoding='utf-8-sig'))
        if info['pipelineVersion']!='1.0.15' or info.get('singleSkeletonPipelineVersion') not in ('1.0.19','1.0.20'):
            raise ValueError('Unexpected/newer pipeline; do not downgrade')
        info.update(singleSkeletonPipelineVersion='1.0.20',singleProcessingProfile='standard-single-v3-normal-reference',singlePlaybackRevision='normal-reference-r2',singlePlaybackReferenceSha256=SOURCE_SHA)
        def update(rows,name,sha):
            row=next((r for r in rows if r['name']==name),None)
            if row is None:rows.append(dict(name=name,sha256=sha))
            else:row['sha256']=sha
        for name in MODULES:
            source=ANIMATION/name;destination=safe(runtime/name);sha=digest(source)
            update(info['files'],name,sha.upper())
            plan.append(dict(target=str(destination),source=str(source.resolve()),sha256=sha,label=label))
        update(info['presetFiles'],REFERENCE,PACK_SHA.upper())
        plan.append(dict(target=str(safe(runtime/REFERENCE)),source=str(source_pack.resolve()),sha256=PACK_SHA,label=label))
        data=json.dumps(info,ensure_ascii=False,indent=2).encode('utf-8')+b'\n'
        plan.append(dict(target=str(info_path),data=data,sha256=hashlib.sha256(data).hexdigest(),label=label))
    for label,folder in (('staging',STAGING),('installed',INSTALL)):
        for name in ('HD2ModManager.dll','HD2ModManager.pdb'):
            source=binaries/name
            plan.append(dict(target=str(safe(folder/name)),source=str(source.resolve()),sha256=digest(source),label=label))
    changes=[]
    for entry in plan:
        target=Path(entry['target']);old=digest(target) if target.exists() else None
        if old!=entry['sha256']:
            entry['previousSha256']=old;changes.append(entry)
    return changes

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    validation=json.loads((AUDIT/'formal-integration-verification.json').read_text(encoding='utf-8'))
    if validation['losslessNormalClips']!=3180 or len(validation['productionExactClips'])!=16:raise ValueError('Missing official R2 validation')
    plan=make_plan()
    for row in plan:
        target=Path(row['target'])
        if target.exists():lock_preflight(target)
    for metadata in (INSTALL/'更新记录.json', INSTALL/'生成链版本.txt', STAGING/'生成链版本.txt'):
        if metadata.exists():lock_preflight(safe(metadata))
    print('Preflight passed:',len(plan),'explicit changes',flush=True)
    if not args.apply or not plan:return
    before=protected();(AUDIT/'protected-before-sync.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');backup=safe(AUDIT/('runtime-before-'+stamp));applied=[]
    try:
        for row in plan:
            target=Path(row['target'])
            if target.exists():
                saved=safe(backup/row['label']/target.relative_to(BUNDLE if row['label']=='bundle' else (STAGING if row['label']=='staging' else INSTALL)))
                saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,saved)
                if digest(saved)!=row['previousSha256']:raise ValueError('Backup hash mismatch')
                row['backup']=str(saved)
        for row in plan:
            target=Path(row['target']);target.parent.mkdir(parents=True,exist_ok=True)
            applied.append(row)
            if 'source' in row:shutil.copy2(row['source'],target)
            else:target.write_bytes(row['data'])
            if digest(target)!=row['sha256']:raise ValueError('Synchronized hash mismatch')
        after=protected()
        if before!=after:raise ValueError('Protected library/config/runtime changed during sync; inspect external edits')
    except Exception:
        for row in reversed(applied):
            target=Path(row['target'])
            if row.get('backup'):shutil.copy2(row['backup'],target)
            elif target.exists():safe(target).unlink()
        raise
    (AUDIT/'protected-after-sync.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
    clean=[{k:v for k,v in row.items() if k!='data'} for row in plan]
    report=dict(pipelineVersion='1.0.15',singleSkeletonPipelineVersion='1.0.20',singlePlaybackRevision='normal-reference-r2',target=str(INSTALL),updatedUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),changedFiles=clean,protectedFileCount=len(after),protectedHashesUnchanged=True,backup=str(backup),luaVersion='1.0.15',deferredLuaPhysicsNotSynchronized=True,userAcceptedR2InGame=True,gameDeployed=False)
    (AUDIT/'sync-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for folder in (INSTALL,STAGING):
        version=folder/'生成链版本.txt'
        if version.exists():
            saved=safe(backup/('installed' if folder==INSTALL else 'staging')/'生成链版本.txt');shutil.copy2(version,saved)
        text=version.read_text(encoding='utf-8-sig') if version.exists() else 'pipelineVersion=1.0.15\ninstallation=manager-1.0.7\n'
        lines=[s for s in text.splitlines() if not s.startswith(('singleSkeletonPipelineVersion=','singlePlaybackRevision='))]
        lines+=['singleSkeletonPipelineVersion=1.0.20','singlePlaybackRevision=normal-reference-r2'];version.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    old=INSTALL/'更新记录.json'
    if old.exists():shutil.copy2(old,safe(backup/'installed/更新记录.json'))
    old.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SYNC COMPLETE:',len(clean),'files;',len(after),'protected hashes unchanged;',backup,flush=True)
if __name__=='__main__':main()
