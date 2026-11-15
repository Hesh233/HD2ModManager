"""Freeze the user-accepted Source2 input and prepare formal 2.3.3, without deploying."""
from pathlib import Path
import sys,json,hashlib,shutil,datetime,re
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
TEST=ROOT/'outputs/test1201-source2-live-rejection-20261111'
OUT=ROOT/'outputs/test1201-source2-accepted-20261111'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
FEEDBACK='这次修正中，暂无发现明显问题，归档，同步到正式代码，并打一个正式的物理包'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def prepare():
 assert not (OUT/'formal-source-proof.json').exists(),'Prepared acceptance inputs are immutable'
 proof=json.loads((TEST/'delivery.json').read_text('utf8'));package=Path(proof['package'])
 assert sha(package)==proof['sha256']=='9e05a4b3ed8d58f48336a147702702622ae797426bda3cbaba49a6f340686ca1'
 OUT.mkdir(exist_ok=True);(OUT/'before').mkdir(exist_ok=True);(OUT/'formal').mkdir(exist_ok=True)
 current=json.loads((TEST/'protected-before.json').read_text('utf8'))
 tracked=set(current)
 for base in [INSTALL,ROOT/'outputs/single-hd2-fix-20261106/manager']:
  if base.exists():
   tracked.update(str(p) for p in base.glob('*.dll'))
   tracked.update(str(base/'anim_batch_mod/build-info.json'))
 for prefix in ['', 'HD2ModManager_main/']:
  tracked.update(str(ROOT/(prefix+p)) for p in ['HD2PhysBoneCompat/src/physbone_compat.lua','HD2PhysBoneCompat/src/physbone_runtime.lua','tools/BuildNativeRuntime.ps1','tools/UpdateIntegratedManager.ps1','tools/native-python/anim_batch_mod/build-info.json'])
 tracked.update(str(p) for p in INSTALL.glob('*library*/*.json'))
 tracked.update(str(p) for p in INSTALL.glob('*.json'))
 tracked.update(str(p) for p in INSTALL.glob('configs/**/*.json'))
 game=Path(r'E:\Steam\steamapps\common\Helldivers 2\data')
 tracked.update(str(p) for p in game.glob('*.patch_*') if p.is_file())
 snapshot={p:sha(p) if Path(p).is_file() else None for p in sorted(tracked)};save(OUT/'protected-before.json',snapshot)
 for p in tracked:
  path=Path(p)
  if path.is_file() and path.is_relative_to(ROOT) and (path.name in ['physbone_compat.lua','physbone_runtime.lua','BuildNativeRuntime.ps1','UpdateIntegratedManager.ps1','build-info.json','HD2ModCore.dll']):
   dst=OUT/'before'/path.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst)
 live=Path(r'C:\Users\Administrator\AppData\Roaming\Arrowhead\Helldivers2\hd2physbone_compact.log');raw=live.read_bytes();(OUT/'accepted-live.log').write_bytes(raw);text=raw.decode('utf-8-sig',errors='replace')
 selected=re.findall(r'\[test1201-source\] SELECTED .*?rid=([0-9a-f]{16})',text)
 readback=[s for s in text.splitlines() if '[test1201-source] READBACK' in s]
 assert '运行时 2.3.3-test1201-source2' in text and len(selected)==8
 save(OUT/'accepted-feedback-and-live.json',dict(userFeedbackVerbatim=FEEDBACK,acceptedAt=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),scope='用户本轮试用暂无明显问题；非全模型/全动作/长期多人/几何或FPS穷尽验收',sessionStart=re.search(r'会话开始 (.*?) \|',text).group(1),selectedInstances=len(selected),resources=selected,readback=readback,sourceRejections=[s for s in text.splitlines() if '[test1201-source] rejected' in s],frontSampleCount=text.count('[test1201-front]'),liveSha256=sha(OUT/'accepted-live.log'),testPackage=proof))
 for name,old,new in [('compat','1.3.3-test1201-source2','1.3.3'),('runtime','2.3.3-test1201-source2','2.3.3')]:
  raw=(TEST/f'physbone_{name}-test1201.lua').read_bytes();assert raw.count(old.encode())==1
  candidate=raw.replace(old.encode(),new.encode());(OUT/'formal'/f'physbone_{name}.lua').write_bytes(candidate)
  assert candidate.replace(new.encode(),old.encode())==raw
 save(OUT/'formal-source-proof.json',dict(status='VERSION_ONLY_CHANGE_FROM_ACCEPTED_SOURCE2',runtimeVersion='2.3.3',compatVersion='1.3.3',sources={name:dict(testSha256=sha(TEST/f'physbone_{name}-test1201.lua'),formalSha256=sha(OUT/'formal'/f'physbone_{name}.lua')) for name in ['compat','runtime']},solverUnchanged=True,rigAndResourceGuardsUnchanged=True))
 print(json.dumps(dict(out=str(OUT),protectedFiles=len(snapshot),selected=len(selected),readback=readback),ensure_ascii=False))
if __name__=='__main__':prepare()
