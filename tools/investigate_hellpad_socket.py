"""Read-only comparison of the user-reported native node 2781352283."""
import hashlib
import json
from pathlib import Path

from package_native_v10 import ROOT, records, payload, save_json
from anim_batch_mod.constants import BONE_TYPE_ID, UNIT_TYPE_ID
from anim_batch_mod.formats import BonesData, UnitData
from anim_batch_mod.native_skeleton import bone_name_hash

HASH = 2781352283
W = ROOT / 'outputs/native-v20-20261104/hellpad-investigation'
P = ROOT / 'outputs/native-manual-20261103/project'


def node(unit, index):
    pose = unit.transforms[index]
    parent = unit.parents[index]
    return dict(indexZeroBased=index, luaIndex=index + 1,
                hash=unit.name_hashes[index], parentIndex=parent,
                parentHash=unit.name_hashes[parent] if parent is not None else None,
                children=[i for i, p in enumerate(unit.parents) if p == index],
                position=pose.position, rotation=pose.rotation, scale=pose.scale)


def main():
    assert bone_name_hash('hellpad_socket') == HASH
    originals = ROOT / 'outputs/native-fix-20261103'
    base = UnitData.parse((originals / 'avatar.toc').read_bytes())
    baseline = node(base, base.name_hashes.index(HASH))
    rows = []
    paths = [
        ('accepted_v15_avatar', P / 'animations/runtime/9ba626afa44a3aa3.patch_2'),
        ('accepted_models', P / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_0'),
        ('known_good_patch_0', ROOT.parent / 'output/9ba626afa44a3aa3.patch_0'),
        ('known_good_patch_22', Path('I:/大部分缩肩打包/备份/初版nanoha/0909output/第3人称/9ba626afa44a3aa3.patch_22')),
    ]
    for label, path in paths:
        units, bones = [], []
        for row in records(path):
            if row[1] not in (UNIT_TYPE_ID, BONE_TYPE_ID):
                continue
            data = payload(path, row)
            if row[1] == UNIT_TYPE_ID:
                u = UnitData.parse(data)
                matches = [node(u, i) for i, h in enumerate(u.name_hashes) if h == HASH]
                for m in matches:
                    m['sameParentAndLocalAsCachedOriginal'] = all(m[k] == baseline[k] for k in ('parentHash', 'position', 'rotation', 'scale'))
                units.append(dict(resource=f'{row[0]:016x}', count=len(u.transforms), matches=matches,
                                  dataSha256=hashlib.sha256(data).hexdigest()))
            else:
                b = BonesData.parse(data)
                bones.append(dict(resource=f'{row[0]:016x}', count=len(b.names),
                                  matches=[dict(animationIndex=i, name=n, hash=h) for i, (n, h) in enumerate(zip(b.names, b.hashes)) if h == HASH]))
        rows.append(dict(label=label, path=str(path), units=units, bones=bones))
    manifest = json.loads((P / 'source-skeleton.json').read_text(encoding='utf-8-sig'))
    profile = json.loads((P / 'diagnostics/B10/B10.json').read_text(encoding='utf-8-sig'))
    findings = dict(status='PASS', scope='Read-only serialized resources and code configuration; no in-game causal test.',
                    resolvedName='hellpad_socket', decimalHash=HASH, hexadecimalHash=f'{HASH:08x}',
                    computedHash=bone_name_hash('hellpad_socket'),
                    misleadingShaderLabelHash=bone_name_hash('HellpadSocket'),
                    cachedOriginalPath=str(originals / 'avatar.toc'), cachedOriginal=baseline,
                    comparisons=rows,
                    sourceBoneHashMatches=[n for n in manifest['bones'] if n['hash'] == HASH],
                    attachmentRows=[r for key in ('native', 'vpk') for r in profile[key] if r.get('index') == 103 or 'hellpad' in json.dumps(r).lower()],
                    armChainReads=[dict(side=c['side'], nativeUpper=c['nativeUpper'], nativeForearm=c['nativeForearm'], nativeHand=c['nativeHand'], nativeGrip=c['nativeGrip']) for c in profile['armChains']],
                    observationBeforeInvestigation=False, changedGameFiles=False, changedBehavior=False)
    save_json(W / 'node-comparison.json', findings)
    print(json.dumps(findings, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
