"""Capture the positive B14-A displacement trial without inferring gun ownership."""
from collections import Counter,defaultdict
import hashlib
import re
from pathlib import Path
from package_native_v12 import ROOT,load,save_json

W=ROOT/'outputs/native-v23-b15-20261105';E=W/'evidence'
GAME=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2'


def main():
    E.mkdir(parents=True,exist_ok=True)
    path=GAME/'hd2physbone.log';data=path.read_bytes();text=data.decode('utf-8',errors='replace')
    at=text.rfind('[attach_probe] variant=A event=loaded version=1.2.0');assert at>=0
    start=text.rfind('\n',0,at)+1
    lines=[r for r in text[start:].splitlines()if '[attach_probe]'in r]
    assert lines and all('[attach_probe] variant=A 'in r for r in lines)
    records=[dict(re.findall(r'(\w+)=([^ ]+)',r))for r in lines]
    counts=Counter(r['event']for r in records)
    assert not any(counts[k]for k in ('disabled','validation_mismatch','rollback','restore_failed'))
    profile=load(ROOT/'outputs/native-manual-20261103/project/diagnostics/B14/variants/A/profile.json')
    expected={(r['name'],str(r['index']+1))for r in profile['attachmentProbe']['nodes']}
    applied={(r['avatar'],r['frame']):r for r in records if r['event']=='applied'}
    by_frame=defaultdict(list);consumers=defaultdict(list)
    for row in records:
        if row['event']=='node':by_frame[row['avatar'],row['frame']].append(row)
        elif row['event']=='consumer':
            assert row['owner']=='unverified';consumers[row['resource']].append(row)
    assert applied and set(applied)==set(by_frame)
    for key,rows in by_frame.items():
        assert len(rows)==17 and {(r['name'],r['index'])for r in rows}==expected
        assert applied[key]['nodes']=='17'and applied[key]['roots']=='8'
        assert all(abs(float(r['dx']))<.002 and abs(float(r['dy']))<.002 and abs(float(r['dz'])-.6)<.002 for r in rows)
    loader=GAME/'chef_loader.log';loader_data=loader.read_bytes()
    loader_rows=[r for r in loader_data.decode('utf-8',errors='replace').splitlines()if r[:8]>=lines[0][:8]]
    assert loader_rows and 'shutdown (clean)'in loader_rows[-1]
    (E/'B14-A-probe-excerpt.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (E/'B14-A-loader-excerpt.log').write_text('\n'.join(loader_rows)+'\n',encoding='utf-8')
    response={k:dict(kind=v[0]['kind'],samples=len(v),
        maxAbsDelta=max(max(abs(float(r[q]))for q in ('dx','dy','dz'))for r in v),
        upwardSamples=sum(abs(float(r['dz'])-.6)<.002 for r in v),owner='unverified')for k,v in consumers.items()}
    def meta(p,d):return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
    report=dict(status='PASS',variant='B14-A',userFeedback='左右手位置没有变化，武器整体往上移动',
        candidateSetPositive=True,individualDriverConfirmed=False,handFollowObserved=False,
        eventCounts=dict(counts),appliedCycles=len(applied),nodesPerCycle=17,
        maxNodeReadbackError=max(float(r['error'])for rows in by_frame.values()for r in rows),
        consumers=response,cleanShutdown=True,sessionStart=lines[0][:8],sessionEnd=loader_rows[-1][:8],
        skippedRestores=[line for line in lines if 'event=restore_skipped'in line],
        scope='User-visible gun response and verified candidate displacement; nearby consumer ownership remains unverified. Two layout-changed restores were skipped, not claimed successful.',
        next='Split the eight B14-A root families into A1/A2 with four each; preserve runtime, transforms and timing.',
        sources=[meta(path,data),meta(loader,loader_data)])
    save_json(E/'B14-A-game-result.json',report)
    print('B14-A positive:',len(applied),'cycles x 17 nodes; max error',report['maxNodeReadbackError'],'; hands unchanged per user; ownership unverified.')


if __name__=='__main__':main()
