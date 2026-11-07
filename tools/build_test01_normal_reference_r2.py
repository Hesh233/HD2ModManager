"""Direct normal-pack playback template build. No global default / model / game changes."""
import copy,hashlib,json,sqlite3,sys,zipfile,struct
from pathlib import Path
from collections import deque
from concurrent.futures import ProcessPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
import lz4;sys.modules['utils.lz4_311']=lz4
from anim_batch_mod import processor as p,single_skeleton as single
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.batch import discover_batch_jobs,build_batch_entries
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.cli import write_output_patch,verify_patch
from audit_single_against_normal import records,NORMAL,OUT as INSTALL
from types import SimpleNamespace
OUT=ROOT/'outputs/test01-normal-reference-r2-20261107';CURRENT=INSTALL/'test-library/[单骨架动画](test01)';MODEL=INSTALL/'test-library/[单骨架模型]test01/vpk2patch';BUILD=OUT/'normal-template-build'
DB=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
def layout(a):return [(e.type,e.subtype,e.bone,e.time) for e in a.entries if e.is_position or e.is_rotation]
def worker(job,source_entry,reference_bytes,config):
 source=AnimationData.parse(source_entry.toc_data);reference=AnimationData.parse(reference_bytes);out=copy.deepcopy(source)
 result=p.modify_animation_with_world_compensation(out,job.bones,job.unit,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True,preserve_unmodified_channels=True,source_arm_constraints=True,preserve_playback_timing=True,playback_reference=reference)
 raw=bytes(source_entry.toc_data) if result.unchanged else out.to_bytes();decoded=AnimationData.parse(raw)
 assert decoded.animation_length==reference.animation_length
 assert layout(decoded)==layout(reference),'Reference frame records/clock differ'
 for a,b in zip(decoded.initial_bone_states,reference.initial_bone_states):
  assert (a.compress_position,a.compress_rotation,a.compress_scale)==(b.compress_position,b.compress_rotation,b.compress_scale)
  assert a.scale==b.scale
 bodies=[job.bones.names.index(n) for n in ['boss','hips','spine1','spine2','chest','neck','head','weapon_aim','attach_weapon']]
 for i in bodies:
  assert decoded.initial_bone_states[i].rotation==reference.initial_bone_states[i].rotation
  assert [(e.time,e.data2) for e in decoded.entries if e.is_rotation and e.bone==i]==[(e.time,e.data2) for e in reference.entries if e.is_rotation and e.bone==i]
 if source.is_additive:assert raw==reference_bytes,'Normal additive bytes differ'
 def events(a):return [(e.type,e.subtype,e.bone,e.time,e.data2) for e in a.entries if not(e.is_position or e.is_rotation or e.is_scale)]
 assert events(decoded)==events(reference)
 output=copy.deepcopy(source_entry);output.toc_data=bytearray(raw);output.gpu_data=bytearray();output.stream_data=bytearray()
 return output,result,dict(id=f'{job.animation_id:016x}',layoutExact=True,durationExact=True,initialLayoutAndScaleExact=True,bodyRotationExact=True,additive=source.is_additive,referenceFrames=len(set(e.time for e in reference.entries if e.is_position or e.is_rotation)))
