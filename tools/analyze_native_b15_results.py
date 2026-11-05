"""Compare the positive A1 and negative A2 trials using bounded log excerpts."""
from collections import Counter,defaultdict
import hashlib
import re
from pathlib import Path
from package_native_v12 import ROOT,load,save_json
W=ROOT/'outputs/native-v24-b16-20261105';E=W/'evidence'
GAME=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2'


def main():
    E.mkdir(parents=True,exist_ok=True)
    p=GAME/'hd2physbone.log';data=p.read_bytes();text=data.decode('utf-8',errors='replace')
    marks=[m.start()for m in re.finditer(r'\[attach_probe\] variant=\S+ event=loaded',text)]
    lp=GAME/'chef_loader.log';ld=lp.read_bytes();loader=ld.decode('utf-8',errors='replace').splitlines()
    results={}
    for variant in ('A1','A2'):
        at=text.rfind('[attach_probe] variant='+variant+' event=loaded version=1.2.0');assert at>=0
        stop=next((i for i in marks if i>at),len(text))
        lines=[r for r in text[text.rfind('\n',0,at)+1:stop].splitlines()if '[attach_probe]'in r]
        records=[dict(re.findall(r'(\w+)=([^ ]+)',r))for r in lines]
        assert all(r['variant']==variant for r in records)
        counts=Counter(r['event']for r in records)
        assert not any(counts[k]for k in ('disabled','validation_mismatch','rollback','restore_failed'))
        profile=load(ROOT/f'outputs/native-manual-20261103/project/diagnostics/B15/variants/{variant}/profile.json')
        expected={(r['name'],str(r['index']+1))for r in profile['attachmentProbe']['nodes']}
        groups=defaultdict(list);consumers=defaultdict(list)
        applied={(r['avatar'],r['frame']):r for r in records if r['event']=='applied'}
        for row in records:
            if row['event']=='node':groups[row['avatar'],row['frame']].append(row)
            elif row['event']=='consumer':
                assert row['owner']=='unverified';consumers[row['resource']].append(row)
        assert applied and set(groups)==set(applied)
        for key,rows in groups.items():
            assert len(rows)==len(expected)and {(r['name'],r['index'])for r in rows}==expected
            assert int(applied[key]['nodes'])==len(expected)and applied[key]['roots']=='4'
            assert all(max(abs(float(r['dx'])),abs(float(r['dy'])),abs(float(r['dz'])-.6))<.002 for r in rows)
        summary={k:dict(kind=v[0]['kind'],samples=len(v),upwardSamples=sum(abs(float(r['dz'])-.6)<.002 for r in v),
            maxAbsDelta=max(max(abs(float(r[q]))for q in ('dx','dy','dz'))for r in v),owner='unverified')for k,v in consumers.items()}
        assert summary
        if variant=='A1':assert any(v['upwardSamples']for v in summary.values())
        else:assert all(v['maxAbsDelta']<1e-6 for v in summary.values())
        begin=next(i for i,r in enumerate(loader)if r[:8]==lines[0][:8])
        finish=next(i for i in range(begin,len(loader))if 'shutdown (clean)'in loader[i])
        loader_rows=loader[begin:finish+1]
        (E/f'B15-{variant}-probe-excerpt.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        (E/f'B15-{variant}-loader-excerpt.log').write_text('\n'.join(loader_rows)+'\n',encoding='utf-8')
        result=dict(status='PASS',variant='B15-'+variant,candidateSetPositive=variant=='A1',
            userFeedback=('武器和握把周期上移；右手短暂闪到准确握持位置后迅速回退；左手未见明显变化。'if variant=='A1'else'没有效果。'),
            rightHandTransientCorrectContactReported=variant=='A1',rightHandTransientCauseConfirmed=False,
            individualDriverConfirmed=False,appliedCycles=len(applied),nodesPerCycle=len(expected),eventCounts=dict(counts),
            maxNodeReadbackError=max(float(r['error'])for rows in groups.values()for r in rows),consumers=summary,cleanShutdown=True,
            sessionStart=lines[0][:8],sessionEnd=loader_rows[-1][:8],
            skippedRestores=[r for r in lines if 'event=restore_skipped'in r],
            scope='Positive/negative result applies to tested states, timing and this subset. Consumer ownership is not established; hand transient is a user observation, not sampled proof of the overwriting stage.',
            sources=[dict(path=str(p),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()),dict(path=str(lp),bytes=len(ld),sha256=hashlib.sha256(ld).hexdigest())])
        save_json(E/f'B15-{variant}-game-result.json',result);results[variant]=result
    save_json(E/'B15-comparison.json',dict(status='PASS',results=results,
        next='Split positive B15-A1 into H (attach_hand_l, attach_hand_r/weapon_aim) and W (attach_weapon/aim_weapon, head_aim). Two root families and three nodes each; retain identical runtime.'))
    print('B15 comparison verified: A1',results['A1']['appliedCycles'],'positive cycles; A2',results['A2']['appliedCycles'],'valid displacement cycles with zero observed consumer delta. Right-hand transient recorded, cause unconfirmed.')


if __name__=='__main__':main()
