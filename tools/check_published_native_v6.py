"""Compare the packaged generator with delivered clips, using its own Python modules."""
import hashlib,json,struct,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'outputs/native-v6-20261104'
MANAGER=WORK/'manager';BASE=ROOT/'outputs/native-fix-20261103'
sys.path.insert(0,str(MANAGER))
from anim_batch_mod.native_skeleton import load_manifest,convert_clip
from anim_batch_mod.archive import TocArchive,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import ModConfig
manifest=load_manifest(WORK/'project/models/test01/source-skeleton.json')
config=WORK/'project/config.toml';options=tomllib.loads(config.read_text(encoding='utf-8-sig'))['native_skeleton']
report=json.loads((WORK/'project/animations/build-report.json').read_text())
selected=[report['animations'][0],next(r for r in report['animations'] if r['additive']),
          next(r for r in report['animations'] if int(r['id'])==2300190009223786134)]
unit=UnitData.parse((BASE/'avatar.toc').read_bytes());bones=BonesData.parse((BASE/'bones.toc').read_bytes())
original=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636')
rows=[]
with (WORK/'project/animations/runtime/9ba626afa44a3aa3.patch_2').open('rb') as f:
    header=f.read(72);types,count=struct.unpack_from('<II',header,4)
    f.seek(72+32*types);records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
    records={(r[0],r[1]):r for r in records}
    for row in selected:
        key=int(row['id']),ANIMATION_TYPE_ID;r=records[key]
        f.seek(r[2]);shipped=f.read(r[7])
        data,metrics=convert_clip(original.entries[key].toc_data,bones,unit,manifest,ModConfig.load(config),options)
        assert data==shipped,('published generator differs',row['id'])
        rows.append(dict(id=row['id'],bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),**metrics))
for name in ('native_animation.py','native_skeleton.py','attachment_skeleton.py','archive.py'):
    assert (MANAGER/'anim_batch_mod'/name).read_bytes()==(ROOT.parent/name).read_bytes()
result=dict(status='PASS',exactGeneratedClips=rows,manager=str(MANAGER),gameTested=False)
(WORK/'published-generator-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
