import json,sys,struct
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.native_animation import read_blocks
from anim_batch_mod.formats import UnitData,BonesData

work=ROOT/'outputs/native-v4-20261103';work.mkdir(exist_ok=True)
store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
archive=TocArchive.load_toc_only(store,'18235e0c9ec0e636')
base=ROOT/'outputs/native-fix-20261103'
u=UnitData.parse((base/'avatar.toc').read_bytes());b=BonesData.parse((base/'bones.toc').read_bytes())
names={int(line.split()[0]):line.split()[1] for line in (ROOT/'HD2ModManager/Resources/AssetMetadata/bonehash.txt').read_text().splitlines() if line.strip()}
print('driver transforms',[(i,names.get(h,str(h)),u.parents[i],u.transforms[i].position) for i,h in enumerate(u.name_hashes) if any(x in names.get(h,'') for x in ('attach','aim','hand','support'))])
count=0;examples=[]
for p in sorted((ROOT/'outputs/native-regression-20261103/project/animations/runtime').glob('*.patch_*')):
    if p.suffix in ('.stream','.gpu_resources'):continue
    ar=TocArchive.parse_parts(p.read_bytes(),b'',b'')
    for e in ar.entries_of_type(ANIMATION_TYPE_ID):
        if count>=20:break
        o=archive.entries[(e.file_id,ANIMATION_TYPE_ID)]
        stats=[]
        for label,data in [('original',o.toc_data),('v3',e.toc_data)]:
            x=read_blocks(data)[0];keys=[k for k in x.entries if k[1] is not None]
            drops=[(i,keys[i-1][:2],k[:2]) for i,k in enumerate(keys) if i>0 and k[0]<keys[i-1][0]-.001]
            stats.append(dict(label=label,keys=len(keys),duration=struct.unpack_from('<f',data,8)[0],drops=drops[:8],dropCount=len(drops),first=[(round(k[0],3),k[1],k[2][:2].hex()) for k in keys[:8]]))
        examples.append(dict(id=e.file_id,stats=stats));count+=1
    if count>=20:break
print(json.dumps(examples[:4],indent=2))
(work/'initial-diagnosis.json').write_text(json.dumps(examples,indent=2),encoding='utf-8')
