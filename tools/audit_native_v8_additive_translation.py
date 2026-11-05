"""Independent compose-before/after-retarget check for additive translation."""
import copy,json,math,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import load_manifest,append_unit,append_bones,convert_clip
from anim_batch_mod.processor import WorldTransform,ModConfig,_compose_additive_local,_calculate_world_transforms
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=load_manifest(P/'source-skeleton.json')
eu=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
cfg=ModConfig.load(P/'config.toml');options=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
rawbase=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[u.name_hashes.index(h)].position),list(u.transforms[u.name_hashes.index(h)].rotation),[1.,1.,1.],False,False,False) for h in b.hashes],animation_length=.033,is_additive=False)
def converted(a):return AnimationData.parse(convert_clip(a.to_bytes(),b,u,m,cfg,options)[0])
base=converted(rawbase)
def pose(a):
    local=copy.deepcopy(eu.transforms)
    for h,s in zip(eb.hashes,a.initial_bone_states):local[eu.name_hashes.index(h)]=WorldTransform(s.position,s.rotation,s.scale)
    return _calculate_world_transforms(local,eu.parents)
results=[]
for driver in ('root','boss','hips','spine1'):
    ai=b.names.index(driver)
    for axis in range(3):
        rawdelta=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in b.names],animation_length=.033,is_additive=True)
        rawdelta.initial_bone_states[ai].position[axis]=.1
        effective=copy.deepcopy(rawbase)
        for bs,ds,es in zip(rawbase.initial_bone_states,rawdelta.initial_bone_states,effective.initial_bone_states):
            x=_compose_additive_local(WorldTransform(bs.position,bs.rotation,bs.scale),WorldTransform(ds.position,ds.rotation,ds.scale));es.position=x.position;es.rotation=x.rotation;es.scale=x.scale
        direct=pose(converted(effective));delta=converted(rawdelta);blended=copy.deepcopy(base)
        for bs,ds,es in zip(base.initial_bone_states,delta.initial_bone_states,blended.initial_bone_states):
            x=_compose_additive_local(WorldTransform(bs.position,bs.rotation,bs.scale),WorldTransform(ds.position,ds.rotation,ds.scale));es.position=x.position;es.rotation=x.rotation;es.scale=x.scale
        indirect=pose(blended);row={'driver':driver,'axis':axis,'inputMetres':.1}
        for name,source_i in [('hips',0),('spine1',1),('l_foot',58),('r_foot',62)]:
            index=eu.name_hashes.index(m['bones'][source_i]['hash']);row[name]=math.dist(direct[index].position,indirect[index].position)
        results.append(row)
maximum=max(row[name] for row in results for name in ('hips','spine1','l_foot','r_foot'))
tolerance=1e-6
report={'validationStatus':'COMPLETE','additiveTranslationStatus':'PASS' if maximum<tolerance else 'FAIL','gameTested':False,'toleranceMetres':tolerance,'scope':'production config, synthetic 10 cm local additive translation; compare retarget(compose(base,delta)) against compose(retarget(base),retarget(delta)); all weights one; actual gameplay state unknown','maxPositionErrorMetres':maximum,'results':results}
(W/'additive-translation-review.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
assert maximum<tolerance,f'Additive translation composition error {maximum} m exceeds {tolerance} m'
