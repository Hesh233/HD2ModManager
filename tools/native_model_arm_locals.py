"""Bind the B8 local-pose copy to actual serialized Unit names and parents."""
import copy
from anim_batch_mod.native_skeleton import bone_name_hash


def with_model_arm_locals(profile, avatar, models):
    result = copy.deepcopy(profile)
    names = {n['index']: n['name'] for c in profile['armChains'] for n in c['nodes']}
    indices = [i for c in profile['armChains'] for i in (c['root'], c['mid'], c['hand'])]
    for row in profile['jointProcedures']:
        names[row['index']] = row['name']
        names[row['parentIndex']] = row['parentName']
        indices.append(row['index'])
    assert len(indices) == len(set(indices)) == 8
    assert len(avatar.transforms) == profile['expectedAvatarNodes']
    layouts = {}
    for resource, layout in profile['modelLayouts'].items():
        unit = models[resource]
        assert len(unit.transforms) == layout['nodeCount']
        assert len(set(unit.name_hashes)) == len(unit.name_hashes)
        rows = []
        for index in indices:
            name = names[index]
            parent = avatar.parents[index]
            parent_name = names[parent]
            hashed, parent_hash = bone_name_hash(name), bone_name_hash(parent_name)
            assert avatar.name_hashes[index] == hashed and avatar.name_hashes[parent] == parent_hash
            model_index = unit.name_hashes.index(hashed)
            model_parent = unit.parents[model_index]
            if model_parent is None or unit.name_hashes[model_parent] != parent_hash:
                raise ValueError(f'Cannot copy local pose across different parents: {resource}/{name}')
            rows.append(dict(name=name, hash=hashed, index=model_index, avatarIndex=index,
                             parentName=parent_name, parentHash=parent_hash,
                             parentIndex=model_parent, avatarParentIndex=parent))
        layouts[resource] = rows
    result['modelArmLocalLayouts'] = layouts
    result['modelArmLocalSync'] = True
    return result
