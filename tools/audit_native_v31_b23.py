"""Verify B23 with NumPy matrices, actual exported layouts and fault injection."""
import json
import math
import sys
from pathlib import Path
import numpy as np

from prepare_native_v31_b23 import ROOT, W, B22, B21, R, SRC, load, save, digest, resources, affine, legacy_arm_math
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData, AnimationData, BonesData
from anim_batch_mod.native_arm_reference import AnimationReference
from anim_batch_mod.processor import _build_tracks, _calculate_world_transforms, _apply_two_bone_ik, WorldTransform
from anim_batch_mod.math3d import matrix3_columns_to_quaternion
from anim_batch_mod.attachment_skeleton import shadows
from anim_batch_mod.motion_skeleton import layers
from lupa.lua51 import LuaRuntime


def array(value):
    values = [value[i] for i in range(1, 13)] if hasattr(value, 'items') else list(value)
    result = np.eye(4)
    result[:3, :4] = np.asarray(values).reshape(4, 3).T
    return result


def flat(matrix):
    return matrix[:3, :4].T.flatten().tolist()


def parenting_check():
    """Audit raw serialized hierarchy/channel edits independently of the builder."""
    import struct
    from anim_batch_mod.archive import TocArchive
    from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID
    folder=W/'native-parenting';name='9ba626afa44a3aa3.patch_5'
    archive=TocArchive.parse_parts((folder/name).read_bytes(),
        (folder/(name+'.gpu_resources')).read_bytes(),(folder/(name+'.stream')).read_bytes())
    assert len(archive.entries)==2 and {key[1] for key in archive.entries}=={UNIT_TYPE_ID,BONE_TYPE_ID}
    old=(W/'v30-avatar.toc').read_bytes()
    revised=bytes(archive.entries[(int('4d1c334d294dfa97',16),UNIT_TYPE_ID)].toc_data)
    assert revised==(W/'runtime-avatar.toc').read_bytes()
    prefix=bytearray(revised[:len(old)]);prefix[52:56]=old[52:56]
    assert prefix==old,'Non-transform Unit section changed'
    before,after=UnitData.parse(old),UnitData.parse(revised)
    meta=load(W/'native-parenting.json')
    assert len(before.parents)==255 and len(after.parents)==260
    def blocks(data):
        offset=struct.unpack_from('<I',data,52)[0];n=struct.unpack_from('<I',data,offset)[0]
        local=[data[offset+16+64*i:offset+16+64*(i+1)] for i in range(n)]
        world=[data[offset+16+64*n+64*i:offset+16+64*n+64*(i+1)] for i in range(n)]
        at=offset+16+128*n
        entries=[data[at+4*i:at+4*(i+1)] for i in range(n)]
        return local,world,entries
    old_local,old_world,old_entries=blocks(old)
    new_local,new_world,new_entries=blocks(revised)
    assert old_local==new_local[:255] and old_world==new_world[:255]
    assert old_entries[:107]==new_entries[:107] and before.name_hashes[:107]==after.name_hashes[:107]
    assert {i for i in range(255) if before.parents[i]!=after.parents[i]}==set(meta['reparentedChildren'])
    def fk(raw,parents):
        cache={};active=set()
        def at(i):
            if i in cache:return cache[i]
            assert i not in active,'Parent cycle'
            active.add(i);v=struct.unpack('<16f',raw[i]);m=np.eye(4)
            m[:3,:3]=np.array(v[:9]).reshape(3,3).T@np.diag(v[12:15]);m[:3,3]=v[9:12]
            p=parents[i];cache[i]=m if p is None else at(p)@m
            active.remove(i);return cache[i]
        return [at(i) for i in range(len(raw))]
    old_fk,new_fk=fk(old_local,before.parents),fk(new_local,after.parents)
    max_bind=max(float(np.max(np.abs(a-b))) for a,b in zip(old_fk,new_fk))
    assert max_bind<2e-5
    old_bone_raw=resources(B22/'runtime/9ba626afa44a3aa3.patch_2',{BONE_TYPE_ID})[(before.bones_ref,BONE_TYPE_ID)]
    old_bones= BonesData.parse(old_bone_raw)
    new_bone_raw=bytes(archive.entries[(after.bones_ref,BONE_TYPE_ID)].toc_data)
    new_bones= BonesData.parse(new_bone_raw)
    assert len(old_bones.names)==len(new_bones.names)
    rows={r['channel']:r for r in meta['rows']}
    for channel in range(len(old_bones.names)):
        expected=rows[channel]['referenceName'] if channel in rows else old_bones.names[channel]
        assert new_bones.names[channel]==expected and new_bones.hashes[channel]==native.bone_name_hash(expected)
        old_index=before.name_hashes.index(old_bones.hashes[channel])
        assert after.name_hashes.index(new_bones.hashes[channel])==old_index,'Animation channel changed target index'
    for row in meta['rows']:
        output,ref=row['outputIndex'],row['referenceIndex']
        assert after.parents[output]==row['parentIndex']
        assert after.name_hashes[output]==native.bone_name_hash(row['name'])
        assert after.name_hashes[output] not in new_bones.hashes
        assert new_world[output]==old_world[ref]
        assert np.max(np.abs(new_fk[output]-old_fk[ref]))<2e-5
    # Avatar meshes/physics have unchanged external payloads as well as unchanged sections.
    path=B22/'runtime/9ba626afa44a3aa3.patch_2'
    with path.open('rb') as stream:
        header=stream.read(72);types,n=struct.unpack_from('<II',header,4);stream.seek(72+32*types)
        records=[struct.unpack('<QQQQQQQIIIIII',stream.read(80)) for _ in range(n)]
    for row in records:
        if row[:2] not in archive.entries:continue
        entry=archive.entries[row[:2]]
        for suffix,offset,size,payload in (('.gpu_resources',row[4],row[9],entry.gpu_data),('.stream',row[3],row[8],entry.stream_data)):
            with Path(str(path)+suffix).open('rb') as stream:stream.seek(offset);assert stream.read(size)==payload
    result=dict(status='PASS',originalNodes=255,outputNodes=260,animationChannels=len(new_bones.names),
        privateReferenceChannels=len(rows),unanimatedNamedOutputs=5,originalChannelIndicesPreserved=True,
        nativeHierarchyAndLocalBytesPreserved=True,oldWorldBindBytesPreserved=True,maximumBindMatrixError=max_bind,
        skinNamesPreserved=True,modelMeshWeightsUnchanged=True,avatarExternalDataUnchanged=True,
        animationResourcesInOverlay=0,changedParents=meta['reparentedChildren'],outputs=meta['rows'],
        patchSha256=digest(folder/name),gameTested=False)
    save(W/'native-parenting-audit.json',result)
    return result


