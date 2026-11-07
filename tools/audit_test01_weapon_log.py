"""Read latest test01 session; no library or game writes."""
import collections,json,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
LOG=Path(r'C:\Users\Administrator\AppData\Roaming\Arrowhead\Helldivers2\hd2_grip_b23.log')
compact=LOG.with_name('hd2_grip_b23_compact.log')
if compact.exists() and (not LOG.exists() or compact.stat().st_mtime>=LOG.stat().st_mtime):LOG=compact
def audit():
    counts=collections.Counter(); samples=collections.defaultdict(list); groups=collections.Counter(); rows=collections.defaultdict(list); scans=[]; start=None; complete=None; finish=None
    with LOG.open(encoding='utf8') as f:
        for line in f:
            try:e=json.loads(line[line.index('{'):])
            except (ValueError,json.JSONDecodeError):continue
            stamp=line[:19];k=e.get('event')
            if k=='loaded':
                counts.clear();samples.clear();groups.clear();rows.clear();scans=[];start=dict(stamp=stamp,config=e)
            finish=stamp;counts[k]+=1
            resource=e.get('weaponResource') or e.get('resource') or '-'
            groups[k+':'+resource]+=1
            if len(samples[k+':'+resource])<2:samples[k+':'+resource].append(dict(stamp=stamp,**e))
            if k in ('applied','left_applied','right_applied','sidearm_probe','left_skipped'):rows[k].append(dict(stamp=stamp,**e))
            if k=='scan' and len(scans)<6:scans.append(dict(stamp=stamp,**e))
            if k=='complete':complete=e
    def dist(a,b):return math.dist(a[9:12],b[9:12])
    right=collections.defaultdict(list)
    for e in rows['right_applied']:
        if e.get('format')=='positions-v1':d=math.dist(e['target'],e['sourceAfter'])
        else:d=dist(e['target'],e['sourceAfter'])
        right[e['resource']].append(d)
    result=dict(log=str(LOG),logBytes=LOG.stat().st_size,start=start,end=finish,eventCounts=dict(counts),byResource=dict(groups),rightHandTargetResidual={r:dict(samples=len(v),min=min(v),max=max(v),median=sorted(v)[len(v)//2]) for r,v in right.items()},complete=complete,samples=dict(samples),scans=scans)
    (TARGET/'test01-武器修正-最新日志.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    (TARGET/'test01-武器修正-日志样本.json').write_text(json.dumps(rows,ensure_ascii=False),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('samples','scans','complete')},ensure_ascii=False,indent=2))
if __name__=='__main__':audit()
