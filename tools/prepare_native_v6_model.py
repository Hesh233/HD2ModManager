"""Rebuild only the established O-3 mappings in an isolated project."""
import copy,hashlib,json,re,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,STATE_MACHINE_TYPE_ID
WORK=ROOT/'outputs/native-v6-20261104';PROJECT=WORK/'project'
SOURCE=PROJECT/'models/test01';OLD=ROOT/'outputs/native-manual-20261103/project/models-o3/test01-O3'
DEST=PROJECT/'models-o3/test01-O3'
def patch(p):return TocArchive.parse_parts(p.read_bytes(),Path(str(p)+'.gpu_resources').read_bytes(),b'')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if DEST.exists():raise FileExistsError(DEST)
DEST.mkdir(parents=True)
source=patch(SOURCE/'9ba626afa44a3aa3.patch_0'); old=patch(OLD/'9ba626afa44a3aa3.patch_0')
assert len(source.entries)==7 and len(old.entries)==17
report=json.loads((ROOT/'outputs/native-fix-20261103/rekey-result.json').read_text(encoding='utf-8-sig'))
lookup={e.file_id & 0xffff:e for e in source.entries_of_type(UNIT_TYPE_ID)}
entries=dict(old.entries);mappings=[]
for line in report['mappings']:
    label,old_id,new_id=re.fullmatch(r'(.+) ← 0x([0-9a-f]+) → 0x([0-9a-f]+)',line).groups()
    e=copy.copy(lookup[int(old_id,16)&0xffff]);key=int(new_id,16),UNIT_TYPE_ID
    assert key in entries
    mappings.append(dict(part=label,sourceUnit=f'{e.file_id:016x}',targetUnit=new_id))
    e.file_id=key[0];entries[key]=e
assert all(e.type_id!=STATE_MACHINE_TYPE_ID for e in entries.values())
old.write_patch(DEST/'9ba626afa44a3aa3.patch_0',list(entries.values()))
for suffix in ('','.gpu_resources'):
    name='9ba626afa44a3aa3.patch_1'+suffix
    assert digest(SOURCE/name)==digest(OLD/name),(name,'unexpected material change')
    shutil.copy2(SOURCE/name,DEST/name)
for directory in (SOURCE,DEST):
    for number in (0,1):(directory/f'9ba626afa44a3aa3.patch_{number}.stream').write_bytes(b'')
for name in ('source-skeleton.json','physbone-rig.bin'):shutil.copy2(SOURCE/name,DEST/name)
shutil.copy2(OLD/'sections.json',DEST/'sections.json')
shutil.copy2(WORK/'conversion.json',DEST/'vpk2patch.json')
shutil.copy2(PROJECT/'config.toml',DEST/'config.toml')
target=dict(armor='O-3 自由之魂',armorArchive='f9ced2d898787705',helmetArchive='a2999407862595df',
    bodyTypes=['Slim','Stocky'],modelScale=1.08,scaleOrigin='source',gameTested=False,mappings=mappings)
(DEST/'replacement-target.json').write_text(json.dumps(target,ensure_ascii=False,indent=2),encoding='utf-8')
(WORK/'o3-mapping.json').write_text(json.dumps(target,ensure_ascii=False,indent=2),encoding='utf-8')
print('Prepared O-3: 11 replacements, 6 existing hidden Units; original test01 materials unchanged.')
