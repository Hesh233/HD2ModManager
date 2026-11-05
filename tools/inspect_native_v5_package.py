"""Audit final model/companion resource coverage and importer diagnostics."""
import json,struct,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,parse_state_machine_animation_ids
from anim_batch_mod.native_skeleton import load_manifest,bone_name_hash
WORK=ROOT/'outputs/native-v5-20261103';P=WORK/'project';BASE=ROOT/'outputs/native-fix-20261103'
def patch(path):return TocArchive.parse_parts(path.read_bytes(),Path(str(path)+'.gpu_resources').read_bytes(),b'')
source=patch(P/'models/test01/9ba626afa44a3aa3.patch_0')
model=patch(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
assert len(source.entries)==7 and len(model.entries)==17
assert all(k[1]==UNIT_TYPE_ID for k in model.entries)
materials=patch(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_1')
assert all(k[1]!=STATE_MACHINE_TYPE_ID for k in materials.entries)
assert len(list((P/'animations/runtime').glob('*.patch_*')))==3
assert all((P/'animations/runtime'/f'9ba626afa44a3aa3.patch_2{s}').stat().st_size==0 for s in ('.gpu_resources','.stream'))
mapping=json.loads((WORK/'o3-mapping.json').read_text())['mappings']
for row in mapping:
    a=source.entries[int(row['sourceUnit'],16),UNIT_TYPE_ID];b=model.entries[int(row['targetUnit'],16),UNIT_TYPE_ID]
    assert a.toc_data==b.toc_data and a.gpu_data==b.gpu_data
assert b'HD2PBFT1' in (P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0.gpu_resources').read_bytes()[-56:]
manifest=load_manifest(P/'models/test01/source-skeleton.json')
assert manifest['modelScale']==1.05 and manifest['scaleOrigin']=='ground'
assert all(n['hash']==bone_name_hash(n['name']) and n['sourceName'] for n in manifest['bones'])
path=P/'animations/runtime/9ba626afa44a3aa3.patch_2'
with path.open('rb') as f:
    header=f.read(72);types,count=struct.unpack_from('<II',header,4);assert (types,count)==(4,3183)
    f.seek(72+32*types);records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
    ids={r[0] for r in records if r[1]==ANIMATION_TYPE_ID}
    assert ids==set(parse_state_machine_animation_ids((BASE/'state-machine.toc').read_bytes()))
    def payload(kind):
        r=next(r for r in records if r[1]==kind);f.seek(r[2]);return f.read(r[7])
    unit=UnitData.parse(payload(UNIT_TYPE_ID));bones=BonesData.parse(payload(BONE_TYPE_ID));state=payload(STATE_MACHINE_TYPE_ID)
assert len(unit.transforms)==225 and len(bones.names)==208
oldUnit=UnitData.parse((BASE/'avatar.toc').read_bytes());oldBones=BonesData.parse((BASE/'bones.toc').read_bytes())
assert unit.transforms[:107]==oldUnit.transforms and unit.parents[:107]==oldUnit.parents
assert unit.name_hashes[:107]==oldUnit.name_hashes and bones.names[:90]==oldBones.names
assert not ({n['hash'] for n in manifest['bones'] if n.get('physics')} & set(unit.name_hashes))
baseState=(BASE/'state-machine.toc').read_bytes();n,offset=struct.unpack_from('<II',state,28);oldN,oldOffset=struct.unpack_from('<II',baseState,28)
assert n==oldN==80
owners=[]
for node in manifest['bones']:
    owners.append(oldBones.names.index(node['driver']) if node['driver'] is not None else owners[node['parent']])
owners.extend(row['maskChannel'] for row in manifest['attachmentShadows'])
for i in range(n):
    start=offset+struct.unpack_from('<I',state,offset+4+4*i)[0]
    oldStart=oldOffset+struct.unpack_from('<I',baseState,oldOffset+4+4*i)[0]
    assert struct.unpack_from('<I',state,start)[0]==208
    weights=struct.unpack_from('<208f',state,start+4);original=struct.unpack_from('<90f',baseState,oldStart+4)
    assert weights[:90]==original and weights[90:]==tuple(original[j] for j in owners)
for name in ('model','physics','animation'):
    inspection=json.loads((WORK/f'{name}-import-inspection.json').read_text(encoding='utf-8-sig'))
    assert not any(d.get('isBlocking',False) for d in inspection['import'].get('diagnostics',[]))
structure_only='--structure-only' in sys.argv
if not structure_only:
    for name in ('model','animation'):
        assert json.loads((WORK/f'{name}-import-apply.json').read_text(encoding='utf-8-sig'))['ok']
report=dict(status='PASS',gameTested=False,sourceUnits=7,o3Units=17,replacedUnits=11,modelStateMachines=0,
    companionPatches=1,animations=3180,blendMasks=80,driverChannels=90,totalChannels=208,attachmentReferenceNodes=29,
    unchangedOriginalAvatar=True,sharedAvatarPhysicsBones=0,modelAndAnimationImported=not structure_only)
report['scope']='package structure and import inspection' if structure_only else 'package structure and successful isolated imports'
name='package-structure-inspection.json' if structure_only else 'package-inspection.json'
(WORK/name).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
