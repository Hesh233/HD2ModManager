"""Read serialized v6/reference clips; quantify independent vs coupled grip targets.

The closest-common-translation calculation is a feasibility diagnostic only.
It does not alter production animation, weapon poses, or game files.
"""
import json, math, struct, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,WorldTransform,_calculate_world_transforms
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate,vec_add,vec_sub
W=ROOT/'outputs/native-v7-20261104';W.mkdir(exist_ok=True)
P=ROOT/'outputs/native-v6-20261104/project';B=ROOT/'outputs/native-fix-20261103'
def records(path):
    f=path.open('rb');h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+32*nt)
    return f,[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
def read(f,r):f.seek(r[2]);return f.read(r[7])
rf,rr=records(ROOT.parent/'output/9ba626afa44a3aa3.patch_0')
vf,vr=records(P/'animations/runtime/9ba626afa44a3aa3.patch_2')
ref=UnitData.parse((ROOT/'outputs/native-v6-20261104/avatar-reference.toc').read_bytes())
rb=BonesData.parse((B/'bones.toc').read_bytes())
avatar=UnitData.parse(read(vf,next(r for r in vr if r[1]==UNIT_TYPE_ID)))
vb=BonesData.parse(read(vf,next(r for r in vr if r[1]==BONE_TYPE_ID)))
rr={r[0]:r for r in rr if r[1]==ANIMATION_TYPE_ID};vr={r[0]:r for r in vr if r[1]==ANIMATION_TYPE_ID}
profile=json.loads((P/'attachment-profile.json').read_text())
manifest=json.loads((P/'source-skeleton.json').read_text())
rindices={n:ref.name_hashes.index(h) for n,h in zip(rb.names,rb.hashes)}
vindices={n:avatar.name_hashes.index(b['hash']) for b in manifest['bones'] if (n:=b['driver']) is not None}
source_by_driver={b['driver']:b for b in manifest['bones'] if b['driver']}
rightrow=next(x for x in profile['vpk'] if x['standardName']=='attach_hand_r')
def world(a,u,b,time):
    tracks=_build_tracks(a);local=list(u.transforms)
    for ai,h in enumerate(b.hashes):local[u.name_hashes.index(h)]=WorldTransform(*(tr[ai].evaluate(time) for tr in tracks))
    return _calculate_world_transforms(local,u.parents)
def add(a,b):return [x+y for x,y in zip(a,b)]
def sub(a,b):return [x-y for x,y in zip(a,b)]
def mul(v,s):return [x*s for x in v]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm(v):return math.sqrt(dot(v,v))
def sphere_projection(center,radius):
    d=norm(center)
    return [0.,0.,0.] if d<=radius else mul(center,1-radius/d)
def coupled_translation(c1,r1,c2,r2):
    """Closest vector to zero in the intersection of two translation spheres."""
    if norm(c1)<=r1 and norm(c2)<=r2:return [0.,0.,0.]
    p=sphere_projection(c1,r1)
    if math.dist(p,c2)<=r2+1e-9:return p
    p=sphere_projection(c2,r2)
    if math.dist(p,c1)<=r1+1e-9:return p
    d=math.dist(c1,c2)
    if d>r1+r2+1e-9 or d<abs(r1-r2)-1e-9 or d<1e-12:return None
    axis=mul(sub(c2,c1),1/d);along=(r1*r1-r2*r2+d*d)/(2*d)
    center=add(c1,mul(axis,along));radius=math.sqrt(max(0.,r1*r1-along*along))
    perpendicular=sub(mul(center,-1),mul(axis,-dot(center,axis)))
    size=norm(perpendicular)
    if size<1e-12:
        candidate=[1.,0.,0.] if abs(axis[0])<.8 else [0.,1.,0.]
        perpendicular=sub(candidate,mul(axis,dot(candidate,axis)));size=norm(perpendicular)
    result=add(center,mul(perpendicular,radius/size))
    assert math.dist(result,c1)<=r1+1e-7 and math.dist(result,c2)<=r2+1e-7
    return result
lengths={}
for side in ('l','r'):
    values=[]
    for first,last in (('shoulder','elbow'),('elbow','hand')):
        a=side+'_'+first;b=side+'_'+last
        source=math.dist(source_by_driver[a]['world'][12:15],source_by_driver[b]['world'][12:15])
        rw=_calculate_world_transforms(ref.transforms,ref.parents)
        values.append({'segment':first+'-'+last,'sourceMetres':source,'referenceMetres':math.dist(rw[rindices[a]].position,rw[rindices[b]].position)})
    lengths[side]=values
build=json.loads((P/'animations/build-report.json').read_text())['animations']
ids=[int(x['id']) for x in sorted((x for x in build if not x['additive']),key=lambda x:x['max_standard_grip_error'],reverse=True)[:8]]
ids+= [18307702697579710200,16381641002705108128,7781841632278966152,16374892322597155811,1404552152609308]
ids=list(dict.fromkeys(ids));results=[]
for fid in ids:
    a=AnimationData.parse(read(rf,rr[fid]));v=AnimationData.parse(read(vf,vr[fid]));assert not a.is_additive
    frames=[]
    for frame in range(13):
        time=a.animation_length*1000*frame/12;rw=world(a,ref,rb,time);vw=world(v,avatar,vb,time)
        hands={side:vw[vindices[side+'_hand']] for side in ('l','r')}
        targets={side:rw[rindices[side+'_hand']] for side in ('l','r')}
        # The v6 weapon adapter's actual source-right -> configured-right rigid map.
        q=quat_multiply(quat_multiply(hands['r'].rotation,rightrow['axisCorrection']),quat_inverse(targets['r'].rotation))
        left_from_weapon=vec_add(hands['r'].position,quat_rotate(q,vec_sub(targets['l'].position,targets['r'].position)))
        centers={side:vec_sub(vw[vindices[side+'_shoulder']].position,targets[side].position) for side in ('l','r')}
        reaches={side:sum(x['sourceMetres'] for x in lengths[side])-1e-6 for side in ('l','r')}
        translation=coupled_translation(centers['l'],reaches['l'],centers['r'],reaches['r'])
        frames.append({'timeMs':time,'leftHandVsWeaponFrameMetres':math.dist(hands['l'].position,left_from_weapon),
            'leftAbsoluteResidualMetres':math.dist(hands['l'].position,targets['l'].position),
            'rightAbsoluteResidualMetres':math.dist(hands['r'].position,targets['r'].position),
            'commonTargetFeasible':translation is not None,'commonTranslationMetres':None if translation is None else norm(translation),
            'commonTranslation':translation,'rigidMapAngleDegrees':math.degrees(2*math.acos(min(1,abs(q[3]))))})
    row={'id':str(fid),'seconds':a.animation_length,'maxLeftHandVsWeaponFrameMetres':max(x['leftHandVsWeaponFrameMetres'] for x in frames),
        'maxLeftAbsoluteResidualMetres':max(x['leftAbsoluteResidualMetres'] for x in frames),'maxRightAbsoluteResidualMetres':max(x['rightAbsoluteResidualMetres'] for x in frames),
        'coupledFeasibleFrames':sum(x['commonTargetFeasible'] for x in frames),'frames':frames}
    results.append(row);print({k:v for k,v in row.items() if k!='frames'},flush=True)
report={'scope':'serialized v6 and user reference, non-additive clips; no live engine or weapon consumer verification; common translation is only a geometric feasibility study',
        'armLengths':lengths,'samples':results,'sampleCount':len(results),'samplesPerClip':13,
        'maxLeftHandVsWeaponFrameMetres':max(x['maxLeftHandVsWeaponFrameMetres'] for x in results)}
(W/'grip-target-analysis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('report',W/'grip-target-analysis.json',flush=True)