def analyze_live_log(path):
    """Summarize real B23 sessions without treating readback as visible success."""
    from collections import Counter, defaultdict
    path=Path(path);sessions=[];current=None
    profile=load(W/'B23-profile.json')
    axes={p['name']:array(p['axes'])[:3,:3] for p in profile['sync']['pairs']}
    def summary(values):
        if not values:return None
        a=np.asarray(values,dtype=float)
        return dict(count=len(a),min=float(a.min()),median=float(np.median(a)),
            p90=float(np.percentile(a,90)),max=float(a.max()))
    def rotation(values):
        m=array(values)[:3,:3]
        return m/np.linalg.norm(m,axis=0)
    def finish(s):
        if s is None or s['version']!='1.0.3':return
        s['leftMetrics']={k:summary(v) for k,v in s.pop('leftValues').items()}
        s['phaseAngles']={phase:{k:summary(v) for k,v in rows.items()} for phase,rows in s.pop('angles').items()}
        s['localDriverResidualDegrees']={k:summary(v) for k,v in s.pop('localResiduals').items()}
        sessions.append(s)
    for line in path.open(encoding='utf-8',errors='replace'):
        at=line.find('{')
        if at<0:continue
        try:row=json.loads(line[at:])
        except ValueError:continue
        event=row.get('event')
        if event=='loaded':
            finish(current)
            current=dict(start=line[:19],version=row.get('version'),events=Counter(),skipReasons=Counter(),
                leftValues=defaultdict(list),angles=defaultdict(lambda:defaultdict(list)),
                localResiduals=defaultdict(list),largestWorldUnitCount=0,modelMatrixErrorMaximum=0.)
        if current is None or current['version']!='1.0.3':continue
        current['end']=line[:19];current['events'][event]+=1
        if event=='scan':
            current['largestWorldUnitCount']=max([current['largestWorldUnitCount']]+[x['units'] for x in row['worlds']])
        elif event=='complete':current['complete']=row
        elif event=='left_skipped':current['skipReasons'][row.get('reason')]+=1
        elif event=='left_applied':
            for key in ('beforeDistance','afterDistance','afterAngleDegrees','reachResidual'):
                current['leftValues'][key].append(row[key])
        elif event=='sync':
            # These session-local Avatar IDs were matched in the held-weapon
            # samples. They are not persistent IDs or Chef world numbers.
            if (current['start']=='2026-11-05 13:39:30' and row['avatar']!=78) or (
                current['start']=='2026-11-05 13:37:17' and row['avatar']!=71):continue
            phase=row['phase'];nodes=row['nodes']
            current['modelMatrixErrorMaximum']=max(current['modelMatrixErrorMaximum'],row['modelMaxMatrixError'])
            for name,node in nodes.items():current['angles'][phase][name].append(node['nativeSourceAngle'])
            if phase=='render_input':
                for child,parent in (('spine2','spine1'),('chest','spine2')):
                    native_local=rotation(nodes[parent]['nativeWorld']).T@rotation(nodes[child]['nativeWorld'])
                    source_local=(rotation(nodes[parent]['sourceWorld'])@axes[parent]).T@(rotation(nodes[child]['sourceWorld'])@axes[child])
                    error=math.degrees(math.acos(float(np.clip((np.trace(native_local.T@source_local)-1)/2,-1,1))))
                    current['localResiduals'][child].append(error)
                if nodes['chest']['nativeSourceAngle']>current.get('largestChestAngle',-1):
                    current['largestChestAngle']=nodes['chest']['nativeSourceAngle']
                    current['largestChestSample']=dict(wallTime=line[:19],sample=row)
    finish(current)
    assert sessions,'No B23 1.0.3 live sessions found'
    result=dict(status='OBSERVED',log=str(path),logSha256=digest(path),timeZone='Asia/Shanghai',sessions=sessions,
        userReportedLeftHandIneffective=True,userReportedFirstStartBlackScreen=True,
        userReportedGunRaisesWithoutTorso=True,
        firstStartFinding='1.0.3 started and shut down with zero pose writes/refreshes; black-screen cause remains unverified.',
        leftFinding='The sampled wrist and linked model agree after render writes, but the next render input uses a different animated pose. Readback success did not establish visible skinning success.',
        torsoFinding='spine1 largely agrees; spine2 and chest have additional local native/Source residuals, with model/source caches agreeing. Missing native controller rotation is supported; a model cache delay alone does not explain this data.',
        implementedNativeParents=['spine2','chest'],
        addedIndependentMotionProbes=['neck','head','l_clavicle','l_shoulder','l_elbow','r_clavicle','r_shoulder','r_elbow'],
        otherIndependentControllerBindings='Not inferred from bone names alone; await expanded paired samples.',
        nextVersion='1.0.4',nextVersionGameTested=False,gameDeployed=False)
    save(W/'B23-1.0.3-live-analysis.json',result)
    print(json.dumps(dict(status='OBSERVED',sessions=[dict(start=s['start'],end=s['end'],
        stats=s.get('complete',{}).get('stats'),left=s['leftMetrics'],localResiduals=s['localDriverResidualDegrees']) for s in sessions]),ensure_ascii=False,indent=2))


