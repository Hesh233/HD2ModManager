"""Real-input regression for the single-HD2 arm contract; no user asset mutation."""
import copy,hashlib,json,math,shutil,sqlite3,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import single_skeleton as single
from anim_batch_mod.archive import PackageStore,ResourceIndex,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.processor import (ModConfig,WorldTransform,_build_tracks,_calculate_world_transforms,
 _compose_additive_local,_build_bake_times,_quat_from_to,_distance,modify_animation_with_world_compensation)
from anim_batch_mod.math3d import quat_multiply as qm,quat_inverse as qi,quat_rotate as qr,vec_sub
OUT=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';LIB=OUT/'test-library'
DB=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
def angle(x,y):return math.degrees(2*math.acos(min(1,abs(sum(a*b for a,b in zip(x,y))/math.sqrt(sum(a*a for a in x)*sum(a*a for a in y))))))
def vangle(x,y):
 d=_distance(x,[0,0,0])*_distance(y,[0,0,0])
 return math.degrees(math.acos(max(-1,min(1,sum(a*b for a,b in zip(x,y))/d)))) if d>1e-9 else None
def cross(x,y):return [x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
def world(clip,unit,bones,time,tracks):
 local=list(unit.transforms);inds={h:i for i,h in enumerate(unit.name_hashes)}
 for i,h in enumerate(bones.hashes):
  sampled=WorldTransform(*(tr[i].evaluate(time) for tr in tracks));j=inds[h]
  local[j]=_compose_additive_local(unit.transforms[j],sampled) if clip.is_additive else sampled
 return _calculate_world_transforms(local,unit.parents)
def process(clip,unit,bones,config):
 return modify_animation_with_world_compensation(clip,bones,unit,config,allow_additive=True,
  apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=True,apply_ik_correction=True)
def main():
 store=PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'));index=ResourceIndex(store,DB);index.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)
 _,entry=index.resolve(single.REFERENCE_UNIT,UNIT_TYPE_ID);native=UnitData.parse(entry.toc_data);_,entry=index.resolve(native.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(entry.toc_data)
 ni={h:i for i,h in enumerate(native.name_hashes)};bi={n:i for i,n in enumerate(bones.names)};nw0=_calculate_world_transforms(native.transforms,native.parents)
 chosen=[int(c['id'],16) for c in json.loads((OUT/'test07-单骨架-手臂文件核查.json').read_text(encoding='utf-8'))['realClipSamples']]
 sources={'test07':LIB/'[单骨架模型]test07/vpk2patch'}
 for name in ['test01','test02']:
  regression=json.loads((ROOT/f'outputs/single-hd2-fix-20261106/final-verified/{name}/import-regression.json').read_text(encoding='utf-8'))
  sources[name]=next(Path(regression['model']).rglob('single-skeleton.json')).parent
 report=dict(status='RUNNING',pipelineVersion=single.PIPELINE_VERSION,armPolicy=single.ARM_POLICY,gameDeployed=False,gameTested=False,cases=[])
 for name,folder in sources.items():
  source_digest=single._model_files(folder);certificate_hash=hashlib.sha256((folder/'single-hd2-bind.json').read_bytes()).hexdigest()
  with tempfile.TemporaryDirectory(prefix='hd2-single-arm-audit-') as temporary:
   work=Path(temporary);model=work/'model';model.mkdir()
   for p in folder.iterdir():
    if '.patch_' in p.name or p.name=='single-hd2-bind.json':shutil.copyfile(p,model/p.name)
   shutil.copyfile(ROOT/'outputs/single-hd2-fix-20261106/audit-index.sqlite3',model/'single-resource-index.sqlite3')
   marker=single.prepare_model(model,store.game_data);config=ModConfig.load(model/'single-config.toml');single._validate_prepared_model(model,marker)
   assert marker['version']==3 and marker['armIKChains']==['l_hand','r_hand']
   units=list(single.model_units(model));target=units[0][1];mi={h:i for i,h in enumerate(target.name_hashes)};mw0=_calculate_world_transforms(target.transforms,target.parents)
   def rest(add=False):return AnimationData(initial_bone_states=[AnimationBoneState([0,0,0] if add else list(native.transforms[ni[h]].position),[0,0,0,1] if add else list(native.transforms[ni[h]].rotation),[0,0,0] if add else list(native.transforms[ni[h]].scale)) for h in bones.hashes],is_additive=add)
   neutral=rest();process(neutral,native,bones,config);neutral=AnimationData.parse(neutral.to_bytes());neutral_world=world(neutral,native,bones,0,_build_tracks(neutral))
   position_error=rotation_error=0
   for _,u in units:
    ui={h:i for i,h in enumerate(u.name_hashes)};uw=_calculate_world_transforms(u.transforms,u.parents)
    for h in native.name_hashes:
     position_error=max(position_error,_distance(neutral_world[ni[h]].position,uw[ui[h]].position));rotation_error=max(rotation_error,angle(neutral_world[ni[h]].rotation,uw[ui[h]].rotation))
   assert position_error<1e-4 and rotation_error<.1,(name,position_error,rotation_error)
   zero=rest(True);process(zero,native,bones,config);zero=AnimationData.parse(zero.to_bytes());assert zero.is_additive
   zero_position=max(_distance(s.position,[0,0,0]) for s in zero.initial_bone_states);zero_rotation=max(angle(s.rotation,[0,0,0,1]) for s in zero.initial_bone_states)
   assert zero_position<1e-4 and zero_rotation<.35, (name,zero_position,zero_rotation,[(n,angle(s.rotation,[0,0,0,1])) for n,s in zip(bones.names,zero.initial_bone_states) if angle(s.rotation,[0,0,0,1])>.1])
   case=dict(model=name,modelScale=marker['modelScale'],modelGeometryUnchanged=True,neutralMaxPositionError=position_error,neutralMaxRotationDegrees=rotation_error,zeroAdditiveMaxPosition=zero_position,zeroAdditiveMaxRotationDegrees=zero_rotation,clips=[])
   legacy=copy.deepcopy(config);legacy.ik_chains={}
   for fid in chosen:
    _,entry=index.resolve(fid,ANIMATION_TYPE_ID);original=AnimationData.parse(entry.toc_data);fixed=copy.deepcopy(original);stats=process(fixed,native,bones,config);fixed=AnimationData.parse(fixed.to_bytes());before=copy.deepcopy(original);process(before,native,bones,legacy)
    ot,ft,bt=map(_build_tracks,[original,fixed,before]);maximums=dict(beforeBend=0,afterBend=0,beforeAnatomicalPlane=0,afterAnatomicalPlane=0,wristRotationDegrees=0,twistRotationDegrees=0,wristTwistPositionDistance=0,wristTwistScaledDistanceError=0)
    for time in _build_bake_times(max(e.time for e in original.entries if e.is_position or e.is_rotation or e.is_scale)) if original.entries else [0]:
     ow=world(original,native,bones,time,ot);fw=world(fixed,target,bones,time,ft);bw=world(before,target,bones,time,bt)
     for side in ['l','r']:
      hashes=[bones.hashes[bi[side+'_'+s]] for s in ['shoulder','elbow','hand']];ninds=[ni[h] for h in hashes];minds=[mi[h] for h in hashes]
      expected=qm(qm(mw0[minds[2]].rotation,qi(nw0[ninds[2]].rotation)),ow[ninds[2]].rotation);maximums['wristRotationDegrees']=max(maximums['wristRotationDegrees'],angle(expected,fw[minds[2]].rotation))
      th=bones.hashes[bi[side+'_hand_twist']];expect_twist=qm(qm(mw0[mi[th]].rotation,qi(nw0[ni[th]].rotation)),ow[ni[th]].rotation);maximums['twistRotationDegrees']=max(maximums['twistRotationDegrees'],angle(expect_twist,fw[mi[th]].rotation))
      maximums['wristTwistPositionDistance']=max(maximums['wristTwistPositionDistance'],_distance(fw[mi[th]].position,fw[minds[2]].position))
      ratio=_distance(target.transforms[minds[2]].position,[0,0,0])/_distance(native.transforms[ninds[2]].position,[0,0,0])
      parent=ow[native.parents[ni[th]]];diff=qr(qi(parent.rotation),vec_sub(ow[ni[th]].position,ow[ninds[2]].position));diff=[x/y for x,y in zip(diff,parent.scale)]
      bind_diff=vec_sub(native.transforms[ni[th]].position,native.transforms[ninds[2]].position)
      J=_quat_from_to(native.transforms[ninds[2]].position,target.transforms[minds[2]].position)
      mapped=qr(J,vec_sub(diff,bind_diff));expected_local=[x+y*ratio for x,y in zip(vec_sub(target.transforms[mi[th]].position,target.transforms[minds[2]].position),mapped)]
      parent=fw[target.parents[mi[th]]];actual_local=qr(qi(parent.rotation),vec_sub(fw[mi[th]].position,fw[minds[2]].position));actual_local=[x/y for x,y in zip(actual_local,parent.scale)]
      maximums['wristTwistScaledDistanceError']=max(maximums['wristTwistScaledDistanceError'],_distance(expected_local,actual_local))
      if original.is_additive:continue
      nv=[vec_sub(ow[ninds[1]].position,ow[ninds[0]].position),vec_sub(ow[ninds[2]].position,ow[ninds[1]].position)];nab=vangle(*nv)
      H=_quat_from_to(native.transforms[ninds[1]].position,target.transforms[minds[1]].position)
      for prefix,w in [('before',bw),('after',fw)]:
       mv=[vec_sub(w[minds[1]].position,w[minds[0]].position),vec_sub(w[minds[2]].position,w[minds[1]].position)];mab=vangle(*mv)
       if nab is None or mab is None:continue
       maximums[prefix+'Bend']=max(maximums[prefix+'Bend'],abs(nab-mab))
       if nab>20 and mab>20:
        S=qm(qm(w[minds[0]].rotation,H),qi(ow[ninds[0]].rotation));plane=vangle(qr(S,cross(*nv)),cross(*mv))
        if plane is not None:maximums[prefix+'AnatomicalPlane']=max(maximums[prefix+'AnatomicalPlane'],plane)
    assert maximums['wristRotationDegrees']<.15 and maximums['twistRotationDegrees']<.15,(name,fid,maximums)
    assert maximums['wristTwistScaledDistanceError']<1e-4,(name,fid,maximums)
    assert len(fixed.initial_bone_states)==90 and stats.arm_retargets>0 and fixed.is_additive==original.is_additive
    case['clips'].append(dict(id=f'{fid:016x}',additive=original.is_additive,armSamples=stats.arm_retargets,**maximums))
   assert single._model_files(folder)==source_digest and hashlib.sha256((folder/'single-hd2-bind.json').read_bytes()).hexdigest()==certificate_hash
   if name=='test07':
    shutil.copyfile(DB,work/'pack-index.sqlite3')
    # Run the real build_project/package writer on a small representative prefix.
    output=work/'animations';output.mkdir();shutil.copyfile(DB,output/'resource-index.sqlite3')
    # build_project requires an empty output; cache path can be injected read-only
    # without mocking the build, processor, archive writer, or validators.
    from unittest.mock import patch
    class CachedIndex(ResourceIndex):
     def load_or_build(self,progress=None):self.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);return True
    output.rmdir() if not any(output.iterdir()) else None
    # Move the disposable cache outside the output before the empty-directory gate.
    (output/'resource-index.sqlite3').unlink();output.rmdir()
    with patch.object(single,'ResourceIndex',CachedIndex):pack=single.build_project(model,store.game_data,output,sample_count=6,threads=2)
    assert pack['armRetargetSamples']>0 and pack['armIKChains']==['l_hand','r_hand'] and pack['sampleOnly'] is True
    archive=TocArchive.parse_parts((output/'runtime/9ba626afa44a3aa3.patch_2').read_bytes(),b'',b'')
    assert len(archive.entries)==6 and all(e.type_id==ANIMATION_TYPE_ID for e in archive.entries.values())
    (OUT/'单骨架手臂修复-真实打包报告.json').write_text(json.dumps(pack,ensure_ascii=False,indent=2),encoding='utf-8')
    case['realPackage']=dict(animations=6,armSamples=pack['armRetargetSamples'],noAvatarUnit=True,noBonesOverride=True)
   report['cases'].append(case);(OUT/'单骨架手臂修复-真实动作验证.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
   print(name,'PASS','neutral',position_error,'zero-additive',zero_position,'clips',len(case['clips']),flush=True)
 report['status']='PASS';(OUT/'单骨架手臂修复-真实动作验证.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');index.close()
if __name__=='__main__':main()


