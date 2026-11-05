"""Build the isolated B23 wrist-frame transfer test; never deploy to the game."""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import sys
import tomllib
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
sys.path.insert(0, str(ROOT / 'outputs/native-fix-20261103/test-runtime'))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.motion_skeleton import source_local
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_inverse, quat_multiply, quat_rotate
from anim_batch_mod.archive import TocArchive, TocEntry, InlinePatchWriter
from anim_batch_mod.motion_skeleton import relative as relative_pose, matrix as pose_matrix

W = ROOT / 'outputs/native-v34-b23-integrated-20261105'
R = ROOT / 'outputs/native-manual-20261103'
B22 = ROOT / 'outputs/native-v30-b22-20261105'
B21 = ROOT / 'outputs/native-v29-b21-20261105'
OBS = ROOT / 'outputs/native-b21-observation-20261105/20261105-094642'
SURVEY = ROOT / 'outputs/native-weapon-survey-20261105/weapon-grip-survey.json'
SRC = ROOT / 'HD2PhysBoneCompat/src'
PACKAGE = 'B23LR-M-多武器握持修正-1.0.7.zip'
PROJECT_PACKAGE = 'B23LR-M-多武器握持测试工程-1.0.7.zip'
DOC = ROOT / 'docs/native-v34-b23-integrated-20261105.md'
PHYSICS_PACKAGE = 'B23-配套纯物理运行时.zip'


def legacy_arm_math():
    """Reuse the existing pure solver and verified packed-matrix conversion."""
    old = (SRC / 'native_attachments.lua').read_text(encoding='utf-8')
    begin = old.index("local M={VERSION='0.12.1'}")
    end = old.index('-- Source mstudioquatinterpbone_t:', begin)
    math_source = old[begin:end]
    compat = (SRC / 'physbone_compat.lua').read_text(encoding='utf-8')
    begin = compat.index('local function stored9_quaternion(r)')
    end = compat.index('local function quaternion_axis_angle(', begin)
    return math_source + compat[begin:end] + '\nM.quaternion=function(r)return {stored9_quaternion(r)}end\nM.rotate=rot\nreturn M\n'


def compose_source(profile):
    return (SRC / 'native_grip_transfer_test_entry.lua').read_text(encoding='utf-8').replace(
        '-- INSERT LEGACY ARM MATH', legacy_arm_math()).replace(
        '-- INSERT TRANSFER MODULE', (SRC / 'native_grip_transfer_test.lua').read_text(encoding='utf-8')).replace(
        '-- INSERT TRANSFER PROFILE', 'return ' + lua(profile)).replace(
        '-- INSERT ATTACHMENT ADAPTER', (SRC / 'attachment_fix_runtime.lua').read_text(encoding='utf-8'))


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def lua(value):
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return '{' + ','.join(lua(v) for v in value) + '}'
    return '{' + ','.join('[' + lua(k) + ']=' + lua(v) for k, v in value.items()) + '}'


def resources(path, wanted):
    """Read just the requested TOC entries, not the 1.7 GB animation archive."""
    result = {}
    with Path(path).open('rb') as stream:
        header = stream.read(72)
        types, count = struct.unpack_from('<II', header, 4)
        stream.seek(72 + 32 * types)
        entries = [struct.unpack('<QQQQQQQIIIIII', stream.read(80)) for _ in range(count)]
        for row in entries:
            if row[1] in wanted:
                stream.seek(row[2])
                result[(row[0], row[1])] = stream.read(row[7])
    return result


def affine(q, p=(0., 0., 0.), scales=(1., 1., 1.)):
    out = []
    for i, axis in enumerate(((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))):
        out.extend(v * scales[i] for v in quat_rotate(q, axis))
    return out + list(p)


def matrices(unit):
    return [affine(t.rotation, t.position, t.scale) for t in unit.transforms]


from anim_batch_mod.attachment_skeleton import runtime_outputs, transfer_attachments


