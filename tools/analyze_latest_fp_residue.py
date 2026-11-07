"""Latest FP residue audit: no Lua/library/deployment changes, fixed directory only."""
import collections,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def main():
 path=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2/hd2_grip_b23.log'
 with path.open('rb') as f:f.seek(max(0,path.stat().st_size-16*1024*1024));lines=f.read().decode('utf-8',errors='replace').splitlines()
 start=max(i for i,l in enumerate(lines) if '"event":"loaded"' in l);lines=lines[start:]
 rows=[]
 for line in lines:
  if '{' not in line:continue
  try:e=json.loads(line[line.index('{'):]);e['stamp']=line[:19];rows.append(e)
  except json.JSONDecodeError:pass
 done=next(e for e in reversed(rows) if e['event']=='complete');s=done['stats']
 intervals=[]
 for i,e in enumerate(rows):
  if e['event']!='view_bypass' or e['status']!='first_person_bypass':continue
  j=next((j for j in range(i+1,len(rows)) if rows[j]['event']=='status' and rows[j]['status']=='active'),None)
  if j is None:continue
  exitFrame=rows[j]['frame'];activeFP=[x for x in rows[i+1:j] if x.get('frame',exitFrame)>=e['frame'] and x.get('frame',exitFrame)<exitFrame]
  first=next((x for x in rows[j+1:] if x['event']=='sidearm_probe' and x['phase']=='before_write'),None)
  # The exit-frame apply precedes its status event. It is NOT an FP write.
  intervals.append(dict(start=e['stamp'],end=rows[j]['stamp'],enterFrame=e['frame'],exitFrame=exitFrame,
    phase=e['phase'],restored=e['restored'],cameraDistance=e['detail'].get('distance'),
    appliedSamplesInsideFp=sum(x['event']=='applied' for x in activeFP),
    sidearmProbesInsideFp=sum(x['event']=='sidearm_probe' for x in activeFP)))
 presentations=[e for e in rows if e['event']=='fp_presentation']
 traces=collections.defaultdict(list)
 for e in presentations:
  for model in e.get('models',[]):traces[(model['resource'],str(model['instance']),model['world'])].append((e,model))
 receiverEvidence=[]
 def position(m):return m[9:12]
 def movement(a,b):return math.dist(position(a),position(b))
 for (resource,instance,world),trace in traces.items():
  freezes=[];changes=[]
  for event,model in trace:
   for key,before in model.get('before',{}).items():
    after=model.get('after',{}).get(key)
    if after:changes.append(max(abs(a-b) for a,b in zip(before,after)))
  for (a,ma),(b,mb) in zip(trace,trace[1:]):
   # Never join separate view intervals, even if Unit/instance IDs were reused.
   boundary=any(a['frame']<e.get('frame',-1)<=b['frame'] and
    ((e['event']=='status' and e.get('status')=='active') or e['event']=='view_bypass') for e in rows)
   if boundary:continue
   if not (ma.get('root') and mb.get('root')):continue
   rootMove=movement(ma['root'],mb['root'])
   for hand in ('l_hand','r_hand'):
    before=ma.get('after',{}).get(hand);after=mb.get('after',{}).get(hand)
    if before and after and rootMove>.1 and movement(before,after)<1e-6:
     freezes.append(dict(hand=hand,start=a['stamp'],end=b['stamp'],rootMovement=rootMove,
      handMovement=movement(before,after),worldBefore=position(before),worldAfter=position(after)))
  receiverEvidence.append(dict(resource=resource,instance=instance,world=world,samples=len(trace),
   maxFpRefreshHandMatrixChange=max(changes) if changes else None,
   stationaryHandWhileRootMoves=len(freezes),examples=freezes[:4]))
 neutral=[]
 for e in rows:
  if e['event']=='sidearm_probe' and e['phase']=='before_write':
   h=e['hands'];a=h.get('sourceRight');b=h.get('sourceRightReference')
   if a and b:neutral.append(max(abs(x-y) for x,y in zip(a,b)))
 report=dict(sessionStart=lines[0][:19],sessionEnd=lines[-1][:19],version=rows[0]['version'],
  eventCounts=dict(collections.Counter(e['event'] for e in rows)),fpIntervals=intervals,
  outputCleanupBalanced=dict(right=s['rightNodeWrites']==s['rightRestores'],left=s['leftNodeWrites']==s['leftRestores'],body=s['bodyNodeWrites']==s['bodyRestores']),
  sourceRightEqualsAnimatedReferenceBeforeWrite=dict(samples=len(neutral),maximumMatrixDifference=max(neutral) if neutral else None),
  disabled=done['disabled'],pendingRestores=done['pendingRestores'],refreshErrors=s['refreshErrors'],
  fpMeshWorldPoseSamplesAvailable=bool(presentations),fpSkinningSamplesAvailable=False,
  fpPresentationSamples=len(presentations),fpCacheRefreshes=s.get('fpPresentationRefreshes'),
  fpCacheRefreshErrors=s.get('fpPresentationErrors'),receiverEvidence=receiverEvidence,
  gameOrRuntimeChanged=False,conclusion=('FP gate/cleanup and cache refresh succeeded, but Source hand matrices freeze while FP arm model roots move. Distinct Avatar/receiver routing is required; filtering IDs alone does not create missing FP Source drivers. Final skin palette/external owner remains unobserved.' if any(x['stationaryHandWhileRootMoves'] for x in receiverEvidence) else 'FP gate/cleanup observed; specific receiver and final skin palette require further evidence.'))
 (TARGET/'第一人称残留-分析.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report))
 return report
if __name__=='__main__':main()
