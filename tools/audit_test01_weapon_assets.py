"""Inspect the actual AR-11/P-92 archives and equipment signatures, read-only."""
import json,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import bone_name_hash
from prepare_native_v31_b23 import matrices
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
store=PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'))
db=sqlite3.connect('file:'+(TARGET/'data/indexes/asset-index.sqlite').as_posix()+'?mode=ro',uri=True)
names={}
for line in (ROOT.parents[1]/'hashlists/bonehash.txt').read_text(encoding='utf-8-sig').splitlines():
 p=line.split(maxsplit=1)
 if len(p)==2:
  try:names[int(p[0])]=p[1]
  except ValueError:pass
for n in ['StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','root','boss','game_mesh','shadow_mesh','IK_left','IK_right','attach_underbarrel','attach_offset','attach_magazine','attach_scope','attach_muzzle','muzzle','laser','pivot']:
 names[bone_name_hash(n)]=n
result={}
for aid in ['f90a06c6e291692d','5d5c93ef05a46880']:
 a=TocArchive.load_toc_only(store,aid);units=[]
 for e in a.entries.values():
  if e.type_id!=UNIT_TYPE_ID:continue
  u=UnitData.parse(e.toc_data);nm=dict(names);b=a.entries.get((u.bones_ref,BONE_TYPE_ID))
  if b:
   bd=BonesData.parse(b.toc_data);nm.update(zip(bd.hashes,bd.names))
  units.append(dict(resource=f'{e.file_id:016x}',count=len(u.parents),hashes=u.name_hashes,parents=u.parents,matrices=matrices(u),nodes=[dict(name=nm.get(h,f'hash_{h:08x}'),index=i,parent=u.parents[i]) for i,h in enumerate(u.name_hashes)]))
 result[aid]=units
(TARGET/'test01-武器修正-资源审计.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
for aid,units in result.items():
 print(aid,len(units),'units')
 for u in units:print(u['resource'],u['count'],[(n['name'],n['index'],n['parent']) for n in u['nodes'] if not n['name'].startswith('hash_')])