def write_parenting_patch(extracted, avatar, rig):
    path=B22/'runtime/9ba626afa44a3aa3.patch_2'
    keys={(int('4d1c334d294dfa97',16),UNIT_TYPE_ID),(avatar.bones_ref,BONE_TYPE_ID)}
    entries=[]
    with path.open('rb') as stream:
        header=stream.read(72);types,count=struct.unpack_from('<II',header,4)
        stream.seek(72+32*types)
        rows=[struct.unpack('<QQQQQQQIIIIII',stream.read(80)) for _ in range(count)]
        for row in rows:
            if row[:2] not in keys:continue
            sides=[]
            for suffix,offset,size in (('.gpu_resources',row[4],row[9]),('.stream',row[3],row[8])):
                with Path(str(path)+suffix).open('rb') as side:
                    side.seek(offset);sides.append(side.read(size))
                assert len(sides[-1])==size
            entries.append(TocEntry(row[0],row[1],bytearray(extracted[row[:2]]),*map(bytearray,sides),
                unknown3=row[10],unknown4=row[11]))
    assert len(entries)==2
    folder=W/'native-parenting';folder.mkdir(exist_ok=True)
    writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),folder/'9ba626afa44a3aa3.patch_5',
        {UNIT_TYPE_ID:1,BONE_TYPE_ID:1},standalone=True)
    for entry in entries:writer.append(entry)
    files=writer.finish()
    save(W/'native-parenting.json',dict(rig,files=[dict(name=p.name,sha256=digest(p),bytes=p.stat().st_size) for p in files]))


