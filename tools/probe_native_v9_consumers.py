from pathlib import Path
import sys,json,sqlite3
r=Path('I:/HD2SDK-CommunityEdition/anim_batch_mod/HD2ModManager');sys.path.insert(0,str(r.parents[1]))
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
b=BonesData.parse((r/'outputs/native-fix-20261103/bones.toc').read_bytes());names=dict(zip(b.hashes,b.names))
w=r/'outputs/native-v9-20261104';index=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')))
index.connection=sqlite3.connect('file:'+str(r/'outputs/native-v8-20261104/project/animations/resource-index.sqlite3')+'?mode=ro',uri=True)
for h in ('a9936cbe561e8180','1c8764d62e12925a'):
 try:
  package,entry=index.resolve(int(h,16),UNIT_TYPE_ID);u=UnitData.parse(entry.toc_data)
  (w/(h+'.toc')).write_bytes(entry.toc_data)
  print(h,package,len(u.transforms),'bones',u.bones_ref,[(i,names.get(x,str(x)),u.parents[i]) for i,x in enumerate(u.name_hashes)])
 except Exception as e:print(h,type(e).__name__,str(e))
index.close()
