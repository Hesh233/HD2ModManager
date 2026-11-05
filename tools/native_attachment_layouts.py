"""Generate attachment identity metadata from the final serialized model Units.

Do this after model remapping/export: its node order/count need not match avatar.
No game or library writes. The optional output is a new profile supplied by caller.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import bone_name_hash


def build_model_layouts(model_patches, profile):
    groups = list(profile['targets'].items()) + list(profile.get('consumerTargets', {}).items())
    targets = {resource: slot for slot, resources in groups for resource in resources}
    if sum(len(ids) for _, ids in groups) != len(targets):
        raise ValueError('A model resource cannot identify two equipment slots')
    if len(profile['signature']) < 3:
        raise ValueError('Attachment ownership requires a multi-node signature')
    layouts = {}
    for path in map(Path, model_patches):
        with path.open('rb') as stream:
            header = stream.read(72)
            if len(header) != 72 or struct.unpack_from('<I', header)[0] != 0xf0000011:
                raise ValueError(f'Invalid patch header: {path}')
            type_count, count = struct.unpack_from('<II', header, 4)
            stream.seek(72 + 32 * type_count)
            records = [struct.unpack('<QQQQQQQIIIIII', stream.read(80)) for _ in range(count)]
            for record in records:
                resource = f'{record[0]:016x}'
                if record[1] != UNIT_TYPE_ID or resource not in targets:
                    continue
                stream.seek(record[2]); payload = stream.read(record[7])
                if len(payload) != record[7]:
                    raise ValueError(f'Truncated model Unit {resource}')
                unit = UnitData.parse(payload)
                if len(set(unit.name_hashes)) != len(unit.name_hashes):
                    raise ValueError(f'Duplicate node hashes in model Unit {resource}')
                signature = []
                for row in profile['signature']:
                    name = row['name']; name_hash = bone_name_hash(name)
                    if row.get('hash', name_hash) != name_hash:
                        raise ValueError(f'Signature hash does not match name: {name}')
                    if name_hash not in unit.name_hashes:
                        raise ValueError(f'Target {resource} lacks signature bone {name}')
                    index = unit.name_hashes.index(name_hash)
                    signature.append(dict(name=name, hash=name_hash, index=index,
                                          parentIndex=unit.parents[index]))
                topology = json.dumps([unit.name_hashes, unit.parents], separators=(',', ':')).encode()
                layout = dict(nodeCount=len(unit.transforms), signature=signature,
                              layoutSha256=hashlib.sha256(topology).hexdigest(),
                              unitSha256=hashlib.sha256(payload).hexdigest(),
                              sourcePatch=path.name, ownerSlot=targets[resource])
                if resource in layouts and layouts[resource] != layout:
                    raise ValueError(f'Conflicting final model definitions for {resource}')
                layouts[resource] = layout
    missing = set(targets) - set(layouts)
    if missing:
        raise ValueError('Final model patches lack target Units: ' + ', '.join(sorted(missing)))
    return layouts


def with_model_layouts(profile, model_patches):
    result = copy.deepcopy(profile)
    result['modelLayouts'] = build_model_layouts(model_patches, result)
    result.pop('expectedModelNodes', None)
    result['version'] = max(4, result.get('version', 0))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--model-patch', required=True, action='append', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding='utf-8-sig'))
    result = with_model_layouts(profile, args.model_patch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({resource: dict(nodeCount=row['nodeCount'], layoutSha256=row['layoutSha256'])
                      for resource, row in result['modelLayouts'].items()}, indent=2))


if __name__ == '__main__':
    main()
