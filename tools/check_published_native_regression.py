import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-regression-20261103'
OLD=ROOT/'outputs/native-fix-20261103'
MANAGER=WORK/'manager-final'
sys.path.insert(0,str(MANAGER))
from anim_batch_mod.native_skeleton import load_manifest,convert_clip
from anim_batch_mod.native_animation import read_blocks
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import ModConfig
from anim_batch_mod.constants import ANIMATION_TYPE_ID
import tomllib
manifest=load_manifest(WORK/'project/models/test01/source-skeleton.json')
cfg=WORK/'project/config.toml'
options=tomllib.loads(cfg.read_text(encoding='utf-8-sig'))['native_skeleton']
unit=UnitData.parse((OLD/'avatar.toc').read_bytes())
bones=BonesData.parse((OLD/'bones.toc').read_bytes())
build=json.loads((OLD/'project/animations/build-report.json').read_text(encoding='utf-8'))
rows=[build['animations'][0],next(r for r in build['animations'] if r['additive']),
      next(r for r in build['animations'] if int(r['id'])==2300190009223786134)]
store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
original=TocArchive.load_toc_only(store,'18235e0c9ec0e636')
results=[]
for row in rows:
    index=build['animations'].index(row)
    path=OLD/f'project/animations/runtime/9ba626afa44a3aa3.patch_{4+index//64}'
    archive=TocArchive.parse_parts(path.read_bytes(),b'',b'')
    key=(int(row['id']),ANIMATION_TYPE_ID)
    data,metrics=convert_clip(original.entries[key].toc_data,bones,unit,manifest,ModConfig.load(cfg),options)
    for old,new in zip(read_blocks(archive.entries[key].toc_data),read_blocks(data)):
        assert old.states[90:]==new.states[90:]
        source=lambda b:[e for e in b.entries if e[1] is not None and e[1]>=90]
        assert source(old)==source(new)
    results.append(dict(id=row['id'],additive=row['additive'],source_bytes_unchanged=True))
for name in ('native_animation.py','native_skeleton.py'):
    assert (MANAGER/'anim_batch_mod'/name).read_bytes()==(ROOT.parent/name).read_bytes()
report=dict(status='PASS',published_python=sys.executable,clips=results)
(WORK/'reports/published-generator.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
