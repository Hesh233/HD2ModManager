"""Audit current loose patches against one preserved B21 session; never deploy."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
from pathlib import Path
import re
import struct

from package_native_v12 import ROOT, load, save_json, digest
from anim_batch_mod.constants import (
    UNIT_TYPE_ID, BONE_TYPE_ID, ANIMATION_TYPE_ID, STATE_MACHINE_TYPE_ID,
)
from anim_batch_mod.formats import UnitData

PATCH = re.compile(r'^([0-9a-f]{16})\.patch_(\d+)$', re.I)
TYPES = {UNIT_TYPE_ID: 'unit', BONE_TYPE_ID: 'bones',
         ANIMATION_TYPE_ID: 'animation', STATE_MACHINE_TYPE_ID: 'state_machine'}
AVATAR = '4d1c334d294dfa97'
COLLECTOR = 'af6cc767304a995d'
WATCHED = (AVATAR, '23a244c877843da3', '30204ad0fe720352',
           '186ea95de7306b1a', 'f9df21c8e52cac95')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observation', type=Path)
    parser.add_argument('--game-data', type=Path,
                        default=Path('E:/Steam/steamapps/common/Helldivers 2/data'))
    args = parser.parse_args()
    output = args.observation.resolve()
    manifest = load(output / 'snapshot-manifest.json')
    layout = load(ROOT / 'outputs/native-v29-b21-20261105/native-capture-layouts.json')
    delivered = load(ROOT / 'outputs/native-v29-b21-20261105/delivery-verification.json')
    originals = {AVATAR: layout['nativeAvatar'],
                 **{rid: layout['resources'][rid] for rid in WATCHED if rid != AVATAR}}
    paths = sorted((p for p in args.game_data.iterdir() if PATCH.fullmatch(p.name)),
                   key=lambda p: (PATCH.fullmatch(p.name)[1], int(PATCH.fullmatch(p.name)[2])))
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    patches, overrides, collectors, animation_count = [], [], [], 0
    for path in paths:
        with path.open('rb') as stream:
            header = stream.read(72)
            magic, type_count, file_count, _ = struct.unpack_from('<IIII', header)
            assert magic == 0xf0000011, path
            table_size = file_count * 80
            assert 72 + type_count * 32 + table_size <= path.stat().st_size
            stream.seek(72 + type_count * 32)
            table = stream.read(table_size)
            rows = [struct.unpack_from('<QQQQQQQIIIIII', table, i * 80)
                    for i in range(file_count)]
            info = dict(path=str(path), bytes=path.stat().st_size,
                        family=PATCH.fullmatch(path.name)[1], patch=int(PATCH.fullmatch(path.name)[2]),
                        sha256=digest(path), fileCount=file_count,
                        types=dict(Counter(TYPES.get(v[1], f'{v[1]:016x}') for v in rows)))
            patches.append(info)
            animation_count += info['types'].get('animation', 0)
            for v in rows:
                rid = f'{v[0]:016x}'
                if rid not in WATCHED and rid != COLLECTOR:
                    continue
                assert v[2] + v[7] <= path.stat().st_size
                stream.seek(v[2])
                raw = stream.read(v[7])
                assert len(raw) == v[7]
                entry = dict(patch=info['patch'], family=info['family'], path=str(path),
                             type=TYPES.get(v[1], f'{v[1]:016x}'), resource=rid,
                             bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                if rid == COLLECTOR:
                    collectors.append(dict(entry, patchSha256=info['sha256'],
                                           matchesDelivered=info['sha256'] == delivered['patchSha256']))
                if rid in WATCHED and v[1] in TYPES:
                    if v[1] == UNIT_TYPE_ID:
                        entry.update(nodeCount=len(UnitData.parse(raw).parents),
                                     matchesExtractedOriginal=entry['sha256'] == originals[rid]['sha256'])
                    overrides.append(entry)
    after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    assert before == after, 'Loose patches changed during audit'
    assert {str(p) for p in args.game_data.iterdir() if PATCH.fullmatch(p.name)} == set(before)
    current_layouts = sorted({u['layout'] for u in manifest['units'] if u['resource'] == AVATAR})
    avatar_overrides = [r for r in overrides if r['resource'] == AVATAR]
    chef = (output / 'chef-latest.log').read_text(encoding='utf-8')
    loaded_patch_count = re.findall(r'in (\d+) patch files', chef)
    collector_matches_log = len(collectors) == 1 and Path(collectors[0]['path']).name in next(
        line for line in chef.splitlines() if 'started mods/hd2modmanager/native_grip_capture' in line)
    native_assets = current_layouts == ['native_107'] and not overrides and animation_count == 0
    report = dict(status='INSPECTED', auditedAt=datetime.now().astimezone().isoformat(),
                  sessionStart=manifest['selected']['started'], sessionEnd=manifest['selected']['completed'],
                  captureSha256=manifest['snapshotSha256'], gameData=str(args.game_data),
                  patches=patches, patchCount=len(patches), chefPatchCount=int(loaded_patch_count[0]),
                  patchCountMatchesChef=len(patches) == int(loaded_patch_count[0]),
                  watchedResourceOverrides=overrides, avatarOverrides=avatar_overrides,
                  looseAnimationOverrides=animation_count, avatarLayouts=current_layouts,
                  collectorEntries=collectors, collectorMatchesChef=collector_matches_log,
                  collectorMatchesDelivered=len(collectors) == 1 and collectors[0]['matchesDelivered'],
                  nativeSkeletonAndWatchedAssetBaselineConfirmed=native_assets,
                  originalNodeCount=layout['nativeAvatar']['nodeCount'],
                  currentLooseFilesOnly=True, patchesUnchangedDuringAudit=True, gameFilesChanged=False,
                  limits=[
                      'Current loose patch tables are inspected after capture; their historical bytes at launch are not recorded.',
                      'Native confirmation is scoped to the observed 107-node Avatar, watched Unit/Bones/state-machine resources and absence of loose animation overrides.',
                      'Other mods remain installed, including QuickDebrief and Chef. Unrelated scripts/material/mesh files are not certified absent.',
                  ])
    save_json(output / 'deployment-audit.json', report)
    print({k: report[k] for k in ('patchCount', 'patchCountMatchesChef', 'avatarLayouts',
           'watchedResourceOverrides', 'looseAnimationOverrides', 'collectorMatchesChef',
           'collectorMatchesDelivered', 'nativeSkeletonAndWatchedAssetBaselineConfirmed')})


if __name__ == '__main__':
    main()
