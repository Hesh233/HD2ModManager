"""Summarize exact-Hips probe2 logs, keep incomplete bundles and scope explicit."""
from pathlib import Path
import argparse,collections,json,math,re,sys
ROOT=Path(__file__).resolve().parents[1]

def analyze(text):
 bodies={};drivers=collections.defaultdict(dict);springs=collections.defaultdict(dict);selected=[]
 for line in text.splitlines():
  fields=dict(re.findall(r'(\w+)=([^\s]+)',line))
  if '[test09-hipsprobe]' in line and 'selected' in line:selected.append(fields)
  elif '[test09-hipsprobe]' in line and fields.get('phase')=='after_physics':bodies[int(fields['sample'])]=fields
  elif '[test09-hipdriver]' in line:drivers[fields['bone']][int(fields['sample'])]=fields
  elif '[test09-hipspring]' in line:springs[fields['bone']][int(fields['sample'])]=fields
 def maximum(items,key):
  values=[float(v[key]) for v in items if key in v and float(v[key])>=0]
  return max(values,default=None)
 def summary(rows,keys):
  return {n:dict(samples=len(v),**{k:maximum(list(v.values()),k) for k in keys}) for n,v in rows.items()}
 issues=[];complete=[];incomplete=[]
 for sample in bodies:
  driver_count=sum(sample in v for v in drivers.values());spring_count=sum(sample in v for v in springs.values())
  (complete if driver_count==2 and spring_count==7 else incomplete).append(dict(sample=sample,drivers=driver_count,springs=spring_count))
 if not selected:issues.append('No exact-Hips selection record; do not fall back to helmet observations.')
 if incomplete:issues.append('One or more truncated bundles; do not synthesize missing final poses.')
 for name,entries in drivers.items():
  v=list(entries.values())
  if maximum(v,'ruleDeg') is not None and maximum(v,'ruleDeg')<1:issues.append(name+': only neutral rule rotations sampled.')
  if (maximum(v,'afterVsWriteDeg') or 0)>.5:issues.append(name+': readback differs from driver cached write.')
  if (maximum(v,'beforeVsLastDeg') or 0)>.5:issues.append(name+': next sampled input differs from prior cached write; check later reset/sync.')
  if (maximum(v,'preBindDeg') or 0)>.5:issues.append(name+': nonidentity pre-bind setter frame; needs canonical frame comparison.')
 for name,entries in springs.items():
  v=list(entries.values())
  if (maximum(v,'afterVsWriteDeg') or 0)>.5:issues.append(name+': readback differs from spring cached write.')
  if (maximum(v,'beforeVsLastDeg') or 0)>.5:issues.append(name+': next sampled input differs from spring cached write.')
  if (maximum(v,'preBindDeg') or 0)>.5:issues.append(name+': nonidentity pre-bind; compare actual bone axes.')
 return dict(status='HIPS_PROBE_RECORDS_SUMMARIZED' if bodies else 'NO_HIPS_PROBE_RECORDS',selectionRecords=selected,completeBundles=complete,incompleteBundles=incomplete,
 drivers=summary(drivers,['ruleDeg','smoothDeg','afterVsWriteDeg','beforeVsLastDeg','preBindDeg']),
 springs=summary(springs,['swingDeg','afterVsWriteDeg','afterVsSolveDeg','beforeVsLastDeg','preBindDeg']),
 issues=issues,rawBundles=dict(bodies=bodies,drivers=drivers,springs=springs),
 scope='exact visible Hips, before/after this physics callback; not GPU frame-end or all subsequent callbacks; afterVsSolve includes legitimate dedup lag')

def main():
 p=argparse.ArgumentParser();p.add_argument('--logs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
 target=args.out.resolve();assert target.is_relative_to(ROOT)
 result=analyze(args.logs.read_text('utf-8-sig'));target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
 print(result['status'],len(result['completeBundles']),'complete bundles',len(result['incompleteBundles']),'incomplete')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
