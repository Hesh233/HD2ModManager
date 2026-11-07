"""Isolated full test01 playback fix build; no model, Lua, profile, or game writes."""
import copy,json,sqlite3,sys,zipfile,hashlib
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import deque
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
import lz4;sys.modules['utils.lz4_311']=lz4
from anim_batch_mod import processor as p,single_skeleton as s
from anim_batch_mod.archive import ResourceIndex,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import AnimationData
from anim_batch_mod.batch import BatchBuildResult,BatchAnimationResult,BatchIssue,build_batch_entries
from audit_test01_single_playback import timeline
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';OUT=ROOT/'outputs/test01-single-jitter-20261107'
MODEL=INSTALL/'test-library/[单骨架模型]test01/vpk2patch';CURRENT=INSTALL/'test-library/[单骨架动画](test01)';BUILD=OUT/'native-clock-r1-build'
DB=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
class CachedIndex(ResourceIndex):
 def load_or_build(self,progress=None):self.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);return True

def process_clip(job,entry,config,flags):
 try:
  source=AnimationData.parse(entry.toc_data);clip=copy.deepcopy(source)
  st=p.modify_animation_with_world_compensation(clip,job.bones,job.unit,job.config or config,
   allow_additive=flags['allow_additive'],apply_offsets_to_additive=False,
   apply_rotate_multipliers=flags['apply_rotate_multipliers'],apply_rotation_compensations=flags['apply_rotation_compensations'],
   apply_ik_correction=flags['apply_ik_correction'],preserve_hand_bend_frame=flags['preserve_hand_bend_frame'],
   preserve_source_key_times=flags['preserve_source_key_times'],preserve_unmodified_channels=flags['preserve_unmodified_channels'],
   source_arm_constraints=flags['source_arm_constraints'],preserve_playback_timing=flags['preserve_playback_timing'])
  data=bytes(entry.toc_data) if st.unchanged else clip.to_bytes();decoded=AnimationData.parse(data)
  a,z=timeline(entry.toc_data),timeline(data)
  assert z['durationMs']==a['durationMs'],'Native duration changed'
  assert z['tailExcess']<=max(0,a['tailExcess'])+.001,'Generated a frame beyond the native clock'
  assert z['mirrorValid'] and z['mirrorEqual'],'Mirrored playback blocks differ'
  keys={(i,kind,p._wire_time_key(0.)) for i in range(len(source.initial_bone_states)) for kind in ['p','r','s']}
  for e in decoded.entries:
   if e.is_position or e.is_rotation or e.is_scale:keys.add((e.bone,'p' if e.is_position else 'r' if e.is_rotation else 's',p._wire_time_key(e.time)))
  missing=[]
  for e in source.entries:
   if e.is_position or e.is_rotation or e.is_scale:
    key=(e.bone,'p' if e.is_position else 'r' if e.is_rotation else 's',p._wire_time_key(e.time))
    if key not in keys:missing.append(key)
  assert not missing,'A native control timestamp was discarded'
  body=[job.bones.names.index(n) for n in ['boss','hips','spine1','spine2','chest','neck','head','weapon_aim','attach_weapon'] if n in job.bones.names]
  assert all(source.initial_bone_states[i].rotation==decoded.initial_bone_states[i].rotation for i in body)
  for i in body:
   def rotations(anim):return sorted([(e.type,e.subtype,e.time,e.data2) for e in anim.entries if e.is_rotation and e.bone==i],key=lambda v:v[2])
   assert rotations(source)==rotations(decoded),'An unmodified body rotation curve changed'
  assert source.hashes==decoded.hashes and source.hashes2==decoded.hashes2 and source.hashes_floats==decoded.hashes_floats
  def events(anim):return sorted([(e.type,e.subtype,e.bone,e.time,e.data2) for e in anim.entries if not(e.is_position or e.is_rotation or e.is_scale)],key=lambda x:x[3])
  assert events(source)==events(decoded),'Animation event times changed'
  if source.is_additive:assert data==bytes(entry.toc_data),'Native additive bytes changed'
  output=copy.deepcopy(entry);output.toc_data=bytearray(data);output.gpu_data=bytearray();output.stream_data=bytearray()
  validation=dict(id=f'{job.animation_id:016x}',nativeDurationMs=a['durationMs'],tailExcessMs=z['tailExcess'],nativeTailExcessMs=a['tailExcess'],additive=source.is_additive,sourceControlTimesRetained=True,bodyRotationCurvesExact=True,eventsExact=True)
  return output,BatchAnimationResult(job.animation_id,job.animation_package,st),None,validation
 except Exception as error:return None,None,BatchIssue(str(job.animation_id),str(error),True),None

def parallel(index,jobs,config,**flags):
 assert not flags['add_unit'];result=BatchBuildResult();progress=flags.pop('progress');flags.pop('threads');flags.pop('preserve_unchanged_bytes');pending=deque();iterator=iter(enumerate(jobs,1));validations=[]
 with ProcessPoolExecutor(max_workers=4) as executor:
  def submit():
   item=next(iterator,None)
   if item is None:return False
   count,job=item;_,entry=index.resolve(job.animation_id,ANIMATION_TYPE_ID);pending.append((count,executor.submit(process_clip,job,entry,config,flags)));return True
  for _ in range(8):
   if not submit():break
  while pending:
   count,future=pending.popleft();entry,animation,issue,v=future.result()
   if issue is not None:result.issues.append(issue)
   if entry is not None:result.entries.append(entry);result.animations.append(animation);validations.append(v)
   if progress:progress('animation',count,len(jobs),'native playback clock')
   submit()
 sentinel=build_batch_entries(index,jobs[:16],config,threads=1,preserve_unchanged_bytes=True,**flags)
 assert not sentinel.fatal_issues
 assert [bytes(e.toc_data) for e in sentinel.entries]==[bytes(e.toc_data) for e in result.entries[:16]]
 (OUT/'full-playback-validation.json').write_text(json.dumps(dict(validated=len(validations),failures=[x.message for x in result.issues],samples=validations),indent=2),encoding='utf-8')
 return result

def main():
 with patch.object(s,'ResourceIndex',CachedIndex),patch.object(s,'build_batch_entries',side_effect=parallel):report=s.build_project(MODEL,Path('E:/Steam/steamapps/common/Helldivers 2/data'),BUILD,threads=4,config_path=CURRENT/'standard-input.toml')
 assert report['expected_animations']==report['available_animations']==3180
 runtime=BUILD/'runtime';manifest=json.loads((CURRENT/'manifest.json').read_text(encoding='utf-8-sig'));manifest['Description']='[全量动作文件] 原生播放时长/精准尾帧修正 native-clock-r1'
 (runtime/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');(runtime/'build-report.json').write_bytes((BUILD/'build-report.json').read_bytes())
 archive=OUT/'test01-single-native-clock-r1.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
  for file in runtime.iterdir():
   if file.is_file():z.write(file,manifest['Name']+'/'+file.name.replace('.patch_2','.patch_0'))
  z.write(OUT/'full-playback-validation.json','verification/full-playback-validation.json')
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 (OUT/'package.json').write_text(json.dumps(dict(path=str(archive),sha256=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),report=report,gameTested=False),ensure_ascii=False,indent=2),encoding='utf-8')
 print('VERIFIED FULL NATIVE PLAYBACK PACKAGE',archive,flush=True)
if __name__=='__main__':main()
