"""Read-only full companion audit against the original game and shadow channels."""
import hashlib,json,struct,sys,math
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive,PackageStore
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import AnimationData,UnitData,BonesData,parse_state_machine_animation_ids
from anim_batch_mod.native_animation import read_blocks
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms
W=ROOT/'outputs/native-v6-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'

def check_clip(raw,original,shadow_rows,binds):
    a=AnimationData.parse(original);b=AnimationData.parse(raw)
    assert len(b.initial_bone_states)==232 and a.animation_length==b.animation_length and a.is_additive==b.is_additive
    assert [(e.bone,e.time,e.data2) for e in a.entries if e.type==0 and e.subtype==2]==[(e.bone,e.time,e.data2) for e in b.entries if e.type==0 and e.subtype==2]
    for block in read_blocks(raw):
        assert not any(block.flags)
        times=[e[0] for e in block.entries];assert times==sorted(times)
    for state in b.initial_bone_states[208:]:
        assert all(math.isfinite(v) for v in state.position+state.rotation+state.scale)
        assert abs(sum(v*v for v in state.rotation)-1)<.002
    at,bt=_build_tracks(a),_build_tracks(b);original_error=0.;shadow_error=0.
    def error(x,y,kind):
        if kind==1 and sum(v*w for v,w in zip(x,y))<0:y=[-v for v in y]
        return max(abs(v-w) for v,w in zip(x,y))
    for frame in range(9):
        t=a.animation_length*1000*frame/8
        for kind in range(3):
            for channel in range(90):original_error=max(original_error,error(at[kind][channel].evaluate(t),bt[kind][channel].evaluate(t),kind))
            for i,row in enumerate(shadow_rows):
                ch=row['animationChannel']
                if ch is not None:expected=at[kind][ch].evaluate(t)
                elif a.is_additive:expected=([0,0,0],[0,0,0,1],[0,0,0])[kind]
                else:expected=binds[row['index']][kind]
                shadow_error=max(shadow_error,error(expected,bt[kind][179+i].evaluate(t),kind))
    assert original_error<2e-5 and shadow_error<2e-5,(original_error,shadow_error)
    return dict(originalError=original_error,shadowError=shadow_error)

def main():
    report=json.loads((P/'animations/build-report.json').read_text());assert report['status']=='complete' and len(report['animations'])==3180
    assert all(r['standard_foot_chains']==0 and not r['planted_feet'] and r['max_pelvis_drop']==0 and r['grip_target']=='configured' for r in report['animations'])
    manifest=json.loads((P/'source-skeleton.json').read_text());shadows=manifest['attachmentShadows'];assert len(shadows)==29
    old=UnitData.parse((B/'avatar.toc').read_bytes());oldbones=BonesData.parse((B/'bones.toc').read_bytes())
    binds=[(t.position,t.rotation,t.scale) for t in old.transforms]
    original=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636')
    path=P/'animations/runtime/9ba626afa44a3aa3.patch_2';results=[]
    with path.open('rb') as f:
        header=f.read(72);nt,count=struct.unpack_from('<II',header,4);assert (nt,count)==(4,3183)
        types=[struct.unpack('<QQQII',f.read(32)) for _ in range(nt)]
        assert {r[1]:r[2] for r in types}=={UNIT_TYPE_ID:1,BONE_TYPE_ID:1,STATE_MACHINE_TYPE_ID:1,ANIMATION_TYPE_ID:3180}
        records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
        assert len({(r[0],r[1]) for r in records})==3183
        assert {r[0] for r in records if r[1]==ANIMATION_TYPE_ID}==set(parse_state_machine_animation_ids((B/'state-machine.toc').read_bytes()))
        offset=72+32*nt+80*count
        for r in records:assert r[2]==offset and r[3]==r[4]==r[8]==r[9]==0;offset+=r[7]
        assert offset==path.stat().st_size
        def payload(r):f.seek(r[2]);return f.read(r[7])
        unit=UnitData.parse(payload(next(r for r in records if r[1]==UNIT_TYPE_ID)))
        bones=BonesData.parse(payload(next(r for r in records if r[1]==BONE_TYPE_ID)))
        assert len(unit.transforms)==249 and len(bones.names)==232
        assert unit.transforms[:107]==old.transforms and unit.parents[:107]==old.parents and unit.name_hashes[:107]==old.name_hashes
        assert bones.names[:90]==oldbones.names
        world=_calculate_world_transforms(unit.transforms,unit.parents)
        for i,row in enumerate(shadows):
            assert unit.transforms[196+i]==old.transforms[row['index']]
            assert bones.names[179+i]==row['name'] and unit.name_hashes[196+i]==row['hash']
            assert max(abs(a-b) for a,b in zip(world[196+i].position,world[row['index']].position))<1e-8
        source_shadows=manifest['sourceAttachmentShadows'];assert len(source_shadows)==24
        for i,row in enumerate(source_shadows):
            assert unit.parents[225+i]==row['sourceParent']
            assert bones.names[208+i]==row['name'] and unit.name_hashes[225+i]==row['hash']
            assert max(abs(a-b) for a,b in zip(world[225+i].position,row['worldMatrix'][12:15]))<1e-5
        state=payload(next(r for r in records if r[1]==STATE_MACHINE_TYPE_ID));base=(B/'state-machine.toc').read_bytes()
        n,o=struct.unpack_from('<II',state,28);bn,bo=struct.unpack_from('<II',base,28);assert n==bn==80
        for i in range(n):
            s=o+struct.unpack_from('<I',state,o+4+4*i)[0];bs=bo+struct.unpack_from('<I',base,bo+4+4*i)[0]
            assert struct.unpack_from('<I',state,s)[0]==232
            weights=struct.unpack_from('<232f',state,s+4);original_weights=struct.unpack_from('<90f',base,bs+4)
            assert weights[:90]==original_weights and weights[179:208]==tuple(original_weights[r['maskChannel']] for r in shadows)
            assert weights[208:]==tuple(original_weights[r['maskChannel']] for r in source_shadows)
        pending=deque()
        with ProcessPoolExecutor(max_workers=6) as pool:
            for r in records:
                if r[1]!=ANIMATION_TYPE_ID:continue
                pending.append(pool.submit(check_clip,payload(r),original.entries[r[0],r[1]].toc_data,shadows,binds))
                if len(pending)>=12:
                    results.append(pending.popleft().result())
                    if len(results)%100==0:print('audited',len(results),'/3180',flush=True)
            while pending:results.append(pending.popleft().result())
    for item in report['files']:
        p=P/'animations'/item['path']
        with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
    result=dict(status='PASS',gameTested=False,animations=3180,patches=1,channels=232,avatarNodes=249,originalAttachmentReferences=29,
        maxOriginalDriverError=max(r['originalError'] for r in results),maxShadowError=max(r['shadowError'] for r in results),
        compactBytes=path.stat().st_size,maxStandardGripResidualMetres=max(r['max_standard_grip_error'] for r in report['animations']),
        maxFootTargetResidualMetres=max(r['max_standard_foot_error'] for r in report['animations']),
        plantedClips=sum(r['planted_feet'] for r in report['animations']))
    (W/'animation-final-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
