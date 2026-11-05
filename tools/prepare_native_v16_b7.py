"""Prepare an incremental split-model refresh probe; preserve accepted v15 assets."""
import copy
import hashlib
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path
from package_native_v12 import load, save_json, digest, files, lua
import package_native_v12 as pack
from native_attachment_layouts import with_model_layouts

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'outputs/native-v16-20261104'
R = ROOT / 'outputs/native-manual-20261103'
P = R / 'project'
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive


def main():
    W.mkdir(exist_ok=True)
    prior = load(R / 'delivery-verification.json')
    assert prior['status'] == 'PASS' and prior['revision'] == 'native-v15'
    save_json(W / 'baseline-delivery.json', prior)
    save_json(W / 'feedback.json', dict(
        v15Animation='user-confirmed-normal',
        B5=dict(grip='same-as-no-Lua', other='same-as-no-Lua'),
        B6=dict(grip='same-as-no-Lua', samplePouch='rapid flickering on ship', splitParts='visible seams', accepted=False),
        B7GameTested=False))
    source = ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua'
    old_source = P / 'source-code/HD2PhysBoneCompat/src/native_attachments.lua'
    before, after = (p.read_text(encoding='utf-8-sig').replace('\r\n', '\n') for p in (old_source, source))
    assert "VERSION='0.10.0'" in before and "VERSION='0.10.1'" in after
    # The arm math and attachment rules are unchanged; only model discovery,
    # selection and refresh membership differ.
    for start, end in [('function M.grip_target', '-- Source mstudio'),
                       (' function self:restore_arms', ' -- Read the matched armor')]:
        assert before.split(start)[1].split(end)[0] == after.split(start)[1].split(end)[0]
    control = load(P / 'ab-profiles/B5.json')
    targets = load(P / 'models-o3/test01-O3/replacement-target.json')['mappings']
    selectors = {x for ids in control['targets'].values() for x in ids}
    consumers = [r['targetUnit'] for r in targets if r['targetUnit'] not in selectors]
    assert len(consumers) == 6 and len(set(consumers)) == 6
    profile = copy.deepcopy(control)
    profile.update(revision='test01-v16-B7', consumerTargets={'body': consumers})
    model_patch = P / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_0'
    profile = with_model_layouts(profile, [model_patch])
    assert profile['targets'] == control['targets'] and len(profile['modelLayouts']) == 11
    for resource, layout in control['modelLayouts'].items():
        assert profile['modelLayouts'][resource] == layout
    save_json(W / 'B7.json', profile)

    weights = load(W / 'skin-weights.json')
    assert weights['status'] == 'PASS'
    names = {n['hash']: n['name'] for n in load(P / 'source-skeleton.json')['bones']}
    parts = {t['targetUnit']: t['part'] for t in targets}
    evidence = []
    for row in weights['rows']:
        if row['resource'] not in parts:
            continue
        nodes = [dict(n, name=names.get(n['hash'], str(n['hash']))) for n in row['weightedNodes']]
        arm = [n for n in nodes if any(x in n['name'] for x in ('shoulder', 'elbow', 'hand', 'clavicle'))]
        evidence.append(dict(resource=row['resource'], part=parts[row['resource']],
                             previousRefresh=row['resource'] in selectors,
                             b7Refresh=row['resource'] in profile['modelLayouts'], armWeights=arm))
    for part, suffix in [('LeftArm/Armor/Any', 'l_hand'), ('RightArm/Armor/Any', 'r_hand')]:
        row = next(r for r in evidence if r['part'] == part)
        assert not row['previousRefresh'] and row['b7Refresh']
        assert any(n['name'].endswith(suffix) and n['weightedVertices'] > 0 for n in row['armWeights'])
    save_json(W / 'consumer-coverage.json', dict(status='PASS', previous=5, current=11, selectorsUnchanged=True,
                                               rows=evidence, gameTested=False))

    log_path = Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2/hd2physbone.log')
    text = log_path.read_text(encoding='utf-8-sig', errors='replace')
    sessions = re.split(r'(?=^.*\[physbone\] 运行时 .*启动于 )', text, flags=re.M)
    observed = []
    for variant in ('test01-v15-B6', 'test01-v14-B5'):
        session = next(s for s in reversed(sessions) if 'variant=' + variant in s)
        lines = [l for l in session.splitlines() if '[attachments]' in l and any(k in l for k in
                 ('variant=', 'arm_consumer_readback', 'palm_contact_error', 'kind=sample_pouch'))]
        excerpt = '\n'.join(lines) + '\n'
        (W / (variant + '-evidence.log')).write_text(excerpt, encoding='utf-8')
        observed.append(dict(variant=variant, armReadbackResources=sorted(set(re.findall(r'arm_consumer_readback .*?resource=([0-9a-f]+)', session))),
                             excerptSha256=hashlib.sha256(excerpt.encode()).hexdigest()))
    save_json(W / 'runtime-evidence.json', dict(status='PASS', source=str(log_path), sha256=digest(log_path),
                                               sessions=observed, limitation='scene-graph reads do not prove rendered skinning'))

    with zipfile.ZipFile(R / 'AB测试/B5-掌心握持校准.zip') as z:
        binary, manifest = z.read('9ba626afa44a3aa3.patch_0'), json.loads(z.read('manifest.json'))
    entry = next(iter(TocArchive.parse_parts(binary).entries.values()))
    original = entry.toc_data[8:].decode('utf-8-sig').replace('\r\n', '\n')
    assert original.count(before) == 1
    profile_start = original.index('local NativeAttachmentProfile = (function()\n') + len('local NativeAttachmentProfile = (function()\n')
    profile_end = original.index('\nend)()', profile_start)
    original_profile = original[profile_start:profile_end]
    new_profile = '-- Generated test01 B7 split-model refresh profile.\nreturn ' + lua(profile) + '\n'
    code = original.replace(before, after).replace(original_profile, new_profile)
    assert code.replace(after, before).replace(new_profile, original_profile) == original
    assert 'PhysBoneRuntime.update=PhysBoneRuntime.render' not in code
    dest = W / 'runtime/B7'
    dest.mkdir(parents=True, exist_ok=True)
    data = code.encode('utf-8')
    resource = struct.pack('<II', len(data), 2) + data
    patch = bytearray(binary[:192]) + resource
    patch.extend(bytes(-len(patch) % 16))
    struct.pack_into('<Q', patch, 32, len(patch))
    struct.pack_into('<I', patch, 160, len(resource))
    parsed = next(iter(TocArchive.parse_parts(patch).entries.values()))
    assert parsed.toc_data == resource and parsed.file_id == entry.file_id
    main_patch = dest / '9ba626afa44a3aa3.patch_0'
    main_patch.write_bytes(patch)
    for suffix in ('.stream', '.gpu_resources'):
        Path(str(main_patch) + suffix).write_bytes(b'')
    manifest.update(Name='test01 v15 动画配套 B7 — 补齐切分部位刷新',
                    Description='保持 B5 render 回调与算法；补齐左右手臂、腿、髋部消费刷新。一次只启用一个 test01 Lua。')
    save_json(dest / 'manifest.json', manifest)
    shutil.copy2(ROOT / 'docs/native-v16-B7-20261104.md', dest / '测试说明.txt')
    (W / 'hd2physbone-B7.lua').write_bytes(data)
    pack.WORK = W
    save_json(W / 'static-packages.json', [pack.archive('AB测试/B7-补齐切分部位刷新.zip', files(dest))])
    save_json(W / 'scope-audit.json', dict(status='PASS', control='v14-B5', probe='v16-B7',
        changed=['complete split-model discovery and refresh', 'profile revision', 'adapter version'],
        sameArmSolver=True, sameAttachmentRules=True, samePhysics=True, callback='render',
        sourceSha256=digest(source), selectorTargets=control['targets'], consumerTargets=profile['consumerTargets'],
        animationSha256=digest(R / 'test01-配套动画.zip'), gameTested=False))
    print('B7 prepared; all 11 real model layouts covered, five selectors unchanged.')


if __name__ == '__main__':
    main()
