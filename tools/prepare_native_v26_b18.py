"""Isolate weapon_aim and independently test missing simple-component refresh."""
import copy
import os
import shutil
import struct
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.archive import TocArchive

W = ROOT / 'outputs/native-v26-b18-20261105'
R = ROOT / 'outputs/native-manual-20261103'
OLD = R / 'project/diagnostics/B17'
NAMES = {'AIM': 'B18-AIM-瞄准子节点测试.zip', 'PARTS': 'B18-PARTS-独立弹药部件刷新测试.zip'}


def main():
    W.mkdir(exist_ok=True)
    baseline = load(R / 'delivery-verification.json')
    assert baseline['status'] == 'PASS' and baseline['revision'] == 'native-v25'
    if not (W / 'baseline-delivery.json').exists():
        save_json(W / 'baseline-delivery.json', baseline)
    assert baseline == load(W / 'baseline-delivery.json')
    comparison = load(W / 'evidence/B17-comparison.json')
    assert comparison['status'] == 'PASS' and comparison['results']['R']['candidateSetPositive']
    assert not comparison['results']['L']['candidateSetPositive']
    layouts = load(W / 'component-layout-audit.json')
    assert layouts['status'] == 'PASS'
    prior = load(OLD / 'variants/R/profile.json')
    assert 'simpleWeaponComponents' not in prior
    rows = prior['attachmentProbe']['nodes']
    assert [r['name'] for r in rows] == ['attach_hand_r', 'weapon_aim']
    groups = {'AIM': [r for r in rows if r['name'] == 'weapon_aim'], 'PARTS': rows}
    assert len(groups['AIM']) == 1 and len(groups['PARTS']) == 2
    avatar = next(iter(units(R / 'project/animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    source = ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua'
    module = ROOT / 'HD2PhysBoneCompat/src/native_attachment_probe.lua'
    assert digest(module) == digest(OLD / 'src/native_attachment_probe.lua')
    old_source = (OLD / 'src/native_attachments.lua').read_text(encoding='utf-8-sig')
    new_source = source.read_text(encoding='utf-8-sig')
    change_start = new_source.index('       -- Opt-in, exact-resource layouts for simple components without a skeleton.\n')
    change_end = new_source.index('       if not kind then\n', change_start)
    assert new_source[:change_start] + new_source[change_end:] == old_source
    original = (OLD / 'variants/R/hd2physbone.lua').read_text(encoding='utf-8-sig')
    assert original.count(old_source) == 1
    updated = original.replace(old_source, new_source)
    marker = 'local NativeAttachmentProfile = (function()\n'
    assert updated.count(marker) == 1
    start = updated.index(marker) + len(marker)
    end = updated.index('\nend)()', start)
    old_profile = updated[start:end]
    header = (OLD / 'variants/R/container-header.bin').read_bytes()
    packages, tree = [], {}
    pack.WORK = W
    for variant, selected_rows in groups.items():
        selected = {r['index'] for r in selected_rows}
        affected = set(selected)
        while True:
            previous = set(affected)
            affected.update(i for i, parent in enumerate(avatar.parents) if parent in previous)
            if affected == previous:
                break
        assert affected == selected, 'Unexpected descendant moved outside selected family'
        roots = [r['index'] for r in selected_rows if r['parentIndex'] not in selected]
        assert len(roots) == 1
        for row in selected_rows:
            assert avatar.name_hashes[row['index']] == row['hash'] and avatar.parents[row['index']] == row['parentIndex']
        tree[variant] = dict(nodes=selected_rows, roots=roots, affectedIndices=sorted(affected))
        profile = copy.deepcopy(prior)
        profile['revision'] = 'test01-v26-B18-' + variant
        profile['attachmentProbe']['variant'] = variant
        profile['attachmentProbe']['nodes'] = selected_rows
        if variant == 'PARTS':
            profile['simpleWeaponComponents'] = copy.deepcopy(layouts['simpleWeaponComponents'])
        restored = copy.deepcopy(profile)
        restored['revision'] = prior['revision']
        restored['attachmentProbe']['variant'] = 'R'
        restored['attachmentProbe']['nodes'] = rows
        restored.pop('simpleWeaponComponents', None)
        assert restored == prior
        new_profile = '-- B18: AIM isolates the leaf; PARTS enables exact simple-component refresh.\nreturn ' + lua(profile) + '\n'
        code = updated[:start] + new_profile + updated[end:]
        assert (code[:start] + old_profile + code[start + len(new_profile):]).replace(new_source, old_source) == original
        data = code.encode('utf-8')
        payload = struct.pack('<II', len(data), 2) + data
        patch = bytearray(header) + payload
        patch.extend(bytes(-len(patch) % 16))
        struct.pack_into('<Q', patch, 32, len(patch))
        struct.pack_into('<I', patch, 160, len(payload))
        assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data == payload
        dest = W / 'runtime' / variant
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / '9ba626afa44a3aa3.patch_0'
        path.write_bytes(patch)
        for suffix in ('.stream', '.gpu_resources'):
            path.with_name(path.name + suffix).write_bytes(b'')
        manifest = load(OLD / 'variants/R/manifest.json')
        manifest.update(Name='test01 B18-' + variant,
                        Description=('仅移动 weapon_aim 子节点，沿用旧部件识别。' if variant == 'AIM' else
                                     '保持 B17-R 位移，仅增加两种无骨架弹药部件的精确识别与刷新。') +
                                    '仅 test01，4秒原位/4秒上移60厘米。一次只启用一个 Lua。')
        save_json(dest / 'manifest.json', manifest)
        shutil.copy2(ROOT / 'docs/native-v26-B18-20261105.md', dest / '测试说明.txt')
        save_json(W / ('B18-' + variant + '.json'), profile)
        (W / ('hd2physbone-B18-' + variant + '.lua')).write_bytes(data)
        packages.append(pack.archive('AB测试/' + NAMES[variant], files(dest)))
    save_json(W / 'static-packages.json', packages)
    save_json(W / 'candidate-tree.json', dict(status='PASS', control='B17-R', groups=tree,
              rootFamiliesPerGroup=1, aimLeafOnly=True, partsNodesExactlyB17R=True, disjoint=False,
              strategy='Two independent comparisons to B17-R: AIM leaf-only with legacy discovery; PARTS unchanged displacement with exact simple-component refresh.'))
    save_json(W / 'scope-audit.json', dict(status='PASS', control='B17-R', probe='B18-AIM/PARTS',
              runtimeImplementationByteIdentical=False, unchangedOutsideOptInDiscovery=True,
              probeImplementationByteIdentical=True, noPoseWriteOrRelinkAdded=True,
              aimUsesLegacyDiscovery=True, partsUsesExactResourceCountAndSignature=True,
              changedSourceFiles=['native_attachments.lua'],
              sourceSha256=digest(source), probeSha256=digest(module), animationSha256=digest(R / 'test01-配套动画.zip'),
              baselineChefSourceSha256=load(OLD / 'reports/chef-compatibility-audit.json')['embeddedSourceSha256'],
              gameTested=False, gameDeployed=False))
    print('B18 prepared: AIM 1 leaf, legacy discovery; PARTS B17-R nodes with two exact simple-component layouts. Probe and solver unchanged.')


if __name__ == '__main__':
    main()
