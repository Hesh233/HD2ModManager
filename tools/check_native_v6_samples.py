import copy,json,math,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import convert_clip,load_manifest,append_unit
from anim_batch_mod.processor import ModConfig,_build_tracks,modify_animation_with_world_compensation,_calculate_world_transforms,WorldTransform
from anim_batch_mod.attachment_skeleton import source_attachment_pose
W=ROOT/'outputs/native-v6-20261104';P=W/'project';BASE=ROOT/'outputs/native-fix-20261103'
m=load_manifest(P/'source-skeleton.json');u=UnitData.parse((BASE/'avatar.toc').read_bytes());b=BonesData.parse((BASE/'bones.toc').read_bytes())
eu=UnitData.parse(append_unit((BASE/'avatar.toc').read_bytes(),m));assert len(eu.transforms)==249
cfg=ModConfig.load(P/'config.toml');options=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
original=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636')
ids=[18307702697579710200,16381641002705108128,7781841632278966152,16374892322597155811]
additive_id=next(int(r['id']) for r in json.loads((ROOT/'outputs/native-v5-20261103/project/animations/build-report.json').read_text())['animations'] if r['additive']);ids.append(additive_id)
results=[]
for id in ids:
    raw=original.entries[id,ANIMATION_TYPE_ID].toc_data;a=AnimationData.parse(raw)
    data,metrics=convert_clip(raw,b,u,m,cfg,options);actual=AnimationData.parse(data)
    assert metrics['standard_foot_chains']==0 and metrics['max_pelvis_drop']==0 and not metrics['planted_feet']
    assert len(actual.initial_bone_states)==232
    configured=copy.deepcopy(a)
    modify_animation_with_world_compensation(configured,b,u,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True)
    maximum=0.;rotation_error=0.
    if not a.is_additive:
        ct,at=_build_tracks(configured),_build_tracks(actual)
        # Audit actual serialized samples against independently reconstructed configured FK.
        for time in (0.,a.animation_length*500.,a.animation_length*1000.):
            locals_=copy.deepcopy(u.transforms)
            for ai,h in enumerate(b.hashes):locals_[u.name_hashes.index(h)]=WorldTransform(*(tr[ai].evaluate(time) for tr in ct))
            world=_calculate_world_transforms(locals_,u.parents)
            for i,row in enumerate(m['sourceAttachmentShadows']):
                expected=source_attachment_pose(world,row);actual_p=at[0][208+i].evaluate(time);actual_q=at[1][208+i].evaluate(time)
                maximum=max(maximum,math.dist(actual_p,expected.position));rotation_error=max(rotation_error,1-abs(sum(x*y for x,y in zip(actual_q,expected.rotation))))
        assert maximum<.001 and rotation_error<1e-5,(maximum,rotation_error)
    results.append(dict(id=str(id),sourceReferencePositionError=maximum,sourceReferenceRotationError=rotation_error,**metrics));print(results[-1],flush=True)
# A neutral additive clip must not inject a new VPK attachment offset or rotation.
neutral=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in range(90)],animation_length=1.,is_additive=True)
data,metrics=convert_clip(neutral.to_bytes(),b,u,m,cfg,options)
neutral=AnimationData.parse(data)
neutral_states=neutral.initial_bone_states[90:179]+neutral.initial_bone_states[208:]
position_error=max(abs(v) for s in neutral_states for v in s.position)
rotation_error=max(abs(abs(s.rotation[3])-1) for s in neutral_states)
assert position_error<1e-6 and rotation_error<1e-6
(W/'neutral-additive-audit.json').write_text(json.dumps(dict(status='PASS',driverConfigApplied=True,maxNeutralPositionError=position_error,maxNeutralQuaternionError=rotation_error,metrics=metrics),indent=2),encoding='utf-8')
report=dict(status='PASS',sourceReferenceNodes=24,untouchedControllerNodes=5,sourceOrigin=True,modelScale=1.08,feetIK=False,neutralAdditive=True,samples=results,gameTested=False)
(W/'sample-audit.json').write_text(json.dumps(report,indent=2))
