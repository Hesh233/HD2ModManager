import sys,math,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'tools'))
from verify_native_v8_grip import records,read
from anim_batch_mod.formats import AnimationData
from anim_batch_mod.processor import _build_tracks
W=ROOT/'outputs/native-v9-20261104';m=json.loads((W/'project/source-skeleton.json').read_text());channels={90+i:n['driver'] for i,n in enumerate(m['bones']) if n['driver'] in ('l_shoulder','l_elbow','r_shoulder','r_elbow')}
f,rows=records(ROOT/'outputs/native-v8-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2');byid={r[0]:r for r in rows};out=[]
for p in (W/'candidate-clips').glob('*.toc'):
 a=AnimationData.parse(read(f,byid[int(p.stem)]));b=AnimationData.parse(p.read_bytes())
 if a.is_additive:continue
 results=[]
 for clip in (a,b):
  tracks=_build_tracks(clip);result={}
  for channel,name in channels.items():
   previous=None;maximum=0.;spikes=0
   for i in range(math.floor(clip.animation_length*60)+1):
    q=tracks[1][channel].evaluate(i*1000/60)
    if previous:
     angle=math.degrees(2*math.acos(min(1.,abs(sum(x*y for x,y in zip(previous,q))))));maximum=max(maximum,angle);spikes+=angle>45
    previous=q
   result[name]={'maxFrameDegrees':maximum,'framesOver45Degrees':spikes}
  results.append(result)
 row={'id':p.stem,'v8':results[0],'v9':results[1]};out.append(row)
 print(p.stem,'old/new max',*[round(max(x['maxFrameDegrees'] for x in r.values()),2) for r in results],'over45',*[sum(x['framesOver45Degrees'] for x in r.values()) for r in results])
f.close()
report={'status':'COMPLETE','sampleRate':60,'gameTested':False,'clips':out,'scope':'Fixed real clips, Source local shoulder/elbow jumps; gameplay states are unidentified. This is not an all-actions naturalness acceptance.'}
(W/'arm-continuity-audit.json').write_text(json.dumps(report,indent=2))
