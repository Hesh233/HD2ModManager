"""Narrow accepted single-animation sync; default is preflight only.
No whole publish, library/profile/model/animation/game write, Core/CLI or Lua copy.
"""
from pathlib import Path
import argparse,ctypes,datetime,hashlib,json,os,shutil
from ctypes import wintypes
ROOT=Path(__file__).resolve().parents[1];ANIMATION=ROOT.parent;AUDIT=ROOT/'outputs/single-animation-size-integration-20261108'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
BUNDLE=ROOT/'tools/native-python/anim_batch_mod'
MODULES=('single_skeleton.py','single_animation_compaction.py')
PROFILE='single-constant-float-boundary2-v1'
def digest(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def safe(path):
 p=Path(path).resolve()
 if not p.is_relative_to(ROOT.resolve()):raise ValueError('Target escaped intended repository: '+str(p))
 return p
def preflight_lock(path):
 if os.name!='nt':return
 api=ctypes.WinDLL('kernel32',use_last_error=True);api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];api.CreateFileW.restype=wintypes.HANDLE;api.CloseHandle.argtypes=[wintypes.HANDLE]
 h=api.CreateFileW(str(path),0x80000000|0x40000000,0,None,3,0,None)
 if h==wintypes.HANDLE(-1).value:raise OSError(ctypes.get_last_error(),'Locked/read-only synchronization target (do not kill manager): '+str(path))
 api.CloseHandle(h)
def protected_check():
 baseline=json.loads((AUDIT/'protected-before.json').read_text(encoding='utf-8'));changed=[]
 for path,h in baseline['files'].items():
  if not Path(path).is_file() or digest(path)!=h:changed.append(path)
 game=Path('E:/Steam/steamapps/common/Helldivers 2/data');after=[]
 for p in sorted(game.glob('*.patch_*')):
  if p.is_file():after.append(dict(path=str(p.absolute()),resolved=str(p.resolve()),sha256=digest(p),bytes=p.stat().st_size))
 if after!=baseline['gameFiles']:changed.append('game symlink names/targets/bytes changed')
 if changed:raise ValueError('Protected inputs changed (possibly external work): '+str(changed))
 return len(baseline['files'])
def plan():
 result=[]
 for label,runtime in (('bundle',BUNDLE),('installed',INSTALL/'anim_batch_mod')):
  ip=safe(runtime/'build-info.json');info=json.loads(ip.read_text('utf-8-sig'))
  if info.get('pipelineVersion')!='1.0.15' or info.get('singleSkeletonPipelineVersion') not in ('1.0.20','1.0.21'):raise ValueError('Unexpected/newer runtime: do not downgrade')
  info.update(singleSkeletonPipelineVersion='1.0.21',singleOutputEncodingProfile=PROFILE,singleBoundaryFramesEachEnd=2)
  for name in MODULES:
   source=ANIMATION/name;h=digest(source);row=next((r for r in info['files'] if r['name']==name),None)
   if row is None:info['files'].append(dict(name=name,sha256=h.upper()))
   else:row['sha256']=h.upper()
   result.append(dict(target=str(safe(runtime/name)),source=str(source.resolve()),sha256=h,label=label))
  data=(json.dumps(info,ensure_ascii=False,indent=2)+'\n').encode('utf-8');result.append(dict(target=str(ip),data=data,sha256=hashlib.sha256(data).hexdigest(),label=label))
 for name in ('HD2ModManager.dll','HD2ModManager.pdb'):
  source=AUDIT/'wpf-build/bin/Release/net10.0-windows'/name
  result.append(dict(target=str(safe(INSTALL/name)),source=str(source),sha256=digest(source),label='installed'))
 vp=safe(INSTALL/'生成链版本.txt');text=vp.read_text('utf-8-sig');lines=[line for line in text.splitlines() if not line.startswith(('singleSkeletonPipelineVersion=','singleOutputEncodingProfile='))]
 lines+=['singleSkeletonPipelineVersion=1.0.21','singleOutputEncodingProfile='+PROFILE]
 data=('\n'.join(lines)+'\n').encode('utf-8');result.append(dict(target=str(vp),data=data,sha256=hashlib.sha256(data).hexdigest(),label='installed'))
 changes=[]
 for r in result:
  old=digest(r['target']) if Path(r['target']).exists() else None
  if old!=r['sha256']:r['previousSha256']=old;changes.append(r)
 return changes
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
 verified=json.loads((AUDIT/'formal-integration-verification.json').read_text(encoding='utf-8'));full=json.loads((AUDIT/'full-accepted-byte-regression.json').read_text(encoding='utf-8'))
 if verified['status']!='pass' or len(verified['samples'])!=16 or full['clips']!=3180 or full['status']!='pass':raise ValueError('Accepted byte/production verification missing')
 certificate=json.loads((AUDIT/'verification-source-sha256.json').read_text(encoding='utf-8'))
 for path,h in certificate.items():
  if digest(path)!=h:raise ValueError('Source/build changed since verification: '+path)
 changes=plan()
 for r in changes:
  if Path(r['target']).exists():preflight_lock(Path(r['target']))
 count=protected_check();print('PREFLIGHT PASS:',len(changes),'target changes;',count,'protected files unchanged.',flush=True)
 if not args.apply or not changes:return
 backup=safe(AUDIT/'runtime-before');backup.mkdir(exist_ok=False);applied=[]
 try:
  for r in changes:
   p=Path(r['target'])
   if p.exists():
    base=BUNDLE if r['label']=='bundle' else INSTALL;b=safe(backup/r['label']/p.relative_to(base));b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b)
    if digest(b)!=r['previousSha256']:raise ValueError('Backup checksum differs')
    r['backup']=str(b)
  for r in changes:
   target=Path(r['target']);target.parent.mkdir(parents=True,exist_ok=True);applied.append(r)
   if 'source' in r:shutil.copy2(r['source'],target)
   else:target.write_bytes(r['data'])
   if digest(target)!=r['sha256']:raise ValueError('Synchronized file checksum differs')
  count=protected_check()
 except BaseException:
  for r in reversed(applied):
   target=safe(r['target'])
   if r.get('backup'):shutil.copy2(r['backup'],target)
   elif target.exists():target.unlink()  # Only our newly-created, verified workspace file.
  raise
 clean=[{k:v for k,v in r.items() if k!='data'} for r in changes];report=dict(status='pass',singleSkeletonPipelineVersion='1.0.21',singleOutputEncodingProfile=PROFILE,userAcceptedTest01=True,
  changedFiles=clean,protectedFiles=count,libraryConfigurationModelsAnimationsAndGameUnchanged=True,noWholePublish=True,coreCliLuaPhysicsNotCopied=True,backup=str(backup),updatedUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (AUDIT/'sync-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('SYNC PASS:',len(changes),'files;',count,'protected.',flush=True)
if __name__=='__main__':main()
