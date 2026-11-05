"""Analyze B9 complete same-frame scene captures, preserving affine scale.

python analyze_native_b9_log.py --log <hd2physbone.log> --output <new-dir>
Requires numpy. Does not write game or manager files.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np


def affine(values):
    a=np.asarray(values,dtype=float)
    if a.shape!=(12,) or not np.isfinite(a).all():raise ValueError('invalid affine matrix')
    m=np.eye(4);m[:3,:3]=a[:9].reshape(3,3).T;m[:3,3]=a[9:]
    return m


def scale_info(m):
    b=m[:3,:3];s=np.linalg.norm(b,axis=0)
    n=b/np.maximum(s,1e-15)
    return dict(axisLengths=s.tolist(),determinant=float(np.linalg.det(b)),
        orthogonalityError=float(np.max(np.abs(n.T@n-np.eye(3)))))


def difference(a,b):
    # Polar rotation separates positive stretch/shear. Reflection is reported
    # by scale_info; no rotation angle is claimed for reflected/singular input.
    angle=None
    if np.linalg.det(a[:3,:3])>1e-12 and np.linalg.det(b[:3,:3])>1e-12:
        ua,_,va=np.linalg.svd(a[:3,:3]);ub,_,vb=np.linalg.svd(b[:3,:3])
        ra,rb=ua@va,ub@vb
        angle=float(np.degrees(np.arccos(np.clip((np.trace(ra.T@rb)-1)/2,-1,1))))
    return dict(positionMeters=float(np.linalg.norm(a[:3,3]-b[:3,3])),
        linearMaxAbs=float(np.max(np.abs(a[:3,:3]-b[:3,:3]))),
        polarRotationDegrees=angle,
        axisLengthMaxAbs=float(np.max(np.abs(np.linalg.norm(a[:3,:3],axis=0)-np.linalg.norm(b[:3,:3],axis=0)))))


def analyze(text):
    phases=defaultdict(list);session=0;invalid=0;notices=[]
    for line_no,line in enumerate(text.splitlines(),1):
        if '[scene_probe] ' not in line:continue
        payload=line.split('[scene_probe] ',1)[1]
        try:e=json.loads(payload)
        except (ValueError,TypeError):invalid+=1;continue
        if e.get('event')=='phase_begin' and e.get('sample')==1 and e.get('phase')=='pre_apply':session+=1
        e['_line']=line_no;e['_session']=session
        if 'phase' in e:phases[(session,e.get('sample'),e.get('frame'),e['phase'])].append(e)
        else:notices.append(e)
    accepted={};incomplete=[];errors=[]
    for key,events in phases.items():
        begin=[e for e in events if e.get('event')=='phase_begin']
        end=[e for e in events if e.get('event')=='phase_end']
        nodes=[e for e in events if e.get('event')=='node']
        errors.extend(e for e in events if e.get('event')=='unavailable')
        if len(begin)!=1 or len(end)!=1 or end[0]['rows']!=len(nodes):
            incomplete.append(dict(key=key,reason='missing_or_inconsistent_phase_boundary'));continue
        if begin[0].get('revision')!='test01-v18-B9' or begin[0].get('readOnly') is not True or begin[0].get('indexBase')!=1:
            incomplete.append(dict(key=key,reason='unexpected_revision_or_index_base'));continue
        groups=defaultdict(list)
        for e in nodes:groups[(e['avatar'],e['modelId'],e['resource'])].append(e)
        for group,rows in groups.items():
            if len(rows)!=8 or len({e['modelIndex'] for e in rows})!=8:
                incomplete.append(dict(key=key,model=group,reason='incomplete_model'));continue
            for e in rows:accepted[(*key[:3],*group,e['name'],key[3])]=e
    observations=[];paired=0
    for key,e in accepted.items():
        other=(*key[:-1],'post_refresh' if key[-1]=='pre_apply' else 'pre_apply')
        if other not in accepted:continue
        try:
            model=e['model'];local=affine(model['localMatrix']);world=affine(model['worldMatrix'])
            parent=world@np.linalg.inv(local)
            av=e['avatarPose'];same=affine(av['worldMatrix']);ap=affine(e['serializedAvatarParentWorld'])
            metrics=dict(session=e['_session'],sample=e['sample'],frame=e['frame'],time=e['time'],phase=e['phase'],
                avatar=e['avatar'],modelId=e['modelId'],resource=e['resource'],name=e['name'],
                modelIndex=e['modelIndex'],avatarIndex=e['avatarIndex'],runtimeParent=model['runtimeParent'],
                parentState=model['parentState'],localScaleApi=model['localScale'],
                localScale=scale_info(local),worldScale=scale_info(world),effectiveParentScale=scale_info(parent),
                effectiveParent=parent.tolist(),parentVsAvatarSame=difference(parent,same),
                parentVsAvatarSerializedParent=difference(parent,ap),worldVsAvatarSame=difference(world,same),line=e['_line'])
            if 'runtimeParentWorld' in model:
                metrics['parentVsModelRuntimeParent']=difference(parent,affine(model['runtimeParentWorld']))
            if key[-1]=='post_refresh':
                pre=accepted[other]['model'];paired+=1
                metrics['sameFrameLocalChange']=difference(local,affine(pre['localMatrix']))
                metrics['sameFrameWorldChange']=difference(world,affine(pre['worldMatrix']))
            observations.append(metrics)
        except (ValueError,KeyError,np.linalg.LinAlgError) as error:
            errors.append(dict(line=e['_line'],reason=str(error),resource=e.get('resource')))
    counts=Counter((r['resource'],str(r['runtimeParent'])) for r in observations)
    summary=dict(status='OBSERVED' if observations else 'NO_COMPLETE_SAMPLES',completeNodePhaseRecords=len(observations),
        sameFrameNodePairs=paired,sessions=session,unavailableRecords=len(errors),malformedLines=invalid,
        incompletePhasesOrModels=incomplete,parentCounts=[dict(resource=k[0],runtimeParent=k[1],records=v)for k,v in sorted(counts.items())],
        gameVisualAcceptance=False,writeRoundtripVerified=False,
        limitation='Raw parent sentinels are external-or-root candidates, not proof of ownership. Review matrices per phase and action timestamps; GPU skinning unobserved.')
    return dict(summary=summary,observations=observations,unavailable=errors,notices=notices)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();blob=args.log.read_bytes()
    result=analyze(blob.decode('utf-8-sig',errors='replace'))
    result['summary'].update(source=str(args.log.resolve()),sourceSha256=hashlib.sha256(blob).hexdigest())
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in result.items():(args.output/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
