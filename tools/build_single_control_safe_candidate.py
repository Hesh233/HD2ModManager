"""Full isolated candidate build + serialized curve and additive checks."""
import copy,hashlib,json,sqlite3,sys,uuid,zipfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_single_elbow_torso as a
s=a.single;p=a.p
DB=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
MODEL=a.DEST/'model-fixed-final/test07';BUILD=a.DEST/'animation-build-1.0.19'
class CachedIndex(a.ResourceIndex):
 def load_or_build(self,progress=None):
  self.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);return True
with patch.object(s,'ResourceIndex',CachedIndex):
 report=s.build_project(MODEL,Path('E:/Steam/steamapps/common/Helldivers 2/data'),BUILD,threads=4,config_path=a.OUT/'config.toml')
assert report['expected_animations']==report['available_animations']==3180
runtime=BUILD/'runtime';pack=next(runtime.glob('*.patch_2'));rows={r[0]:r for r in a.records(pack) if r[1]==a.ANIMATION_TYPE_ID}
index=CachedIndex(a.PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));index.load_or_build()
_,e=index.resolve(s.REFERENCE_UNIT,a.UNIT_TYPE_ID);n=a.UnitData.parse(e.toc_data);_,e=index.resolve(n.bones_ref,a.BONE_TYPE_ID);b=a.BonesData.parse(e.toc_data)
protected={b.names.index(name) for name in a.TORSO if name in b.names};validation=dict(clips=0,additive=0,additiveByteExact=0,unmodifiedRotationCurvesExact=0,failures=[],gameTested=False)
with pack.open('rb') as f:
 for fid,r in rows.items():
  f.seek(r[2]);raw=f.read(r[7]);output=a.AnimationData.parse(raw);_,e=index.resolve(fid,a.ANIMATION_TYPE_ID);source=a.AnimationData.parse(e.toc_data)
  validation['clips']+=1
  if source.is_additive:
   validation['additive']+=1;validation['additiveByteExact']+=raw==e.toc_data
  else:
   exact=all(source.initial_bone_states[i].rotation==output.initial_bone_states[i].rotation for i in protected)
   def rotations(clip):return [(e.bone,e.type,e.subtype,e.time,e.data2) for e in clip.entries if e.is_rotation and e.bone in protected]
   exact=exact and rotations(source)==rotations(output)
   validation['unmodifiedRotationCurvesExact']+=exact
   if not exact:validation['failures'].append(f'{fid:016x}')
assert validation['additive']==validation['additiveByteExact']==187
assert not validation['failures'],validation['failures'][:10]
index.close();(a.DEST/'full-build-validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
name='[单骨架动画](test07)';guid=str(uuid.UUID(bytes_le=hashlib.md5(('single-animation:'+name).encode()).digest()))
(runtime/'manifest.json').write_text(json.dumps(dict(Version=1,Guid=guid,Name=name,Description='[全量动作文件] 单骨架1.0.19坐标/手肘修正；需配套重新导入模型'),ensure_ascii=False,indent=2),encoding='utf-8')
(runtime/'build-report.json').write_bytes((BUILD/'build-report.json').read_bytes())
zip_path=a.DEST/'test07-single-1.0.19-candidate.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
 for file in runtime.iterdir():
  if file.is_file():z.write(file,name+'/'+file.name.replace('.patch_2','.patch_0'))
 for file in MODEL.iterdir():
  if file.is_file() and not file.name.endswith('.sqlite3'):z.write(file,'[单骨架模型]test07/vpk2patch/'+file.name)
with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None
summary=dict(path=str(zip_path),sha256=hashlib.file_digest(zip_path.open('rb'),'sha256').hexdigest(),validation=validation,report=report)
(a.DEST/'candidate-package.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('CANDIDATE VERIFIED',zip_path,flush=True)
