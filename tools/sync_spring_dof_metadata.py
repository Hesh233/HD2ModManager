"""Update only physics version metadata; keep current user/pipeline/source hashes."""
import copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=[ROOT/'tools/native-python/anim_batch_mod/build-info.json',
 ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/anim_batch_mod/build-info.json',
 ROOT/'outputs/single-hd2-fix-20261106/manager/anim_batch_mod/build-info.json']
rows=[]
for path in paths:
 if not path.exists():continue
 raw=path.read_bytes();before=json.loads(raw.decode('utf-8-sig'));after=copy.deepcopy(before)
 after['physicsRuntimeVersion']='2.3.0';after['physicsCompatVersion']='1.3.0'
 for key in before:
  if key not in ('physicsRuntimeVersion','physicsCompatVersion'):assert before[key]==after[key]
 backup=Path(str(path)+'.before-spring-dof-130-20261108.bak')
 if path==paths[1]:backup=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/非运行文件/归档/旧版备份/anim_batch_mod-build-info.json.before-spring-dof-130-20261108.bak'
 if not backup.exists():backup.write_bytes(raw)
 text=json.dumps(after,ensure_ascii=False,indent=2)+'\n'
 if b'\r\n' in raw:text=text.replace('\n','\r\n')
 path.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+text.encode('utf-8'))
 rows.append(dict(path=str(path),previous=before.get('physicsRuntimeVersion'),current='2.3.0',
  unrelatedFieldsPreserved=True,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
p=ROOT/'tools/BuildNativeRuntime.ps1';raw=p.read_bytes();text=raw.decode('utf-8-sig')
old="physicsRuntimeVersion='2.2.1';"
if old in text:
 assert text.count(old)==1;text=text.replace(old,"physicsRuntimeVersion='2.3.0'; physicsCompatVersion='1.3.0';")
else:assert "physicsRuntimeVersion='2.3.0'; physicsCompatVersion='1.3.0';" in text
p.write_bytes((b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b'')+text.encode('utf-8'))
(ROOT/'outputs/vrd-analysis-20261107/spring-dof-metadata-20261108.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print('physics metadata updated:',len(rows),'files; all other values preserved')
