"""Read deployed patch tables and identify the live Avatar override; never deploy."""
from collections import Counter
import hashlib
from pathlib import Path
import re
import struct
from package_native_v12 import ROOT, load, save_json, digest
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID, ANIMATION_TYPE_ID, STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import UnitData

W = ROOT / 'outputs/native-b21-observation-20261105/20261105-092343'
GAME = Path('E:/Steam/steamapps/common/Helldivers 2/data')
AVATAR = 0x4d1c334d294dfa97
MATCH = re.compile(r'^9ba626afa44a3aa3\.patch_(\d+)$')
TYPES = {UNIT_TYPE_ID:'unit', BONE_TYPE_ID:'bones', ANIMATION_TYPE_ID:'animation', STATE_MACHINE_TYPE_ID:'state_machine'}


def main():
    entries, avatar_candidates = [], []
    b21 = load(ROOT / 'outputs/native-v29-b21-20261105/native-capture-layouts.json')
    observed_originals = {r: b21['resources'][r] for r in
        ('23a244c877843da3', '30204ad0fe720352', '186ea95de7306b1a', 'f9df21c8e52cac95')}
    observed_overrides = {r: [] for r in observed_originals}
    for path in sorted((p for p in GAME.iterdir() if MATCH.fullmatch(p.name)),
                       key=lambda p:int(MATCH.fullmatch(p.name)[1])):
        with path.open('rb') as stream:
            header = stream.read(72)
            magic, type_count, file_count, _ = struct.unpack_from('<IIII', header)
            assert magic == 0xf0000011
            stream.seek(72 + type_count * 32)
            table = stream.read(file_count * 80)
            rows = [struct.unpack_from('<QQQQQQQIIIIII', table, i * 80) for i in range(file_count)]
            summary = dict(path=str(path), bytes=path.stat().st_size, patch=int(MATCH.fullmatch(path.name)[1]),
                fileCount=file_count, types=dict(Counter(TYPES.get(v[1], f'{v[1]:016x}') for v in rows)), avatar=[])
            for v in rows:
                rid = f'{v[0]:016x}'
                if rid in observed_originals and v[1] == UNIT_TYPE_ID:
                    stream.seek(v[2])
                    observed_raw = stream.read(v[7])
                    assert len(observed_raw) == v[7]
                    sha = hashlib.sha256(observed_raw).hexdigest()
                    observed_overrides[rid].append(dict(patch=summary['patch'], sha256=sha,
                        matchesExtractedOriginal=sha == observed_originals[rid]['sha256']))
                if v[0] != AVATAR or v[1] not in (UNIT_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID):
                    continue
                stream.seek(v[2])
                raw = stream.read(v[7])
                assert len(raw) == v[7]
                row = dict(type=TYPES[v[1]], resource=f'{v[0]:016x}', bytes=len(raw),
                           sha256=hashlib.sha256(raw).hexdigest())
                if v[1] == UNIT_TYPE_ID:
                    row['nodeCount'] = len(UnitData.parse(raw).parents)
                    (W / ('deployed-avatar-patch-' + str(summary['patch']) + '.unit')).write_bytes(raw)
                    avatar_candidates.append(dict(patch=summary['patch'], path=str(path), **row))
                summary['avatar'].append(row)
        entries.append(summary)
    assert avatar_candidates, 'No loose patch overrides the Avatar'
    selected = max(avatar_candidates, key=lambda row:row['patch'])
    full_sha = digest(Path(selected['path']))
    v15 = load(ROOT / 'outputs/native-v29-b21-20261105/delivery-verification.json')['protectedAssetSha256']
    v15_sha = next(sha for name, sha in v15.items() if name.endswith('9ba626afa44a3aa3.patch_2'))
    v30 = ROOT / 'outputs/native-v30-b22-20261105/runtime/9ba626afa44a3aa3.patch_2'
    v30_sha = digest(v30) if v30.is_file() else None
    selected.update(patchSha256=full_sha,
        unitMatchesB21Test01Layout=selected['sha256'] == b21['test01Avatar']['sha256'],
        unitMatchesExtractedNative=selected['sha256'] == b21['nativeAvatar']['sha256'],
        entirePatchMatchesV15=full_sha == v15_sha, entirePatchMatchesV30=full_sha == v30_sha)
    result = dict(status='INSPECTED', gameData=str(GAME), patches=entries, effectiveAvatar=selected,
        observedNativeUnitOverrides=observed_overrides,
        captureAddonPatchSha256=digest(GAME / '9ba626afa44a3aa3.patch_11'),
        captureAddonMatchesDelivered=digest(GAME / '9ba626afa44a3aa3.patch_11') ==
            load(ROOT / 'outputs/native-v29-b21-20261105/delivery-verification.json')['patchSha256'],
        originalNodeCount=b21['nativeAvatar']['nodeCount'], nativeGameBaseline=False,
        currentLooseFilesOnly=True, gameFilesChanged=False,
        limits='Current loose patch bytes and the matching latest log are inspected. Other mods are not certified absent.')
    save_json(W / 'deployment-audit.json', result)
    print(dict(effectiveAvatar=selected, patchCount=len(entries)))


if __name__ == '__main__':
    main()
