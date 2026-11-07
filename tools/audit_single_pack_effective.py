"""Replay latest selected clips and trace the actual arm IK solver, read-only inputs."""
import copy,hashlib,json,math,sqlite3,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import processor as proc,single_skeleton as single
from anim_batch_mod.archive import PackageStore,ResourceIndex,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from audit_single_against_normal import records,NORMAL,CURRENT,OUT,ARM,angle
from anim_batch_mod.math3d import quat_normalize

def main():
 model=OUT/'test-library/[单骨架模型]test07/vpk2patch';a=CURRENT.parent;marker=json.loads((a/'single-skeleton.json').read_text(encoding='utf-8'));single._validate_prepared_model(model,marker)
 config=proc.ModConfig.load(a/'single-config.toml');standard=proc.ModConfig.load(ROOT.parent/'config.toml')
 index=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));db=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
 _,e=index.resolve(0x4d1c334d294dfa97,UNIT_TYPE_ID);unit=UnitData.parse(e.toc_data);_,e=index.resolve(unit.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(e.toc_data)
 # 16 prior uniform samples, plus known older arm-motion suspects, not just prefix jobs.
 ids=[int(c['id'],16) for c in json.loads((OUT/'test07-单骨架-手臂文件核查.json').read_text(encoding='utf-8'))['realClipSamples']]
 ids+= [3542481557377973498,11623262177752411465,2372646189065085873,7487460257401496141,2079987957316695397]
 ids=list(dict.fromkeys(ids));nr={r[0]:r for r in records(NORMAL)};cr={r[0]:r for r in records(CURRENT)}
 report=dict(status='RUNNING',currentModelValidated=True,modelScale=marker['modelScale'],modelConfigurationHash=marker['configSha256'],
  declaredReference={'unit':marker['referenceUnit'],'archive':marker['referenceArchive'],'readByCurrentPrepareModel':True,'usesBaseAnimFile':False,'usesUnitAnimFile':False},
  referenceFile=str(NORMAL),samples=[],gameOrLibraryModified=False)
 real_solver=proc._apply_two_bone_ik
 with NORMAL.open('rb') as nf,CURRENT.open('rb') as cf:
  for fid in ids:
   if fid not in nr or fid not in cr:continue
   nrow,crow=nr[fid],cr[fid];nf.seek(nrow[2]);cf.seek(crow[2]);normal_bytes=nf.read(nrow[7]);current_bytes=cf.read(crow[7]);normal=AnimationData.parse(normal_bytes);current=AnimationData.parse(current_bytes)
   _,e=index.resolve(fid,ANIMATION_TYPE_ID);source=AnimationData.parse(e.toc_data);replayed=copy.deepcopy(source)
   with patch.object(proc,'_apply_two_bone_ik',wraps=real_solver) as trace:
    stats=proc.modify_animation_with_world_compensation(replayed,bones,unit,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=True,apply_ik_correction=True)
    solver_calls=trace.call_count
   row=dict(id=f'{fid:016x}',additive=source.is_additive,byteExactLatestReplay=replayed.to_bytes()==current_bytes,
    currentArmProjectionSamples=stats.arm_retargets,currentTwoBoneSolverCalls=solver_calls,currentReportedIKCorrections=stats.ik_corrections,
    eventTablesMatch=normal.hashes==current.hashes and normal.hashes2==current.hashes2 and normal.hashes_floats==current.hashes_floats,
    flagsMatch=(normal.unk,normal.unk2,normal.is_additive)==(current.unk,current.unk2,current.is_additive),normalVsCurrent={})
   nt,ct=proc._build_tracks(normal),proc._build_tracks(current)
   for i,name in ARM.items():
    differences=[]
    for t in [0,33,min(normal.animation_length,current.animation_length)*500,min(normal.animation_length,current.animation_length)*1000]:
     differences.append(dict(timeMs=t,rotationDegrees=angle(nt[1][i].evaluate(t),ct[1][i].evaluate(t)),positionDistance=math.dist(nt[0][i].evaluate(t),ct[0][i].evaluate(t))))
    row['normalVsCurrent'][name]=differences
   # Replay contemporary standard configuration as a diagnostic, not proof of
   # October provenance; the root TOML/processor have changed since that date.
   for comp in [False,True]:
    probe=copy.deepcopy(source)
    with patch.object(proc,'_apply_two_bone_ik',wraps=real_solver) as trace:
     st=proc.modify_animation_with_world_compensation(probe,bones,unit,standard,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=comp,apply_ik_correction=True)
     calls=trace.call_count
    row['standardRotationComp'+str(comp)]=dict(twoBoneSolverCalls=calls,ikCorrections=st.ik_corrections,byteExactNormal=probe.to_bytes()==normal_bytes)
   report['samples'].append(row);print(row['id'],'replay=',row['byteExactLatestReplay'],'projection=',stats.arm_retargets,'actual-solver=',solver_calls,flush=True)
 report['latestReferenceModelFingerprint']=single._model_files(model);report['status']='PASS_AUDIT_COMPLETE_NOT_GAME_ACCEPTANCE'
 report['replayExactCount']=sum(x['byteExactLatestReplay'] for x in report['samples']);report['actualSolverCallsTotal']=sum(x['currentTwoBoneSolverCalls'] for x in report['samples'])
 for path,key in [(CURRENT,'currentSha256'),(NORMAL,'normalSha256')]:
  with path.open('rb') as f:report[key]=hashlib.file_digest(f,'sha256').hexdigest()
 build=json.loads((a/'build-report.json').read_text(encoding='utf-8'));report['currentBuildShaMatches']=report['currentSha256']==next(x['sha256'] for x in build['files'] if x['name'].endswith('.patch_2'))
 (OUT/'单骨架-配置参考及IK实证-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');index.close()
 print('SUMMARY',len(report['samples']),report['replayExactCount'],report['actualSolverCallsTotal'],report['currentBuildShaMatches'])
if __name__=='__main__':main()
