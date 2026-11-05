"""Verify serialized arm directions, bend planes and native-reference twist frames."""
import json
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v12 import load,save_json
from anim_batch_mod.native_arm_reference import AnimationReference
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform,_cross
from anim_batch_mod.math3d import vec_sub,quat_rotate,quat_inverse_rotate,quat_multiply,quat_inverse
from anim_batch_mod.motion_skeleton import source_local

W=ROOT/'outputs/native-v14-20261104';P=W/'project'
def length(v):return math.sqrt(sum(x*x for x in v))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def angular(a,b):return math.degrees(math.acos(max(-1,min(1,dot(a,b)/(length(a)*length(b))))))
def project(v,axis):return [x-y*dot(v,axis)/dot(axis,axis) for x,y in zip(v,axis)]

def main(final=False):
    base=ROOT/'outputs/native-fix-20261103';ub=(base/'avatar.toc').read_bytes();bb=(base/'bones.toc').read_bytes()
    unit=UnitData.parse(ub);bones=BonesData.parse(bb);manifest=native.load_manifest(P/'source-skeleton.json')
    expanded=UnitData.parse(native.append_unit(ub,manifest));eb=BonesData.parse(native.append_bones(bb,manifest))
    ni={n:unit.name_hashes.index(h) for n,h in zip(bones.names,bones.hashes)}
    si={n['driver']:len(unit.transforms)+i for i,n in enumerate(manifest['bones']) if n['driver']}
    db=_calculate_world_transforms(unit.transforms,unit.parents)
    refs,_=native._reference_rotations(manifest['bones'],[native.local_pose(source_local(n,i,manifest)) for i,n in enumerate(manifest['bones'])],
        [native.row_pose(n['world']) for n in manifest['bones']],db,ni,manifest)
    source_axes={};native_axes={}
    for side in ('l','r'):
        a,b,c=[ni[side+'_'+s] for s in ('shoulder','elbow','hand')]
        normal=_cross(vec_sub(db[b].position,db[a].position),vec_sub(db[c].position,db[b].position))
        for joint in ('shoulder','elbow'):
            name=side+'_'+joint
            source_axes[name]=quat_inverse_rotate(refs[si[name]-len(unit.transforms)],normal)
            native_axes[name]=quat_inverse_rotate(db[ni[name]].rotation,normal)
    reference=AnimationReference(ROOT.parent/'output/9ba626afa44a3aa3.patch_0')
    def world(a,u,b,t):
        tracks=_build_tracks(a);local=list(u.transforms)
        for ch,h in enumerate(b.hashes):local[u.name_hashes.index(h)]=WorldTransform(*(tr[ch].evaluate(t) for tr in tracks))
        return _calculate_world_transforms(local,u.parents)
    worst_direction=worst_frame=worst_flex=0.;samples=0;negative=0;rows=[]
    if final:
        from package_native_v10 import records,payload
        final_path=P/'animations/runtime/9ba626afa44a3aa3.patch_2'
        final_rows={r[0]:r for r in records(final_path)}
    for path in sorted((W/'arm-candidates').glob('*.toc')):
        clip=int(path.stem)
        a=AnimationData.parse(payload(final_path,final_rows[clip]) if final else path.read_bytes())
        r=AnimationData.parse(reference.read(clip))
        if a.is_additive:continue
        maximum=0.;frames=0
        for frame in range(17):
            t=a.animation_length*1000*frame/16
            sw=world(a,expanded,eb,t);nw=world(r,unit,bones,t)
            for side in ('l','r'):
                svec=[];nvec=[]
                for joint,end in (('shoulder','elbow'),('elbow','hand')):
                    name=side+'_'+joint;child=side+'_'+end
                    sd=vec_sub(sw[si[child]].position,sw[si[name]].position)
                    nd=vec_sub(nw[ni[child]].position,nw[ni[name]].position)
                    if min(length(sd),length(nd))<1e-5:continue
                    svec.append(sd);nvec.append(nd)
                    direction=angular(sd,nd);worst_direction=max(worst_direction,direction);maximum=max(maximum,direction)
                    sa=project(quat_rotate(sw[si[name]].rotation,source_axes[name]),sd)
                    na=project(quat_rotate(nw[ni[name]].rotation,native_axes[name]),nd)
                    if min(length(sa),length(na))>1e-5:worst_frame=max(worst_frame,angular(sa,na))
                    if dot(nd,quat_rotate(nw[ni[name]].rotation,unit.transforms[ni[child]].position))<0:negative+=1
                    samples+=1;frames+=1
                if len(svec)==2:
                    worst_flex=max(worst_flex,abs(angular(*svec)-angular(*nvec)))
        rows.append(dict(id=str(clip),samples=frames,maxSegmentDirectionErrorDegrees=maximum))
    assert worst_direction<.25 and worst_frame<.25 and worst_flex<.25,(worst_direction,worst_frame,worst_flex)
    report=dict(status='PASS',gameTested=False,clips=len(rows),samples=samples,negativeReferenceSegmentSamples=negative,
        maxSegmentDirectionErrorDegrees=worst_direction,maxReferenceFrameTwistErrorDegrees=worst_frame,
        maxElbowFlexionDifferenceDegrees=worst_flex,clipsMeasured=rows,
        scope='matches reference geometry and projected anatomical axes, including negative reference translations')
    report['payloadSource']='final archive' if final else 'candidate files'
    save_json(W/('final-motion-audit.json' if final else 'candidate-audit.json'),report);print(json.dumps(report,indent=2))

if __name__=='__main__':main(final='--final' in sys.argv)