def build_profile():
    manifest = load(B22 / 'source-skeleton.json')
    report = load(B22 / 'build-report.json')
    assert report['status'] == 'complete' and report['retarget_version'] == 'native-reference-arms-v15'
    extracted = resources(B22 / 'runtime/9ba626afa44a3aa3.patch_2', {UNIT_TYPE_ID, BONE_TYPE_ID})
    avatar_raw = extracted[(int('4d1c334d294dfa97', 16), UNIT_TYPE_ID)]
    avatar = UnitData.parse(avatar_raw)
    native_raw = (B21 / 'assets/native_avatar-4d1c334d294dfa97.toc').read_bytes()
    original = UnitData.parse(native_raw)
    bones = BonesData.parse((B21 / 'assets/native-avatar.bones').read_bytes())
    assert len(avatar.parents) == 255 and len(original.parents) == 107
    assert avatar.name_hashes[:107] == original.name_hashes
    assert avatar.parents[:107] == original.parents
    assert matrices(avatar)[:107] == matrices(original)
    source_offset = 107
    by_driver = {n['driver']: i for i, n in enumerate(manifest['bones']) if n['driver']}
    by_native_name = {name: original.name_hashes.index(h) for name, h in zip(bones.names, bones.hashes)}
    (W/'v30-avatar.toc').write_bytes(avatar_raw)
    bone_key=(avatar.bones_ref,BONE_TYPE_ID)
    avatar_raw,bone_raw,rig=runtime_outputs(avatar_raw,extracted[bone_key],manifest,by_native_name)
    extracted[(int('4d1c334d294dfa97',16),UNIT_TYPE_ID)]=avatar_raw
    extracted[bone_key]=bone_raw
    avatar=UnitData.parse(avatar_raw)
    write_parenting_patch(extracted,avatar,rig)
    (W/'runtime-avatar.toc').write_bytes(avatar_raw)
    rig_rows={r['driver']:r for r in rig['rows']}
    bind = _calculate_world_transforms(original.transforms, original.parents)
    source_bind = [native.local_pose(source_local(n, i, manifest)) for i, n in enumerate(manifest['bones'])]
    reference, _ = native._reference_rotations(manifest['bones'], source_bind,
        [native.row_pose(n['world']) for n in manifest['bones']], bind, by_native_name, manifest)

    def node(name, index=None):
        h = native.bone_name_hash(name)
        index = avatar.name_hashes.index(h) if index is None else index
        assert avatar.name_hashes[index] == h
        return dict(name=name, index=index, parent=avatar.parents[index], hash=h)

    def source(name):
        index = by_driver[name]
        return node(manifest['bones'][index]['name'])

    def reference_source(name):
        return node(rig_rows[name]['referenceName']) if name in rig_rows else source(name)

    target, nr, nl = node('attach_hand_r'), node('r_hand'), node('l_hand')
    shadow = next(x for x in manifest['attachmentShadows'] if x['index'] == target['index'])
    original_mount = node(shadow['name'])
    assert original_mount['parent'] == nr['index'] == target['parent']
    assert shadow['animationChannel'] == bones.names.index('attach_hand_r')
    assert original_mount['index'] == 220 and target['index'] == 84
    assert matrices(avatar)[original_mount['index']] == matrices(original)[target['index']]
    axes, calibration = {}, {}
    for side in ('r', 'l'):
        name = side + '_hand'
        si, ni = by_driver[name], by_native_name[name]
        # Source wrist rotation = native reference wrist rotation * inv(native bind) * source reference.
        # The inverse registration recovers native wrist AXES at the Source wrist origin.
        q = quat_multiply(quat_inverse(reference[si]), bind[ni].rotation)
        axes[side] = affine(q)
        roundtrip = quat_multiply(reference[si], q)
        assert abs(abs(sum(a*b for a, b in zip(roundtrip, bind[ni].rotation))) - 1) < 1e-6
        calibration[side] = dict(source=node(manifest['bones'][si]['name']), native=node(name),
            animationReference=dict(index=source_offset+si),
            sourceReferenceRotation=reference[si], nativeBindRotation=bind[ni].rotation,
            sourceToNativeAxes=axes[side], origin='live Source wrist; zero extra translation',
            scope='Exact converter reference axes; no palm-surface or in-game grip calibration')

    sr, sl = source('r_hand'), source('l_hand')
    watched = [target, nr, nl, sr, sl, original_mount, node('attach_hand_l'), node('weapon_aim'),
        source('r_shoulder'), source('r_elbow'), source('l_shoulder'), source('l_elbow')]
    right_raw = (B21 / 'assets/test01_model-e0b67b19ba91057b.toc').read_bytes()
    current_models = resources(R / 'project/models-o3/test01-O3/9ba626afa44a3aa3.patch_0', {UNIT_TYPE_ID})
    assert right_raw == current_models[(int('e0b67b19ba91057b', 16), UNIT_TYPE_ID)], 'current right model changed'
    right_model = UnitData.parse(right_raw)
    signature = []
    for driver in ('spine1', 'r_shoulder', 'r_elbow', 'r_hand', 'l_hand'):
        av = source(driver)
        mi = right_model.name_hashes.index(av['hash'])
        signature.append(dict(name=av['name'], hash=av['hash'], index=mi,
            parent=right_model.parents[mi], avatarIndex=av['index']))
        if av['index'] not in [x['index'] for x in watched]:
            watched.append(av)
    models = {'e0b67b19ba91057b': dict(kind='model', resource='e0b67b19ba91057b',
        count=len(right_model.parents), nodes=signature)}
    # Reuse B20's body resource selection, deriving B23's five-node signatures
    # from the current exported Units instead of assuming every part has arm indices.
    legacy_models = load(ROOT / 'outputs/native-v28-b20-20261105/B20-R.json')['modelLayouts']
    body_fixtures = {}
    for resource_id, layout in legacy_models.items():
        if layout['ownerSlot'] != 'body':
            continue
        raw = current_models[(int(resource_id, 16), UNIT_TYPE_ID)]
        assert hashlib.sha256(raw).hexdigest() == layout['unitSha256'], 'B20 body resource changed: ' + resource_id
        unit = UnitData.parse(raw)
        nodes = []
        for av in signature:
            index = unit.name_hashes.index(av['hash'])
            nodes.append(dict(name=av['name'], hash=av['hash'], index=index,
                parent=unit.parents[index], avatarIndex=av['avatarIndex']))
        models[resource_id] = dict(kind='model', resource=resource_id, count=len(unit.parents), nodes=nodes)
        body_fixtures[resource_id] = dict(hashes=unit.name_hashes, parents=unit.parents,
            matrices=matrices(unit), resource=resource_id)
    consumers, fixtures = {}, {}
    for kind, id_, filename, root_name, markers in (
        ('weapon', '186ea95de7306b1a', 'weapon-186ea95de7306b1a.toc', 'boss',
         ('boss', 'IK_right', 'IK_left', 'attach_underbarrel')),
        ('foregrip', 'f9df21c8e52cac95', 'foregrip-f9df21c8e52cac95.toc', 'skeleton',
         ('skeleton', 'IK_left'))):
        raw = (B21 / 'assets' / filename).read_bytes()
        unit = UnitData.parse(raw)
        rows = []
        for name in markers:
            i = unit.name_hashes.index(native.bone_name_hash(name))
            rows.append(dict(name=name, index=i, parent=unit.parents[i], hash=unit.name_hashes[i]))
        consumers[id_] = dict(kind=kind, resource=id_, count=len(unit.parents), nodes=rows,
            root=next(x['index'] for x in rows if x['name'] == root_name), order=0 if kind=='weapon' else 1)
        fixtures[kind] = dict(hashes=unit.name_hashes, parents=unit.parents, matrices=matrices(unit),
                             resource=id_)
    reference_matrices = load(OBS / 'native-grip-reference-matrices.json')
    # 2026-11-05 user decisions: the left hand always follows the held weapon's own
    # IK_left marker. Right IK is optional: the right-mount transfer never uses it.
    # Static boss->IK matrices come from the offline survey; the SMG row is validated
    # against B21 live observation below, proving the shared serialization convention.
    survey = load(SURVEY)
    weapon_targets = {}
    from survey_native_weapon_grips import Survey
    reader = Survey()
    fixtures['weapons'] = []
    for item in survey['weapons']:
        if not item['ikLeft']: continue
        if item['rootName'] not in ('boss', 'skeleton'): continue
        if not item.get('rootToIKLeft'): continue
        weapon_targets[item['resource']] = dict(rootName=item['rootName'],
            rootToIKLeft=item['rootToIKLeft'],
            leftPolicy=('aim_only' if set(item.get('equipmentTypes', [])) & {10,31} and item['resource']!='9eb160830321bfd6' else 'always'))
        if item.get('rootToIKRight'):
            weapon_targets[item['resource']]['rootToIKRight'] = item['rootToIKRight']
        file_id = int(item['resource'], 16)
        entry = next((reader.archive(archive).entries[(file_id, UNIT_TYPE_ID)]
                      for archive in reader.unit_archives[file_id]
                      if (file_id, UNIT_TYPE_ID) in reader.archive(archive).entries), None)
        assert entry is not None, 'Missing actual weapon fixture: ' + item['resource']
        unit = UnitData.parse(entry.toc_data)
        weapon_targets[item['resource']]['linkNodes'] = [n for n in ('skeleton','root','boss') if native.bone_name_hash(n) in unit.name_hashes]
        assert native.bone_name_hash('IK_left') in unit.name_hashes
        assert native.bone_name_hash(item['rootName']) in unit.name_hashes
        fixtures['weapons'].append(dict(hashes=unit.name_hashes, parents=unit.parents,
            matrices=matrices(unit), resource=item['resource'], rootName=item['rootName']))
    fixtures['carried'] = []
    for resource_id in ('a9936cbe561e8180','db50297b40133d12','4851d75853622a47','7686544f539bb9b7','16f397ca5f51f271'):
        file_id=int(resource_id,16)
        entry=next(reader.archive(a).entries[file_id,UNIT_TYPE_ID] for a in reader.unit_archives[file_id]
                   if (file_id,UNIT_TYPE_ID) in reader.archive(a).entries)
        unit=UnitData.parse(entry.toc_data)
        fixtures['carried'].append(dict(hashes=unit.name_hashes,parents=unit.parents,matrices=matrices(unit),resource=resource_id))
    reader.db.close()
    assert '186ea95de7306b1a' in weapon_targets, 'SMG baseline missing from survey'
    baseline_error = max(abs(a - b) for a, b in zip(
        weapon_targets['186ea95de7306b1a']['rootToIKRight'],
        reference_matrices['right']['weaponBossToIKRight']))
    assert baseline_error < 1e-6, 'survey/observation convention diverged: %g' % baseline_error
    save(W / 'weapon-targets.json', dict(source=str(SURVEY), convention='root local chain (relToRoot)',
        count=len(weapon_targets), leftOnlyCount=sum('rootToIKRight' not in row for row in weapon_targets.values()),
        smgStaticVsObservedMaxError=baseline_error, targets=weapon_targets))
    legacy_left = next(c for c in load(ROOT / 'outputs/native-v28-b20-20261105/B20-R.json')['armChains'] if c['side'] == 'l')
    left_nodes = [reference_source(n) for n in ('l_clavicle', 'l_shoulder', 'l_elbow', 'l_hand')]
    assert [n['index'] for n in left_nodes] == [legacy_left[k] for k in ('parent', 'root', 'mid', 'hand')]
    assert all(b['parent'] == a['index'] for a, b in zip(left_nodes, left_nodes[1:]))
    sync_pairs = []
    for driver in ('hips','spine1','spine2','chest','neck','head',
                   'l_clavicle','l_shoulder','l_elbow','l_hand','r_clavicle','r_shoulder','r_elbow','r_hand'):
        si, ni = by_driver[driver], by_native_name[driver]
        sync_pairs.append(dict(name=driver, native=node(driver), source=source(driver),
            axes=affine(quat_multiply(quat_inverse(reference[si]), bind[ni].rotation))))
        if driver in rig_rows:sync_pairs[-1]['reference']=reference_source(driver)
    # Additional left/telemetry nodes are verified inside their optional paths;
    # they must not tighten the already proven right-hand selection gate.
    for resource_id, model in models.items():
        raw = current_models[(int(resource_id, 16), UNIT_TYPE_ID)]
        unit = UnitData.parse(raw)
        model['observeNodes'] = [dict(name=p['source']['name'], index=unit.name_hashes.index(p['source']['hash']),
            avatarIndex=p['source']['index'], driver=p['name']) for p in sync_pairs]
    left_outputs=[source(n) for n in ('l_shoulder','l_elbow','l_hand')]
    left_indices = {n['index'] for n in left_outputs}
    body_outputs=[]
    for name in ('spine2','chest'):
        out=source(name);local=list(matrices(avatar)[out['index']])
        local[:9]=affine(quat_multiply(quat_inverse(bind[by_native_name[name]].rotation),reference[by_driver[name]]))[:9]
        source_parent_index=manifest['bones'][by_driver[name]]['parent']
        body_outputs.append(dict(node=out,native=node(name),reference=reference_source(name),
            positionParent=node(manifest['bones'][source_parent_index]['name']),localPose=local))
    converter_options = tomllib.loads((R / 'project/config.toml').read_text(encoding='utf-8-sig'))['native_skeleton']
    profile = dict(version=1, variant='test01-v34-B23LR-M', packageName=PACKAGE,
        axisRegistration='converter-reference-rotation',
        avatar=dict(kind='avatar', resource='4d1c334d294dfa97', count=len(avatar.parents), nodes=watched), models=models,
        consumers=consumers, target=target, nativeRight=nr, nativeLeft=nl, sourceRight=sr, sourceLeft=sl,
        originalMount=original_mount, rightAxes=axes['r'], leftAxes=axes['l'],
        protected=[dict(x, world=x['name']!='weapon_aim') for x in watched
                   if x['index']!=target['index'] and x['index'] not in left_indices],
        bodySync=dict(enabled=True,outputs=body_outputs,mode='native_parent_unanimated_output'),
        leftGrip=dict(enabled=True, nodes=left_nodes, outputs=left_outputs,
            weaponTargets=weapon_targets,
            contactMetres=0.002, contactDegrees=0.1,
            linkMetres=0.002, linkDegrees=0.1, hingeAxis=legacy_left['hingeAxis'],
            forearmHingeAxis=legacy_left['forearmHingeAxis'],
            softDistance=converter_options.get('grip_soft_distance', 0.0),
            reachPolicy='anim_batch_mod.processor._apply_two_bone_ik', requireNativeContact=False),
        sync=dict(enabled=True, seconds=0.2, maxSamples=1800, pairs=sync_pairs,
            aim=node('weapon_aim'), reference='same-callback numeric poses; weapon aim is not a camera sample'),
        weaponRight=reference_matrices['right']['weaponBossToIKRight'],
        weaponForegripLeft=reference_matrices['left']['weaponBossToForegripIKLeft'],
        minNodes=3, maxNodes=512, maxRecords=50000,
        scanSeconds=0.5, logSeconds=0.2, consumerRadius=3.0, maxWristMountDistance=0.5,
        matchTolerance=0.001, localTolerance=0.00002, worldTolerance=0.002)
    profile['attachments'] = transfer_attachments(avatar,manifest,by_native_name,reference,bind)
    corrected = {row['node']['index'] for row in profile['attachments']}
    profile['protected'] = [row for row in profile['protected'] if row['index'] not in corrected]
    fixtures.update(avatar=dict(hashes=avatar.name_hashes, parents=avatar.parents, matrices=matrices(avatar),
        resource='4d1c334d294dfa97'), model=dict(hashes=right_model.name_hashes, parents=right_model.parents,
        matrices=matrices(right_model), resource='e0b67b19ba91057b'), bodyModels=body_fixtures)
    fixtures['animationIndices']=[avatar.name_hashes.index(h) for h in BonesData.parse(bone_raw).hashes]
    save(W / 'B23-profile.json', profile)
    save(W / 'runtime-fixture.json', fixtures)
    save(W / 'wrist-registration.json', dict(status='OFFLINE_CONVERTER_AXES_VERIFIED', hands=calibration,
        dynamicReference=dict(node=original_mount, sourceChannel=shadow['animationChannel'],
            read='local_pose every render; copied before target write',
            limitation='Original animation shadow may not include controller-only live rewrites'),
        v30OriginalNativeBindMatchesB21=True, palmSurfaceCalibrated=False, gameTested=False,
        provenance={str(p): digest(p) for p in (
            B22 / 'source-skeleton.json', B22 / 'build-report.json',
            ROOT.parent / 'native_skeleton.py', ROOT.parent / 'native_arm_reference.py',
            ROOT.parent / 'attachment_skeleton.py', OBS / 'native-grip-reference-matrices.json')}))
    return profile


