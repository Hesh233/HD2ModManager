"""Read B10 roundtrip result lines; reject incomplete PASS records."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from analyze_native_b9_log import affine,difference


def analyze(text):
    session=0;groups=defaultdict(lambda:dict(nodes=[],results=[]));rejected=[];unexpected=[]
    for n,line in enumerate(text.splitlines(),1):
        if '[physbone]'in line and '启动于'in line:session+=1
        if '[scene_roundtrip]'not in line:continue
        fields={s.split('=',1)[0]:s.split('=',1)[1]for s in line.split()if '='in s}
        if 'event'not in fields:unexpected.append(dict(line=n,text=line));continue
        event=fields['event'];fields['line']=n
        if event=='rejected':rejected.append(fields);continue
        key=(session,fields.get('trial'),fields.get('frame'))
        if event=='node':groups[key]['nodes'].append(fields)
        elif event=='result':groups[key]['results'].append(fields)
    accepted=[];failures=[];incomplete=[]
    for key,group in groups.items():
        if len(group['results'])!=1:incomplete.append(dict(key=key,reason='result_count'));continue
        result=group['results'][0]
        if result['status']!='PASS':failures.append(dict(key=key,result=result));continue
        nodes=group['nodes'];unique={(r['avatar'],r['model'],r['resource'],r['index'])for r in nodes}
        if len(nodes)!=int(result['writes'])or len(unique)!=len(nodes)or len(nodes)!=8*int(result['models']):
            incomplete.append(dict(key=key,reason='node_count_or_duplicates'));continue
        try:
            metrics=[]
            for row in nodes:
                arrays={k:affine([float(x)for x in row[k].split(',')])for k in('before_local','after_local','before_world','after_world')}
                localmax=float(np.max(np.abs(arrays['before_local']-arrays['after_local'])))
                world=difference(arrays['before_world'],arrays['after_world'])
                if localmax>1e-6 or world['positionMeters']>.001 or world['linearMaxAbs']>.0002 or world['axisLengthMaxAbs']>.00002:
                    raise ValueError('PASS numbers exceed tolerance')
                metrics.append(dict(resource=row['resource'],index=int(row['index']),localMaxAbs=localmax,world=world))
            accepted.append(dict(session=key[0],trial=int(key[1]),frame=int(key[2]),models=int(result['models']),nodes=metrics))
        except (KeyError,ValueError)as error:incomplete.append(dict(key=key,reason=str(error)))
    return dict(status='OBSERVED'if accepted else'NO_VALID_PASS',passedTrials=accepted,failedTrials=failures,
        rejected=rejected,incomplete=incomplete,unexpected=unexpected,
        limitation='A numerical PASS verifies sampled getter/setter roundtrip only; GPU behavior and visual grip need user confirmation.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--log',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    data=a.log.read_bytes();result=analyze(data.decode('utf-8-sig',errors='replace'))
    result.update(source=str(a.log.resolve()),sourceSha256=hashlib.sha256(data).hexdigest())
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],passedTrials=len(result['passedTrials']),failedTrials=len(result['failedTrials']),rejected=len(result['rejected']),incomplete=len(result['incomplete']))))
