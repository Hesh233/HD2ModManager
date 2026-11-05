"""Compare actual candidate hand poses with user-accepted v9 output."""
import json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'tools'))
from package_native_v10 import records,payload
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform
W=ROOT/'outputs/native-v10-20261104';old=ROOT/'outputs/native-v9-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'
rs=records(old);lookup={r[0]:r for r in rs if r[1]==ANIMATION_TYPE_ID}
u=UnitData.parse(payload(old,next(r for r in rs if r[1]==UNIT_TYPE_ID)));b=BonesData.parse(payload(old,next(r for r in rs if r[1]==BONE_TYPE_ID)))
m=json.loads((W/'project/source-skeleton.json').read_text());channels={u.name_hashes.index(h):i for i,h in enumerate(b.hashes)};chains=[]
for side in ('l_hand','r_hand'):
    ui=u.name_hashes.index(next(n['hash'] for n in m['bones'] if n['driver']==side));chain=[]
    while ui is not None:chain.append((channels.get(ui),u.transforms[ui]));ui=u.parents[ui]
    chains.append(chain[::-1])
def pose(tr,chain,t):
    local=[WorldTransform(*(x[ch].evaluate(t) for x in tr)) if ch is not None else base for ch,base in chain]
    return _calculate_world_transforms(local,[None]+list(range(len(local)-1)))[-1]
results=[]
for path in (W/'candidate-clips').glob('*.toc'):
    a=AnimationData.parse(payload(old,lookup[int(path.stem)]));c=AnimationData.parse(path.read_bytes())
    if c.is_additive:continue
    at,ct=_build_tracks(a),_build_tracks(c);pe=qe=bpe=bqe=0.
    for i in range(61):
        t=a.animation_length*1000*i/60
        for chain in chains:
            x,y=pose(at,chain,t),pose(ct,chain,t)
            pe=max(pe,math.dist(x.position,y.position))
            norm=math.sqrt(sum(v*v for v in x.rotation)*sum(v*v for v in y.rotation))
            q=abs(sum(v*w for v,w in zip(x.rotation,y.rotation)))/norm
            qe=max(qe,math.degrees(2*math.acos(min(1.,q))))
    for i in range(9):
        t=a.animation_length*1000*i/8
        if i not in (0,8):t=round(t*30/1000)*1000/30
        for chain in chains:
            x,y=pose(at,chain,t),pose(ct,chain,t)
            bpe=max(bpe,math.dist(x.position,y.position))
            sign=-1 if sum(v*w for v,w in zip(x.rotation,y.rotation))<0 else 1
            bqe=max(bqe,max(abs(v-sign*w) for v,w in zip(x.rotation,y.rotation)))
    assert bpe<2e-5 and bqe<2e-5,('Baked hand pose changed',path.stem,bpe,bqe)
    results.append(dict(id=path.stem,positionMetres=pe,rotationDegrees=qe,
                        bakedPositionMetres=bpe,bakedQuaternionDifference=bqe))
report=dict(status='COMPLETE',gameTested=False,clips=results)
(W/'accepted-grip-candidate-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
