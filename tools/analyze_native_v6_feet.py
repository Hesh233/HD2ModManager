"""Compare quiet-foot reference clips with their packaged VPK tracks."""
import json, math, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,WorldTransform,_calculate_world_transforms
from anim_batch_mod.math3d import quat_inverse_rotate,vec_sub
W=ROOT/'outputs/native-v6-analysis-20261104';P=ROOT/'outputs/native-v6-20261104/project';BASE=ROOT/'outputs/native-fix-20261103'
def records(path):
    f=path.open('rb');h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+32*nt)
    return f,[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
def read(f,r):f.seek(r[2]);return f.read(r[7])
rf,rr=records(ROOT.parent/'output/9ba626afa44a3aa3.patch_0');vf,vr=records(P/'animations/runtime/9ba626afa44a3aa3.patch_2')
ref=UnitData.parse((ROOT/'outputs/native-v6-20261104/avatar-reference.toc').read_bytes());bones=BonesData.parse((BASE/'bones.toc').read_bytes())
avatar=UnitData.parse(read(vf,next(r for r in vr if r[1]==UNIT_TYPE_ID)));vb=BonesData.parse(read(vf,next(r for r in vr if r[1]==BONE_TYPE_ID)))
vr={r[0]:r for r in vr if r[1]==ANIMATION_TYPE_ID};rr={r[0]:r for r in rr if r[1]==ANIMATION_TYPE_ID}
base_map={n:ref.name_hashes.index(h) for n,h in zip(bones.names,bones.hashes)}
source={n:avatar.name_hashes.index(h) for n,h in zip(vb.names,vb.hashes)}
source_map={name:source['hd2n_4e4fb4fa303d_anim_'+code+'_'+name] for name,code in [('hips','000'),('l_foot','058'),('r_foot','062')]}
base_channels={ref.name_hashes.index(h):i for i,h in enumerate(bones.hashes)};vpk_channels={avatar.name_hashes.index(h):i for i,h in enumerate(vb.hashes)}
def sample(tracks,u,channels,indices,t):
    cache={}
    def get(i):
        if i in cache:return cache[i]
        ai=channels.get(i);l=u.transforms[i] if ai is None else WorldTransform(*(tr[ai].evaluate(t) for tr in tracks))
        parent=u.parents[i]
        if parent is None:w=l
        else:
            from anim_batch_mod.math3d import quat_rotate,quat_multiply,vec_add
            p=get(parent);w=WorldTransform(vec_add(p.position,quat_rotate(p.rotation,l.position)),quat_multiply(p.rotation,l.rotation),[1,1,1])
        cache[i]=w;return w
    root=get(0)
    return {n:WorldTransform(quat_inverse_rotate(root.rotation,vec_sub(get(i).position,root.position)),get(i).rotation,[1,1,1]) for n,i in indices.items()}
def stats(rows):
    result={}
    for name in ('hips','l_foot','r_foot'):
        result[name+'Travel']=max(math.dist(a[name].position,b[name].position) for a in rows for b in rows)
        result[name+'Angle']=max(math.degrees(2*math.acos(min(1,abs(sum(x*y for x,y in zip(a[name].rotation,b[name].rotation)))))) for a in rows for b in rows)
    return result
found=[];scanned=0
build=json.loads((P/'animations/build-report.json').read_text())['animations']
for info in build:
    if info['additive']:continue
    fid=int(info['id']);a=AnimationData.parse(read(rf,rr[fid]));scanned+=1
    if not 1.0<=a.animation_length<=12:continue
    tracks=_build_tracks(a);times=[a.animation_length*1000*i/8 for i in range(9)]
    rows=[sample(tracks,ref,base_channels,base_map,t) for t in times];rs=stats(rows)
    if max(rs['l_footTravel'],rs['r_footTravel'])<.008 and rs['hipsAngle']>1.5:
        b=AnimationData.parse(read(vf,vr[fid]));bt=_build_tracks(b)
        vs=stats([sample(bt,avatar,vpk_channels,source_map,t) for t in times])
        found.append({'id':str(fid),'seconds':a.animation_length,'reference':rs,'vpk':vs})
        print(json.dumps(found[-1]),flush=True)
        if len(found)>=12:break
    if scanned%250==0:print('scanned',scanned,flush=True)
report={'scope':'actual packaged non-additive clips with <=8 mm reference-foot motion and >1.5 degree hip rotation; clip gameplay state unidentified','samplesPerClip':9,'scannedNonAdditive':scanned,'samples':found}
(W/'feet-clips.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('complete',len(found),'of',scanned,flush=True)
