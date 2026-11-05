"""Build B20 from the exact tested B19-R: native orientation plus left probes."""
import copy
import os
import shutil
import struct
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
from sync_native_grip_alignment import sync

os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime

W = ROOT / 'outputs/native-v28-b20-20261105'
OLD = ROOT / 'outputs/native-v27-b19-20261105'
R = ROOT / 'outputs/native-manual-20261103'
NAMES = {'R': 'B20-R-右手保留原生朝向.zip', 'A': 'B20-A-左手挂点对齐.zip',
         'H': 'B20-H-左手腕对齐.zip', 'T': 'B20-T-左腕辅助骨对齐.zip'}


def main():
    W.mkdir(exist_ok=True)
    sync()
    prior = load(OLD / 'B19-R.json')
    old_scope = load(OLD / 'scope-audit.json')
    assert prior['nativeGripAlignment']['exclusive'] and not prior['armSync'] and not prior['armGripSync']
    avatar_path = R / 'project/animations/runtime/9ba626afa44a3aa3.patch_2'
    model_path = R / 'project/models-o3/test01-O3/9ba626afa44a3aa3.patch_0'
    avatar = next(iter(units(avatar_path).values()))
    models = units(model_path)
    assert len(avatar.parents) == prior['expectedAvatarNodes'] == 255
    assert prior['nativeSkeletonNodes'] == 107 and prior['sourceSkeletonNodes'] == 89
    prefix = 'hd2n_4e4fb4fa303d_'
    names = {46: 'l_elbow', 47: 'l_hand', 48: 'attach_hand_l', 64: 'l_hand_twist',
             71: 'r_hand', 84: 'attach_hand_r', 85: 'weapon_aim',
             114: prefix + 'anim_007_l_elbow', 115: prefix + 'anim_008_l_hand',
             138: prefix + 'anim_031_r_hand', 131: prefix + 'aux_024_valvebiped_l_weapon_bone',
             154: prefix + 'aux_047_valvebiped_weapon_bone', 171: prefix + 'aux_064_valvebiped_handl'}

    def spec(index):
        name = names[index]
        assert avatar.name_hashes[index] == bone_name_hash(name), name
        return dict(name=name, index=index, parentIndex=avatar.parents[index], hash=avatar.name_hashes[index])

    expected_parents = {46: 44, 47: 46, 48: 47, 64: 46, 84: 71, 85: 84,
                        114: 113, 115: 114, 131: 115, 138: 137, 154: 138, 171: 114}
    assert all(avatar.parents[i] == p for i, p in expected_parents.items())
    pairs = {key: dict(target=spec(t), source=spec(s), rotationMode='native-world')
             for key, t, s in [('R', 84, 154), ('A', 48, 131), ('H', 47, 115), ('T', 64, 171)]}
    source_indices = set(range(107, 196))
    affected = {}
    for p in pairs.values():
        selected = {p['target']['index']}
        while True:
            expanded = selected | {i for i, parent in enumerate(avatar.parents) if parent in selected}
            if expanded == selected:
                break
            selected = expanded
        assert not selected & source_indices and 103 not in selected
        affected[p['target']['name']] = sorted(selected)
    reference = next(row for row in prior['vpk'] if row['standardName'] == 'attach_hand_l')
    references = [reference['referenceIndex'], reference['sourceReferenceIndex']]
    assert references == [219, 244]
    for index, key in zip(references, ('referenceName', 'sourceReferenceName')):
        assert avatar.parents[index] == 47 and avatar.name_hashes[index] == bone_name_hash(reference[key])
    assert affected == {'attach_hand_r': [84, 85], 'attach_hand_l': [48],
                        'l_hand': list(range(47, 64)) + references, 'l_hand_twist': [64]}
    source_anchors = [115, 131, 138, 154, 171]
    model_sources = {}
    assert len(prior['modelLayouts']) == 11
    for resource in prior['modelLayouts']:
        unit = models[resource]
        model_sources[resource] = {}
        for i in source_anchors:
            index = unit.name_hashes.index(avatar.name_hashes[i])
            assert unit.name_hashes[unit.parents[index]] == avatar.name_hashes[avatar.parents[i]]
            model_sources[resource][names[i]] = index
    old_source = (W / 'baseline/native_attachments.lua').read_text(encoding='utf-8-sig')
    assert digest(W / 'baseline/native_attachments.lua') == old_scope['sourceSha256']['native_attachments.lua']
    assert digest(W / 'baseline/native_grip_alignment.lua') == old_scope['sourceSha256']['native_grip_alignment.lua']
    new_source = (ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    original = (OLD / 'hd2physbone-B19-R.lua').read_text(encoding='utf-8-sig')
    assert original.count(old_source) == 1
    updated = original.replace(old_source, new_source)
    marker = 'local NativeAttachmentProfile = (function()\n'
    assert updated.count(marker) == 1
    start = updated.index(marker) + len(marker)
    end = updated.index('\nend)()', start)
    old_profile_source = updated[start:end]
    header = (OLD / 'runtime/R/9ba626afa44a3aa3.patch_0').read_bytes()[:192]
    assert len(header) == 192
    manifest = load(OLD / 'runtime/R/manifest.json')
    descriptions = {'R': '右手只对齐位置，保留当帧原生朝向与缩放。',
                    'A': '在 R 基线上，增加原生左手挂点位置对齐。',
                    'H': '在 R 基线上，增加原生左手腕位置对齐。',
                    'T': '在 R 基线上，增加原生左腕辅助骨位置对齐。'}
    packages = []
    pack.WORK = W
    vm = LuaRuntime()
    for variant in NAMES:
        p = copy.deepcopy(prior)
        p.update(revision='test01-v28-B20-' + variant, armSync=False, armGripSync=False, diagnosticMode='apply')
        for key in ('attachmentProbe', 'sceneRoundtrip', 'sceneObservation'):
            p[key]['enabled'] = False
        p['nativeGripAlignment'] = dict(enabled=True, exclusive=True, variant=variant,
            pairs=copy.deepcopy([pairs['R']] + ([] if variant == 'R' else [pairs[variant]])),
            checks=[spec(i) for i in sorted(names)], watchSources=[spec(i) for i in source_anchors],
            preserveChildren=[spec(85)], scalePolicy='preserve-native-world',
            orientationPolicy='native-world-position-only', logFrames=120,
            consumerObservation=dict(enabled=True, rightSourceIndex=154, leftSourceIndex=131,
                                     leftWristIndex=115, maxUnits=12, maxDistance=3))
        profile_source = '-- B20: Source anchors read-only; preserve native aiming basis and align position.\nreturn ' + lua(p) + '\n'
        code = updated[:start] + profile_source + updated[end:]
        assert vm.eval('function(s) local f,e=loadstring(s);return f~=nil,e end')(code)[0], variant
        assert (code[:start] + old_profile_source + code[start + len(profile_source):]).replace(new_source, old_source) == original
        body = code.encode('utf-8')
        payload = struct.pack('<II', len(body), 2) + body
        patch = bytearray(header) + payload
        patch.extend(bytes(-len(patch) % 16))
        struct.pack_into('<Q', patch, 32, len(patch))
        struct.pack_into('<I', patch, 160, len(payload))
        parsed = TocArchive.parse_parts(patch)
        assert len(parsed.entries) == 1 and next(iter(parsed.entries.values())).toc_data == payload
        folder = W / 'runtime' / variant
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / '9ba626afa44a3aa3.patch_0'
        path.write_bytes(patch)
        for suffix in ('.stream', '.gpu_resources'):
            path.with_name(path.name + suffix).write_bytes(b'')
        m = dict(manifest, Name='test01 B20-' + variant,
                 Description=descriptions[variant] + ' test01 骨骼只读。每次只启用一个 test01 Lua。')
        save_json(folder / 'manifest.json', m)
        shutil.copy2(ROOT / 'docs/native-v28-B20-20261105.md', folder / '测试说明.txt')
        save_json(W / ('B20-' + variant + '.json'), p)
        (W / ('hd2physbone-B20-' + variant + '.lua')).write_bytes(body)
        packages.append(pack.archive('AB测试/' + NAMES[variant], files(folder)))
    save_json(W / 'static-packages.json', packages)
    save_json(W / 'mapping-audit.json', dict(status='PASS', indexBase=0, candidates=pairs,
        affectedWorldIndices=affected, sourceBoneIndices=sorted(source_indices),
        sourceDescendantsUnaffected=True, hellpadSocketUnaffected=True, modelSourceIndices=model_sources,
        inactiveLegacyReferenceWorldIndices=references, legacyReferenceLocalsPreserved=True,
        noUnitOrAnimationEdits=True, weaponAimLocalPreserved=True,
        bindingCalibrationVerified=False, leftDriverIdentified=False,
        evidence='B19-LR left output readbacks passed without user-observed left movement. B20 is pending a game trial.'))
    source_files = ['native_attachments.lua', 'native_grip_alignment.lua', 'physbone_runtime.lua',
                    'native_attachment_probe.lua', 'native_scene_observer.lua', 'native_scene_roundtrip.lua']
    source_sha = {name: digest(ROOT / 'HD2PhysBoneCompat/src' / name) for name in source_files}
    assert all(source_sha[name] == old_scope['sourceSha256'][name] for name in source_files[2:])
    asset_sha = {str(path.relative_to(R)): digest(path) for path in
                 (avatar_path, model_path, R / 'test01-配套动画.zip', R / 'test01-模型材质.zip')}
    assert asset_sha == old_scope['assetSha256']
    historical = ['delivery-verification.json', '先读我-B19.md', 'B19-R.json', 'hd2physbone-B19-R.lua']
    historical += [row['name'] for row in load(OLD / 'delivery-verification.json')['packages']]
    save_json(W / 'scope-audit.json', dict(status='PASS', baseline='B19-R', sourceSha256=source_sha,
        assetSha256=asset_sha, historicalB19Sha256={name: digest(OLD / name) for name in historical},
        legacyArmSyncDisabled=True, legacyAttachmentAndProcedureWritesBypassed=True,
        probeDisabled=True, directModelOrSourceWrites=False, equipmentRelink=False,
        consumerObservationReadOnly=True, originalB18DiscoveryOptInDisabled=True,
        gameTested=False, gameDeployed=False))
    feedback = load(W / 'evidence/B19-comparison.json')
    assert feedback['status'] == 'PASS'
    left = [s['targets']['attach_hand_l'] for s in feedback['sessions'] if s['variant'] == 'B19-LR']
    assert len(left) == 1 and left[0]['samples'] == 161 and left[0]['maxMatrixError'] < 1e-7
    save_json(W / 'evidence/B19-user-feedback.json', dict(
        source='User messages in the current conversation',
        rightAndLR='右手成功握住武器，上下摆动视觉也正常，武器大概扭转了90度，需要纠正，左手无变化',
        orientationClarification='枪口朝上，握把朝内，同时枪身大概有20度的倾斜',
        correctedAxisConfirmed=False, leftWriteReadback=left[0],
        b20Strategy='Keep native world basis and scale; copy Source anchor position only; compare R/A/H/T.'))
    print('Prepared B20 R/A/H/T: four isolated variants; 11 model layouts and unchanged B19 assets verified.')


if __name__ == '__main__':
    main()
