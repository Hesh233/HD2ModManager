"""Fast playback timing audit versus actual game resources, not processed baseline."""
import json,math,struct,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
import lz4;sys.modules['utils.lz4_311']=lz4
from anim_batch_mod.archive import ResourceIndex,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from audit_single_against_normal import records,OUT as INSTALL
OUT=ROOT/'outputs/test01-single-jitter-20261107';PACK=INSTALL/'test-library/[单骨架动画](test01)/9ba626afa44a3aa3.patch_0'
def timeline(raw):
 flags,n,duration,size,h,h2=struct.unpack_from('<IIfIII',raw);cursor=26+8*(h+h2);nb=math.ceil(3*n/8);nb+=nb%2;bits=raw[cursor:cursor+nb];cursor+=nb;additive=False
 for i in range(n):
  cp,cq,cs=[bool((bits[(i*3+j)//8]>>((i*3+j)%8))&1) for j in range(3)]
  cursor+=6 if cp else 12;cursor+=4 if cq else 16
  if cs:additive=additive or struct.unpack_from('<H',raw,cursor)[0]==32767
  else:additive=additive or struct.unpack_from('<f',raw,cursor)[0]==0
  cursor+=6 if cs else 12
 cursor+=h*4;times=[];scale=[];events=[];bybone={};order=[];end=None
 while True:
  typ=raw[cursor+1]>>6
  if typ:
   a,b,c,d=raw[cursor:cursor+4];bone=(a>>4)|((b&63)<<4);tm=float(((a&15)<<16)|(d<<8)|c);length=8 if typ==3 else 10;sub=0
  else:
   sub=struct.unpack_from('<H',raw,cursor)[0]
   if sub==3:end=cursor+2;break
   bone,tm=struct.unpack_from('<If',raw,cursor+2);tm*=1000;length={2:10,4:22,5:26,6:22}[sub]
  if typ in [2,3] or sub in [4,5]:times.append(tm);bybone.setdefault((bone,typ==3 or sub==5),[]).append(tm)
  elif typ==1 or sub==6:scale.append(tm)
  elif sub==2:events.append(tm)
  cursor+=length
 unique=sorted(set(times));gaps=[y-x for x,y in zip(unique,unique[1:])]
 declared=duration*1000
 footer=struct.unpack_from('<I',raw,end)[0] if end+4<=len(raw) else None
 mirror_start=end+4;mirror_valid=mirror_start+16<=len(raw) and struct.unpack_from('<II',raw,mirror_start)==(flags,n)
 mirror_equal=mirror_valid and raw[:12]==raw[mirror_start:mirror_start+12] and raw[16:end]==raw[mirror_start+16:mirror_start+end]
 return dict(durationMs=declared,lastTransform=max(times,default=declared),lastScale=max(scale,default=0),lastEvent=max(events,default=0),keys=len(times),uniqueTimes=len(unique),minGap=min(gaps,default=0),shortGaps=sum(g<1 for g in gaps),beyondDuration=sum(t>declared+.001 for t in times),tailExcess=max(times,default=declared)-declared,mirrorValid=mirror_valid,mirrorEqual=mirror_equal,footer=footer,firstBlockEnd=end,rawLength=len(raw),additive=additive)
def main():
 idx=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));db=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';idx.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
 report=dict(samples=[],changedDuration=0,shortenedOver10Ms=0,currentTailBeyond1Ms=0,sourceTailBeyond1Ms=0,sourceMirrorDifferent=0)
 with PACK.open('rb') as f:
  for i,r in enumerate(records(PACK)):
   f.seek(r[2]);out=timeline(f.read(r[7]));_,e=idx.resolve(r[0],ANIMATION_TYPE_ID);src=timeline(e.toc_data)
   row=dict(id=f'{r[0]:016x}',source=src,current=out,durationDelta=out['durationMs']-src['durationMs'])
   report['samples'].append(row);report['changedDuration']+=abs(row['durationDelta'])>.001;report['shortenedOver10Ms']+=row['durationDelta']< -10;report['currentTailBeyond1Ms']+=out['tailExcess']>1;report['sourceTailBeyond1Ms']+=src['tailExcess']>1;report['sourceMirrorDifferent']+=src['mirrorValid'] and not src['mirrorEqual']
   if i%250==0:print(i,'duration10',report['shortenedOver10Ms'],'tail',report['currentTailBeyond1Ms'],flush=True)
 idx.close();report['samples'].sort(key=lambda r:abs(r['durationDelta']),reverse=True)
 (OUT/'timing.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='samples'},indent=2));print(json.dumps(report['samples'][:8],indent=2))

if __name__=='__main__':main()
