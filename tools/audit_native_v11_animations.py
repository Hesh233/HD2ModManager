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
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate
from package_native_v10 import records,payload
W=ROOT/'outputs/native-v11-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'

def check_clip(raw,original,channels,driver_count,shadow_rows,shadow_start,binds,baseline,lower_channels,foot_channels,accepted_grip,hand_chains):
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
    pt=_build_tracks(prior)
    for channel,angle in foot_channels.items():
        q=[0.,math.sin(math.radians(angle)/2),0.,math.cos(math.radians(angle)/2)]
        for frame in range(9):
            t=a.animation_length*1000*frame/8
            before=pt[1][channel].evaluate(t)
            expected=quat_multiply(quat_multiply(quat_inverse(q),before),q) if b.is_additive else quat_multiply(before,q)
            assert error(expected,bt[1][channel].evaluate(t),1)<2e-5,('Foot Y rotation',channel,t)
            p=pt[0][channel].evaluate(t)
            if b.is_additive:p=quat_rotate(quat_inverse(q),p)
            assert error(p,bt[0][channel].evaluate(t),0)<2e-5,('Foot translation basis',channel,t)
    if b.is_additive:
        for channel in range(channels):
            if channel not in foot_channels:
                assert prior.initial_bone_states[channel]==b.initial_bone_states[channel],('Additive non-foot initial',channel)
        def nonfoot_keys(clip):
            return [(e.bone,e.type,e.subtype,e.time,e.data2) for e in clip.entries if e.bone not in foot_channels]
        assert nonfoot_keys(prior)==nonfoot_keys(b),'Non-foot additive keys changed'
    for channel in lower_channels:
        assert prior.initial_bone_states[channel]==b.initial_bone_states[channel],('Lower-body initial pose changed',channel)
    def lower_keys(clip):
        return [(e.bone,e.type,e.subtype,e.time,e.data2) for e in clip.entries
            if e.bone in lower_channels and (e.is_position or e.is_rotation or e.is_scale)]
    assert lower_keys(prior)==lower_keys(b),'Lower-body or motion-layer keys changed from v8'
    accepted=_build_tracks(AnimationData.parse(accepted_grip))
    hand_position_error=0.;hand_rotation_error=0.;baked_position_error=0.;baked_rotation_error=0.
    def hand_pose(tracks,chain,t):
        local=[WorldTransform(*(track[ch].evaluate(t) for track in tracks)) if ch is not None else base for ch,base in chain]
        return _calculate_world_transforms(local,[None]+list(range(len(local)-1)))[-1]
    if not b.is_additive:
        for baked in (False,True):
            for frame in range(9):
                t=a.animation_length*1000*frame/8
                if baked and frame not in (0,8):t=round(t*30/1000)*1000/30
                for chain in hand_chains:
                    old_hand=hand_pose(accepted,chain,t);new_hand=hand_pose(bt,chain,t)
                    pe=math.dist(old_hand.position,new_hand.position);qe=error(old_hand.rotation,new_hand.rotation,1)
                    if baked:baked_position_error=max(baked_position_error,pe);baked_rotation_error=max(baked_rotation_error,qe)
                    else:hand_position_error=max(hand_position_error,pe);hand_rotation_error=max(hand_rotation_error,qe)
        assert baked_position_error<2e-5 and baked_rotation_error<2e-5,('Accepted v10 baked grip changed',baked_position_error,baked_rotation_error)
        assert hand_position_error<.005 and hand_rotation_error<.02,('Interpolated grip changed materially',hand_position_error,hand_rotation_error)
    return dict(nativeError=native_error,shadowError=shadow_error,handPositionError=hand_position_error,handRotationError=hand_rotation_error,bakedHandPositionError=baked_position_error,bakedHandRotationError=baked_rotation_error)

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
    baseline_path=ROOT/'outputs/native-v8-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'
    baseline_records={r[0]:r for r in records(baseline_path) if r[1]==ANIMATION_TYPE_ID}
    accepted_path=ROOT/'outputs/native-v10-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'
    accepted_records={r[0]:r for r in records(accepted_path) if r[1]==ANIMATION_TYPE_ID}
    channel_by_unit={eu.name_hashes.index(h):i for i,h in enumerate(eb.hashes)}
    hand_chains=[]
    for name in ('l_hand','r_hand'):
        ui=eu.name_hashes.index(next(n['hash'] for n in m['bones'] if n['driver']==name));chain=[]
        while ui is not None:
            chain.append((channel_by_unit.get(ui),eu.transforms[ui]));ui=eu.parents[ui]
        hand_chains.append(chain[::-1])
    assert set(baseline_records)==ids
    hip=len(u.transforms)+next(i for i,node in enumerate(m['bones']) if node['driver']=='hips')
    lower_channels=set()
    for i in range(len(m['bones'])):
        cursor=len(u.transforms)+i
        while cursor is not None and cursor!=hip:cursor=eu.parents[cursor]
        if cursor==hip:lower_channels.add(len(b.names)+i)
    lower_channels.update(range(len(b.names)+len(m['bones']),len(b.names)+len(m['bones'])+len(m['motionLayers'])))
    foot_channels={len(b.names)+i:(20. if node['driver']=='l_foot' else -20.) for i,node in enumerate(m['bones']) if node['driver'] in ('l_foot','r_foot')}
    lower_channels-=set(foot_channels)
    assert len(lower_channels)>10
    shadow_start=eb.names.index(m['attachmentShadows'][0]['name']);results=[];pending=deque()
    def completed():
        clip_id,future=pending.popleft()
        try:results.append(future.result())
        except Exception as error:raise RuntimeError(f'Animation {clip_id} failed final audit') from error
    with ProcessPoolExecutor(max_workers=6) as pool:
        for r in rs:
            if r[1]!=ANIMATION_TYPE_ID:continue
            pending.append((r[0],pool.submit(check_clip,payload(path,r),original.entries[r[0],r[1]].toc_data,len(eb.names),len(b.names),m['attachmentShadows'],shadow_start,binds,payload(baseline_path,baseline_records[r[0]]),lower_channels,foot_channels,payload(accepted_path,accepted_records[r[0]]),hand_chains)))
            if len(pending)>=12:
                completed()
                if len(results)%200==0:print('audited',len(results),'/',len(ids),flush=True)
        while pending:completed()
    for item in build['files']:
        with (P/'animations'/item['path']).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==item['sha256']
    result=dict(status='PASS',gameTested=False,animations=len(ids),patches=1,channels=len(eb.names),avatarNodes=len(eu.transforms),blendMasks=mask_count,
        unchangedOriginalAvatar=True,unchangedNativeDriverChannels=len(b.names),maxOriginalDriverError=max(r['nativeError'] for r in results),maxShadowError=max(r['shadowError'] for r in results),
        unchangedLowerBodyAndMotionLayerChannels=len(lower_channels),lowerBodyComparedWithV8AcrossAllClips=True,
        additiveNonFootChannelsUnchangedFromV8=True,footLocalYDegrees={'l_foot':20,'r_foot':-20},footAdditiveBasisChecked=True,
        acceptedV10BakedHandPosesPreserved=True,maxBakedHandPositionErrorMetres=max(r['bakedHandPositionError'] for r in results),maxBakedHandQuaternionError=max(r['bakedHandRotationError'] for r in results),
        maxInterpolatedHandPositionErrorMetres=max(r['handPositionError'] for r in results),maxInterpolatedHandQuaternionError=max(r['handRotationError'] for r in results),
        compactBytes=path.stat().st_size,maxStandardGripResidualMetres=max(r['max_standard_grip_error'] for r in build['animations']),plantedClips=0,
        scope='all serialized animations, archive coverage, events, float tracks, native tracks, original shadows and regenerated structural resources; grip and game timing audited separately')
    (W/'animation-final-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
