"""Read-only fast temporal scan of the latest single pack vs the user's normal pack."""
import collections,hashlib,json,math,struct,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import decompress_rotation,decompress_position
OUT=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
NORMAL=ROOT.parent/'output/9ba626afa44a3aa3.patch_0'
CURRENT=OUT/'test-library/[单骨架动画](test07)/9ba626afa44a3aa3.patch_0'
# Same 90-channel Bones layout is verified independently from game/unit_anim/base_anim.
ARM={8:'r_clavicle',9:'l_clavicle',11:'l_shoulder',12:'r_shoulder',13:'r_elbow',14:'r_hand',15:'l_elbow',17:'l_hand',35:'r_hand_twist',45:'r_shoulder_twist',61:'l_shoulder_twist',75:'l_hand_twist'}
def records(path):
 with path.open('rb') as f:
  h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+32*nt);return [struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
def angle(a,b):
 d=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
 return math.degrees(2*math.acos(min(1,abs(sum(x*y for x,y in zip(a,b)))/d))) if d>1e-12 else None
def scan(raw):
 unk,count,duration,size,h1,h2=struct.unpack_from('<IIfIII',raw,0);cursor=26+8*(h1+h2)
 nb=math.ceil(count*3/8);nb+=nb%2;flags=raw[cursor:cursor+nb];cursor+=nb;quats={};zero_scales=0;frame0={}
 for i in range(count):
  compressed=lambda k:(flags[(i*3+k)//8]>>((i*3+k)%8))&1
  cp,cq,cs=[compressed(k) for k in range(3)]
  p=decompress_position(struct.unpack_from('<3H',raw,cursor)) if cp else struct.unpack_from('<3f',raw,cursor);cursor+=6 if cp else 12
  q=decompress_rotation(struct.unpack_from('<I',raw,cursor)[0]) if cq else struct.unpack_from('<4f',raw,cursor);cursor+=4 if cq else 16
  scale=decompress_position(struct.unpack_from('<3H',raw,cursor)) if cs else struct.unpack_from('<3f',raw,cursor);cursor+=6 if cs else 12
  zero_scales+=scale[0]==0
  if i in ARM:quats[i]=(0.,q);frame0[i]=dict(p=p,q=q,scale=scale)
 cursor+=4*h1;total=rotations=events=nonmonotonic=duplicates=0;max_time=0.;steps=collections.Counter();stats={i:dict(keys=0,maxStepDegrees=0.,stepsOver30=0,stepsOver60=0,zeroTimeChanges=0,maxGapMs=0.,worst=None) for i in ARM}
 while cursor<len(raw):
  typ=raw[cursor+1]>>6
  if typ:
   b0,b1,b2,b3=raw[cursor:cursor+4];bone=(b0>>4)|((b1&63)<<4);tm=float(((b0&15)<<16)|(b3<<8)|b2);data=cursor+4;subtype=0
   length=8 if typ==3 else 10;rotation=typ==3
  else:
   subtype=struct.unpack_from('<H',raw,cursor)[0]
   if subtype==3:break
   if subtype not in (2,4,5,6):raise ValueError(('unknown entry',cursor,subtype))
   bone,tm=struct.unpack_from('<If',raw,cursor+2);tm*=1000.;data=cursor+10
   length={2:10,4:22,5:26,6:22}[subtype];rotation=subtype==5
   events+=subtype==2
  total+=1;max_time=max(max_time,tm)
  if rotation and bone in ARM:
   q=decompress_rotation(struct.unpack_from('<I',raw,data)[0]) if typ else struct.unpack_from('<4f',raw,data)
   prev_t,prev_q=quats[bone];dt=tm-prev_t;delta=angle(prev_q,q);st=stats[bone];st['keys']+=1;rotations+=1
   if dt<-.001:nonmonotonic+=1
   if abs(dt)<.001:duplicates+=1
   elif dt>0:steps[round(dt,3)]+=1;st['maxGapMs']=max(st['maxGapMs'],dt)
   if delta is not None:
    if delta>st['maxStepDegrees']:st['maxStepDegrees']=delta;st['worst']=dict(fromMs=prev_t,toMs=tm,degrees=delta,fromQ=prev_q,toQ=q)
    st['stepsOver30']+=delta>30 and dt>0;st['stepsOver60']+=delta>60 and dt>0;st['zeroTimeChanges']+=delta>.1 and abs(dt)<.001
   quats[bone]=(tm,q)
  cursor+=length
 return dict(channelCount=count,duration=duration,headerFlags=[unk,struct.unpack_from("<H",raw,24+8*(h1+h2))[0]],additive=zero_scales>0,entries=total,events=events,armRotations=rotations,
  maxEntryTimeMs=max_time,nonmonotonicArmKeys=nonmonotonic,duplicateArmTimes=duplicates,commonStepsMs=steps.most_common(5),
  arm={ARM[i]:st for i,st in stats.items()},frame0={ARM[i]:v for i,v in frame0.items()})
def main():
 nrows={r[0]:r for r in records(NORMAL)};crows={r[0]:r for r in records(CURRENT)}
 report=dict(normal=str(NORMAL),current=str(CURRENT),normalCount=len(nrows),currentCount=len(crows),idSetsEqual=set(nrows)==set(crows),
  changedResources=0,identicalResources=0,channelMismatches=0,durationMismatches=0,eventCountMismatches=0,flagMismatches=0,maxDurationDifferenceSeconds=0,
  durationWorst=[],jumpCandidates=[],curveSamples=[],gameOrLibraryModified=False)
 globalstats={'normal':collections.Counter(),'current':collections.Counter()};countersteps={'normal':collections.Counter(),'current':collections.Counter()};start=time.time()
 with NORMAL.open('rb') as nf,CURRENT.open('rb') as cf:
  for i,fid in enumerate(sorted(nrows.keys()&crows.keys())):
   nr,cr=nrows[fid],crows[fid];nf.seek(nr[2]);cf.seek(cr[2]);a=nf.read(nr[7]);b=cf.read(cr[7]);same=a==b
   report['identicalResources']+=same;report['changedResources']+=not same
   ns,cs=scan(a),scan(b);report['channelMismatches']+=ns['channelCount']!=cs['channelCount'];dd=abs(ns['duration']-cs['duration']);report['durationMismatches']+=dd>1e-4;report['maxDurationDifferenceSeconds']=max(report['maxDurationDifferenceSeconds'],dd)
   report['eventCountMismatches']+=ns['events']!=cs['events'];report['flagMismatches']+=ns['headerFlags']!=cs['headerFlags'] or ns['additive']!=cs['additive']
   if dd>.001:report['durationWorst'].append(dict(id=f'{fid:016x}',normal=ns['duration'],current=cs['duration'],delta=dd))
   for name,s in [('normal',ns),('current',cs)]:
    globalstats[name].update(dict(nonmonotonic=s['nonmonotonicArmKeys'],duplicateTimes=s['duplicateArmTimes'],stepsOver30=sum(x['stepsOver30'] for x in s['arm'].values()),stepsOver60=sum(x['stepsOver60'] for x in s['arm'].values()),zeroTimeChanges=sum(x['zeroTimeChanges'] for x in s['arm'].values())))
    for dt,number in s['commonStepsMs']:countersteps[name][dt]+=number
   for bone,st in cs['arm'].items():
    old=ns['arm'][bone];increase=st['maxStepDegrees']-old['maxStepDegrees']
    if st['maxStepDegrees']>25 and increase>10:
     report['jumpCandidates'].append(dict(id=f'{fid:016x}',bone=bone,additive=cs['additive'],increase=increase,normal=old['maxStepDegrees'],current=st['maxStepDegrees'],worst=st['worst']))
   if i%100==0 or fid in [0x0004fd6ec81ff21c,0x258c6e03a38bbeb2,0xd999a338adf26fed]:report['curveSamples'].append(dict(id=f'{fid:016x}',normal=ns,current=cs))
   if (i+1)%250==0:
    print('scan',i+1,'elapsed',round(time.time()-start,1),flush=True)
  report['globalTemporalCounts']={k:dict(v) for k,v in globalstats.items()};report['commonKeyIntervals']={k:v.most_common(12) for k,v in countersteps.items()}
  report['jumpCandidates'].sort(key=lambda x:x['increase'],reverse=True);report['jumpCandidateCount']=len(report['jumpCandidates']);report['jumpCandidateUniqueClips']=len({c['id'] for c in report['jumpCandidates']});report['jumpCandidateBones']=dict(collections.Counter(c['bone'] for c in report['jumpCandidates']));report['jumpCandidates']=report['jumpCandidates'][:60]
  report['durationWorst'].sort(key=lambda x:x['delta'],reverse=True);report['durationWorst']=report['durationWorst'][:30]
  report['elapsedSeconds']=time.time()-start
  for path,key in [(NORMAL,'normalSha256'),(CURRENT,'currentSha256')]:
   with path.open('rb') as digest_file:report[key]=hashlib.file_digest(digest_file,'sha256').hexdigest()
 (OUT/'单骨架-正常包对照-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k not in ['curveSamples','jumpCandidates','durationWorst']},ensure_ascii=False),flush=True)
 print('TOP JUMPS',json.dumps(report['jumpCandidates'][:8],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
