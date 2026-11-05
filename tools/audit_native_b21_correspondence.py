"""Verify the concrete static claims against extracted original Unit payloads."""
from package_native_v12 import ROOT, load, save_json, digest

W = ROOT / 'outputs/native-v29-b21-20261105'


def main():
    evidence = load(W / 'native-reference-assets.json')
    layouts = load(W / 'native-capture-layouts.json')
    assert evidence['status'] == 'EXTRACTED' and evidence['packagePatchesExcluded']
    assert not evidence['nativePrefixDifferenceIndices']
    assert len([r for r in evidence['resources'] if r['kind'] == 'native_armor']) == 24
    for row in evidence['resources']:
        assert digest(W / row['path']) == row['sha256'], row['path']
    source_only = []
    excluded = {'l_hand', 'r_hand', 'l_hand_twist', 'r_hand_twist', 'attach_hand_l', 'attach_hand_r'}
    for row in layouts['test01Models'].values():
        skin = row['skin']
        assert skin['skinNodeIndices']
        assert len(skin['skinNodeIndices']) == skin['sourceNamespaceInputs']
        assert not set(skin['skinNodeNames']) & excluded
        source_only.append(dict(resource=row['resource'], skinInputCount=len(skin['skinNodeIndices']),
                                sourceNamespaceInputs=skin['sourceNamespaceInputs']))
    assert len(source_only) == 11

    def find(row, name):
        return next(n for n in row['nodes'] if n['name'] == name)

    hands = []
    for side, avatar_index, source_index, model_resource, model_index, native_models in (
        ('l', 47, 115, 'd154442f2e33fdee', 31, ['23a244c877843da3', 'f6d665ef313b5a3c']),
        ('r', 71, 138, 'e0b67b19ba91057b', 40, ['30204ad0fe720352', '3b2875408869343e']),
    ):
        native_name = side + '_hand'
        avatar = find(layouts['nativeAvatar'], native_name)
        source_name = 'hd2n_4e4fb4fa303d_anim_' + ('008_l_hand' if side == 'l' else '031_r_hand')
        source = find(layouts['test01Avatar'], source_name)
        model = layouts['test01Models'][model_resource]
        model_hand = find(model, source_name)
        assert (avatar['index'], source['index'], model_hand['index']) == (avatar_index, source_index, model_index)
        assert model_hand['index'] in model['skin']['skinNodeIndices'] and source['hash'] == model_hand['hash']
        for resource in native_models:
            row = layouts['resources'][resource]
            node = find(row, native_name)
            assert row['nodeCount'] == 38 and node['index'] == 15
            assert node['index'] in row['skin']['skinNodeIndices'] and node['hash'] == avatar['hash']
            assert len(row['packages']) == 4
        hands.append(dict(side=side, nativeName=native_name, nativeAvatarIndex=avatar_index,
            nativeHandModelIndex=15, nativeHandModels=native_models, sourceName=source_name,
            sourceAvatarIndex=source_index, test01ModelResource=model_resource, test01ModelIndex=model_index))
    topology = {}
    for name in ('l_hand', 'attach_hand_l', 'l_hand_twist', 'r_hand', 'attach_hand_r', 'weapon_aim'):
        node = find(layouts['nativeAvatar'], name)
        topology[name] = dict(index=node['index'], parentIndex=node['parentIndex'], parentName=node['parentName'])
    assert topology['attach_hand_l']['parentName'] == 'l_hand'
    assert topology['l_hand_twist']['parentName'] == 'l_elbow'
    assert topology['attach_hand_r']['parentName'] == 'r_hand'
    assert topology['weapon_aim']['parentName'] == 'attach_hand_r'
    weapon = layouts['resources']['186ea95de7306b1a']
    grip = layouts['resources']['f9df21c8e52cac95']
    assert find(weapon, 'IK_left')['parentName'] == find(weapon, 'IK_right')['parentName'] == 'boss'
    assert find(grip, 'IK_left')['parentName'] == 'skeleton'
    save_json(W / 'static-correspondence-audit.json', dict(status='PASS', indexBase=0,
        originalArmorUnitCount=24, test01ModelCount=11, nativePrefixBindDataIdentical=True,
        handCorrespondence=hands, nativeAvatarTopology=topology, test01SkinInputs=source_only,
        weaponIK=dict(resource=weapon['resource'], left=find(weapon, 'IK_left')['index'],
                      right=find(weapon, 'IK_right')['index'], parent='boss'),
        foregripIK=dict(resource=grip['resource'], left=find(grip, 'IK_left')['index'], parent='skeleton'),
        sourceAssetReportSha256=digest(W / 'native-reference-assets.json'),
        layoutReportSha256=digest(W / 'native-capture-layouts.json'), gamePoseCaptured=False,
        conclusion='The native hand nodes are absent from the test01 mesh skin inputs; they cannot directly deform those meshes. Indirect engine propagation remains unverified.',
        limits='Static bind data and mesh BoneInfo remaps, not live IK priorities or decoded per-vertex weights.'))
    print('PASS: original/native and Source hand indices, 24 original armor Units, all 11 Source-only test01 skin mappings.')


if __name__ == '__main__':
    main()
