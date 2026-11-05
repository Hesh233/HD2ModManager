"""Create an isolated repair workspace and inspect Source procedure records."""
import json, shutil, struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/native-v11-20261104'
P=W/'project'
BASE=ROOT/'outputs/native-manual-20261103'
W.mkdir(exist_ok=True)
if not P.exists():
    shutil.copytree(BASE/'project',P,ignore=shutil.ignore_patterns('animations','reports','source-code','__pycache__'))
before=W/'source-before';before.mkdir(exist_ok=True)
for path in [ROOT.parent/'processor.py',ROOT.parent/'native_skeleton.py',ROOT/'HD2PhysBoneCompat/src/native_attachments.lua']:
    if not (before/path.name).exists():shutil.copy2(path,before/path.name)
data=(ROOT/'testVPK/test01.vpk').read_bytes()
magic,ver,size=struct.unpack_from('<III',data);assert magic==0x55aa1234
start=12 if ver==1 else 28
pos=start
def string():
    global pos
    end=data.index(0,pos);s=data[pos:end].decode();pos=end+1;return s
entries=[];weights=[]
while (ext:=string()):
    while (folder:=string()):
        while (name:=string()):
            crc,preload,archive,off,length,term=struct.unpack_from('<IHHIIH',data,pos);pos+=18
            pre=data[pos:pos+preload];pos+=preload
            if ext in ('mdl','vvd'):
                assert archive==0x7fff
                raw=pre+data[start+size+off:start+size+off+length]
                if ext=='vvd':
                    count=struct.unpack_from('<I',raw,16)[0];offset=struct.unpack_from('<I',raw,56)[0]
                    histogram={}
                    for i in range(count):
                        at=offset+48*i;values=struct.unpack_from('<3f',raw,at)
                        for j,w in enumerate(values):
                            if w>0:histogram[raw[at+12+j]]=histogram.get(raw[at+12+j],0)+1
                    weights.append(dict(path=folder+'/'+name+'.vvd',vertices=count,weightConsumers=histogram))
                    continue
                dest=W/(name+'.mdl');dest.write_bytes(raw)
                count,offset=struct.unpack_from('<II',raw,156)
                bones=[]
                for i in range(count):
                    at=offset+i*216;ni,parent=struct.unpack_from('<ii',raw,at)
                    bn=raw[at+ni:raw.index(0,at+ni)].decode()
                    proc,pi=struct.unpack_from('<ii',raw,at+164)
                    b=dict(index=i,name=bn,parent=parent,type=proc)
                    if proc==2:
                        base=at+pi;control,n,ti=struct.unpack_from('<iii',raw,base)
                        triggers=[]
                        for j in range(n):
                            v=struct.unpack_from('<12f',raw,base+ti+48*j)
                            triggers.append(dict(invTolerance=v[0],trigger=list(v[1:5]),position=list(v[5:8]),rotation=list(v[8:12])))
                        b.update(control=control,triggers=triggers)
                    bones.append(b)
                entries.append(dict(path=folder+'/'+name+'.mdl',file=str(dest),bones=bones))
report=W/'source-procedures.json';report.write_text(json.dumps(entries,indent=2),encoding='utf-8')
(W/'source-weight-consumers.json').write_text(json.dumps(weights,indent=2),encoding='utf-8')
for e in entries:print(e['path'],[(b['index'],b['name'],b['type'],b.get('control'),len(b.get('triggers',[]))) for b in e['bones'] if b['type']])
print('Workspace:',W)
