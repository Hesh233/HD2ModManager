"""Regress real clips against the delivered v10, including baked hand poses."""
import json,math,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
from anim_batch_mod.native_skeleton import convert_clip
from anim_batch_mod.processor import ModConfig,_build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID
from package_native_v10 import records,payload
W=ROOT/'outputs/native-v12-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
OLD=ROOT/'outputs/native-manual-20261103/project/animations/runtime/9ba626afa44a3aa3.patch_2'
rs=records(OLD);oldrows={r[0]:r for r in rs if r[1]==ANIMATION_TYPE_ID}
eu=UnitData.parse(payload(OLD,next(r for r in rs if r[1]==UNIT_TYPE_ID)))
eb=BonesData.parse(payload(OLD,next(r for r in rs if r[1]==BONE_TYPE_ID)))
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes())
m=json.loads((P/'source-skeleton.json').read_text());cfg=ModConfig.load(P/'config.toml')
options=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
lookup={int(r['id']):r for r in json.loads((ROOT/'outputs/native-v10-20261104/project/animations/build-report.json').read_text())['animations']}
indices={n['driver']:len(u.transforms)+i for i,n in enumerate(m['bones']) if n['driver']}
mapping=[eu.name_hashes.index(h) for h in eb.hashes]
def world(tr,t):
    local=list(eu.transforms)
    for ch,ui in enumerate(mapping):local[ui]=WorldTransform(*(x[ch].evaluate(t) for x in tr))
    return _calculate_world_transforms(local,eu.parents)
def angle(a,b):
    norm=math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    return math.degrees(2*math.acos(min(1.,abs(sum(x*y for x,y in zip(a,b)))/norm)))
source=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
archives={};results=[];out=W/'candidate-clips';out.mkdir(exist_ok=True)
for path in (ROOT/'outputs/native-v10-20261104/candidate-clips').glob('*.toc'):
    fid=int(path.stem);package=lookup[fid]['package']
    if package not in archives:archives[package]=TocArchive.load_toc_only(source,package)
    raw=archives[package].entries[fid,ANIMATION_TYPE_ID].toc_data
    result,metrics=convert_clip(raw,b,u,m,cfg,options);(out/path.name).write_bytes(result)
    a=AnimationData.parse(payload(OLD,oldrows[fid]));c=AnimationData.parse(result)
    at,ct=_build_tracks(a),_build_tracks(c);pe=qe=lower=0.;steps={}
    if not c.is_additive:
        for i in range(9):
            t=a.animation_length*1000*i/8
            if i not in (0,8):t=round(t*30/1000)*1000/30
            aw,cw=world(at,t),world(ct,t)
            for name in ('l_hand','r_hand'):
                ai=indices[name];pe=max(pe,math.dist(aw[ai].position,cw[ai].position));qe=max(qe,angle(aw[ai].rotation,cw[ai].rotation))
            for name in ('hips','l_thigh','r_thigh','l_knee','r_knee','l_foot','r_foot'):
                ai=indices[name];lower=max(lower,math.dist(aw[ai].position,cw[ai].position))
        for side in ('l','r'):
            for joint in ('shoulder','elbow'):
                name=side+'_'+joint;ch=mapping.index(indices[name]);q=None;maximum=0
                for i in range(math.floor(c.animation_length*60)+1):
                    nextq=ct[1][ch].evaluate(i*1000/60)
                    if q is not None:maximum=max(maximum,angle(q,nextq))
                    q=nextq
                steps[name]=maximum
        assert pe<2e-5 and qe<.005 and lower<1e-7,(fid,pe,qe,lower)
    row=dict(id=str(fid),additive=c.is_additive,bakedHandMetres=pe,bakedHandDegrees=qe,lowerBodyMetres=lower,maxFrameDegrees=steps)
    results.append(row);print(json.dumps(row),flush=True)
continuous=all(v<45 for r in results for v in r['maxFrameDegrees'].values())
report=dict(status='PASS' if continuous else 'FAILED',gameTested=False,clips=results)
(W/'candidate-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
assert continuous,'New shoulder/elbow discontinuity in the fixed regression clips'