def registration_animation_check():
    """Read packaged clips after all conversion steps, not only the bind equation."""
    report = load(B22 / 'build-report.json')
    manifest = load(B22 / 'source-skeleton.json')
    avatar = UnitData.parse((W / 'v30-avatar.toc').read_bytes())
    original = UnitData.parse((B21 / 'assets/native_avatar-4d1c334d294dfa97.toc').read_bytes())
    bones = BonesData.parse((B21 / 'assets/native-avatar.bones').read_bytes())
    original_count = len(bones.names)
    animation_names = bones.names + [n['name'] for n in native.animation_nodes(manifest)]
    animation_names += [x['name'] for x in layers(manifest)] + [x['name'] for x in shadows(manifest)]
    channel_to_unit = []
    for name in animation_names:
        h = native.bone_name_hash(name)
        channel_to_unit.append(avatar.name_hashes.index(h))
    reference = AnimationReference(R / 'project/refs/arm-reference.patch_0')
    # Stratified deterministic samples, including additive clips for the shadow check.
    ordinary = [x for x in report['animations'] if not x['additive']]
    additive = [x for x in report['animations'] if x['additive']]
    selected = [ordinary[round(i * (len(ordinary)-1)/11)] for i in range(12)]
    selected += [additive[round(i * (len(additive)-1)/3)] for i in range(4)]
    patch = B22 / 'runtime/9ba626afa44a3aa3.patch_2'
    # Read only selected animation entries using the index already parsed by AnimationReference's format.
    wanted_ids = {int(x['id']) for x in selected}
    import struct
    blobs = {}
    with patch.open('rb') as stream:
        header = stream.read(72);types,count = struct.unpack_from('<II', header, 4)
        stream.seek(72+32*types)
        entries = [struct.unpack('<QQQQQQQIIIIII', stream.read(80)) for _ in range(count)]
        for row in entries:
            if row[0] in wanted_ids and row[1] == ANIMATION_TYPE_ID:
                stream.seek(row[2]);blobs[row[0]]=stream.read(row[7])
    assert len(blobs) == len(wanted_ids)
    registration = load(W / 'wrist-registration.json')['hands']
    results = []
    for item in selected:
        clip = AnimationData.parse(blobs[int(item['id'])]);tracks = _build_tracks(clip)
        ref_clip = AnimationData.parse(reference.read(int(item['id'])))
        ref_tracks = _build_tracks(ref_clip)
        maximum = 0.;shadow_maximum = 0.
        for fraction in (0., .2, .5, .8, 1.):
            time = fraction*clip.animation_length*1000.
            if not clip.is_additive:
                local = list(avatar.transforms)
                for ch, ui in enumerate(channel_to_unit):
                    local[ui] = WorldTransform(*(tr[ch].evaluate(time) for tr in tracks))
                world = _calculate_world_transforms(local, avatar.parents)
                ref_local = list(original.transforms)
                for ch, h in enumerate(bones.hashes):
                    ui=original.name_hashes.index(h)
                    ref_local[ui]=WorldTransform(*(tr[ch].evaluate(time) for tr in ref_tracks))
                ref_world = _calculate_world_transforms(ref_local, original.parents)
                for side in ('r', 'l'):
                    row=registration[side]
                    s=world[row.get('animationReference',row['source'])['index']];n=ref_world[row['native']['index']]
                    recovered=array(affine(s.rotation)) @ array(row['sourceToNativeAxes'])
                    target=array(affine(n.rotation))
                    # Interpolated per-joint float tracks need not exactly match world-space reference interpolation.
                    delta=recovered[:3,:3].T @ target[:3,:3]
                    deg=math.degrees(math.acos(float(np.clip((np.trace(delta)-1)/2,-1,1))))
                    maximum=max(maximum,deg)
            shadow_channel = original_count + len(manifest['bones']) + len(layers(manifest)) + 22
            assert manifest['attachmentShadows'][22]['index'] == 84
            # Native output position is swapped in B22; rotation and the shadow are independently retained.
            original_rotation = tracks[1][bones.names.index('attach_hand_r')].evaluate(time)
            shadow_rotation = tracks[1][shadow_channel].evaluate(time)
            shadow_maximum=max(shadow_maximum,1-abs(sum(a*b for a,b in zip(original_rotation,shadow_rotation))))
        results.append(dict(clip=item['id'], additive=item['additive'], samples=5,
            maximumWristAxisDegrees=maximum, shadowRotationQuaternionError=shadow_maximum))
    # Bound reports are evidence, not a false assertion of an exact live controller mapping.
    assert max(x['shadowRotationQuaternionError'] for x in results) < 1e-5
    assert max(x['maximumWristAxisDegrees'] for x in results) < 0.01, results
    save(W / 'packaged-animation-axis-audit.json', dict(status='PASS', clips=results,
        interpretation='Converter wrist-axis registration in 16 packaged clips; not live IK or palm calibration',
        maximumWristAxisDegrees=max(x['maximumWristAxisDegrees'] for x in results),
        gameTested=False))