def main():
 BUILD.mkdir();index=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));index.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)
 marker=json.loads((MODEL/'single-skeleton.json').read_text(encoding='utf-8-sig'));single._validate_prepared_model(MODEL,marker)
 _,e=index.resolve(single.REFERENCE_UNIT,UNIT_TYPE_ID);unit=UnitData.parse(e.toc_data);_,e=index.resolve(unit.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(e.toc_data)
 config=p.ModConfig.load(CURRENT/'single-config.toml');discovery=discover_batch_jobs(index.store,index,[single.REFERENCE_ARCHIVE],config,requested_unit_id=single.REFERENCE_UNIT,include_ik_bones=True)
 assert not discovery.fatal_issues;rows={r[0]:r for r in records(NORMAL)};jobs=sorted(discovery.jobs,key=lambda j:j.animation_id);assert len(jobs)==len(rows)==3180
 pending=deque();items=iter(enumerate(jobs,1));entries=[];validations=[];stats=[];sentinel_jobs=[];sentinel_bytes=[]
 with NORMAL.open('rb') as nf,ProcessPoolExecutor(max_workers=4) as executor:
  def submit():
   item=next(items,None)
   if item is None:return False
   number,job=item;_,source=index.resolve(job.animation_id,ANIMATION_TYPE_ID);r=rows[job.animation_id];nf.seek(r[2]);normal_raw=nf.read(r[7])
   if number<=16:
    job.playback_reference=AnimationData.parse(normal_raw);sentinel_jobs.append(job)
   pending.append((number,executor.submit(worker,job,source,normal_raw,config)));return True
  for _ in range(8):
   if not submit():break
  while pending:
   number,future=pending.popleft();entry,result,validation=future.result();entries.append(entry);stats.append(result);validations.append(validation)
   if number<=16:sentinel_bytes.append(bytes(entry.toc_data))
   if number%100==0:print('normal template',number,3180,flush=True)
   submit()
 sentinel=build_batch_entries(index,sentinel_jobs,config,allow_additive=True,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,threads=1,preserve_hand_bend_frame=False,preserve_source_key_times=True,preserve_unmodified_channels=True,source_arm_constraints=True,preserve_playback_timing=True,preserve_unchanged_bytes=True)
 assert not sentinel.fatal_issues;assert sentinel_bytes==[bytes(e.toc_data) for e in sentinel.entries]
 runtime=BUILD/'runtime';runtime.mkdir();paths=write_output_patch(index.store,SimpleNamespace(output=runtime,patch_index=2,force=False),entries);verify_patch(paths[0],[j.animation_id for j in jobs])
 validation=dict(clips=len(validations),reference=str(NORMAL),referenceSha256=hashlib.file_digest(NORMAL.open('rb'),'sha256').hexdigest(),samples=validations,productionBackendSentinels=16,gameTested=False)
 (OUT/'full-normal-reference-validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
 report=json.loads((CURRENT/'build-report.json').read_text(encoding='utf-8-sig'));report.update(playbackRevision='normal-reference-r2',frameTimePolicy='user-normal-pack-template',preservePlaybackTiming=False,preserveUnmodifiedChannels=False,preserveSourceKeyTimes=False,referencePlaybackPath=str(NORMAL),referencePlaybackSha256=validation['referenceSha256'],ikEvaluations=sum(x.ik_evaluations for x in stats),ikCorrections=sum(x.ik_corrections for x in stats),armTargetProjections=sum(x.arm_target_projections for x in stats),armRequestedTargetMaxDistance=max(x.arm_requested_target_max_distance for x in stats),gameTested=False)
 report['files']=[dict(name=x.name,sha256=hashlib.file_digest(x.open('rb'),'sha256').hexdigest()) for x in paths];(runtime/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 for name in ['single-config.toml','standard-input.toml']:(runtime/name).write_bytes((CURRENT/name).read_bytes())
 am=json.loads((CURRENT/'single-skeleton.json').read_text(encoding='utf-8-sig'));am.update(playbackRevision='normal-reference-r2',frameTimePolicy='user-normal-pack-template',preservePlaybackTiming=False,preserveUnmodifiedChannels=False,preserveSourceKeyTimes=False,referencePlaybackSha256=validation['referenceSha256']);(runtime/'single-skeleton.json').write_text(json.dumps(am,ensure_ascii=False,indent=2),encoding='utf-8')
 manifest=json.loads((CURRENT/'manifest.json').read_text(encoding='utf-8-sig'));manifest['Description']='[全量动作文件] 正常包首尾完整帧播放模板 normal-reference-r2';(runtime/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 archive=OUT/'test01-normal-reference-r2.zip'
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
  for file in runtime.iterdir():
   if file.is_file():z.write(file,manifest['Name']+'/'+file.name.replace('.patch_2','.patch_0'))
  z.write(OUT/'full-normal-reference-validation.json','verification/full-normal-reference-validation.json')
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 (OUT/'package.json').write_text(json.dumps(dict(path=str(archive),sha256=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),report=report,globalDefaultChanged=False,gameTested=False),ensure_ascii=False,indent=2),encoding='utf-8');index.close();print('NORMAL REFERENCE R2 VERIFIED',archive,flush=True)
if __name__=='__main__':main()
