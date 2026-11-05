"""Check actual game streams and conversion semantics before the full build."""
import json,sys,time,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.native_animation import read_blocks
from anim_batch_mod.native_skeleton import convert_clip,load_manifest
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,parse_state_machine_animation_ids
from anim_batch_mod.processor import ModConfig,_build_tracks
work=ROOT/'outputs/native-v4-20261103'
base=ROOT/'outputs/native-fix-20261103'
manifest=load_manifest(work/'project/models/test01/source-skeleton.json')
unit=UnitData.parse((base/'avatar.toc').read_bytes()); bones=BonesData.parse((base/'bones.toc').read_bytes())
store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
archive=TocArchive.load_toc_only(store,'18235e0c9ec0e636')
ids=set(parse_state_machine_animation_ids((base/'state-machine.toc').read_bytes()))
entries=[e for e in archive.entries_of_type(ANIMATION_TYPE_ID) if e.file_id in ids]
distinct=[]
for e in entries:
    a,b=read_blocks(e.toc_data)
    if (a.header[:12]+a.header[16:],a.flags,a.states,a.hash_floats,a.entries)!=(b.header[:12]+b.header[16:],b.flags,b.states,b.hash_floats,b.entries):distinct.append(e.file_id)
print('distinct blocks',distinct,flush=True)
assert not distinct
rows=[];config=ModConfig.load(work/'project/config.toml')
for entry in [*entries[:4],next(e for e in entries if AnimationData.parse(e.toc_data).is_additive)]:
    start=time.monotonic()
    data,metrics=convert_clip(entry.toc_data,bones,unit,manifest,config,
        {'fps':30,'apply_driver_config':True,'rotate_multipliers':True,'ik_correction':True})
    original=AnimationData.parse(entry.toc_data); result=AnimationData.parse(data)
    a,b=_build_tracks(original),_build_tracks(result); max_error=0.
    for frame in range(61):
        t=original.animation_length*1000*frame/60
        for kind in range(3):
            for channel in range(len(bones.names)):
                x,y=a[kind][channel].evaluate(t),b[kind][channel].evaluate(t)
                if kind==1 and sum(v*w for v,w in zip(x,y))<0:y=[-v for v in y]
                max_error=max(max_error,max(abs(v-w) for v,w in zip(x,y)))
    assert max_error<2e-5,max_error
    rows.append(dict(id=entry.file_id,seconds=time.monotonic()-start,bytes=len(data),maxDriverError=max_error,**metrics))
    print(rows[-1],flush=True)
(work/'sample-audit.json').write_text(json.dumps(dict(status='PASS',distinctBlocks=distinct,clips=rows),indent=2))
