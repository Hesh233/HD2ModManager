"""B11 complete same-frame grip motion analysis; never infers weapon ownership."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from analyze_native_b9_log import affine,difference


def analyze(text):
    phases=defaultdict(list);session=0;malformed=0
    for line_no,line in enumerate(text.splitlines(),1):
        if '[grip_probe] 'not in line:continue
        try:e=json.loads(line.split('[grip_probe] ',1)[1])
        except ValueError:malformed+=1;continue
        if e.get('event')=='begin'and e['sample']==1 and e['phase']=='pre_apply':session+=1
        e['_line']=line_no;phases[(session,e['sample'],e['frame'],e['phase'])].append(e)
    valid={};unavailable=[];incomplete=[]
    for key,events in phases.items():
        begins=[e for e in events if e['event']=='begin'];ends=[e for e in events if e['event']=='end']
        actors=[e for e in events if e['event']=='actor'];unavailable.extend(e for e in events if e['event']=='unavailable')
        if len(begins)!=1 or len(ends)!=1 or ends[0]['actors']!=len(actors)or len({e['avatar']for e in actors})!=len(actors):
            incomplete.append(dict(key=key,reason='phase_count'));continue
        if begins[0].get('revision')!='test01-v20-B11'or begins[0].get('indexBase')!=1 or begins[0].get('readOnly')is not True:
            incomplete.append(dict(key=key,reason='metadata'));continue
        for actor in actors:valid[(*key[:3],actor['avatar'],key[3])]=actor
    records=[];previous={}
    for key in sorted(valid):
        if key[-1]!='post_refresh':continue
        before=valid.get((*key[:-1],'pre_apply'));after=valid[key]
        if not before:continue
        try:
            chest=affine(after['nodes']['native_chest']['worldMatrix']);chest0=affine(before['nodes']['native_chest']['worldMatrix'])
            inv=np.linalg.inv(chest);inv0=np.linalg.inv(chest0)
            nodes={};relative={}
            prev=previous.get((key[0],key[3]))
            for name,row in after['nodes'].items():
                w=affine(row['worldMatrix']);pre=affine(before['nodes'][name]['worldMatrix'])
                rel=inv@w;relative[name]=rel
                nodes[name]=dict(sameFrame=difference(w,pre),relativeChest=rel.tolist())
                if prev and name in prev['relative']:
                    nodes[name]['motionSincePreviousPost']=difference(rel,prev['relative'][name])
                    nodes[name]['previousPostToThisPre']=difference(inv0@pre,prev['relative'][name])
            models=[]
            for model in after['models']:
                side='left'if model['side']=='l'else'right'
                hand=affine(model['nodes']['hand']['worldMatrix']);source=affine(after['nodes']['source_'+side+'_hand']['worldMatrix'])
                models.append(dict(resource=model['resource'],side=side,modelVsAvatarSource=difference(hand,source),relativeChest=(inv@hand).tolist()))
            candidates=[];candidate_rel={}
            for c in after['candidates']:
                result=dict(id=c['id'],resource=c['resource'],kind=c['kind'],owner='unverified',nodes={})
                for name,row in c['nodes'].items():
                    w=affine(row['worldMatrix']);local=affine(row['localMatrix']);parent=w@np.linalg.inv(local);rel=inv@w
                    cr=dict(relativeChest=rel.tolist(),parentState=row['parent'],
                        distanceToNativeRightHand=difference(w,affine(after['nodes']['native_right_hand']['worldMatrix']))['positionMeters'],
                        distanceToNativeLeftHand=difference(w,affine(after['nodes']['native_left_hand']['worldMatrix']))['positionMeters'])
                    if row['parent']in('nil',0,-1):
                        cr['effectiveParentComparisons']={role:difference(parent,affine(after['nodes'][role]['worldMatrix']))
                            for role in ('native_right_grip','native_weapon_attach','native_sling','native_samplepouch')}
                    ck=(c['id'],name);candidate_rel[ck]=rel
                    if prev and ck in prev['candidates']:cr['motionSincePreviousPost']=difference(rel,prev['candidates'][ck])
                    result['nodes'][name]=cr
                candidates.append(result)
            previous[(key[0],key[3])]=dict(relative=relative,candidates=candidate_rel)
            records.append(dict(session=key[0],sample=key[1],frame=key[2],avatar=key[3],time=after['time'],
                bodyStable=after['bodyStable'],active=after['active'],nodes=nodes,models=models,candidates=candidates))
        except (ValueError,KeyError,np.linalg.LinAlgError)as error:incomplete.append(dict(key=key,reason=str(error)))
    return dict(status='OBSERVED'if records else'NO_COMPLETE_SAMPLES',pairedActorSamples=len(records),
        malformedLines=malformed,incomplete=incomplete,unavailable=unavailable,records=records,
        limitation='Equipment is proximity-filtered and ownership remains unverified. Same-callback motion does not directly measure final GPU skinning or automatically identify aiming actions.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--log',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    blob=a.log.read_bytes();result=analyze(blob.decode('utf-8-sig',errors='replace'))
    result.update(source=str(a.log.resolve()),sourceSha256=hashlib.sha256(blob).hexdigest())
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k]for k in('status','pairedActorSamples','malformedLines')},ensure_ascii=False))
