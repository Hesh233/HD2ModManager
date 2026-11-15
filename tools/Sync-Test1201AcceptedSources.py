"""Apply only accepted physics sources, version assertions and physics metadata."""
from pathlib import Path
import sys,json,hashlib,re,shutil
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/test1201-source2-accepted-20261111';INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (OUT/'source-sync.json').exists(),'Source synchronization is already frozen'
baseline=json.loads((OUT/'protected-before.json').read_text('utf8'));plan=[]
def add(p,data,reason):
 assert p.is_relative_to(ROOT)
 original=p.read_bytes();before=sha(p)
 if str(p) in baseline:assert before==baseline[str(p)],f'Changed since snapshot: {p}'
 backup=OUT/'before'/p.relative_to(ROOT);backup.parent.mkdir(parents=True,exist_ok=True)
 if backup.exists():assert backup.read_bytes()==original
 else:backup.write_bytes(original)
 plan.append((p,data,dict(path=str(p),beforeSha256=before,afterSha256=hashlib.sha256(data).hexdigest(),reason=reason)))
for prefix in ['', 'HD2ModManager_main/']:
 for kind in ['compat','runtime']:
  p=ROOT/prefix/'HD2PhysBoneCompat/src'/f'physbone_{kind}.lua';add(p,(OUT/'formal'/p.name).read_bytes(),'Promote accepted Source2 exactly; version suffix only removed')
 p=ROOT/prefix/'tools/BuildNativeRuntime.ps1';raw=p.read_bytes();new=raw.replace(b"physicsRuntimeVersion='2.3.1'",b"physicsRuntimeVersion='2.3.3'").replace(b"physicsCompatVersion='1.3.1'",b"physicsCompatVersion='1.3.3'")
 assert new!=raw and new.count(b"physicsRuntimeVersion='2.3.3'")==1 and new.count(b"physicsCompatVersion='1.3.3'")==1
 add(p,new,'Only physics version fields; keep other build settings')
 for n in ['driver-update-test.py','single-front-skirt-test.py','spring-dof-model-test.py','test06-native-vrd-bind-test.py']:
  p=ROOT/prefix/'HD2PhysBoneCompat/test'/n;raw=p.read_bytes();assert b'1.3.1' in raw;add(p,raw.replace(b'1.3.1',b'1.3.3'),'Update only compat version expectations, retain all physics assertions')
metadata=[ROOT/'tools/native-python/anim_batch_mod/build-info.json',ROOT/'HD2ModManager_main/tools/native-python/anim_batch_mod/build-info.json',INSTALL/'anim_batch_mod/build-info.json']
# The older isolated single-fix staging DLL is intentionally not promoted to B3 or relabelled.
for p in metadata:
 raw=p.read_bytes();v=json.loads(raw);assert v['physicsRuntimeVersion']=='2.3.1';text=raw.decode('utf-8-sig')
 text,n=re.subn(r'("physicsRuntimeVersion"\s*:\s*")2\.3\.1(")',r'\g<1>2.3.3\2',text);assert n==1
 if 'physicsCompatVersion' in v:
  text,n=re.subn(r'("physicsCompatVersion"\s*:\s*")1\.3\.1(")',r'\g<1>1.3.3\2',text);assert n==1
 else:
  newline='\r\n' if '\r\n' in text else '\n';text=text.replace('"physicsRuntimeVersion": "2.3.3",','"physicsRuntimeVersion": "2.3.3",'+newline+'  "physicsCompatVersion": "1.3.3",')
 new=json.loads(text);assert {k for k in set(v)|set(new) if v.get(k)!=new.get(k)}=={'physicsRuntimeVersion','physicsCompatVersion'}
 add(p,text.encode('utf8'),'Only physics runtime/compat metadata; preserve B3, single/R2 and other fields')
for p,data,row in plan:
 assert sha(p)==row['beforeSha256'];p.write_bytes(data);assert sha(p)==row['afterSha256']
(OUT/'source-sync.json').write_text(json.dumps(dict(status='ACCEPTED_PHYSICS_SOURCE_SYNCED',files=[row for _,_,row in plan],olderSingleFixStagingPreserved=True),ensure_ascii=False,indent=2),'utf8')
print('Synced',len(plan),'scoped source/version files; no model, animation, deployment or other code changes')
