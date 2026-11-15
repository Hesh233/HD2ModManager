"""Numerical diagnostics of saved actual-Hips probe2 rotations; no game writes."""
from pathlib import Path
import json,math,sys,hashlib,re
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
import numpy as np
from anim_batch_mod.math3d import quat_rotate,quat_multiply,quat_conjugate
import audit_test06_vrd_skirt as a
from build_test09_axis_test import sha,save
OUT=ROOT/'outputs/test09-chr654-hips-probe2-20261110/live-probe2-2300';AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110'

def arr(s):
 v=np.array([float(x) for x in s.split(',')]);assert np.isfinite(v).all()
 if len(v)==4:assert abs(np.linalg.norm(v)-1)<2e-5;v/=np.linalg.norm(v)
 return v.tolist()

def logq(q):
 v=np.array(q);v/=np.linalg.norm(v)
 if v[3]<0:v=-v
 n=np.linalg.norm(v[:3]);return v[:3]/n*2*math.atan2(n,v[3]) if n>1e-8 else np.zeros(3)

def av(a,b):
 return math.degrees(math.acos(np.clip(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)),-1,1)))

def main():
 audit=json.loads((OUT/'hips-analysis.json').read_text('utf8'));raw=audit['rawBundles'];frames={v['name']:v for v in json.loads((AXIS/'test09-source-frame-profile.json').read_text('utf8'))['frames']}
 assert len(audit['completeBundles'])==16 and not audit['incompleteBundles']
 activation=json.loads((OUT/'activation-state.json').read_text('utf8'));physics=[v for v in activation['files'] if v['sidecarKind']=='base' and '实际Hips裙骨取证-probe2' in v['sourcePath']];assert len(physics)==1
 p=Path(physics[0]['sourcePath']);payloads=[a.payload(p,r) for r in a.patch_rows(p) if r[1]==0xa14e8dfa2cd117e2]
 published=ROOT/'outputs/test09-chr654-hips-probe2-20261110/hd2physbone-test09.lua';assert len(payloads)==1 and payloads[0][8:]==published.read_bytes()
 source_model=[Path(v['sourcePath']) for v in activation['files'] if v['sidecarKind']=='base' and '[单骨架模型]test09_chr654' in v['sourcePath'] and 'Overwrite' in v['sourcePath']];assert len(source_model)==1
 units=a.units(source_model[0]);assert '34a40a5ae7a392ba' in units
 results=[];composition=[]
 for sample,b in raw['bodies'].items():
  assert b['resource']=='34a40a5ae7a392ba'
  hips=arr(b['hipsW']);gravity=quat_rotate(quat_conjugate(hips),[0,0,-1])
  for name,rows in raw['springs'].items():
   frame=frames[name];s=rows[sample];h=raw['drivers'][frame['parentName']][sample]
   helper=arr(h['localQ']);child=arr(s['localQ']);net=arr(s['hipRelQ']);helperworld=arr(h['worldQ']);childworld=arr(s['worldQ'])
   local_comp=a.angle(quat_multiply(helper,child),net)
   world_comp=a.angle(quat_multiply(helperworld,child),childworld)
   assert max(local_comp,world_comp)<.001
   composition.append(max(local_comp,world_comp))
   drive=logq(helper);n=np.linalg.norm(drive);axis=drive/n if n>1e-5 else np.zeros(3)
   forward=frame['forward'];solver=arr(s['solverDirW']);visible=quat_rotate(childworld,forward)
   results.append(dict(sample=int(sample),bone=name,parent=frame['parentName'],helperAngleDeg=math.degrees(n),
    childRotationProjectedOnDriverAxisDeg=float(np.degrees(np.dot(logq(child),axis))),
    netRotationProjectedOnDriverAxisDeg=float(np.degrees(np.dot(logq(net),axis))),
    driverGoalVsWorldDownDeg=av(quat_rotate(helper,forward),gravity),actualDirectionVsWorldDownDeg=av(quat_rotate(net,forward),gravity),
    actualDirectionVsDriverGoalDeg=av(quat_rotate(net,forward),quat_rotate(helper,forward)),
    solverVsObservedSourceAxisDeg=av(solver,visible),compositionErrorDeg=max(local_comp,world_comp)))
 active=[r for r in results if r['helperAngleDeg']>15];opposed=[r for r in active if r['childRotationProjectedOnDriverAxisDeg']<0]
 body_changes=[float(v) for b in raw['bodies'].values() for v in b['bodyDeltaDeg'].split(',')]
 summary=dict(status='LIVE_HIPS_COUNTER_ROTATION_CONFIRMED_NOT_GAME_FIX',runtimeVersion='2.3.4-test09-hipsprobe2',
 sourceModel=str(source_model[0]),deployedLuaExact=True,actualResource='34a40a5ae7a392ba',completeSamples=16,helperRecords=32,springRecords=112,
 helperMaximumAnglesDeg={n:float(v['smoothDeg']) for n,v in audit['drivers'].items()},
 maxObservedHelperChildCompositionErrorDeg=max(composition),activeDriverBoneSamples=len(active),opposingSpringBoneSamples=len(opposed),
 largestCounterExample=next(r for r in results if r['sample']==11 and r['bone']=='skirt_a_c'),
 helperWriteVsReadMaximumDeg=max(v['afterVsWriteDeg'] for v in audit['drivers'].values()),
 springWriteVsReadMaximumDeg=max(v['afterVsWriteDeg'] for v in audit['springs'].values()),
 observedOverwriteVsLastMaximumDeg=max(v['beforeVsLastDeg'] for v in list(audit['drivers'].values())+list(audit['springs'].values())),
 maxInferredPreBindDeg=max(v['preBindDeg'] for v in list(audit['drivers'].values())+list(audit['springs'].values())),
 bodyLeanRangeDeg=[min(float(b['leanUp']) for b in raw['bodies'].values()),max(float(b['leanUp']) for b in raw['bodies'].values())],
 bodyImmediatePhysicsChangeMaxDeg=max(body_changes),
 caveats=['Signed angles are quaternion rotation-vector projections on the helper driver axis, not scalar subtraction of arbitrary Euler angles.',
 'Solver and observed source-axis directions can differ during motion due to one-frame driver anchor lag and write dedup; this is not itself a bind conversion defect.',
 'Observations are physics callback boundaries, not GPU frame end. No inter-frame trajectory or collision penetration depth was captured.',
 'No automatic action labels were captured: the logged pose samples must not be mislabeled as a specific running/idle frame.'])
 save(OUT/'counter-rotation-details.json',results);save(OUT/'diagnosis-summary.json',summary)
 print(json.dumps({k:v for k,v in summary.items() if k not in ['caveats','sourceModel']},ensure_ascii=False,indent=2))

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
