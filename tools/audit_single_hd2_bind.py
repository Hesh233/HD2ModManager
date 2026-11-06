"""Independent serialized single-HD2 model/batch check. Never writes to a model or game."""
import argparse,copy,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from anim_batch_mod import single_skeleton as single
from anim_batch_mod.archive import PackageStore,ResourceIndex,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.processor import ModConfig,modify_animation_with_world_compensation,_calculate_world_transforms

def audit(case,game_data):
    regression=json.loads((case/'import-regression.json').read_text(encoding='utf-8'))
    payload=next(Path(regression['model']).rglob('single-skeleton.json')).parent
    marker=json.loads((payload/'single-skeleton.json').read_text(encoding='utf-8'))
    single._validate_prepared_model(payload,marker)
    config=ModConfig.load(payload/'single-config.toml')
    index=ResourceIndex(PackageStore(game_data),case/'single-bind-audit.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID})
    try:
        index.load_or_build()
        _,entry=index.resolve(single.REFERENCE_UNIT,UNIT_TYPE_ID);original=UnitData.parse(entry.toc_data)
        _,entry=index.resolve(original.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(entry.toc_data)
        rest=AnimationData(initial_bone_states=[AnimationBoneState(
            position=copy.copy(original.transforms[original.name_hashes.index(h)].position),
            rotation=copy.copy(original.transforms[original.name_hashes.index(h)].rotation),
            scale=copy.copy(original.transforms[original.name_hashes.index(h)].scale),
            compress_position=False,compress_rotation=False,compress_scale=False) for h in bones.hashes],animation_length=1)
        o=marker['options']
        def process(clip):
            return modify_animation_with_world_compensation(clip,bones,original,config,allow_additive=o['allow_additive'],
                apply_offsets_to_additive=False,apply_rotate_multipliers=o['rotate_multipliers'],
                apply_rotation_compensations=o['rotation_compensation'],apply_ik_correction=o['ik_correction'])
        process(rest);rest=AnimationData.parse(rest.to_bytes())
        transforms=copy.deepcopy(original.transforms)
        for h,state in zip(bones.hashes,rest.initial_bone_states):transforms[original.name_hashes.index(h)]=state
        worlds=_calculate_world_transforms(transforms,original.parents)
        position_error=rotation_error=0;compared=0
        for _,unit in single.model_units(payload):
            target=_calculate_world_transforms(unit.transforms,unit.parents)
            for i,h in enumerate(original.name_hashes):
                a,b=worlds[i],target[unit.name_hashes.index(h)]
                position_error=max(position_error,math.dist(a.position,b.position))
                rotation_error=max(rotation_error,1-abs(sum(x*y for x,y in zip(a.rotation,b.rotation))))
                compared+=1
        if position_error>1e-4 or rotation_error>1e-6:raise AssertionError(('Rest/model bind mismatch',position_error,rotation_error))
        runtime=case/'animations/runtime';path=next(runtime.glob('*.patch_2'))
        archive=TocArchive.parse_parts(path.read_bytes(),Path(str(path)+'.gpu_resources').read_bytes(),Path(str(path)+'.stream').read_bytes())
        assert not archive.entries_of_type(UNIT_TYPE_ID) and not archive.entries_of_type(BONE_TYPE_ID)
        clips=additive=0
        for entry in archive.entries_of_type(ANIMATION_TYPE_ID):
            _,raw=index.resolve(entry.file_id,ANIMATION_TYPE_ID);clip=AnimationData.parse(raw.toc_data)
            additive+=int(clip.is_additive);process(clip)
            assert bytes(entry.toc_data)==clip.to_bytes(),'Not identical to the shared original batch'
            assert len(clip.initial_bone_states)==marker['boneCount']==len(bones.names)
            clips+=1
        report=dict(status='PASS',pipelineVersion=marker['pipelineVersion'],bindPolicy=marker['bindPolicy'],
            modelScale=marker['modelScale'],offsetBones=len(config.offsets),rotationBones=len(config.rotation_compensations),
            comparedDriverWorlds=compared,maxRestPositionError=position_error,maxRestRotationError=rotation_error,
            clips=clips,additiveClips=additive,channelCount=marker['boneCount'],batchBytesMatch=True,
            protectedModelUnchanged=regression['protectedModelUnchanged'],noSourceRig=True,noLua=True,
            sampleOnly=True,gameTested=False)
        (case/'single-bind-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report));return report
    finally:index.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case',type=Path);p.add_argument('--game-data',required=True,type=Path)
    a=p.parse_args();audit(a.case,a.game_data)
