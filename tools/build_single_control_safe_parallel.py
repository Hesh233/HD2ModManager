"""Full isolated candidate build + serialized curve and additive checks."""
import copy,hashlib,json,sqlite3,sys,uuid,zipfile,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_single_elbow_torso as a
s=a.single;p=a.p
DB=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
MODEL=a.DEST/'model-fixed-final/test07';BUILD=a.DEST/'animation-build-1.0.19-parallel'
class CachedIndex(a.ResourceIndex):
 def load_or_build(self,progress=None):
  self.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);return True
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from anim_batch_mod.batch import BatchBuildResult,BatchAnimationResult,BatchIssue,build_batch_entries

def process_clip(job,entry,config,flags):
 try:
  clip=a.AnimationData.parse(entry.toc_data)
  stats=p.modify_animation_with_world_compensation(clip,job.bones,job.unit,job.config or config,
   allow_additive=flags['allow_additive'],apply_offsets_to_additive=False,
   apply_rotate_multipliers=flags['apply_rotate_multipliers'],apply_rotation_compensations=flags['apply_rotation_compensations'],
   apply_ik_correction=flags['apply_ik_correction'],preserve_hand_bend_frame=flags['preserve_hand_bend_frame'],
   preserve_source_key_times=flags['preserve_source_key_times'],preserve_unmodified_channels=flags['preserve_unmodified_channels'],
   source_arm_constraints=flags['source_arm_constraints'])
  output=copy.deepcopy(entry);output.toc_data=bytearray(entry.toc_data if stats.unchanged else clip.to_bytes())
  output.gpu_data=bytearray();output.stream_data=bytearray()
  return output,BatchAnimationResult(job.animation_id,job.animation_package,stats),None
 except Exception as error:return None,None,BatchIssue(str(job.animation_id),str(error),True)

def parallel_batch(index,jobs,config,**flags):
 assert not flags['add_unit']
 result=BatchBuildResult();pending=deque();items=iter(enumerate(jobs,1));progress=flags.pop('progress')
 flags.pop('threads');flags.pop('preserve_unchanged_bytes')
 with ProcessPoolExecutor(max_workers=4) as executor:
  def submit():
   item=next(items,None)
   if item is None:return False
   number,job=item;_,entry=index.resolve(job.animation_id,a.ANIMATION_TYPE_ID)
   pending.append((number,executor.submit(process_clip,job,entry,config,flags)));return True
  for _ in range(8):
   if not submit():break
  while pending:
   number,future=pending.popleft();entry,animation,issue=future.result()
   if issue is not None:result.issues.append(issue)
   if entry is not None:result.entries.append(entry);result.animations.append(animation)
   if progress:progress('animation',number,len(jobs),'isolated processor workers')
   submit()
 # Compare the serialized bytes against the actual production batch backend on
 # a bounded sentinel set before accepting this faster verification executor.
 sentinel=build_batch_entries(index,jobs[:16],config,threads=1,preserve_unchanged_bytes=True,**flags)
 assert not sentinel.fatal_issues
 assert [bytes(e.toc_data) for e in sentinel.entries]==[bytes(e.toc_data) for e in result.entries[:16]]
 return result

def main():
 with patch.object(s,'ResourceIndex',CachedIndex),patch.object(s,'build_batch_entries',side_effect=parallel_batch):
  report=s.build_project(MODEL,Path('E:/Steam/steamapps/common/Helldivers 2/data'),BUILD,threads=4,config_path=a.OUT/'config.toml')
 report['verificationExecutor']='bounded-process-workers-production-byte-sentinels'
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

if __name__=='__main__':main()
