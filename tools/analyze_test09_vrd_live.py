"""Saved live probe1 analysis and actual GPU consumers. Evidence only."""
from pathlib import Path
import collections,copy,hashlib,json,math,re,struct,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
import numpy as np
from lupa.lua51 import LuaRuntime
import audit_test06_vrd_skirt as a
from build_test09_axis_test import sha,save
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_rotate
BASE=ROOT/'outputs/test09-chr654-vrd-followup-20261110'
OUT=BASE/'live-probe1-2230';AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'


def main():
 text=(OUT/'hd2physbone_compact.log.snapshot').read_text('utf-8-sig');analysis=json.loads((OUT/'probe-analysis.json').read_text('utf8'))
 activation=json.loads((OUT/'activation-state.json').read_text('utf8'));physics=[x for x in activation['files'] if x['sidecarKind']=='base' and 'VRD与前倾取证-probe1' in x['sourcePath']]
 assert len(physics)==1;physics_source=Path(physics[0]['sourcePath'])
 rows=a.patch_rows(physics_source);lua=[a.payload(physics_source,r)[8:] for r in rows if r[1]==0xa14e8dfa2cd117e2]
 assert len(lua)==1 and lua[0]==(BASE/'hd2physbone-test09.lua').read_bytes()
 tags={v for v in re.findall(r'\[test09-vrdprobe\].*? tag=([^ ]+)',text)};assert tags=={'#ID[8a026ed4c1830deb]'}
 matrices=collections.defaultdict(dict)
 for line in text.splitlines():
  if '[test09-vrdrow]' in line:
   v=dict(re.findall(r'(\w+)=([^\s]+)',line));matrices[int(v['sample'])][v['bone']]=v
 profile=json.loads((AXIS/'test09-source-frame-profile.json').read_text('utf8'));vm=LuaRuntime(unpack_returned_tuples=True);M=vm.execute((AXIS/'physbone_compat-test09.lua').read_bytes())
 byname={b['name']:b for b in profile['driverBones']}
 rule_checks=[]
 for sample,entries in matrices.items():
  for name,v in entries.items():
   delta=[float(x) for x in v['delta'].split(',')];n=np.linalg.norm(delta);delta=(np.array(delta)/n).tolist()
   b=byname[name];q=M.quatinterp(a.table(vm,delta),a.table(vm,dict(b,fadeOutside=True)))
   angle=a.angle(q) if q is not None else -1;difference=abs(angle-float(v['ruleDeg']))
   # Logs round control quaternion to 5 decimals; not full-frame capture.
   assert difference<.025,(sample,name,difference)
   rule_checks.append(dict(sample=sample,bone=name,replayedRuleDeg=angle,loggedRuleDeg=float(v['ruleDeg']),roundingDifferenceDeg=difference))
 constant_positions=[]
 for b in profile['driverBones']:
  p=np.array([r['position'] for r in b['rules']]);variation=float(np.max(np.linalg.norm(p-p[0],axis=1)))
  assert variation==0;constant_positions.append(dict(bone=b['name'],rulePositionVariationM=variation,missingDynamicTranslationNotSupported=True))
 model=INSTALL/'test-library/[单骨架模型]test09_chr654/Overwrite/9ba626afa44a3aa3.patch_0';units=a.units(model)
 # The real active Hip resource is the SECOND Hip replacement, not the first
 # exported template selected in the earlier generic GPU extraction.
 hip=json.loads((OUT/'gpu-active-hips-lod0.json').read_text('utf8'));helmet=json.loads((OUT/'gpu-sampled-helmet-lod0.json').read_text('utf8'))
 assert hip['resource']=='34a40a5ae7a392ba' and helmet['resource']=='8a026ed4c1830deb'
 consumers=[]
 for doc in [hip,helmet]:
  u=units[doc['resource']];names={bone_name_hash(n):n for n in byname};mesh=doc['meshes'][0]
  counts={};f={bone_name_hash(v['name']) for v in profile['frames']}
  skirtv=0
  for v in mesh['vertices']:
   ws=[w for w in v['weights'] if w['group']==0]
   hits=set();is_skirt=False
   for w in ws:
    node=w['node'];seen=set()
    if u.name_hashes[node] in f:is_skirt=True
    while node is not None and node not in seen:
     seen.add(node);h=u.name_hashes[node]
     if h in names:hits.add(names[h])
     node=u.parents[node]
   if is_skirt:skirtv+=1
   for name in hits:counts[name]=counts.get(name,0)+1
  consumers.append(dict(resource=doc['resource'],kind='active-Hips' if doc is hip else 'sampled-Helmet',drawnVertices=len(mesh['vertices']),
   drawnTriangles=len(mesh['faces']),directSkirtWeightedVertices=skirtv,verticesWithHelperAncestor=counts))
 # Reconstruct bind and apply logged helmet helper rotations to the active Hip
 # OFFLINE to validate that the shipped Hip mesh has actual helper consumers.
 # This is NOT evidence that the unsampled live Hip had these same poses.
 u=units[hip['resource']];mesh=hip['meshes'][0];v=mesh['vertices'];pos=np.array([x['position'] for x in v]);weights=[[w for w in x['weights'] if w['group']==0] for x in v]
 inverse=np.array([np.array(m).reshape(4,4).T for m in mesh['inverseBindMatrices']]);W0=_calculate_world_transforms(u.transforms,u.parents)
 def mat(t):
  m=np.eye(4);m[:3,:3]=np.array([quat_rotate(t.rotation,a) for a in np.eye(3)]).T;m[:3,3]=t.position;return m
 def skin(local):
  w=_calculate_world_transforms(local,u.parents);mats=np.array([mat(t) for t in w]);out=np.zeros_like(pos)
  for i,(p,ws) in enumerate(zip(pos,weights)):
   h=np.r_[p,1]
   for t in ws:out[i]+=t['weight']*(mats[t['node']]@inverse[t['matrixIndex']]@h)[:3]
   total=sum(t['weight'] for t in ws)
   if total:out[i]/=total
  return out
 bind=skin(u.transforms);meshworld=np.array(hip['TransformInfo']['Matrices'][mesh['transformIndex']]['Values']).reshape(4,4).T
 expected=(meshworld@np.c_[pos,np.ones(len(pos))].T).T[:,:3];binderr=float(np.max(np.linalg.norm(bind-expected,axis=1)));assert binderr<1e-5
 # Choose sample with all six driver rows and strongest logged front helper.
 sample=max([s for s,e in matrices.items() if len(e)==6],key=lambda s:sum(float(matrices[s][n]['smoothDeg']) for n in ['skirt_front_helper1','skirt_front_helper2']))
 local=copy.deepcopy(u.transforms)
 for name,values in matrices[sample].items():
  node=u.name_hashes.index(bone_name_hash(name));q=[float(x) for x in values['helperLocal'].split(',')];q=(np.array(q)/np.linalg.norm(q)).tolist();local[node].rotation=q
 moved=skin(local);d=np.linalg.norm(moved-bind,axis=1);helper_nodes={u.name_hashes.index(bone_name_hash(n)) for n in byname}
 # Only observed nonzero rotations change model copy; no spring/animation replay.
 demonstration=dict(status='OFFLINE_CONSUMER_DEMONSTRATION_NOT_LIVE_HIPS_REPLAY',borrowedHelmetSample=sample,bindSkinMaxErrorM=binderr,
  maxVertexDisplacementCm=float(d.max()*100),verticesDisplacedAbove1mm=int(np.sum(d>.001)),
  source='Saved logged helmet helper locals applied to an isolated active-Hips bind copy; no live Hip or GPU poses were recorded')
 save(OUT/'deep-analysis.json',dict(status='SAMPLED_VRD_ROTATION_ACTIVE_VISUAL_HIPS_NOT_YET_OBSERVED',runtimeVersion='2.3.3-test09-vrdprobe1',
  appliedUtc=activation['appliedUtc'],startedShanghai='2026-11-10 22:29:22',deployedLuaExact=True,
  sampledTag=next(iter(tags)),sampledUnitKind='Helmet',activeHipResource='34a40a5ae7a392ba',activeHipWasNotSampled=True,
  samples=19,completeSixDriverSamples=18,incompleteSample=19,incompleteCause='compact 90s/128KiB log cap cut after sample19 row4',
  driverSummary=analysis['drivers'],bodySummary=analysis['body'],ruleReplayChecks=len(rule_checks),maxRuleAngleRoundingErrorDeg=max(v['roundingDifferenceDeg'] for v in rule_checks),
  canonicalSetterFrameMismatchNotObserved=True,overwriteAtSampleBoundariesNotObserved=True,
  sourceRulePositionFacts=constant_positions,gpuConsumers=consumers,offlineHipConsumerDemonstration=demonstration,
  frameEndGpuVisibilityNotObserved=True,bodyLeanCauseNotProven=True,gameVisualAccepted=False,productionOrGameFilesModified=False))
 save(OUT/'rule-replay.json',rule_checks)
 print('Deep analysis',len(rule_checks),'rule checks','consumers',consumers,'demo',demonstration)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
