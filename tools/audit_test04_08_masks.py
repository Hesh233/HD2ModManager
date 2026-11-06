import sys,json,struct
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();sys.path.insert(0,str(r.parents[1]));w=r/'outputs/test04-08-rs89-20261106'
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import STATE_MACHINE_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import BonesData
from anim_batch_mod.native_skeleton import source_blend_mask_owners
raw=(r/'outputs/attachment-root-mask-fix-20261106/inputs/state-machine.toc').read_bytes()
native_bones=BonesData.parse((r/'outputs/attachment-root-mask-fix-20261106/inputs/bones.toc').read_bytes())
orig_at=struct.unpack_from('<I',raw,32)[0];count=struct.unpack_from('<I',raw,28)[0]
results=[]
for k in range(4,9):
 name=f'test{k:02d}';folder=w/(name+'-initial')/name
 m=json.loads((folder/'animations/source-skeleton.json').read_text(encoding='utf-8-sig'));report=json.loads((folder/'animations/build-report.json').read_text())
 p=next((folder/'animations/runtime').glob('*.patch_2'));a=TocArchive.parse_parts(*(Path(str(p)+s).read_bytes() for s in ['','.gpu_resources','.stream']))
 patched=bytes(a.entries_of_type(STATE_MACHINE_TYPE_ID)[0].toc_data);at=struct.unpack_from('<I',patched,32)[0]
 assert count==struct.unpack_from('<I',patched,28)[0];owners=source_blend_mask_owners(native_bones,m);checks=0
 for i in range(count):
  start=orig_at+struct.unpack_from('<I',raw,orig_at+4+4*i)[0];dest=at+struct.unpack_from('<I',patched,at+4+4*i)[0]
  n=struct.unpack_from('<I',raw,start)[0];old=struct.unpack_from(f'<{n}f',raw,start+4)
  assert patched[dest+4:dest+4+4*n]==raw[start+4:start+4+4*n]
  assert struct.unpack_from('<I',patched,dest)[0]==n+len(owners)
  appended=struct.unpack_from(f'<{len(owners)}f',patched,dest+4+4*n)
  assert all(x==old[j] for x,j in zip(appended,owners));checks+=len(owners)
 result=dict(status='PASS',model=name,masks=count,ownerChecks=checks,nativeMaskBytesUnchanged=True,sourceBones=len(m['bones']),rootMasks=report.get('unmapped_root_masks',[]),sampleOnly=True,gameTested=False)
 (folder/'mask-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');results.append(result);print(json.dumps(result))
(w/'all-mask-audits.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
