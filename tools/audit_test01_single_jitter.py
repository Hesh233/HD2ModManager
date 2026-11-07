from pathlib import Path
import copy,json,sys,time
ROOT=Path('anim_batch_mod/HD2ModManager').resolve();sys.path.insert(0,str(ROOT/'tools'))
import audit_single_against_normal as fast
OUT=ROOT/'outputs/test01-single-jitter-20261107';OUT.mkdir(exist_ok=True)
CURRENT=fast.OUT/'test-library/[单骨架动画](test01)/9ba626afa44a3aa3.patch_0'
normal=fast.NORMAL;nr={r[0]:r for r in fast.records(normal)};cr={r[0]:r for r in fast.records(CURRENT)}
# Keep the exact currently loaded generation implementation for differential tests.
for name in ['processor.py','single_skeleton.py','batch.py','formats.py']:
 (OUT/(name+'.before-jitter.bak')).write_bytes((ROOT.parent/name).read_bytes())
report=dict(current=str(CURRENT),normal=str(normal),count=len(cr),shortIntervalJumps=[],allCandidates=[],additiveChanged=0,duplicateTimes=0,nonmonotonic=0)
with CURRENT.open('rb') as cf,normal.open('rb') as nf:
 for k,fid in enumerate(sorted(cr)):
  r=cr[fid];cf.seek(r[2]);raw=cf.read(r[7]);out=fast.scan(raw)
  r=nr[fid];nf.seek(r[2]);nraw=nf.read(r[7]);baseline=fast.scan(nraw)
  if out['additive'] and raw!=nraw:report['additiveChanged']+=1
  report['duplicateTimes']+=out['duplicateArmTimes'];report['nonmonotonic']+=out['nonmonotonicArmKeys']
  for bone,row in out['arm'].items():
   w=row['worst'];n=baseline['arm'][bone]
   if w and (row['maxStepDegrees']>20 or row['stepsOver60']):
    candidate=dict(id=f'{fid:016x}',bone=bone,additive=out['additive'],maxStep=row['maxStepDegrees'],baselineMaxStep=n['maxStepDegrees'],stepsOver30=row['stepsOver30'],stepsOver60=row['stepsOver60'],worst=w,duration=out['duration'])
    report['allCandidates'].append(candidate)
    if w['toMs']-w['fromMs']<2 and row['maxStepDegrees']>20:report['shortIntervalJumps'].append(candidate)
  if k%250==0:print(k,'short',len(report['shortIntervalJumps']),flush=True)
report['allCandidates'].sort(key=lambda r:r['maxStep'],reverse=True);report['shortIntervalJumps'].sort(key=lambda r:r['maxStep'],reverse=True)
(OUT/'scan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('TOTAL',report['count'],'short',len(report['shortIntervalJumps']),'additiveChanged',report['additiveChanged'],'duplicates',report['duplicateTimes'],'nonmonotonic',report['nonmonotonic'])
print(json.dumps(report['shortIntervalJumps'][:10],indent=2),flush=True)
