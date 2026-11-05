"""Compact the generated companion and independently compare every native clip."""
import hashlib,json,struct,sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocEntry,TocArchive,InlinePatchWriter,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,UNIT_TYPE_ID
from anim_batch_mod.formats import AnimationData
from anim_batch_mod.native_animation import compact_constant_tracks,read_blocks
from anim_batch_mod.processor import _build_tracks
WORK=ROOT/'outputs/native-v4-20261103';ANIM=WORK/'project/animations'

def check_clip(raw,original):
    data,removed=compact_constant_tracks(raw)
    before=AnimationData.parse(raw); after=AnimationData.parse(data); base=AnimationData.parse(original)
    assert before.initial_bone_states==after.initial_bone_states
    # Independently identify every removed track, and prove all its serialized
    # keys equal its initial value. The comparison does not use the compactor's set.
    def signature(e):return e.bone,0 if e.is_position else 1 if e.is_rotation else 2 if e.is_scale else 3
    retained={signature(e) for e in after.entries}
    for e in before.entries:
        if signature(e) not in retained:
            state=before.initial_bone_states[e.bone]
            expected=(state.position,state.rotation,state.scale)[signature(e)[1]]
            assert e.data2==expected or (e.is_rotation and e.data2==[-v for v in expected])
    assert len(after.initial_bone_states)==179
    assert base.animation_length==after.animation_length and base.is_additive==after.is_additive
    assert [(e.bone,e.time) for e in base.entries if e.type==0 and e.subtype==2]==[
        (e.bone,e.time) for e in after.entries if e.type==0 and e.subtype==2]
    for block in read_blocks(data):
        assert not any(block.flags)
        times=[e[0] for e in block.entries];assert times==sorted(times)
        assert all(struct.unpack_from('<H',e[2])[0] in (2,4,5,6) for e in block.entries)
    a,b=_build_tracks(base),_build_tracks(after);error=0.
    for frame in range(9):
        t=base.animation_length*1000*frame/8
        for kind in range(3):
            for channel in range(90):
                x,y=a[kind][channel].evaluate(t),b[kind][channel].evaluate(t)
                if kind==1 and sum(v*w for v,w in zip(x,y))<0:y=[-v for v in y]
                error=max(error,max(abs(v-w) for v,w in zip(x,y)))
    assert error<2e-5,error
    return data,dict(constant_keys_removed=removed,max_original_driver_error=error,
        dense_bytes=len(raw),compact_bytes=len(data))

def main():
    report=json.loads((ANIM/'build-report.json').read_text())
    assert report['status']=='complete' and len(report['animations'])==3180
    path=ANIM/'runtime/9ba626afa44a3aa3.patch_2'
    assert not (WORK/'animation-final-audit.json').exists()
    store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
    original=TocArchive.load_toc_only(store,'18235e0c9ec0e636')
    rawsize=path.stat().st_size
    with path.open('rb') as f:
        magic,types,count,unknown,header=struct.unpack('<IIII56s',f.read(72))
        assert magic==0xf0000011 and count==3183 and types==4
        declared=[struct.unpack('<QQQII',f.read(32)) for _ in range(types)]
        records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
        assert len({(r[0],r[1]) for r in records})==3183
        assert {r[1]:r[2] for r in declared}=={UNIT_TYPE_ID:1,BONE_TYPE_ID:1,STATE_MACHINE_TYPE_ID:1,ANIMATION_TYPE_ID:3180}
        expected=72+32*types+80*count
        for r in records:
            assert r[2]==expected and r[3]==r[4]==r[8]==r[9]==0
            expected+=r[7]
        assert expected==rawsize
        writer=InlinePatchWriter(TocArchive(unknown,header,{}),path.with_name(path.name+'.compact'),{r[1]:r[2] for r in declared})
        rows={};pending=deque()
        def entry(r,data):return TocEntry(r[0],r[1],bytearray(data),unknown1=r[5],unknown2=r[6],unknown3=r[10],unknown4=r[11])
        with ProcessPoolExecutor(max_workers=4) as pool:
            for r in records:
                f.seek(r[2]);payload=f.read(r[7]);assert len(payload)==r[7]
                if r[1]!=ANIMATION_TYPE_ID:
                    writer.append(entry(r,payload));continue
                pending.append((r,pool.submit(check_clip,payload,original.entries[r[0],r[1]].toc_data)))
                if len(pending)>=8:
                    row,future=pending.popleft();data,metrics=future.result()
                    writer.append(entry(row,data));rows[str(row[0])]=metrics
                    if len(rows)%100==0:print('validated',len(rows),'/3180',flush=True)
            while pending:
                row,future=pending.popleft();data,metrics=future.result()
                writer.append(entry(row,data));rows[str(row[0])]=metrics
        compact=writer.finish()
    # Dense output is our own temporary build. Promote only after all checks pass.
    for new in compact:
        destination=Path(str(new).replace('.patch_2.compact','.patch_2'))
        assert destination.resolve().is_relative_to((ANIM/'runtime').resolve())
        new.replace(destination)
    for row in report['animations']:row.update(rows[row['id']])
    report['constant_tracks_compacted']=True
    for row in report['files']:
        p=ANIM/row['path'];row['bytes']=p.stat().st_size
        with p.open('rb') as f:row['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    (ANIM/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    audit=dict(status='PASS',gameTested=False,animations=len(rows),patches=1,denseBytes=rawsize,
        compactBytes=path.stat().st_size,maxOriginalDriverError=max(r['max_original_driver_error'] for r in rows.values()),
        removedConstantKeys=sum(r['constant_keys_removed'] for r in rows.values()),
        maxStandardGripResidualMetres=max(r['max_standard_grip_error'] for r in report['animations']))
    (WORK/'animation-final-audit.json').write_text(json.dumps(audit,indent=2));print(json.dumps(audit,indent=2),flush=True)

if __name__=='__main__':main()
