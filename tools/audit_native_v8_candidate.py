"""Compare frozen v7 and v8 using neutral input and selected real game clips."""
import copy,importlib.util,json,math,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import native_skeleton as current
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.processor import ModConfig,_build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate,vec_add,vec_sub
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103';V7=ROOT/'outputs/native-v7-20261104'
spec=importlib.util.spec_from_file_location('anim_batch_mod.frozen_v7',V7/'manager/anim_batch_mod/native_skeleton.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=current.load_manifest(P/'source-skeleton.json')
eu=UnitData.parse(current.append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(current.append_bones((B/'bones.toc').read_bytes(),m))
cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
sm={n['driver']:eu.name_hashes.index(n['hash']) for n in m['bones'] if n['driver']};am=[eu.name_hashes.index(h) for h in eb.hashes]
def world(a,t):
    tr=_build_tracks(a);local=list(eu.transforms)
    for ai,ui in enumerate(am):local[ui]=WorldTransform(*(x[ai].evaluate(t) for x in tr))
    return _calculate_world_transforms(local,eu.parents)
def convert(mod,raw):
    data,metrics=mod.convert_clip(raw,b,u,m,cfg,opts);return AnimationData.parse(data),metrics
neutral=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[u.name_hashes.index(h)].position),list(u.transforms[u.name_hashes.index(h)].rotation),[1.,1.,1.],False,False,False) for h in b.hashes],animation_length=.033,is_additive=False)
neutral_rows={}
for name,mod in [('v7',old),('v8',current)]:
    a,metrics=convert(mod,neutral.to_bytes());w=world(a,0)
    neutral_rows[name]={'hipsToSpine1Metres':math.dist(w[sm['hips']].position,w[sm['spine1']].position),'positions':{n:w[sm[n]].position for n in ('hips','spine1','l_hand','r_hand','l_foot','r_foot')},'metrics':metrics}
expected=math.dist(m['bones'][0]['world'][12:15],m['bones'][1]['world'][12:15])
assert abs(neutral_rows['v8']['hipsToSpine1Metres']-expected)<1e-6
build=json.loads((V7/'project/animations/build-report.json').read_text())['animations'];lookup={int(r['id']):r for r in build}
ids=list(dict.fromkeys([int(r['id']) for r in sorted((r for r in build if not r['additive']),key=lambda r:r['max_standard_grip_error'],reverse=True)[:4]]+[18307702697579710200,16381641002705108128,7781841632278966152,16374892322597155811,2300190009223786134,16559285465095148]))
archives={};results=[];candidate=W/'candidate-clips';candidate.mkdir(exist_ok=True)
for fid in ids:
    row=lookup[fid];package=row['package']
    if package not in archives:archives[package]=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),package)
    raw=archives[package].entries[fid,ANIMATION_TYPE_ID].toc_data
    a,ma=convert(old,raw);data,mb=current.convert_clip(raw,b,u,m,cfg,opts);c=AnimationData.parse(data);(candidate/f'{fid}.toc').write_bytes(data)
    legerror=0.;nativeerror=0.;waist=[]
    for i in range(13):
        t=a.animation_length*1000*i/12;aw=world(a,t);cw=world(c,t)
        for name in ('hips','l_thigh','r_thigh','l_knee','r_knee','l_foot','r_foot'):
            legerror=max(legerror,math.dist(aw[sm[name]].position,cw[sm[name]].position))
        for ai in range(90):nativeerror=max(nativeerror,math.dist(aw[am[ai]].position,cw[am[ai]].position))
        waist.append(math.dist(cw[sm['hips']].position,cw[sm['spine1']].position))
    assert legerror<1e-6 and nativeerror<1e-6,(fid,legerror,nativeerror)
    result=dict(id=str(fid),additive=c.is_additive,v7=ma,v8=mb,maxLowerBodyChangeMetres=legerror,maxNativeChangeMetres=nativeerror,minWaistMetres=min(waist),maxWaistMetres=max(waist));results.append(result);print(json.dumps(result),flush=True)
report=dict(status='PASS',gameTested=False,neutral=neutral_rows,expectedBindWaistMetres=expected,samples=results,scope='Neutral waist proportions and unchanged native/lower-body motion; absolute grip residual does not verify live weapon contact')
(W/'candidate-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PASS',json.dumps(neutral_rows))