def run_harness(profile, fixture, harness, source=None):
    vm = LuaRuntime(unpack_returned_tuples=True)
    def values(matrix):
        return vm.table_from(flat(matrix))
    def expected(source, original, native_pose, axes):
        source_m, l, n = array(source), array(original), array(native_pose)
        source_m[:3,:3] /= np.linalg.norm(source_m[:3,:3], axis=0)
        result = source_m @ array(axes) @ l
        result[:3,:3] = n[:3,:3]
        return values(result)
    vm.globals().numpy_target=expected
    vm.globals().numpy_multiply=lambda a,b: values(array(a) @ array(b))
    vm.globals().numpy_relative=lambda a,b: values(np.linalg.inv(array(a)) @ array(b))
    def processor_endpoint(root, mid, hand, target):
        root, mid, hand, target = [array(x) for x in (root, mid, hand, target)]
        matrices = [root, np.linalg.inv(root) @ mid, np.linalg.inv(mid) @ hand]
        local = []
        for m in matrices:
            scales = np.linalg.norm(m[:3,:3], axis=0)
            q = matrix3_columns_to_quaternion((m[:3,:3]/scales).T.tolist())
            local.append(WorldTransform(m[:3,3].tolist(),q,scales.tolist()))
        _apply_two_bone_ik(local,[None,0,1],0,1,2,target[:3,3].tolist(),
            pole_state={},soft_distance=profile['leftGrip']['softDistance'])
        return vm.table_from(_calculate_world_transforms(local,[None,0,1])[2].position)
    vm.globals().processor_endpoint=processor_endpoint
    vm.globals().profile=vm.table_from(profile,recursive=True)
    vm.globals().fixture=vm.table_from(fixture,recursive=True)
    vm.globals().hash_name=native.bone_name_hash
    vm.globals().arm_math=vm.execute(legacy_arm_math())
    vm.globals().module=vm.execute(source if source is not None else (SRC / 'native_grip_transfer_test.lua').read_text(encoding='utf-8'))
    return vm.execute(harness)


