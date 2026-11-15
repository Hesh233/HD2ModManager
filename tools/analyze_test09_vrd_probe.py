"""Summarize bounded test09 VRD probe records without touching game/manager state."""
from pathlib import Path
import argparse,collections,json,re,sys
ROOT=Path(__file__).resolve().parents[1]

def analyze(text):
 rows=collections.defaultdict(list);bodies=[]
 for line in text.splitlines():
  if '[test09-vrdrow]' in line:
   v=dict(re.findall(r'(\w+)=([^\s]+)',line));rows[v['bone']].append(v)
  elif '[test09-vrdprobe]' in line and 'phase=after_physics' in line:
   bodies.append(dict(re.findall(r'(\w+)=([^\s]+)',line)))
 result={}
 for name,entries in rows.items():
  def nums(k):return [float(v[k]) for v in entries if k in v and float(v[k])>=0]
  def maximum(k):return max(nums(k),default=None)
  result[name]=dict(samples=len(entries),controls=sorted({e.get('ctrl','?') for e in entries}),
   coveredSamples=sum(int(e['matches'])>0 for e in entries),uncoveredSamples=sum(int(e['matches'])==0 for e in entries),
   maxRuleAngleDeg=maximum('ruleDeg'),maxSmoothedAngleDeg=maximum('smoothDeg'),
   maxAfterLocalVsWriteDeg=maximum('localVsWriteDeg'),maxPreLocalVsPreviousWriteDeg=maximum('preVsLastWriteDeg'),
   maxWorldRelativeVsLocalDeg=maximum('worldVsLocalDeg'),maxInferredPreRotationDeg=maximum('inferredPreDeg'))
 tilts=[float(v['leanUp']) for v in bodies if float(v.get('leanUp',-1))>=0]
 changes=[float(x) for v in bodies for x in v.get('bodyPhysicsDeltaDeg','').split(',') if x and float(x)>=0]
 hints=[]
 if not rows:hints.append('No VRD probe records: confirm probe version/target model/recording window. Load log alone cannot establish VRD outputs.')
 for name,v in result.items():
  if v['coveredSamples']==0:hints.append(name+': no rule coverage at sampled poses; inspect control delta and canonical frame before tuning parameters.')
  elif (v['maxRuleAngleDeg'] or 0)<1:hints.append(name+': covered but near-neutral output; sampled pose may be in authored neutral zone.')
  if (v['maxAfterLocalVsWriteDeg'] or 0)>.5:hints.append(name+': immediate local pose differs from cached write; verify setter/readback or write failure.')
  if (v['maxPreLocalVsPreviousWriteDeg'] or 0)>.5:hints.append(name+': pose before physics differs from preceding cached write; possible later animation reset/overwrite, not proven by this metric alone.')
  if (v['maxWorldRelativeVsLocalDeg'] or 0)>.5:hints.append(name+': world parent-relative rotation and local rotation differ; inspect pre-bind transform/setter frame semantics.')
 return dict(status='PROBE_RECORDS_SUMMARIZED' if rows else 'NO_PROBE_RECORDS',samples=len(bodies),drivers=result,
  body=dict(leanUpRangeDeg=[min(tilts),max(tilts)] if tilts else None,maxImmediatePhysicsRotationChangeDeg=max(changes,default=None)),
  hints=hints,scope='low-frequency observations immediately before/after this physics callback, NOT full GPU trajectory or proof of all later render callbacks')

def main():
 p=argparse.ArgumentParser();p.add_argument('--logs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
 target=args.out.resolve();assert target.is_relative_to(ROOT),'evidence output stays in workspace'
 j=analyze(args.logs.read_text('utf-8-sig'));j['sourceLog']=str(args.logs.resolve());target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(j,ensure_ascii=False,indent=2),'utf8');print(j['status'],j['samples'],'samples',len(j['drivers']),'drivers')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
