"""Compare authored reference animation, current retarget and Lua attachment math."""
import json,math,struct,sys,tomllib,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform,ModConfig,modify_animation_with_world_compensation,_compose_additive_local
from anim_batch_mod.native_skeleton import load_manifest,append_unit,convert_clip
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate,vec_add,vec_sub
W=ROOT/'outputs/native-v6-20261104';V5=ROOT/'outputs/native-v5-20261103';BASE=ROOT/'outputs/native-fix-20261103'
def records(path):
    f=path.open('rb');h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+nt*32)
    return f,{r[0]:r for r in (struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)) if r[1]==ANIMATION_TYPE_ID}
def read(f,r):f.seek(r[2]);return f.read(r[7])
def poses(a,u,b,t,source=False):
    tracks=_build_tracks(a);local=copy.deepcopy(u.transforms);byhash={h:i for i,h in enumerate(u.name_hashes)}
    for i,h in enumerate(b.hashes):
        p=WorldTransform(*(tr[i].evaluate(t) for tr in tracks));ui=byhash[h]
        local[ui]=_compose_additive_local(u.transforms[ui],p) if a.is_additive else p
    if source:
        for i in range(89):local[107+i]=WorldTransform(*(tr[90+i].evaluate(t) for tr in tracks))
        for i,row in enumerate(m['attachmentShadows']):local[196+i]=WorldTransform(*(tr[179+i].evaluate(t) for tr in tracks))
    return _calculate_world_transforms(local,u.parents)
u=UnitData.parse((BASE/'avatar.toc').read_bytes());ref_u=UnitData.parse((W/'avatar-reference.toc').read_bytes());b=BonesData.parse((BASE/'bones.toc').read_bytes())
m=load_manifest(V5/'project/source-skeleton.json');extended=UnitData.parse(append_unit((BASE/'avatar.toc').read_bytes(),m))
profile=json.loads((V5/'project/attachment-profile.json').read_text());byname={n:u.name_hashes.index(h) for n,h in zip(b.names,b.hashes)}
original=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636')
rf,rr=records(ROOT.parent/'output/9ba626afa44a3aa3.patch_0');vf,vr=records(V5/'project/animations/runtime/9ba626afa44a3aa3.patch_2')
assert set(rr)==set(vr)
cfg=ModConfig.load(V5/'project/config.toml');samples=[]
ids=[18307702697579710200,18053434533899883251,16381641002705108128,27293056250338873,15679743041498935277,15317599675835573914,3551476695834673990,7781841632278966152]
ids+= [int(r['id']) for r in json.loads((V5/'feet-sample-audit.json').read_text())['clips']]
for id in ids:
    raw=original.entries[id,ANIMATION_TYPE_ID].toc_data;a=AnimationData.parse(raw);ref=AnimationData.parse(read(rf,rr[id]));v5=AnimationData.parse(read(vf,vr[id]));processed=copy.deepcopy(a)
    modify_animation_with_world_compensation(processed,b,u,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True)
    if a.is_additive:continue
    row=dict(id=str(id),duration=a.animation_length,metrics={});metrics=row['metrics']
    for frame in range(9):
        t=a.animation_length*1000*frame/8
        ow=poses(a,u,b,t);rw=poses(ref,ref_u,b,t);pw=poses(processed,u,b,t);vw=poses(v5,extended,b,t,True)
        for name in ('r_hand','l_hand','attach_weapon','aim_weapon','weapon_aim','hips','l_foot','r_foot'):
            i=byname[name]
            metrics['processed_vs_reference_'+name]=max(metrics.get('processed_vs_reference_'+name,0),math.dist(pw[i].position,rw[i].position))
        for ar in profile['vpk']:
            if ar['standardName'] not in ('attach_weapon','aim_weapon','weapon_aim','attach_hand_l','attach_hand_r'):continue
            i=ar['index'];di=ar['driverAnchorIndex'];si=ar['sourceAnchorIndex']+107;ri=ar['referenceIndex']
            inv=quat_inverse(vw[di].rotation);off=quat_rotate(inv,vec_sub(vw[ri].position,vw[di].position));sq=quat_multiply(vw[si].rotation,ar['axisCorrection'])
            p=vec_add(vw[si].position,quat_rotate(sq,off))
            metrics['lua_translation_'+ar['standardName']]=max(metrics.get('lua_translation_'+ar['standardName'],0),math.dist(p,ow[i].position))
            # Detect parent-output feedback: references must be unaffected by selected original nodes.
            ancestors=[];j=extended.parents[ri]
            while j is not None:ancestors.append(j);j=extended.parents[j]
            assert not set(ancestors)&{r['index'] for r in profile['vpk']}
    samples.append(row);print(json.dumps(row),flush=True)
report=dict(status='measured',referenceIdsMatch=True,referenceAnimations=len(rr),samples=samples,
    nativeUnitHashMatch=u.name_hashes==ref_u.name_hashes)
(W/'reference-comparison.json').write_text(json.dumps(report,indent=2))
