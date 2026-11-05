import sys, json, struct
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[3]))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.binary import BinaryReader
from anim_batch_mod.formats import AnimationEntry

def block(data,start=0):
    r=BinaryReader(data); r.seek(start)
    unk,count,length,size,h1,h2=r.unpack('<IIfIII')
    r.read(8*(h1+h2)+2)
    nf=((3*count+7)//8+1)//2*2
    flags=r.read(nf)
    for i in range(count):
        for j in range(3):
            compressed=(flags[(3*i+j)//8]>>((3*i+j)%8))&1
            r.read((4 if j==1 else 6) if compressed else (16 if j==1 else 12))
    r.read(4*h1)
    entries=0
    while True:
        entry=AnimationEntry.parse(r)
        if entry.type==0 and entry.subtype==3: break
        entries+=1
    return dict(start=start,end=r.tell(),count=count,size=size,entries=entries)

if __name__=='__main__':
    store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
    ar=TocArchive.load_toc_only(store,'18235e0c9ec0e636')
    for e in list(ar.entries_of_type(ANIMATION_TYPE_ID))[:3]:
        d=e.toc_data; a=block(d); end=a['end']; b=block(d,end+4)
        print(json.dumps(dict(id=e.file_id,bytes=len(d),a=a,b=b,between=d[end:end+4].hex(),tail=d[b['end']:].hex(),same=d[:12]==d[end+4:end+16] and d[16:end]==d[end+20:b['end']])))
