"""Split B16-H into left and right families; preserve its complete runtime."""
import copy
import os
import shutil
import struct
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.archive import TocArchive

W = ROOT / 'outputs/native-v25-b17-20261105'
R = ROOT / 'outputs/native-manual-20261103'
OLD = R / 'project/diagnostics/B16'
NAMES = {'L': 'B17-L-左手挂点测试.zip', 'R': 'B17-R-右手挂点测试.zip'}


def main():
    W.mkdir(exist_ok=True)
    baseline = load(R / 'delivery-verification.json')
    assert baseline['status'] == 'PASS' and baseline['revision'] == 'native-v24'
    if not (W / 'baseline-delivery.json').exists():
        save_json(W / 'baseline-delivery.json', baseline)
    assert baseline == load(W / 'baseline-delivery.json')
    comparison = load(W / 'evidence/B16-comparison.json')
    assert comparison['status'] == 'PASS' and comparison['results']['H']['candidateSetPositive']
    assert not comparison['results']['W']['candidateSetPositive']
    prior = load(OLD / 'variants/H/profile.json')
    rows = prior['attachmentProbe']['nodes']
    assert [r['name'] for r in rows] == ['attach_hand_l', 'attach_hand_r', 'weapon_aim']
    groups = {'L': [r for r in rows if r['name'] == 'attach_hand_l'],
              'R': [r for r in rows if r['name'] != 'attach_hand_l']}
    assert len(groups['L']) == 1 and len(groups['R']) == 2
    assert sorted(groups['L'] + groups['R'], key=lambda r: r['index']) == rows
    assert not {r['index'] for r in groups['L']} & {r['index'] for r in groups['R']}
    avatar = next(iter(units(R / 'project/animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    source = ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua'
    module = ROOT / 'HD2PhysBoneCompat/src/native_attachment_probe.lua'
    assert digest(source) == digest(OLD / 'src/native_attachments.lua')
    assert digest(module) == digest(OLD / 'src/native_attachment_probe.lua')
    original = (OLD / 'variants/H/hd2physbone.lua').read_text(encoding='utf-8-sig')
    marker = 'local NativeAttachmentProfile = (function()\n'
    assert original.count(marker) == 1
    start = original.index(marker) + len(marker)
    end = original.index('\nend)()', start)
    old_profile = original[start:end]
    header = (OLD / 'variants/H/container-header.bin').read_bytes()
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
        profile['revision'] = 'test01-v25-B17-' + variant
        profile['attachmentProbe']['variant'] = variant
        profile['attachmentProbe']['nodes'] = selected_rows
        restored = copy.deepcopy(profile)
        restored['revision'] = prior['revision']
        restored['attachmentProbe']['variant'] = 'H'
        restored['attachmentProbe']['nodes'] = rows
        assert restored == prior
        new_profile = '-- B17 subset of game-positive B16-H; unchanged runtime.\nreturn ' + lua(profile) + '\n'
        code = original[:start] + new_profile + original[end:]
        assert code[:start] + old_profile + code[start + len(new_profile):] == original
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
        manifest = load(OLD / 'variants/H/manifest.json')
        manifest.update(Name='test01 B17-' + variant + (' 左手挂点' if variant == 'L' else ' 右手挂点'),
                        Description='有效 B16-H 的左右挂点拆分；仅 test01，4秒原位/4秒上移60厘米。一次只启用一个 Lua。')
        save_json(dest / 'manifest.json', manifest)
        shutil.copy2(ROOT / 'docs/native-v25-B17-20261105.md', dest / '测试说明.txt')
        save_json(W / ('B17-' + variant + '.json'), profile)
        (W / ('hd2physbone-B17-' + variant + '.lua')).write_bytes(data)
        packages.append(pack.archive('AB测试/' + NAMES[variant], files(dest)))
    save_json(W / 'static-packages.json', packages)
    save_json(W / 'candidate-tree.json', dict(status='PASS', control='B16-H', groups=tree,
              rootFamiliesPerGroup=1, disjoint=True, unionExactlyEqualsB16H=True, excludedHellpad=2781352283,
              strategy='L: attach_hand_l only. R: attach_hand_r with its child weapon_aim; one highest-level write per variant.'))
    save_json(W / 'scope-audit.json', dict(status='PASS', control='B16-H', probe='B17-L/R',
              runtimeImplementationByteIdentical=True, onlyProfileRevisionVariantAndNodeSubsetChanged=True,
              sourceSha256=digest(source), probeSha256=digest(module), animationSha256=digest(R / 'test01-配套动画.zip'),
              baselineChefSourceSha256=load(OLD / 'reports/chef-compatibility-audit.json')['embeddedSourceSha256'],
              gameTested=False, gameDeployed=False))
    print('B17 prepared: L 1 root/1 node; R 1 root/2 nodes. Exact B16-H partition; runtime unchanged.')


if __name__ == '__main__':
    main()
