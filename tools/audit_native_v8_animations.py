"""Audit every final animation, preserving native tracks, events and archive layout."""
import hashlib,json,math,struct,sys
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
sys.path.insert(0,str(ROOT/'tools'))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import AnimationData,UnitData,BonesData,parse_state_machine_animation_ids
from anim_batch_mod.native_animation import read_blocks
from anim_batch_mod.native_skeleton import load_manifest,append_unit,append_bones,append_state_machine_masks
from anim_batch_mod.processor import _build_tracks
from package_native_v8 import records,payload
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'

def check_clip(raw,original,channels,driver_count,shadow_rows,shadow_start,binds,baseline,lower_channels):
    a=AnimationData.parse(original);b=AnimationData.parse(raw)
    assert len(b.initial_bone_states)==channels
    assert a.animation_length==b.animation_length and a.is_additive==b.is_additive
    assert [(e.bone,e.time,e.data2) for e in a.entries if e.type==0 and e.subtype==2]==[(e.bone,e.time,e.data2) for e in b.entries if e.type==0 and e.subtype==2]
    for block in read_blocks(raw):
        assert not any(block.flags)
        times=[e[0] for e in block.entries];assert times==sorted(times)
    for s in b.initial_bone_states:
        assert all(math.isfinite(v) for v in s.position+s.rotation+s.scale)
        assert abs(sum(v*v for v in s.rotation)-1)<.003
    for e in b.entries:
        if e.is_position or e.is_rotation or e.is_scale:assert all(math.isfinite(v) for v in e.data2)
    at,bt=_build_tracks(a),_build_tracks(b);native_error=0.;shadow_error=0.
    def error(x,y,kind):
        if kind==1 and sum(v*w for v,w in zip(x,y))<0:y=[-v for v in y]
        return max(abs(v-w) for v,w in zip(x,y))
    for frame in range(9):
        t=a.animation_length*1000*frame/8
        for kind in range(3):
            for channel in range(driver_count):native_error=max(native_error,error(at[kind][channel].evaluate(t),bt[kind][channel].evaluate(t),kind))
            for i,row in enumerate(shadow_rows):
                ch=row['animationChannel']
                if ch is not None:expected=at[kind][ch].evaluate(t)
                elif a.is_additive:expected=([0,0,0],[0,0,0,1],[0,0,0])[kind]
                else:expected=binds[row['index']][kind]
                shadow_error=max(shadow_error,error(expected,bt[kind][shadow_start+i].evaluate(t),kind))
    assert native_error<2e-5 and shadow_error<2e-5,(native_error,shadow_error)
    prior=AnimationData.parse(baseline)
    assert len(prior.initial_bone_states)==channels
    if b.is_additive:assert raw==baseline,'Additive payload changed from v7'
    for channel in lower_channels:
        assert prior.initial_bone_states[channel]==b.initial_bone_states[channel],('Lower-body initial pose changed',channel)
    def lower_keys(clip):
        return [(e.bone,e.type,e.subtype,e.time,e.data2) for e in clip.entries
            if e.bone in lower_channels and (e.is_position or e.is_rotation or e.is_scale)]
    assert lower_keys(prior)==lower_keys(b),'Lower-body or motion-layer keys changed from v7'
    return dict(nativeError=native_error,shadowError=shadow_error)

