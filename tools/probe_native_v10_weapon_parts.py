"""Read original weapon/composite resource tables without changing game data."""
import json,sqlite3,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import PackageStore,ResourceIndex,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
W=ROOT/'outputs/native-v10-20261104'
names={int(h):n for h,n in (line.split(' ',1) for line in (ROOT.parents[1]/'hashlists/friendlynames.txt').read_text().splitlines() if ' ' in line)}
bones={int(h):n for h,n in (line.split(' ',1) for line in (ROOT.parents[1]/'hashlists/bonehash.txt').read_text().splitlines() if ' ' in line)}
index=ResourceIndex(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')))
index.connection=sqlite3.connect('file:'+str(ROOT/'outputs/native-v9-20261104/project/animations/resource-index.sqlite3')+'?mode=ro',uri=True)
out=[];packages={}
for h in ('c4232a0e62166d91','a7ee1ebf58fcdf1f','9eb160830321bfd6'):
    package,entry=index.resolve(int(h,16),UNIT_TYPE_ID);u=UnitData.parse(entry.toc_data)
    (W/(h+'.toc')).write_bytes(entry.toc_data)
    comp=struct.unpack_from('<Q',entry.toc_data,16)[0]
    row=dict(id=h,name=names.get(int(h,16)),package=package,nodes=len(u.transforms),composite=f'{comp:016x}',bones=[bones.get(x,str(x)) for x in u.name_hashes])
    if comp:
        cp,ce=index.resolve(comp,0xc4f0f4be7fb0c8d6);data=ce.toc_data
        n=struct.unpack_from('<I',data,8)[0];assert n<1024 and 16+n*16<=len(data)
        row['members']=[dict(type=f'{t:016x}',id=f'{i:016x}',name=names.get(i)) for t,i in (struct.unpack_from('<QQ',data,16+j*16) for j in range(n))]
        (W/(f'{comp:016x}.composite.toc')).write_bytes(data)
    out.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    arc=TocArchive.load_toc_only(index.store,package)
    units=[]
    for e in arc.entries_of_type(UNIT_TYPE_ID):
        try:cu=UnitData.parse(e.toc_data)
        except Exception:continue
        folder=W/'weapon-parts';folder.mkdir(exist_ok=True)
        (folder/f'{e.file_id:016x}.toc').write_bytes(e.toc_data)
        units.append(dict(id=f'{e.file_id:016x}',name=names.get(e.file_id),nodes=len(cu.transforms),bones=[bones.get(x,str(x)) for x in cu.name_hashes]))
    packages[package]=units
index.close()
(W/'weapon-parts-assets.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
(W/'weapon-package-units.json').write_text(json.dumps(packages,ensure_ascii=False,indent=2),encoding='utf-8')
for k,v in packages.items():print('PACKAGE',k,json.dumps([{'id':r['id'],'name':r['name'],'nodes':r['nodes'],'bones':r['bones'][:15]} for r in v],ensure_ascii=False))
