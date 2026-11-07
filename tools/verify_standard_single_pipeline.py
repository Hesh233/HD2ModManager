"""Full golden control, default-path isolation, and a full legacy-model single candidate."""
import copy,hashlib,importlib.util,json,sqlite3,sys,tempfile,time,uuid,zipfile
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import processor as proc,single_skeleton as single
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from audit_single_against_normal import records,NORMAL
OUT=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';MODEL=OUT/'test-library/[单骨架模型]test07/vpk2patch';STANDARD=OUT/'config.toml'
DB=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
REPORT=Path(sys.argv[1]) if len(sys.argv)>1 else OUT/'单骨架成熟流程-全量验证-20261107.json'
def save(r):REPORT.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 started=time.time();store=PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'));index=ResourceIndex(store);index.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)
 _,e=index.resolve(single.REFERENCE_UNIT,UNIT_TYPE_ID);unit=UnitData.parse(e.toc_data);_,e=index.resolve(unit.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(e.toc_data);config=proc.ModConfig.load(STANDARD)
 normal_rows={r[0]:r for r in records(NORMAL)};report=dict(status='RUNNING',processingProfile=single.PROCESSING_PROFILE,normalControl=dict(total=len(normal_rows),byteExact=0,mismatches=[],ikEvaluations=0),additiveIds=[],defaultCompatibility=[],gameDeployed=False,gameTested=False)
 loader=SourceFileLoader('anim_batch_mod._before_standard',str(OUT/'processor.py.before-standard-single-20261107.bak'));spec=importlib.util.spec_from_loader(loader.name,loader);before=importlib.util.module_from_spec(spec);sys.modules[loader.name]=before;loader.exec_module(before);oldconfig=before.ModConfig.load(STANDARD)
 if REPORT.exists():report=json.loads(REPORT.read_text(encoding='utf-8'))
 resume_count=report['normalControl']['byteExact']+len(report['normalControl']['mismatches'])
 checked=set(int(c['id'],16) for c in json.loads((OUT/'单骨架-配置参考及IK实证-20261107.json').read_text(encoding='utf-8'))['samples'])
 with NORMAL.open('rb') as nf:
  for count,fid in enumerate(sorted(normal_rows),1):
   if count<=resume_count:continue
   r=normal_rows[fid];nf.seek(r[2]);gold=nf.read(r[7]);_,entry=index.resolve(fid,ANIMATION_TYPE_ID);source=AnimationData.parse(entry.toc_data)
   if source.is_additive:report['additiveIds'].append(f'{fid:016x}')
   clip=copy.deepcopy(source);stats=proc.modify_animation_with_world_compensation(clip,bones,unit,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True)
   report['normalControl']['ikEvaluations']+=stats.ik_evaluations
   if (bytes(entry.toc_data) if stats.unchanged else clip.to_bytes())==gold:report['normalControl']['byteExact']+=1
   else:
    normal=AnimationData.parse(gold);report['normalControl']['mismatches'].append(dict(id=f'{fid:016x}',additive=source.is_additive,sourceDuration=source.animation_length,generatedDuration=clip.animation_length,normalDuration=normal.animation_length))
   if fid in checked:
    old,new=copy.deepcopy(source),copy.deepcopy(source)
    before.modify_animation_with_world_compensation(old,bones,unit,oldconfig,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True)
    proc.modify_animation_with_world_compensation(new,bones,unit,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True)
    report['defaultCompatibility'].append(dict(id=f'{fid:016x}',byteExact=old.to_bytes()==new.to_bytes()))
   if count%100==0:save(report);print('normal',count,'exact',report['normalControl']['byteExact'],'elapsed',round(time.time()-started,1),flush=True)
 with NORMAL.open('rb') as nf:
  remaining=[]
  for mismatch in report['normalControl']['mismatches']:
   fid=int(mismatch['id'],16);nr=normal_rows[fid];nf.seek(nr[2]);gold=nf.read(nr[7]);_,entry=index.resolve(fid,ANIMATION_TYPE_ID);clip=AnimationData.parse(entry.toc_data)
   st=proc.modify_animation_with_world_compensation(clip,bones,unit,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True)
   if (bytes(entry.toc_data) if st.unchanged else clip.to_bytes())==gold:report['normalControl']['byteExact']+=1
   else:remaining.append(mismatch)
  report['normalControl']['mismatches']=remaining
 save(report)
 assert all(x['byteExact'] for x in report['defaultCompatibility']),'Existing default/dual processing changed'
 print('NORMAL CONTROL',report['normalControl']['byteExact'],len(normal_rows),'mismatches',len(report['normalControl']['mismatches']),flush=True)
 # Source config is read at build time; v3 geometry is validated but its failed
 # animation contract is never loaded/executed. Do not modify the library.
 fingerprints=single._model_files(MODEL);old_manifest=(MODEL/'single-skeleton.json').read_bytes();additive_ids={int(x,16) for x in report['additiveIds']}
 with tempfile.TemporaryDirectory(prefix='hd2-standard-single-') as td:
  work=Path(td);output=work/'build'
  class CachedIndex(ResourceIndex):
   def load_or_build(self,progress=None):self.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);return True
  real_batch=single.build_batch_entries
  def traced_batch(*args,**kwargs):
   assert kwargs['preserve_hand_bend_frame'] is False and kwargs['preserve_source_key_times'] is True and kwargs['preserve_unchanged_bytes'] is True
   assert set(args[2].ik_chains)=={'l_hand','r_hand','l_foot','r_foot'}
   for c in args[2].ik_chains.values():assert c.target_multiplier==[.4,.4,1.0]
   result=real_batch(*args,**kwargs);unchanged=0;changed=[]
   with NORMAL.open('rb') as nf:
    for e in result.entries:
     if e.type_id==ANIMATION_TYPE_ID and e.file_id in additive_ids:
      r=normal_rows[e.file_id];nf.seek(r[2]);same=bytes(e.toc_data)==nf.read(r[7]);unchanged+=same
      if not same:changed.append(f'{e.file_id:016x}')
   report['modelAdditivePreservation']=dict(total=len(additive_ids),byteExactNormal=unchanged,changedIds=changed)
   save(report);return result
  with patch.object(single,'ResourceIndex',CachedIndex),patch.object(single,'build_batch_entries',side_effect=traced_batch):built=single.build_project(MODEL,store.game_data,output,threads=4,config_path=STANDARD)
  assert built['expected_animations']==built['available_animations']==3180 and built['ikEvaluations']>0
  assert report['modelAdditivePreservation']['byteExactNormal']==len(additive_ids),'Native additive data changed'
  runtime=output/'runtime';name='[单骨架动画](test07)';guid=str(uuid.UUID(bytes_le=hashlib.md5(('single-animation:'+name).encode()).digest()))
  (runtime/'manifest.json').write_text(json.dumps(dict(Version=1,Guid=guid,Name=name,Description='[全量动作文件]'),ensure_ascii=False,indent=2),encoding='utf-8')
  (runtime/'build-report.json').write_bytes((output/'build-report.json').read_bytes())
  (OUT/'单骨架成熟流程-test07全量打包报告-20261107.json').write_bytes((output/'build-report.json').read_bytes())
  zip_path=OUT/'test07-单骨架成熟标准-1.0.18-待测试.zip'
  with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
   for p in runtime.iterdir():
    if p.is_file():z.write(p,name+'/'+p.name.replace('.patch_2','.patch_0'))
  with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None
  report['fullModelPackage']=dict(path=str(zip_path),sha256=hashlib.file_digest(zip_path.open('rb'),'sha256').hexdigest(),animations=3180,ikEvaluations=built['ikEvaluations'],ikCorrections=built['ikCorrections'],inputVersion=built['inputModelManifestVersion'],legacyConfigIgnored=built['legacyModelConfigurationIgnored'],sourceConfigSha256=built['standardConfigSha256'],temporaryOutputCleaned=True)
 assert single._model_files(MODEL)==fingerprints and (MODEL/'single-skeleton.json').read_bytes()==old_manifest
 report['modelLibraryUnchanged']=True;report['elapsedSeconds']=time.time()-started
 report['status']='PASS' if report['normalControl']['byteExact']==len(normal_rows) else 'NORMAL_CONTROL_DIFFERENCES_REQUIRE_REVIEW'
 save(report);index.close();print('FINAL',report['status'],report['fullModelPackage'],flush=True)
if __name__=='__main__':main()