def zip_folder(folder, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(folder.iterdir()):
            if file.is_file():
                archive.write(file, file.name)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
    return dict(name=str(path.relative_to(W)), sha256=digest(path), bytes=path.stat().st_size)


def main():
    W.mkdir(parents=True, exist_ok=True)
    profile = build_profile()
    code = compose_source(profile)
    (W / 'legacy-arm-math.lua').write_text(legacy_arm_math(), encoding='utf-8')
    vm = LuaRuntime(unpack_returned_tuples=True)
    valid, error = vm.eval('function(s) local f,e=loadstring(s);return f~=nil,e end')(code)
    assert valid, error
    body = code.encode('utf-8')
    (W / 'hd2attachmentfix-B23.lua').write_bytes(body)
    old_patch = (B22 / 'attachment-fix-runtime/patch版/9ba626afa44a3aa3.patch_4').read_bytes()
    header = old_patch[:192]
    assert struct.unpack_from('<I', header)[0] == 0xf0000011
    assert struct.unpack_from('<Q', header, 120)[0] == 192
    payload = struct.pack('<II', len(body), 2) + body
    patch = bytearray(header) + payload
    patch.extend(bytes(-len(patch) % 16))
    struct.pack_into('<Q', patch, 32, len(patch))
    struct.pack_into('<I', patch, 160, len(payload))
    parsed = TocArchive.parse_parts(patch)
    assert len(parsed.entries) == 1
    assert bytes(next(iter(parsed.entries.values())).toc_data) == payload
    folder = W / 'runtime'
    folder.mkdir(exist_ok=True)
    patch_name = '9ba626afa44a3aa3.patch_4'
    (folder / patch_name).write_bytes(patch)
    for ext in ('.stream', '.gpu_resources'):
        (folder / (patch_name + ext)).write_bytes(b'')
    manifest = dict(Version=1, Guid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'hd2modmanager:test01:B23:LR-M')),
        Name='[骨骼挂点修正] test01 B23-LR-M 1.0.7 挂点整合',
        Description='B23 1.0.7：修正 LAS-44 链接识别，补充副武器握持策略、左右手单持物品、部件刷新和 21 个非头部挂点。沿用本枪 IK_left、原骨长和越界恢复。完整包包含 Lua 与配套 260 节点骨架，停用旧 B23 包后启用。离线通过，游戏效果待验证。')
    save(folder / 'manifest.json', manifest)
    doc = DOC
    shutil.copy2(doc, folder / '测试说明.md')
    (W / 'container-header.bin').write_bytes(header)
    shutil.copy2(folder / 'manifest.json', W / 'manifest.json')
    shutil.copy2(doc, W / '测试说明.md')
    physics = W / 'physics-companion'
    physics.mkdir(exist_ok=True)
    for p in (B22 / 'physics-runtime/patch版').iterdir():
        if p.is_file():
            shutil.copy2(p, physics / p.name)
    (physics / '测试说明.md').write_text('B23 配套纯物理包，字节沿用 B22 导出。\n\n'
        '启用此包和 B23 挂点测试包；停用旧版合并物理/挂点 Lua。单独启用此包可作无挂点写入对照。\n', encoding='utf-8')
    physics_lua = (B22 / 'physics-runtime/lua版/hd2physbone.lua').read_text(encoding='utf-8-sig')
    assert 'local options = { compat = PhysBoneCompat, mode = \'external\' }' in physics_lua
    assert 'local NativeAttachments =' not in physics_lua and 'local NativeAttachmentProfile =' not in physics_lua
    for file in (W/'native-parenting').iterdir():
        if file.is_file():shutil.copy2(file,folder/file.name)
    physics_target = W / 'AB测试' / PHYSICS_PACKAGE
    physics_target.parent.mkdir(parents=True, exist_ok=True)
    old_physics = ROOT / 'outputs/native-v31-b23-20261105/AB测试' / PHYSICS_PACKAGE
    if old_physics.exists():
        # Rebuilds only differ by ZIP timestamps; keep the delivered bytes identical.
        with zipfile.ZipFile(old_physics) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist()) == {p.name for p in physics.iterdir() if p.is_file()}
            for name in archive.namelist():
                import hashlib as _hashlib
                assert _hashlib.sha256(archive.read(name)).hexdigest() == digest(physics / name), name
        shutil.copy2(old_physics, physics_target)
        physics_record = dict(name=str(physics_target.relative_to(W)), sha256=digest(physics_target),
            bytes=physics_target.stat().st_size)
        packages = [zip_folder(folder, W / 'AB测试' / PACKAGE), physics_record]
    else:
        packages = [zip_folder(folder, W / 'AB测试' / PACKAGE),
                    zip_folder(physics, W / 'AB测试' / PHYSICS_PACKAGE)]
    save(W / 'static-packages.json', packages)
    save(W / 'build-audit.json', dict(status='PASS', luaVersion='5.1', profile=profile['variant'],
        addonResource=f'{struct.unpack_from("<Q", header, 104)[0]:016x}',
        patchSha256=digest(folder / patch_name), sourceSha256=digest(W / 'hd2attachmentfix-B23.lua'),
        physicsCompanionByteIdentical=True, rightTarget='attach_hand_r', leftWrites=True,
        leftTargets=[n['name'] for n in profile['leftGrip']['outputs']],
        legacyArmMathSha256=digest(W / 'legacy-arm-math.lua'), upperBodyObservationOnly=False,
        nativeParentOutputs=['spine2','chest'],leftOutputsUnanimated=True,avatarNodes=profile['avatar']['count'],
        parentingPatchSha256=digest(W/'native-parenting/9ba626afa44a3aa3.patch_5'),
        productionStubModified=True, gameDeployed=False, gameTested=False,
        leftTarget='weapon-self IK_left', weaponTargetCount=len(profile['leftGrip']['weaponTargets']),
        weaponTargetsSource=str(SURVEY)))
    print(json.dumps(dict(status='PASS', packages=packages, output=str(W)), ensure_ascii=False, indent=2))