def main():
    parenting_check()
    profile = load(W / 'B23-profile.json')
    fixture = load(W / 'runtime-fixture.json')
    test = ROOT / 'HD2PhysBoneCompat/test'
    harness=(test / 'native_grip_transfer_harness.lua').read_text(encoding='utf-8').replace(
        '-- STRICT_ID_FIXTURE',(test / 'strict_id32_fixture.lua').read_text(encoding='utf-8'))
    result=run_harness(profile,fixture,harness)
    logs=list(result['logs'].values())
    (W / 'runtime-fixture.log').write_text('\n'.join(logs),encoding='utf-8')
    events=[json.loads(x) for x in logs]
    observed=[x for x in events if x['event']=='consumer']
    assert any(x['kind']=='foregrip' and 'sourceLeftDistance' in x for x in observed)
    assert all('sourceLeftDistance' not in x for x in observed if x['kind']=='weapon')
    assert all(x['owner']=='unverified' for x in observed)
    assert any(x['event']=='applied' and 'rightWristToMarker' in x
               and np.linalg.norm(array(x['rightWristToMarker'])[:3,3])>.001 for x in events)
    assert any(x['event']=='left_applied' and x['afterDistance']<0.002 and x['afterAngleDegrees']<0.1 for x in events)
    assert any(x['event']=='left_applied' and not x['nativeInContact'] and x['reachResidual']>1 for x in events)
    targets=profile['leftGrip']['weaponTargets']
    assert len(targets)>=100 and '186ea95de7306b1a' in targets and '84354339522c932d' in targets
    assert all('rootToIKLeft' in r for r in targets.values())
    assert set(result['actualWeaponLayouts'].values()) == set(targets), 'Not every resource layout was exercised'
    left_only={resource for resource,row in targets.items() if 'rootToIKRight' not in row}
    assert len(left_only)==10 and set(result['leftOnlyWeaponLayouts'].values())==left_only
    assert 'a8a91eb54892b6b2' in left_only and 'a955c4ea6f6d4203' in left_only
    assert any(x['event']=='mount_skipped' and x['retry']=='next_render' for x in events)
    assert any(x['event']=='left_applied' and x.get('weaponResource')=='26e40437ea275296' for x in events)
    for resource in left_only:
        rows=[x for x in events if x['event']=='consumer' and x['resource']==resource]
        assert rows and all(x['rightMarkerAvailable'] is False and 'predictedRightMarkerError' not in x for x in rows)
    assert any(x['event']=='left_applied' and x.get('weaponResource')=='84354339522c932d' for x in events), \
        'dynamic allowlisted weapon never wrote the left arm'
    assert any(x['event']=='consumer' and x['kind']=='weapon' and 'predictedLeftMarkerError' in x for x in observed)
    assert {x['phase'] for x in events if x['event']=='sync'}=={'update','render_input','render_output'}
    sync={x['phase']: x for x in events if x['event']=='sync' and x['frame']==1002}
    assert sync['update']['nodes']['chest']['modelMatrixError']>0.01
    assert sync['render_input']['nodes']['chest']['modelMatrixError']>0.01
    assert sync['render_output']['nodes']['chest']['modelMatrixError']<1e-6
    old=next(x for x in events if x['event']=='sync' and x['frame']==1001 and x['phase']=='update')
    chest=sync['update']['nodes']['chest']
    assert np.max(np.abs(array(chest['sourceWorld'])-array(old['nodes']['chest']['sourceWorld'])))>0.1
    assert np.max(np.abs(array(chest['nativeWorld'])-array(old['nodes']['chest']['nativeWorld'])))>0.1
    plain={k:(list(v.values()) if hasattr(v,'items') else v) for k,v in result.items() if k!='logs'}
    plain.update(status='PASS',gameTested=False,leftWeaponSelfIkVerified=True,gripNoLongerGatesLeft=True,
        weaponTargetCount=len(targets),leftOnlyTargetCount=len(left_only),
        sourceSha256=digest(SRC / 'native_grip_transfer_test.lua'),
        harnessSha256=digest(test / 'native_grip_transfer_harness.lua'),
        legacyArmMathSha256=digest(W / 'legacy-arm-math.lua'))
    save(W / 'runtime-audit.json',plain)
    registration_animation_check()
    print(json.dumps(plain,ensure_ascii=False,indent=2))


