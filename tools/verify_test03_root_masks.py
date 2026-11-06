import json,sys,shutil,sqlite3,struct
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();sys.path.insert(0,str(r.parents[1]));w=r/'outputs/attachment-root-mask-fix-20261106';inputs=w/'inputs';inputs.mkdir(parents=True,exist_ok=True)
temp=Path('C:/Users/ADMINI~1/AppData/Local/Temp/hd2animations-635b6f94/build')
shutil.copy2(temp/'source-skeleton.json',inputs/'source-skeleton.json')
with sqlite3.connect((temp/'resource-index.sqlite3').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(w/'input-resource-index.sqlite3') as dst:src.backup(dst)
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import append_state_machine_masks,source_blend_mask_owners
m=json.loads((inputs/'source-skeleton.json').read_text());store=PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'))
index=ResourceIndex(store,w/'input-resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID})
try:
 index.load_or_build();_,ue=index.resolve(int(m['referenceUnit'],0),UNIT_TYPE_ID);u=UnitData.parse(ue.toc_data)
 _,be=index.resolve(u.bones_ref,BONE_TYPE_ID);b=BonesData.parse(be.toc_data)
 _,se=index.resolve(u.state_machine_ref,STATE_MACHINE_TYPE_ID);raw=bytes(se.toc_data)
 (inputs/'bones.toc').write_bytes(be.toc_data);(inputs/'state-machine.toc').write_bytes(raw)
 out,count=append_state_machine_masks(raw,b,m);owners=source_blend_mask_owners(b,m)
 old_at=struct.unpack_from('<I',raw,32)[0];new_at=struct.unpack_from('<I',out,32)[0];checks=0
 for i in range(count):
  a=old_at+struct.unpack_from('<I',raw,old_at+4+4*i)[0];c=new_at+struct.unpack_from('<I',out,new_at+4+4*i)[0]
  n=struct.unpack_from('<I',raw,a)[0];weights=struct.unpack_from(f'<{n}f',raw,a+4)
  assert out[c+4:c+4+4*n]==raw[a+4:a+4+4*n]
  added=struct.unpack_from(f'<{len(owners)}f',out,c+4+4*n)
  assert all(x==weights[owner] for x,owner in zip(added,owners));checks+=len(owners)
 roots=[dict(name=n['name'],sourceName=n.get('sourceName'),owner=owners[i],driver=b.names[owners[i]]) for i,n in enumerate(m['bones']) if n['parent'] is None and n['driver'] is None]
 report=dict(status='PASS',roots=roots,masks=count,ownerChecks=checks,originalMasksByteIdentical=True,sourceNodesRetained=len(m['bones']),gameTested=False)
 (w/'real-test03-mask-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
finally:index.close()
