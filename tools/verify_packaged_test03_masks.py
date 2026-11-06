import json,struct,sys
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();sys.path.insert(0,str(r.parents[1]));w=r/'outputs/attachment-root-mask-fix-20261106'
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import STATE_MACHINE_TYPE_ID
p=next((w/'test03-rs89/test03/animations/runtime').glob('*.patch_2'))
a=TocArchive.parse_parts(*(Path(str(p)+s).read_bytes() for s in ('','.gpu_resources','.stream')));after=bytes(a.entries_of_type(STATE_MACHINE_TYPE_ID)[0].toc_data)
before=(w/'inputs/state-machine.toc').read_bytes();ob=struct.unpack_from('<I',before,32)[0];ab=struct.unpack_from('<I',after,32)[0];count=struct.unpack_from('<I',before,28)[0]
for i in range(count):
 o=ob+struct.unpack_from('<I',before,ob+4+4*i)[0];n=ab+struct.unpack_from('<I',after,ab+4+4*i)[0];channels=struct.unpack_from('<I',before,o)[0]
 assert before[o+4:o+4+4*channels]==after[n+4:n+4+4*channels]
 assert before[o+4:o+8]==after[n+4+4*channels:n+8+4*channels] # Source Armature channel follows native entity channel 0.
report=json.loads((w/'test03-rs89/test03/animations/build-report.json').read_text());assert report['unmapped_root_masks'][0]['ownerName']=='StingrayEntityRoot'
result=dict(status='PASS',runtimeMasksChecked=count,originalMaskBytesPreserved=True,rootMappings=report['unmapped_root_masks'],sampleOnly=True,gameTested=False)
(w/'packaged-root-mask-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