def audit_generated_profile():
    """Exercise the production model compiler with test02's different Source indices."""
    from copy import deepcopy
    from prepare_native_v31_b23 import matrices, compose_source
    from anim_batch_mod.constants import UNIT_TYPE_ID
    project=ROOT/'outputs/native-test02-integrated-20261105'
    cfg=load(project/'calibration/attachment-profile.json')
    exported=project/'gui-attachment-fix-runtime'
    assert load(exported/'calibration/attachment-profile.json')==cfg, 'Published GUI service calibration differs'
    assert digest(exported/'attachment-fix/patch版/9ba626afa44a3aa3.patch_5')==digest(project/'calibration/native-parenting/9ba626afa44a3aa3.patch_5')
    f=deepcopy(load(W/'runtime-fixture.json'))
    compiled=deepcopy(cfg)
    # Only fixture setup uses the historical SMG signature. Actual tested
    # weapons/components are dynamically discovered by the production profile.
    compiled['consumers']=load(W/'B23-profile.json')['consumers']
    def fixture(raw,resource):
        unit=UnitData.parse(raw)
        return dict(hashes=unit.name_hashes,parents=unit.parents,matrices=matrices(unit),resource=resource)
    values=resources(project/'calibration/native-parenting/9ba626afa44a3aa3.patch_5',{UNIT_TYPE_ID})
    f['avatar']=fixture(values[(int(cfg['avatar']['resource'],16),UNIT_TYPE_ID)],cfg['avatar']['resource'])
    models=resources(ROOT/'outputs/native-test02-20261105/models/test02/9ba626afa44a3aa3.patch_0',{UNIT_TYPE_ID})
    f['bodyModels']={res:fixture(models[(int(res,16),UNIT_TYPE_ID)],res) for res in cfg['models']}
    f['model']=next(iter(f['bodyModels'].values()))
    test=ROOT/'HD2PhysBoneCompat/test'
    full=(test/'native_grip_transfer_harness.lua').read_text(encoding='utf8')
    prefix=full[:full.index('reset()\nlocal runtime=make_runtime()')]
    cases=full[full.index('-- Integrated paths omitted'):full.index('check(strictIdStats.invalidArgumentCalls')]
    harness=prefix+'''\nlocal runtime
local lri,lmi,lhi=fullProfile.leftGrip.nodes[2].index+1,fullProfile.leftGrip.nodes[3].index+1,fullProfile.leftGrip.nodes[4].index+1
local lr,lm,lh=fullProfile.leftGrip.outputs[1].index+1,fullProfile.leftGrip.outputs[2].index+1,fullProfile.leftGrip.outputs[3].index+1
'''+cases+"\nreturn {checks=checks,integratedCases=integratedCases,logs=logs}\n"
    harness=harness.replace('-- STRICT_ID_FIXTURE',(test/'strict_id32_fixture.lua').read_text(encoding='utf8'))
    result=run_harness(compiled,f,harness)
    code=compose_source(cfg)
    production=exported/'attachment-fix/lua版/hd2attachmentfix.lua'
    # Newlines around the inserted profile are not meaningful Lua differences.
    assert production.read_text(encoding='utf8').replace('\n\n','\n')==code.replace('\n\n','\n'), 'C#/Python composition diverged'
    (project/'runtime-fixture.log').write_text('\n'.join(result['logs'].values()),encoding='utf8')
    report=dict(status='PASS',checks=result['checks'],integratedCases=result['integratedCases'],
        avatarNodes=cfg['avatar']['count'],modelResources=len(cfg['models']),
        sourceLeftIndex=cfg['sourceLeft']['index'],productionComposerMatchesB23=True,publishedGuiServiceExportVerified=True,
        luaSourceSha256=digest(production),gameTested=False)
    save(project/'runtime-audit.json',report);print(json.dumps(report,ensure_ascii=False))


