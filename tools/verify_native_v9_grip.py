"""Measure the built v9 hand targets without declaring game gripping passed.

Exit 0 means this diagnostic completed; inspect validationStatus and gripStatus.
A large geometric residual is a measured limitation, not a parser/test failure.
"""
import argparse,hashlib,json,math,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,WorldTransform,_calculate_world_transforms
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate,vec_add,vec_sub

def records(path):
    f=path.open('rb');h=f.read(72)
    if len(h)!=72:raise ValueError('Truncated archive header: '+str(path))
    nt,n=struct.unpack_from('<II',h,4);f.seek(72+32*nt)
    return f,[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
def read(f,r):f.seek(r[2]);return f.read(r[7])
def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def world(tracks,u,channel_to_unit,time):
    local=list(u.transforms)
    for ai,ui in enumerate(channel_to_unit):local[ui]=WorldTransform(*(tr[ai].evaluate(time) for tr in tracks))
    return _calculate_world_transforms(local,u.parents)

def resolved_attachment(worlds,row,source):
    """Resolve the stored reference according to its declared runtime policy."""
    target=worlds[row['sourceReferenceIndex']]
    if row.get('policy')!='source-blended-reference':return target
    native_anchor=worlds[row['configuredAnchorIndex']]
    source_anchor=worlds[source[row['driverAnchorName']]]
    inverse=quat_inverse(native_anchor.rotation);axis=row['axisCorrection']
    p=quat_rotate(axis,quat_rotate(inverse,vec_sub(target.position,native_anchor.position)))
    q=quat_multiply(axis,quat_multiply(inverse,target.rotation))
    return WorldTransform(vec_add(source_anchor.position,quat_rotate(source_anchor.rotation,p)),quat_multiply(source_anchor.rotation,q),[1.,1.,1.])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=ROOT/'outputs/native-v9-20261104/project')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--samples-per-clip',type=int,default=25)
    parser.add_argument('--tolerance-metres',type=float,default=.01)
    args=parser.parse_args()
    if args.samples_per_clip<2 or not 0<args.tolerance_metres<.1:raise ValueError('Invalid sampling/tolerance')
    p=args.project.resolve();out=args.output or p.parent/'grip-validation-audit.json'
    model=json.loads((p/'source-skeleton.json').read_text(encoding='utf-8'))
    profile=json.loads((p/'attachment-profile.json').read_text(encoding='utf-8'))
    # Read final serialized structures; never assume a v6 channel count or offset.
    files=list((p/'animations/runtime').glob('*.patch_*'))
    files=[f for f in files if f.name.rsplit('.',1)[-1].startswith('patch_')]
    if len(files)!=1:raise ValueError('Expected one final animation patch')
    patch=files[0];reference=ROOT.parent/'output/9ba626afa44a3aa3.patch_0'
    vf,vrows=records(patch);rf,rrows=records(reference)
    try:
        avatar=UnitData.parse(read(vf,next(r for r in vrows if r[1]==UNIT_TYPE_ID)))
        vb=BonesData.parse(read(vf,next(r for r in vrows if r[1]==BONE_TYPE_ID)))
        reference_unit_path=ROOT/'outputs/native-v9-20261104/unit-anim-reference.toc'
        ref=UnitData.parse(reference_unit_path.read_bytes())
        rb=BonesData.parse((ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes())
        vi={h:i for i,h in enumerate(avatar.name_hashes)};ri={h:i for i,h in enumerate(ref.name_hashes)}
        vmap=[vi[h] for h in vb.hashes];rmap=[ri[h] for h in rb.hashes]
        native={n:vi[h] for n,h in zip(rb.names,rb.hashes)}
        rnames={n:ri[h] for n,h in zip(rb.names,rb.hashes)}
        source={b['driver']:vi[b['hash']] for b in model['bones'] if b['driver'] is not None}
        by_name={x['standardName']:x for x in profile['vpk'] if x.get('standardName')}
        right=by_name['attach_hand_r']
        vr={r[0]:r for r in vrows if r[1]==ANIMATION_TYPE_ID};rr={r[0]:r for r in rrows if r[1]==ANIMATION_TYPE_ID}
        if set(vr)!=set(rr):raise ValueError('Animation ID sets differ from reference')
        build_path=p/'animations/build-report.json'
        build=json.loads(build_path.read_text(encoding='utf-8'))['animations']
        worst=sorted((x for x in build if not x['additive']),key=lambda x:x.get('max_standard_grip_error',0),reverse=True)[:8]
        ids=list(dict.fromkeys([int(x['id']) for x in worst]+[18307702697579710200,16381641002705108128,7781841632278966152,16374892322597155811,1404552152609308]))
        rows=[]
        for fid in ids:
            a=AnimationData.parse(read(rf,rr[fid]));v=AnimationData.parse(read(vf,vr[fid]))
            if a.is_additive or v.is_additive:raise ValueError('Selected non-additive sample has additive flags')
            if len(v.initial_bone_states)!=len(vb.hashes):raise ValueError('Animation/Bones mismatch')
            duration_delta=a.animation_length-v.animation_length
            if abs(duration_delta)>.01:raise ValueError('Reference duration differs by more than 10 ms')
            duration=min(a.animation_length,v.animation_length)
            rt,vt=_build_tracks(a),_build_tracks(v);frames=[]
            for frame in range(args.samples_per_clip):
                time=duration*1000*frame/(args.samples_per_clip-1)
                rw=world(rt,ref,rmap,time);vw=world(vt,avatar,vmap,time)
                lhs=vw[source['l_hand']];rhs=vw[source['r_hand']]
                lref=rw[rnames['l_hand']];rref=rw[rnames['r_hand']]
                q=quat_multiply(quat_multiply(rhs.rotation,right['axisCorrection']),quat_inverse(rref.rotation))
                # This is the reference hand pair in the v9 right-hand frame.
                # It measures whether a weapon moved with that frame could retain
                # the reference left-hand location; no live weapon Unit is queried.
                expected_left=vec_add(rhs.position,quat_rotate(q,vec_sub(lref.position,rref.position)))
                row={'timeMs':time,'leftToReferenceMetres':math.dist(lhs.position,lref.position),
                    'rightToReferenceMetres':math.dist(rhs.position,rref.position),
                    'leftToRightAnchoredReferenceMetres':math.dist(lhs.position,expected_left),
                    'nativeToSourceLeftMetres':math.dist(vw[native['l_hand']].position,lhs.position),
                    'nativeToSourceRightMetres':math.dist(vw[native['r_hand']].position,rhs.position)}
                for name in ('attach_hand_l','attach_hand_r','attach_weapon'):
                    ar=by_name[name];si=ar['sourceReferenceIndex']
                    if not 0<=si<len(vw):raise ValueError('Source attachment index out of range')
                    anchor=source[ar['driverAnchorName']]
                    target=resolved_attachment(vw,ar,source)
                    row[name+'ResolvedSourceTargetDistanceMetres']=math.dist(target.position,vw[anchor].position)
                frames.append(row)
            metrics={k:max(f[k] for f in frames) for k in frames[0] if k!='timeMs'}
            rows.append({'id':str(fid),'sampledSeconds':duration,'referenceDurationDeltaSeconds':duration_delta,'maxima':metrics,'frames':frames})
            print(fid,'left_pair_max_m',round(metrics['leftToRightAnchoredReferenceMetres'],6),flush=True)
        maximum=max(row['maxima']['leftToRightAnchoredReferenceMetres'] for row in rows)
        failed=[row['id'] for row in rows if row['maxima']['leftToRightAnchoredReferenceMetres']>args.tolerance_metres]
        report={'validationStatus':'COMPLETE','gripStatus':'OFFLINE_GEOMETRIC_RESIDUAL_EXCEEDS_TOLERANCE' if failed else 'SAMPLED_GEOMETRY_WITHIN_TOLERANCE_NOT_GAME_VERIFIED',
            'gameTested':False,'aimControllerVerified':False,'weaponConsumerTimingVerified':False,
            'scope':'final serialized animation hand geometry versus traditional-rig reference; sample selection includes worst residual clips with unidentified gameplay semantics',
            'excludedClaims':['No full-action coupled hand forcing was applied.','No live weapon Unit or procedural aim result was read.','Passing this measurement would not establish game gripping correctness.'],
            'animationPatch':str(patch),'animationSha256':digest(patch),'referencePatch':str(reference),'referenceSha256':digest(reference),
            'referenceUnitSha256':digest(reference_unit_path),'avatarNodes':len(avatar.transforms),'animationChannels':len(vb.hashes),
            'attachmentReferenceMode':model.get('attachmentReferenceMode','baked-source-offset'),
            'sampleCount':len(rows),'samplesPerClip':args.samples_per_clip,'toleranceMetres':args.tolerance_metres,
            'maxLeftToRightAnchoredReferenceMetres':maximum,'exceedingClipIds':failed,'samples':rows}
        out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('samples','exceedingClipIds')},indent=2))
        return 0
    finally:vf.close();rf.close()
if __name__=='__main__':raise SystemExit(main())
