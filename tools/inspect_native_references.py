import json, struct, sys
from collections import Counter
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[3]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData

result=[]
for arg in sys.argv[1:]:
    p=Path(arg)
    data=p.read_bytes()
    count_types,count_files=struct.unpack_from('<II',data,4)
    start=72+count_types*32
    types=Counter(struct.unpack_from('<Q',data,start+i*80+8)[0] for i in range(count_files))
    item={'file':str(p),'files':count_files,'types':{f'{k:016x}':v for k,v in types.items()}}
    if count_files<100:
        ar=TocArchive.parse_parts(data,Path(str(p)+'.gpu_resources').read_bytes() if Path(str(p)+'.gpu_resources').exists() else b'',
                                 Path(str(p)+'.stream').read_bytes() if Path(str(p)+'.stream').exists() else b'')
        item['resources']=[]
        for (fid,tid),e in ar.entries.items():
            row={'id':f'{fid:016x}','type':f'{tid:016x}','toc':len(e.toc_data),'gpu':len(e.gpu_data),'stream':len(e.stream_data)}
            if tid==UNIT_TYPE_ID:
                try:
                    u=UnitData.parse(e.toc_data); row.update(nodes=len(u.name_hashes),bones_ref=f'{u.bones_ref:016x}',state_ref=f'{u.state_machine_ref:016x}')
                except Exception as ex: row['parse_error']=str(ex)
            if tid==BONE_TYPE_ID:
                b=BonesData.parse(e.toc_data); row.update(channels=len(b.names),last_names=b.names[-12:])
            if tid==STATE_MACHINE_TYPE_ID:
                count,offset=struct.unpack_from('<II',e.toc_data,28)
                row.update(masks=count,channels=struct.unpack_from('<I',e.toc_data,offset+struct.unpack_from('<I',e.toc_data,offset+4)[0])[0] if count else 0)
            item['resources'].append(row)
    result.append(item)
print(json.dumps(result,ensure_ascii=False,indent=2))