def analyze_weapon_coverage(path):
    """Attribute the latest completed observations to resources and retain failure evidence."""
    from collections import Counter, defaultdict
    from datetime import datetime
    import hashlib
    path=Path(path); fingerprint=hashlib.sha256(); active=False; loaded=None
    counts=Counter(); skipped=Counter(); by_resource=defaultdict(list); failures=[]; recent_left={}; right=defaultdict(list)
    last_left=None; completed=None; las_samples=[]
    with path.open('rb') as stream:
        for raw in stream:
            fingerprint.update(raw)
            line=raw.decode('utf-8'); at=line.find('{')
            if at<0:continue
            event=json.loads(line[at:]); kind=event.get('event'); stamp=event.get('_date',line[:19])
            if kind=='loaded':
                active=True
                if active:
                    counts.clear(); skipped.clear(); by_resource.clear(); failures=[];recent_left.clear();right.clear()
                    loaded=dict(timestamp=stamp,**event);last_left=None;completed=None;las_samples=[]
            if not active:continue
            counts[kind]+=1
            if kind=='left_applied' and 'weaponResource' in event:
                last_left=dict(timestamp=stamp,**event)
                by_resource[event['weaponResource']].append(event)
                recent_left[(event['avatar'],event['frame'])]=event['weaponResource']
            elif kind=='left_skipped':skipped[event['reason']]+=1
            elif kind=='consumer' and event.get('resource')=='73d84eaae8c75342' and event.get('mountDistance',1)<.002:
                las_samples.append(event)
            elif kind=='applied' and 'rightWristToMarker' in event:
                resource=recent_left.get((event['avatar'],event['frame']))
                if resource:right[resource].append(float(np.linalg.norm(array(event['rightWristToMarker'])[:3,3])))
            elif kind=='disabled':failures.append(dict(timestamp=stamp,lastLeftSample=last_left,**event))
            elif kind=='complete':completed=dict(timestamp=stamp,**event)
    assert loaded and completed, 'No complete session'
    survey=load(ROOT/'outputs/native-weapon-survey-20261105/weapon-grip-survey.json')
    identities={row['resource']:row for row in survey['weapons']}
    previous=load(ROOT/'outputs/native-v33-b23lr-coverage-20261105/B23-profile.json')['leftGrip']['weaponTargets']
    current=load(W/'B23-profile.json')['leftGrip']['weaponTargets']
    def summary(values):
        return dict(count=len(values),minimum=float(min(values)),median=float(np.median(values)),maximum=float(max(values)))
    observations={}
    for resource,rows in by_resource.items():
        observations[resource]=dict(designation=identities[resource].get('designations'),
            name=identities[resource].get('weaponNames'),sampledLeftWrites=len(rows),
            leftResidualMetres=summary([row['afterDistance'] for row in rows]),
            unreachableResidualAgreementMax=max(abs(row['afterDistance']-row['reachResidual']) for row in rows),
            rightWristToMarkerMetres=summary(right[resource]) if right[resource] else None,
            visibleGameResultConfirmed=False)
    added=[dict(resource=resource,designation=identities[resource].get('designations'),
                name=identities[resource].get('weaponNames'),rightMarker=identities[resource]['ikRight'])
           for resource in sorted(set(current)-set(previous))]
    result=dict(status='OBSERVED',logPath=str(path),logSha256=fingerprint.hexdigest(),
        loaded=loaded,completed=completed,eventCounts=dict(counts),leftSkipReasons=dict(skipped),
        perWeapon=observations,failures=failures,addedTargets=added,
        previousTargetCount=len(previous),currentTargetCount=len(current),unresolvedUnitIds=survey['failures'],
        scope='Readback and termination evidence only; no claim of visible grip success or exact triggering action')
    if las_samples:
        weapon=next(row for row in load(W/'runtime-fixture.json')['weapons'] if row['resource']=='73d84eaae8c75342')
        boss=weapon['hashes'].index(native.bone_name_hash('boss'))
        rotation=array(weapon['matrices'][boss])[:3,:3]
        local_angle=math.degrees(math.acos(float(np.clip((np.trace(rotation)-1)/2,-1,1))))
        result['las44RejectedLinkEvidence']=dict(samples=len(las_samples),
            bossToMountDistanceMetres=summary([r['mountDistance'] for r in las_samples]),
            bossToMountAngleDegrees=summary([r['mountAngleDegrees'] for r in las_samples]),
            serializedBossLocalAngleDegrees=local_angle,
            maximumAngleDifferenceDegrees=max(abs(r['mountAngleDegrees']-local_angle) for r in las_samples),
            interpretation='Observed boss rotation matches its serialized local rotation; the prior boss-only rotation gate rejected it. Skeleton/root matching is verified offline, pending live validation.')
    result['comparisonBaselineVersion']='1.0.6'
    if failures:
        result['secondsDisabledBeforeExit']=(datetime.fromisoformat(completed['timestamp'])-
                                            datetime.fromisoformat(failures[-1]['timestamp'])).total_seconds()
    save(W/'weapon-coverage-live-analysis.json',result)
    print(json.dumps(dict(status=result['status'],eventCounts=result['eventCounts'],
        sampledWeaponIds=list(observations),failureReasons=[row['reason'] for row in failures],
        addedTargets=added,output=str(W/'weapon-coverage-live-analysis.json')),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--live-log':analyze_live_log(sys.argv[2])
    elif len(sys.argv)==3 and sys.argv[1]=='--weapon-log':analyze_weapon_coverage(sys.argv[2])
    elif '--generated-test02' in sys.argv:audit_generated_profile()
    else:main()