def _upgrade_reference_job(prior, original, bones_raw, unit_raw, manifest):
    from anim_batch_mod.attachment_skeleton import upgrade_reference_animation
    return upgrade_reference_animation(prior,original,BonesData.parse(bones_raw),UnitData.parse(unit_raw),manifest)


def upgrade_test02_companion():
    """Reuse validated test02 retargeted tracks and append the missing references."""
    import copy
    from anim_batch_mod.archive import PackageStore, ResourceIndex
    from anim_batch_mod.constants import ANIMATION_TYPE_ID, STATE_MACHINE_TYPE_ID
    from anim_batch_mod.attachment_skeleton import upgrade_reference_animation
    previous=ROOT/'outputs/native-test02-20261105/animations'
    project=ROOT/'outputs/native-test02-integrated-20261105'
    output=project/'animations-upgraded'
    output.mkdir(exist_ok=False)
    manifest=load(project/'calibration/source-skeleton.json')
    old_report=load(previous/'build-report.json');assert old_report['status']=='complete'
    old_path=previous/'runtime/9ba626afa44a3aa3.patch_2'
    rig_path=project/'calibration/native-parenting/9ba626afa44a3aa3.patch_5'
    rig=TocArchive.parse_parts(rig_path.read_bytes(),Path(str(rig_path)+'.gpu_resources').read_bytes(),Path(str(rig_path)+'.stream').read_bytes())
    store=PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'))
    index=ResourceIndex(store,output/'resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID})
    index.load_or_build();cache={}
    _,original_unit=native.resolve_inline(index,store,int(manifest['referenceUnit'],0),UNIT_TYPE_ID,cache)
    unit=UnitData.parse(original_unit.toc_data)
    _,bone_entry=native.resolve_inline(index,store,unit.bones_ref,BONE_TYPE_ID,cache)
    bones=BonesData.parse(bone_entry.toc_data)
    _,state=native.resolve_inline(index,store,unit.state_machine_ref,STATE_MACHINE_TYPE_ID,cache)
    runtime=output/'runtime';runtime.mkdir()
    writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),runtime/'9ba626afa44a3aa3.patch_2',
        {UNIT_TYPE_ID:1,BONE_TYPE_ID:1,STATE_MACHINE_TYPE_ID:1,ANIMATION_TYPE_ID:len(old_report['animations'])},standalone=True)
    for entry in rig.entries.values():writer.append(entry)
    state=copy.deepcopy(state);state.toc_data,masks=native.append_state_machine_masks(state.toc_data,bones,manifest);writer.append(state)
    report=dict(status='building',game_tested=False,source=str(previous),animations=[],expected_animations=len(old_report['animations']),
        source_bones=len(manifest['bones']),addedReferenceChannels=len(manifest['attachmentShadows']),blend_masks_extended=masks,
        existingRetargetSwapAndEventsPreserved=True,allOriginalReferenceKeysChecked=True,avatarNodes=241)
    def save_report():save(output/'build-report.json',report)
    save_report()
    try:
        with old_path.open('rb') as stream:
            header=stream.read(72);types,count=struct.unpack_from('<II',header,4);stream.seek(72+32*types)
            records={row[:2]:row for row in [struct.unpack('<QQQQQQQIIIIII',stream.read(80)) for _ in range(count)]}
            from collections import deque
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=8) as pool:
                pending=deque();iterator=iter(old_report['animations'])
                def enqueue():
                    item=next(iterator,None)
                    if item is None:return
                    file_id=int(item['id']);row=records[file_id,ANIMATION_TYPE_ID]
                    stream.seek(row[2]);prior=stream.read(row[7])
                    _,original=native.resolve_inline(index,store,file_id,ANIMATION_TYPE_ID,cache)
                    pending.append((item,row,pool.submit(_upgrade_reference_job,prior,bytes(original.toc_data),
                        bytes(bone_entry.toc_data),bytes(original_unit.toc_data),manifest)))
                for _ in range(16):enqueue()
                while pending:
                    item,row,future=pending.popleft();data=future.result();file_id=int(item['id'])
                    writer.append(TocEntry(file_id,ANIMATION_TYPE_ID,bytearray(data),bytearray(),bytearray(),unknown3=row[10],unknown4=row[11]))
                    report['animations'].append(dict(item,originalReferenceChannelsVerified=True))
                    number=len(report['animations'])
                    if number%100==0:save_report();print('Reference channels',number,'/',len(old_report['animations']),flush=True)
                    enqueue()
        files=writer.finish();report.update(status='complete',files=[dict(path='runtime/'+p.name,sha256=digest(p),bytes=p.stat().st_size) for p in files]);save_report()
        save(output/'source-skeleton.json',manifest)
        print('test02 reference upgrade complete',flush=True)
    except Exception as error:
        report.update(status='failed',error=str(error));save_report();raise
    finally:index.close()


if __name__ == '__main__':
    if '--upgrade-test02' in sys.argv:upgrade_test02_companion()
    else:main()