def main():
    build=json.loads((P/'animations/build-report.json').read_text());assert build['status']=='complete'
    assert all(r['standard_foot_chains']==0 and not r['planted_feet'] and r['max_pelvis_drop']==0 and r['grip_target']=='configured' for r in build['animations'])
    m=load_manifest(P/'source-skeleton.json');ub=(B/'avatar.toc').read_bytes();bb=(B/'bones.toc').read_bytes();sb=(B/'state-machine.toc').read_bytes()
    u=UnitData.parse(ub);b=BonesData.parse(bb);binds=[(t.position,t.rotation,t.scale) for t in u.transforms]
    original=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636')
    path=P/'animations/runtime/9ba626afa44a3aa3.patch_2';rs=records(path)
    ids=set(parse_state_machine_animation_ids(sb));assert len(ids)==build['expected_animations']==len(build['animations'])
    assert len(rs)==len(ids)+3 and len({(r[0],r[1]) for r in rs})==len(rs)
    assert {r[0] for r in rs if r[1]==ANIMATION_TYPE_ID}==ids
    with path.open('rb') as f:
        header=f.read(72);nt,count=struct.unpack_from('<II',header,4)
        types=[struct.unpack('<QQQII',f.read(32)) for _ in range(nt)]
    assert {r[1]:r[2] for r in types}=={UNIT_TYPE_ID:1,BONE_TYPE_ID:1,STATE_MACHINE_TYPE_ID:1,ANIMATION_TYPE_ID:len(ids)}
    end=72+32*nt+80*count
    for r in rs:assert r[2]==end and r[3]==r[4]==r[8]==r[9]==0;end+=r[7]
    assert end==path.stat().st_size
    def one(kind):return payload(path,next(r for r in rs if r[1]==kind))
    final_u=one(UNIT_TYPE_ID);final_b=one(BONE_TYPE_ID);final_s=one(STATE_MACHINE_TYPE_ID)
    assert final_u==append_unit(ub,m) and final_b==append_bones(bb,m)
    expected_s,mask_count=append_state_machine_masks(sb,b,m);assert final_s==expected_s
    eu=UnitData.parse(final_u);eb=BonesData.parse(final_b)
    assert eu.transforms[:len(u.transforms)]==u.transforms and eu.parents[:len(u.parents)]==u.parents and eu.name_hashes[:len(u.name_hashes)]==u.name_hashes
    assert eb.names[:len(b.names)]==b.names
    # The original serialized TransformInfo remains byte-identical in the relocated block.
    old_at=struct.unpack_from('<I',ub,52)[0];new_at=struct.unpack_from('<I',final_u,52)[0]
    n=len(u.transforms);en=len(eu.transforms)
    for stride,old_base,new_base in ((64,old_at+16,new_at+16),(64,old_at+16+64*n,new_at+16+64*en),(4,old_at+16+128*n,new_at+16+128*en)):
        assert ub[old_base:old_base+stride*n]==final_u[new_base:new_base+stride*n]
    baseline_path=ROOT/'outputs/native-v7-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'
    baseline_records={r[0]:r for r in records(baseline_path) if r[1]==ANIMATION_TYPE_ID}
    assert set(baseline_records)==ids
    hip=len(u.transforms)+next(i for i,node in enumerate(m['bones']) if node['driver']=='hips')
    lower_channels=set()
    for i in range(len(m['bones'])):
        cursor=len(u.transforms)+i
        while cursor is not None and cursor!=hip:cursor=eu.parents[cursor]
        if cursor==hip:lower_channels.add(len(b.names)+i)
    lower_channels.update(range(len(b.names)+len(m['bones']),len(b.names)+len(m['bones'])+len(m['motionLayers'])))
    assert len(lower_channels)>10
    shadow_start=eb.names.index(m['attachmentShadows'][0]['name']);results=[];pending=deque()
    with ProcessPoolExecutor(max_workers=6) as pool:
        for r in rs:
            if r[1]!=ANIMATION_TYPE_ID:continue
            pending.append(pool.submit(check_clip,payload(path,r),original.entries[r[0],r[1]].toc_data,len(eb.names),len(b.names),m['attachmentShadows'],shadow_start,binds,payload(baseline_path,baseline_records[r[0]]),lower_channels))
            if len(pending)>=12:
                results.append(pending.popleft().result())
                if len(results)%200==0:print('audited',len(results),'/',len(ids),flush=True)
        while pending:results.append(pending.popleft().result())
    for item in build['files']:
        with (P/'animations'/item['path']).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
    result=dict(status='PASS',gameTested=False,animations=len(ids),patches=1,channels=len(eb.names),avatarNodes=len(eu.transforms),blendMasks=mask_count,
        unchangedOriginalAvatar=True,unchangedNativeDriverChannels=len(b.names),maxOriginalDriverError=max(r['nativeError'] for r in results),maxShadowError=max(r['shadowError'] for r in results),
        unchangedLowerBodyAndMotionLayerChannels=len(lower_channels),lowerBodyComparedWithV7AcrossAllClips=True,
        additivePayloadsUnchangedFromV7=True,
        compactBytes=path.stat().st_size,maxStandardGripResidualMetres=max(r['max_standard_grip_error'] for r in build['animations']),plantedClips=0,
        scope='all serialized animations, archive coverage, events, float tracks, native tracks, original shadows and regenerated structural resources; grip and game timing audited separately')
    (W/'animation-final-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
