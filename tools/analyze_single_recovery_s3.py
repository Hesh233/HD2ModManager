"""Read-only S3 landing/recovery shape evidence; never identifies an FP capture by assumption."""
from pathlib import Path
import argparse, collections, csv, datetime, hashlib, json, math, os, statistics, sys
import build_detailed_grip_test as b
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start'
LOG=Path(os.environ['APPDATA'])/'Arrowhead/Helldivers2/hd2_single_TEST_DETAILED_test01_RAGDOLL_S3_20261109_113311.log'
PROFILE=ROOT/'outputs/single-test01-ragdoll-probe-20261109/s3/single-observer-profile.json'
FP=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/非运行文件/归档/测试报告/第一人称手臂修复可行性-离线分析20261109.json'

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--log',type=Path,default=globals()['LOG'])
 parser.add_argument('--out',type=Path,help='New evidence directory (defaults to a subfolder named after the log)')
 parser.add_argument('--profile',type=Path,default=globals()['PROFILE'])
 parser.add_argument('--fp-reference',type=Path,default=globals()['FP'])
 parser.add_argument('--compare',type=Path,help='Earlier report to compare without overwriting it')
 args=parser.parse_args(argv)
 LOG,OUT,PROFILE,FP=args.log.resolve(),(args.out or (globals()['OUT']/args.log.stem)).resolve(),args.profile,args.fp_reference
 OUT.mkdir(parents=True,exist_ok=True);profile=b.load(PROFILE);fp=b.load(FP);names={n['index']:n.get('name') for n in profile['resources']['34a40a5ae7a392ba']['nodes']}
 modes=collections.Counter();resources=collections.Counter();motion=[];poses=[];native={};events=collections.Counter();complete=None;firstStamp=None;lastStamp=None
 for line in LOG.open(encoding='utf-8-sig'):
  at=line.find('{')
  if at<0:continue
  r=json.loads(line[at:]);events[r['event']]+=1;firstStamp=firstStamp or line[:19];lastStamp=line[:19]
  if r['event']=='complete':complete=r
  if 'resource' in r:resources[r['resource']]+=1
  if r['event']=='single_model_motion' and r['resource']=='34a40a5ae7a392ba':
   v={names.get(x[0]):x for x in r['values']};motion.append(dict(stamp=line[:19],time=r['time'],frame=r['frame'],v=v))
  if r['event']=='single_ragdoll_pose':
   row=dict(stamp=line[:19],time=r['time'],frame=r['frame'],poses={n.get('name'):n for n in r['poses'] if n.get('available')})
   if r['kind']=='native_avatar_reference':
    native[r['frame']]=row;modes[(r['animationState'].get('value'),r['boneMode'].get('value'))]+=1
   if r['resource']=='34a40a5ae7a392ba':poses.append(row)
 if not motion:raise ValueError('No main-model motion samples in the specified S3 log')
 keys=('l_elbow','r_elbow','l_hand','r_hand');normal={k:statistics.median(sorted(r['v'][k][8] for r in motion)[:max(1,len(motion)//2)]) for k in keys}
 original={k:fp['baseFp']['nativeArmRestGeometry'][k[0]]['upperMetres' if 'elbow'in k else 'forearmMetres'] for k in keys}
 start=motion[0]['time'];windows=[];active=None
 for row in motion:
  vals={k:row['v'][k][8] for k in keys};native_like=max(abs(vals[k]-original[k])/original[k] for k in keys)<.025
  if native_like and active is None:active=dict(first=row['stamp'],firstTime=row['time'],firstFrame=row['frame'])
  if active is not None:
   if native_like:active.update(last=row['stamp'],lastTime=row['time'],lastFrame=row['frame'])
   else:
    active['firstNonNativeStamp']=row['stamp'];active['firstNonNativeFrame']=row['frame'];active['seconds']=active['lastTime']-active['firstTime'];windows.append(active);active=None
 if active:active['seconds']=active['lastTime']-active['firstTime'];windows.append(active)
 comparisons={name:[] for name in names.values() if name};zero_locals=0;local_rows=0;scale_deviation=0
 for row in poses:
  n=native.get(row['frame'])
  for name,p in row['poses'].items():
   local_rows+=1;zero_locals+=sum(x*x for x in p['localPose'][9:])<1e-12
   scale_deviation=max(scale_deviation,max(abs(v-1) for v in p['worldScale']))
   if n and name in comparisons and name in n['poses']:
    comparisons[name].append(math.sqrt(sum((a-b)**2 for a,b in zip(p['worldPose'][9:],n['poses'][name]['worldPose'][9:]))))
 summary={k:dict(normalMetres=normal[k],fpOriginalNativeMetres=original[k],minObservedMetres=min(r['v'][k][8] for r in motion),minimumSample={name:min(motion,key=lambda r:r['v'][k][8])[name]for name in('stamp','time','frame')},maxObservedMetres=max(r['v'][k][8] for r in motion),expansionRatio=max(r['v'][k][8] for r in motion)/normal[k],maxNativeReferencePositionDifference=max(comparisons[k])if comparisons[k]else None) for k in keys}
 report=dict(status='ANALYZED_NOT_SOLVER_PROOF',sourceLog=str(LOG),sourceSha256=hashlib.sha256(LOG.read_bytes()).hexdigest(),events=dict(events),resources=dict(resources),fpAvatarSamples=resources.get('d0cf4d493ca08bed',0),nativeModes=[dict(fsm=k[0],mode=k[1],samples=v) for k,v in modes.items()],armSegments=summary,nativeLengthWindows=windows,modelLocalTranslationZeroRows=zero_locals,modelPoseRows=local_rows,maxWorldScaleDeviation=scale_deviation,notes=['This S3 stream has no FP Avatar samples; do not label it an FP recording.','Model local translations are zero under external bone links: exported-parent FK distance is a segment/space comparison, not a proved broken FK cache.','World arm segments change between source-sized animation geometry and lengths matching original native FP/TP arms while matrix scale stays ~1.','Correlation with native reference and original lengths supports native ragdoll/recovery handoff as a candidate, not direct Havok/GPU observation.','No model, animation, physics or game data changed.'])
 report.update(firstStamp=firstStamp,lastStamp=lastStamp,complete=complete,motionSamples=len(motion),mainModelPoseSamples=len(poses),nativeReferenceFrames=len(native))
 report['compressionWindows']=[]
 active=None
 for row in motion:
  compressed=[k for k in keys if row['v'][k][8]<normal[k]*.8]
  if compressed:
   if active is None:active=dict(first=row['stamp'],firstTime=row['time'],firstFrame=row['frame'],minMetres={k:row['v'][k][8] for k in keys})
   active.update(last=row['stamp'],lastTime=row['time'],lastFrame=row['frame'])
   active['minMetres']={k:min(active['minMetres'][k],row['v'][k][8])for k in keys}
  elif active is not None:
   active['seconds']=active['lastTime']-active['firstTime'];report['compressionWindows'].append(active);active=None
 if active:
  active['seconds']=active['lastTime']-active['firstTime'];report['compressionWindows'].append(active)
 report['sameFrameNativeWorldComparison']={name:dict(samples=len(values),maxPositionDifferenceMetres=max(values)) for name,values in comparisons.items() if values}
 report['otherRecordedParentDistances']={name:dict(normalMetres=statistics.median(sorted(r['v'][name][8] for r in motion)[:max(1,len(motion)//2)]),minimumMetres=min(r['v'][name][8] for r in motion),maximumMetres=max(r['v'][name][8] for r in motion),metric='world_distance_to_exported_parent_not_cache_error') for name in motion[0]['v'] if name not in keys}
 episodes=[]
 for window in windows:
  if episodes and window['firstTime']-episodes[-1]['lastTime']<.5:
   episodes[-1].update(last=window['last'],lastTime=window['lastTime'],lastFrame=window['lastFrame']);episodes[-1]['nativeWindowsMerged']+=1
  else:episodes.append(dict(window,nativeWindowsMerged=1))
 for episode in episodes:
  previous_rows=[r for r in motion if episode['firstTime']-4<=r['time']<=episode['firstTime']]
  active_rows=[r for r in motion if episode['firstTime']<=r['time']<=episode['lastTime']+.3]
  recoveries=[w for w in report['compressionWindows']if episode['lastTime']<=w['firstTime']<=episode['lastTime']+1]
  episode.update(seconds=episode['lastTime']-episode['firstTime'],hipHeightBeforeWindowMax=max(r['v']['hips'][3] for r in previous_rows),hipHeightWindowMinimum=min(r['v']['hips'][3] for r in active_rows),compressionAfterNativeWindow=recoveries,interpretation='hip_height_and_world_length_correlation_not_direct_ground_contact_or_havok_state')
 report['fallRecoveryEpisodes']=episodes
 with (OUT/'single-recovery-motion.csv').open('w',encoding='utf-8',newline='')as f:
  writer=csv.writer(f);writer.writerow(['timestamp','time','frame','hipHeightMetres',*keys])
  for r in motion:writer.writerow([r['stamp'],r['time'],r['frame'],r['v']['hips'][3],*(r['v'][k][8]for k in keys)])
 if args.compare:
  previous=b.load(args.compare)
  report['comparison']=dict(sourceReport=str(args.compare.resolve()),sourceSha256=hashlib.sha256(args.compare.read_bytes()).hexdigest(),previousLog=previous['sourceLog'],segments={k:dict(previousNormal=previous['armSegments'][k]['normalMetres'],normalDifference=summary[k]['normalMetres']-previous['armSegments'][k]['normalMetres'],previousMin=previous['armSegments'][k]['minObservedMetres'],previousMax=previous['armSegments'][k]['maxObservedMetres']) for k in keys})
 (OUT/'single-recovery-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 try:
  import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
  fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True);ts=[r['time']-start for r in motion]
  axes[0].plot(ts,[r['v']['hips'][3] for r in motion],color='#334155');axes[0].set_ylabel('Hip height (m)')
  for episode in episodes:axes[0].text((episode['firstTime']+episode['lastTime'])/2-start,23.4,episode['first'][11:],ha='center',va='top',fontsize=8,color='#92400e')
  for k,color in [('l_elbow','#2563eb'),('r_elbow','#f97316')]:axes[1].plot(ts,[r['v'][k][8]*100 for r in motion],label=k,color=color,lw=1)
  for k,color in [('l_hand','#2563eb'),('r_hand','#f97316')]:axes[2].plot(ts,[r['v'][k][8]*100 for r in motion],label=k,color=color,lw=1)
  for ax,k in [(axes[1],'l_elbow'),(axes[2],'l_hand')]:
   ax.axhline(original[k]*100,ls='--',color='#dc2626',label='Original native bind length');ax.axhline(normal[k]*100,ls=':',color='#16a34a',label='Model-size animation length');ax.set_ylabel('Segment (cm)');ax.legend(loc='upper right',fontsize=8)
  for ax in axes:
   for w in windows:ax.axvspan(w['firstTime']-start,w['lastTime']-start,color='#f59e0b',alpha=.12)
   ax.grid(alpha=.18)
  axes[2].set_xlabel('Seconds from first valid model sample');fig.suptitle('test01 S3: world segment-length handoff while scale stays ~1 (no FP recording)')
  fig.tight_layout();fig.savefig(OUT/'single-recovery-shape.png',dpi=140);plt.close(fig)
 except ImportError:pass
 print(json.dumps(dict(fpAvatarSamples=report['fpAvatarSamples'],armSegments=summary,nativeLengthWindows=windows,zeroLocalRows=f'{zero_locals}/{local_rows}',maxWorldScaleDeviation=scale_deviation),ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
