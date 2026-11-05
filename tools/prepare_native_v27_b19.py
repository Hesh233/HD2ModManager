"""Build an exclusive Source-to-native grip experiment from the tested B17-R."""
import copy
import os
import shutil
import struct
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
from sync_native_grip_alignment import sync

os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime

W = ROOT / 'outputs/native-v27-b19-20261105'
R = ROOT / 'outputs/native-manual-20261103'
OLD = R / 'project/diagnostics/B17'
NAMES = {'0': 'B19-0-关闭旧写入对照.zip', 'R': 'B19-R-原生右手挂点对齐test01.zip',
         'LR': 'B19-LR-原生双手挂点对齐test01.zip'}


def main():
    W.mkdir(exist_ok=True)
    sync()
    prior = load(OLD / 'variants/R/profile.json')
    assert prior['armSync'] and prior['armGripSync'] and prior['protectControllerParents']
    assert [r['name'] for r in prior['attachmentProbe']['nodes']] == ['attach_hand_r', 'weapon_aim']
    avatar_path = R / 'project/animations/runtime/9ba626afa44a3aa3.patch_2'
    model_path = R / 'project/models-o3/test01-O3/9ba626afa44a3aa3.patch_0'
    avatar = next(iter(units(avatar_path).values()))
    models = units(model_path)
    assert len(avatar.parents) == prior['expectedAvatarNodes'] == 255
    prefix = 'hd2n_4e4fb4fa303d_'
    names = {48: 'attach_hand_l', 84: 'attach_hand_r', 85: 'weapon_aim',
             47: 'l_hand', 71: 'r_hand', 115: prefix + 'anim_008_l_hand',
             138: prefix + 'anim_031_r_hand', 131: prefix + 'aux_024_valvebiped_l_weapon_bone',
             154: prefix + 'aux_047_valvebiped_weapon_bone'}
    def spec(index):
        name = names[index]
        assert avatar.name_hashes[index] == bone_name_hash(name), name
        return dict(name=name, index=index, parentIndex=avatar.parents[index], hash=avatar.name_hashes[index])
    pairs = [dict(target=spec(84), source=spec(154)), dict(target=spec(48), source=spec(131))]
    assert avatar.parents[84] == 71 and avatar.parents[85] == 84
    assert avatar.parents[154] == 138 and avatar.parents[131] == 115
    source_indices = set(range(prior['nativeSkeletonNodes'], prior['nativeSkeletonNodes'] + prior['sourceSkeletonNodes']))
    affected = {}
    for p in pairs:
        selected = {p['target']['index']}
        while True:
            expanded = selected | {i for i, parent in enumerate(avatar.parents) if parent in selected}
            if expanded == selected:
                break
            selected = expanded
        assert not selected & source_indices, 'Native target is an ancestor of a Source bone'
        affected[p['target']['name']] = sorted(selected)
    assert affected == {'attach_hand_r': [84, 85], 'attach_hand_l': [48]}
    model_sources = {}
    for resource in prior['modelLayouts']:
        unit = models[resource]
        model_sources[resource] = {}
        for i in (131, 154):
            index = unit.name_hashes.index(avatar.name_hashes[i])
            assert unit.name_hashes[unit.parents[index]] == avatar.name_hashes[avatar.parents[i]]
            model_sources[resource][names[i]] = index
    old_source = (OLD / 'src/native_attachments.lua').read_text(encoding='utf-8-sig')
    new_source = (ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    original = (OLD / 'variants/R/hd2physbone.lua').read_text(encoding='utf-8-sig')
    assert original.count(old_source) == 1
    updated = original.replace(old_source, new_source)
    marker = 'local NativeAttachmentProfile = (function()\n'
    assert updated.count(marker) == 1
    start = updated.index(marker) + len(marker)
    end = updated.index('\nend)()', start)
    old_profile_source = updated[start:end]
    header = (OLD / 'variants/R/container-header.bin').read_bytes()
    assert len(header) == 192
    manifest = load(OLD / 'variants/R/manifest.json')
    descriptions = {'0': '关闭旧手臂 IK、挂点映射和腕辅助写入，保留动画；不进行新对齐。',
                    'R': '关闭旧写入，逐帧将原生 attach_hand_r 的位置和方向对齐 test01 原武器骨。',
                    'LR': '与 R 相同，额外将原生 attach_hand_l 对齐 test01 原左武器骨。'}
    packages = []
    pack.WORK = W
    vm = LuaRuntime()
    for variant in NAMES:
        p = copy.deepcopy(prior)
        p.update(revision='test01-v27-B19-' + variant, armSync=False, armGripSync=False,
                 diagnosticMode='observe' if variant == '0' else 'apply')
        p['attachmentProbe']['enabled'] = False
        p['sceneRoundtrip']['enabled'] = False
        if 'sceneObservation' in p:
            p['sceneObservation']['enabled'] = False
        p['nativeGripAlignment'] = dict(enabled=True, exclusive=True, variant=variant,
            pairs=copy.deepcopy(pairs if variant == 'LR' else pairs[:1]), checks=[spec(i) for i in sorted(names)],
            watchSources=[spec(131), spec(154)], preserveChildren=[spec(85)],
            scalePolicy='preserve-native-world', orientationPolicy='source-world-no-calibration', logFrames=120)
        profile_source = '-- B19: existing Source weapon bones are read-only; native grips are the only outputs.\nreturn ' + lua(p) + '\n'
        code = updated[:start] + profile_source + updated[end:]
        assert vm.eval('function(s) local f,e=loadstring(s);return f~=nil,e end')(code)[0], variant
        assert (code[:start] + old_profile_source + code[start + len(profile_source):]).replace(new_source, old_source) == original
        body = code.encode('utf-8')
        payload = struct.pack('<II', len(body), 2) + body
        patch = bytearray(header) + payload
        patch.extend(bytes(-len(patch) % 16))
        struct.pack_into('<Q', patch, 32, len(patch))
        struct.pack_into('<I', patch, 160, len(payload))
        assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data == payload
        folder = W / 'runtime' / variant
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / '9ba626afa44a3aa3.patch_0'
        path.write_bytes(patch)
        for suffix in ('.stream', '.gpu_resources'):
            path.with_name(path.name + suffix).write_bytes(b'')
        m = dict(manifest, Name='test01 B19-' + variant,
                 Description=descriptions[variant] + ' test01 挂点只读。每次只启用一个 test01 Lua。')
        save_json(folder / 'manifest.json', m)
        shutil.copy2(ROOT / 'docs/native-v27-B19-20261105.md', folder / '测试说明.txt')
        save_json(W / ('B19-' + variant + '.json'), p)
        (W / ('hd2physbone-B19-' + variant + '.lua')).write_bytes(body)
        packages.append(pack.archive('AB测试/' + NAMES[variant], files(folder)))
    save_json(W / 'static-packages.json', packages)
    save_json(W / 'mapping-audit.json', dict(status='PASS', indexBase=0, pairs=pairs,
        affectedWorldIndices=affected, sourceBoneIndices=sorted(source_indices), sourceDescendantsUnaffected=True,
        modelSourceIndices=model_sources, noUnitOrAnimationEdits=True, weaponAimLocalPreserved=True,
        bindingCalibrationVerified=False, evidence='B17-R verified the parent/child group response; B18-AIM has no new game result.'))
    source_files = ['native_attachments.lua', 'native_grip_alignment.lua', 'physbone_runtime.lua',
                    'native_attachment_probe.lua', 'native_scene_observer.lua', 'native_scene_roundtrip.lua']
    save_json(W / 'scope-audit.json', dict(status='PASS', baseline='B17-R',
        sourceSha256={name: digest(ROOT / 'HD2PhysBoneCompat/src' / name) for name in source_files},
        assetSha256={str(path.relative_to(R)): digest(path) for path in
                     (avatar_path, model_path, R / 'test01-配套动画.zip', R / 'test01-模型材质.zip')},
        legacyArmSyncDisabled=True, legacyAttachmentAndProcedureWritesBypassed=True,
        probeDisabled=True, directModelOrSourceWrites=False, equipmentRelink=False,
        originalB18DiscoveryOptInDisabled=True, gameTested=False, gameDeployed=False))
    save_json(W / 'prior-conflict-analysis.json', dict(status='SOURCE_CONFIRMED_GAME_CAUSE_UNCONFIRMED',
        profile=prior['revision'], armSync=prior['armSync'], armGripSync=prior['armGripSync'],
        protectControllerParents=prior['protectControllerParents'],
        findings=[
            'sync_arms reads nativeGrip and writes Source shoulder/elbow/hand before the displacement probe; moving Source weapon-bone targets with this path active creates a competing direction.',
            'weapon_aim uses original-world policy; protectControllerParents consequently excludes attach_hand_r from the ordinary mapping.',
            'B17 probe runs after the legacy solver and adapter; B19 bypasses the legacy write branch and disables the probe.',
            'The observed flicker cannot be attributed to these paths without the controlled game trial.'],
        gameLogLastKnown='B17-R, 2026-11-05 00:50:27–00:55:24 Asia/Shanghai'))
    print('Prepared B19-0/R/LR; native output allowlist and all 11 model Source anchor layouts verified.')


if __name__ == '__main__':
    main()
