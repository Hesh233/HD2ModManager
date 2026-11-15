"""Analyze FP A1 reception failures and measured melee contacts without inventing holder identity."""
from pathlib import Path
import argparse, collections, hashlib, json, math
import numpy as np
from analyze_left_items_and_single_live import records, digest
from build_first_person_source_test import ROOT

LOG_DIR=Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2')
FP_LOG=LOG_DIR/'hd2_grip_TEST_PERF_test06_FP_SOURCE_A1_20261109_135025.part01.log'
TP_LOG=LOG_DIR/'hd2_grip_TEST_PERF_test06_LEFT_ITEMS_V12_20261109_112549.part01.log'
OUT=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/live-a1-135025'
CONTRACT=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/receiver-a1/fp-source-contract.json'
MELEE={'792d5d2a340fd6e6':'Machete','e3b6aedd07fcb464':'Stun Lance','5f3ec9bda2bd8553':'Breaching Hammer','b0f1b354ba1d38d8':'One True Flag'}

def matrix(values):
 result=np.eye(4);result[:3,:3]=np.asarray(values[:9]).reshape(3,3).T;result[:3,3]=values[9:];return result

def angle(a,b):
 ar=a[:3,:3]/np.linalg.norm(a[:3,:3],axis=0);br=b[:3,:3]/np.linalg.norm(b[:3,:3],axis=0)
 return math.degrees(math.acos(float(np.clip((np.sum(ar*br)-1)/2,-1,1))))

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fp-log',type=Path,default=FP_LOG);parser.add_argument('--tp-log',type=Path,default=TP_LOG);parser.add_argument('--out',type=Path,default=OUT);parser.add_argument('--contract',type=Path,default=CONTRACT)
 args=parser.parse_args(argv);args.out.mkdir(parents=True,exist_ok=True)
 contract=json.loads(args.contract.read_text(encoding='utf-8'));parents={n['index']:n['parent']for n in contract['avatar']['nativeGraph']}
 events=collections.Counter();reasons=collections.Counter();captures=[];visibility=[];source_stats=None;complete=None;first=last=None;source_version=None;fk=[];maximum_scale_deviation=0
 for stamp,number,r in records(args.fp_log):
  first=first or stamp;last=stamp;e=r.get('event');events[e]+=1
  if e=='loaded':source_version=r.get('testVersion')
  if e=='fp_source_unavailable':reasons[r['reason']]+=1
  if e=='fp_source_complete':source_stats=r['stats']
  if e=='complete':complete=r
  if e and e.startswith('fp_arm_'):visibility.append(dict(stamp=stamp,line=number,**r))
  if e=='fp_native_and_melee_capture':
   captures.append(dict(stamp=stamp,line=number,**r));native={n['index']:n for n in r['nativePoses']}
   for i,n in native.items():
    world=matrix(n['world']);maximum_scale_deviation=max(maximum_scale_deviation,float(np.max(np.abs(np.linalg.norm(world[:3,:3],axis=0)-1))))
    if parents[i] in native:
     error=float(np.max(np.abs(matrix(native[parents[i]]['world'])@matrix(n['localPose'])-world)));fk.append(dict(error=error,name=n['name'],frame=r['frame'],stamp=stamp))
 if source_version!='1.0.18-test.fp-source.1':raise ValueError('This evidence analyzer targets the A1 protocol; do not reuse its conclusions for an A2/unknown log')
 capture_melee=[]
 for capture in captures:
  native={n['name']:matrix(n['world'])for n in capture['nativePoses']}
  for item in capture['meleeItems']:
   if item['resource'] not in MELEE:continue
   root=next((n for n in item['roots']if n['index']==0),item['roots'][0]);world=matrix(root['world']);valid=[]
   for node in item['roots']:
    if not item['fpWorld'] or node.get('parent') not in (None,0):continue
    for name in ('attach_hand_r','weapon_aim'):
     expected=native[name]@matrix(node['localPose']);distance=float(np.linalg.norm(matrix(node['world'])[:3,3]-expected[:3,3]));degrees=angle(matrix(node['world']),expected)
     if distance<=.012 and degrees<=3:valid.append(dict(index=node['index'],candidate=name,distance=distance,degrees=degrees,hypothesisOnly=True))
   capture_melee.append(dict(stamp=capture['stamp'],frame=capture['frame'],resource=item['resource'],fpWorld=item['fpWorld'],rootPosition=world[:3,3].tolist(),nativeHandDistanceMetres=float(np.linalg.norm(world[:3,3]-native['r_hand'][:3,3]))if item['fpWorld'] else None,nativeMountDistanceMetres=float(np.linalg.norm(world[:3,3]-native['attach_hand_r'][:3,3]))if item['fpWorld']else None,currentLocalMatchedCandidates=valid,usableHeldContactCalibration=bool(valid),directParentUnitObserved=False))
 summaries={}
 for rid,name in MELEE.items():
  rows=[r for r in capture_melee if r['resource']==rid];distances=[r['nativeHandDistanceMetres']for r in rows if r['nativeHandDistanceMetres']is not None]
  positions=np.asarray([r['rootPosition']for r in rows]);summaries[rid]=dict(designation=name,fpObjectCaptureSamples=len(rows),validHeldContactCalibrationSamples=sum(r['usableHeldContactCalibration']for r in rows),rootMotionMetres=float(np.max(np.linalg.norm(positions-positions[0],axis=1)))if len(rows)else None,nativeHandDistanceRangeMetres=[min(distances),max(distances)]if distances else None)
 measured=[];input_logs=[]
 for path in (args.tp_log,args.fp_log):
  right={};left={};contacts={};ev=collections.Counter()
  for stamp,number,r in records(path):
   ev[r.get('event')]+=1
   if r.get('event')=='right_applied'and r.get('resource')in MELEE:right[r['frame']]=dict(stamp=stamp,line=number,**r)
   if r.get('event')=='left_applied'and r.get('weaponResource')in MELEE:left[r['frame']]=dict(stamp=stamp,line=number,**r)
   if r.get('event')=='test_final_contacts':contacts[r['frame']]=r
  for frame,r in right.items():
   rid=r['resource'];c=contacts.get(frame,{}).get('results',{});measured.append(dict(sourceLog=str(path.resolve()),stamp=r['stamp'],frame=frame,resource=rid,designation=MELEE[rid],rightReachResidualMetres=r.get('reachResidual'),rightFinalContactResidualMetres=c.get('right',{}).get('finalResidual'),leftReachResidualMetres=left.get(frame,{}).get('reachResidual'),leftFinalContactResidualMetres=c.get('left',{}).get('finalResidual'),nativeMountShift=c.get('right',{}).get('nativeMountShift'),anchor='skeleton_knuckle_proxy_not_mesh_surface',fullContactResults=c))
  input_logs.append(dict(path=str(path.resolve()),sha256=digest(path),bytes=path.stat().st_size,events=dict(ev)))
 precision_path=args.out/'live-native-fk-replay.json';precision=json.loads(precision_path.read_text(encoding='utf-8'))if precision_path.exists()else[]
 native_fixture=json.loads((ROOT/'HD2PhysBoneCompat/test/fixtures/first_person_source_live_a1_20261109_135025.json').read_text(encoding='utf-8'))
 precision_matches_source=native_fixture['sourceSha256']==digest(args.fp_log) and [r['frame']for r in precision]==[r['frame']for r in captures]
 if not precision_matches_source:precision=[]
 source_frames=source_stats['writes']//len(contract['avatar']['outputs'])if source_stats else None
 report=dict(status='ANALYZED_NOT_LIVE_ROOT_CAUSE_OR_GPU_PROOF',sourceLogs=input_logs,firstStamp=first,lastStamp=last,events=dict(events),sourceFailureReasons=dict(reasons),fpCounts=dict(collections.Counter(str(r['fpCount'])for r in captures)),nativeFpCaptureSamples=len(captures),sourceStats=source_stats,fpSourceOutputFrames=source_frames,receiverMatrixDiagnosticsLogged=events.get('fp_source_receiver',0),sourceFailuresShare=source_stats['failures']/source_frames if source_stats and source_frames else None,showPermissionEventCount=events.get('fp_arm_source_receiver_visible',0),actualMeshVisibilityCountsRecorded=False,gameVisualVerification=False,complete=complete,maxNativeFpMatrixScaleDeviation=maximum_scale_deviation,nativeParentLocalFk=dict(samples=len(fk),maximumError=max((r['error']for r in fk),default=0),worst=sorted(fk,key=lambda r:r['error'],reverse=True)[:5]),float32Replay=dict(sourceFixtureHashVerified=precision_matches_source,samples=len(precision),maximumExpectedError=max((r['max32']for r in precision),default=None),sourceWorldThreshold=.0002,thresholdFailures=sum(r['max32']>=.0002 for r in precision),actualSourceMatricesNotRecorded=True),meleeObjectSummaries=summaries,meleeFpCaptures=capture_melee,meleeTpFinalContacts=measured,notes=[
  f'FP97 was installed and the exact e698 right model was matched on {source_stats["receiverMatches"]} frames; this is CPU-node evidence, not visible mesh/GPU acceptance.',
  'A1 shared per-module log timing: its forced 1Hz native capture starves all successful fp_source_receiver matrix diagnostics. Visibility events restored a saved mesh mask without recording visible mesh counts.',
  f'{source_stats["failures"]} fp_source_world_readback assertions remove per-frame display permission. Captured native matrices and float32 FK replay do not justify loosening the threshold.',
  'The old-cache native-producer schedule reproduces A1 offline and the pre-sampling cache flush resolves that fixture. The A1 live file lacks actual failed Source/native-before-after matrices, so this schedule remains a tested hypothesis, not a directly observed engine root cause.',
  'The 10 FP flag roots are stationary and 2.7-3.2 metres from the selected FP hand; none satisfies the current-local native-mount hypothesis. This may be stale cache or a different/dropped owner: do not calibrate to it.',
  'Melee TP final knuckle-proxy errors confirm unreached contacts with native mount shift zero. Only flag and hammer have measured held-contact samples here; machete/lance must not be claimed calibrated.',
  'Reload-left remains deferred. No railgun/muzzle policy, model, animation, native physics or active deployment changed.'
 ])
 (args.out/'fp-a1-live-and-melee-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(status=report['status'],nativeFpSamples=len(captures),failures=source_stats['failures'],receiverMatches=source_stats['receiverMatches'],receiverMatrixDiagnosticsLogged=report['receiverMatrixDiagnosticsLogged'],float32Replay=report['float32Replay'],meleeSummaries=summaries,meleeMeasured=[{k:v for k,v in r.items()if k!='fullContactResults'}for r in measured]),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
