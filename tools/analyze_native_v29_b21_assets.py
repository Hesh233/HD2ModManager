"""Extract original B-01/Avatar/weapon data and inspect serialized skin bindings."""
import csv
import hashlib
import math
import struct
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest
from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData
from anim_batch_mod.native_skeleton import bone_name_hash

W = ROOT / 'outputs/native-v29-b21-20261105'
SDK = ROOT.parents[1]
P = ROOT / 'outputs/native-manual-20261103/project'
DATA = Path('E:/Steam/steamapps/common/Helldivers 2/data')
AVATAR = '4d1c334d294dfa97'
ARCHIVES = {'58e4bd4b2278d15c': 'B-01 Tactical Variation 1',
            '562a45e9bc984eb9': 'B-01 Tactical Variation 2',
            '6cd3d55c05d4eac1': 'B-01 Tactical Variation 3',
            '519cc1ec2eb56e1d': 'B-01 Tactical Variation 4',
            '94eaeaffd878dd6d': 'SMG-203 Gallant', '64f56a84b883af7d': 'Vertical Foregrip'}


def names_from(path):
    result = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            try:
                result[int(parts[0])] = parts[1]
            except ValueError:
                pass
    return result


def compose(a, b):
    result = [sum(a[j+3*k]*b[c*3+k] for k in range(3)) for c in range(3) for j in range(3)]
    result += [sum(a[j+3*k]*b[9+k] for k in range(3))+a[9+j] for j in range(3)]
    return result


def affine_rows(raw, unit):
    offset = struct.unpack_from('<I', raw, 52)[0] + 16
    local = []
    for i in range(len(unit.parents)):
        row = struct.unpack_from('<16f', raw, offset+64*i)
        local.append([row[j]*row[12+j//3] for j in range(9)] + list(row[9:12]))
    world = {}
    visiting = set()

    def one(i):
        if i not in world:
            assert i not in visiting, 'cyclic serialized skeleton'
            visiting.add(i)
            parent = unit.parents[i]
            world[i] = local[i] if parent is None else compose(one(parent), local[i])
            visiting.remove(i)
        return world[i]

    return local, [one(i) for i in range(len(local))]


def skin_bindings(data, unit):
    """Read BoneInfo remaps and mesh references, as stingray/unit.py does.

    This proves which nodes are eligible skin inputs; it does not assign vertex
    regions or claim every palette entry has a nonzero vertex weight.
    """
    n = len(unit.parents)

    def read(fmt, at):
        assert at >= 0 and at+struct.calcsize(fmt) <= len(data), 'skin section outside Unit'
        return struct.unpack_from(fmt, data, at)

    palettes = []
    block = read('<I', 88)[0]
    if block:
        count = read('<I', block)[0]
        assert count < 256
        for off in read('<'+'I'*count, block+4):
            start = block+off
            size, matrix_off, real_off, remap_off = read('<4I', start)
            assert size <= 1024
            real = list(read('<'+'I'*size, start+real_off))
            assert all(i < n for i in real), 'skin palette index outside TransformInfo'
            read('<'+'f'*(16*size), start+matrix_off)
            remap_start = start+remap_off
            groups = read('<I', remap_start)[0]
            assert groups < 256
            remaps = []
            for g in range(groups):
                at, length = read('<2I', remap_start+4+8*g)
                assert length <= 1024
                remap = list(read('<'+'I'*length, remap_start+at))
                assert all(i < len(real) for i in remap), 'skin remap outside real-index list'
                remaps.append([real[i] for i in remap])
            palettes.append(dict(realIndices=real, remappedIndices=remaps))
    meshes = []
    block = read('<I', 100)[0]
    if block:
        count = read('<I', block)[0]
        assert count < 512
        for i, off in enumerate(read('<'+'I'*count, block+4)):
            start = block+off
            transform = read('<I', start+48)[0]
            palette, stream = read('<iI', start+56)
            assert palette == -1 or 0 <= palette < len(palettes), 'mesh references missing palette'
            meshes.append(dict(meshIndex=i, transformIndex=transform, boneInfoIndex=palette, streamIndex=stream))
    referenced = {m['boneInfoIndex'] for m in meshes if m['boneInfoIndex'] >= 0}
    skin_nodes = sorted({i for p in referenced for remap in palettes[p]['remappedIndices'] for i in remap})
    return dict(palettes=palettes, meshes=meshes, skinNodeIndices=skin_nodes,
                evidence='Serialized mesh BoneInfo remaps; vertex weights were not decoded.')


def main():
    W.mkdir(exist_ok=True)
    store = PackageStore(DATA)
    friendly = names_from(SDK / 'hashlists/friendlynames.txt')
    bone_names = names_from(SDK / 'hashlists/bonehash.txt')
    manifest = load(P / 'source-skeleton.json')
    bone_names.update({b['hash']: b['name'] for b in manifest['bones']})
    base_archive = TocArchive.load_toc_only(store, '18235e0c9ec0e636')
    base_raw = base_archive.entries[int(AVATAR, 16), UNIT_TYPE_ID].toc_data
    base = UnitData.parse(base_raw)
    assert len(base.parents) == 107
    bones = base_archive.entries[base.bones_ref, BONE_TYPE_ID]
    bone_data = BonesData.parse(bones.toc_data)
    bone_names.update(zip(bone_data.hashes, bone_data.names))
    assets = W / 'assets'
    assets.mkdir(exist_ok=True)
    (assets / 'native-avatar.bones').write_bytes(bones.toc_data)
    if (base.state_machine_ref, STATE_MACHINE_TYPE_ID) in base_archive.entries:
        (assets / 'native-avatar.state_machine').write_bytes(base_archive.entries[base.state_machine_ref, STATE_MACHINE_TYPE_ID].toc_data)
    native_by_hash = {h:i for i,h in enumerate(base.name_hashes)}
    report_rows = []
    capture_resources = {}

    def describe(resource, raw, kind, package, label):
        unit = UnitData.parse(raw)
        local, world = affine_rows(raw, unit)
        rows = []
        for i, h in enumerate(unit.name_hashes):
            parent = unit.parents[i]
            rows.append(dict(index=i, hash=h, name=bone_names.get(h), parentIndex=parent,
                parentName=None if parent is None else bone_names.get(unit.name_hashes[parent]),
                nativeAvatarIndex=native_by_hash.get(h), localMatrix=local[i], worldBindMatrix=world[i]))
        skin = skin_bindings(raw, unit)
        skin['skinNodeNames'] = [rows[i]['name'] for i in skin['skinNodeIndices']]
        path = assets / (kind+'-'+resource+'.toc')
        path.write_bytes(raw)
        row = dict(resource=resource, kind=kind, package=package, label=label, path=str(path.relative_to(W)),
            friendlyName=friendly.get(int(resource,16)), nodeCount=len(unit.parents), sha256=digest(path),
            bonesRef=f'{unit.bones_ref:016x}', stateMachineRef=f'{unit.state_machine_ref:016x}',
            nodes=rows, skin=skin)
        report_rows.append(row)
        return row

    native = describe(AVATAR, base_raw, 'native_avatar', '18235e0c9ec0e636', 'Original Helldiver Avatar')
    assert all(native['nodes'][native_by_hash[bone_name_hash(name)]]['name'] == name
               for name in ('l_hand','r_hand','attach_hand_l','attach_hand_r','weapon_aim'))
    hand_hashes = {bone_name_hash(n) for n in ('l_hand','r_hand')}
    ik_hashes = {bone_name_hash(n) for n in ('IK_left','IK_right')}
    for package, label in ARCHIVES.items():
        archive = TocArchive.load_toc_only(store, package)
        for (fid, kind), entry in archive.entries.items():
            if kind != UNIT_TYPE_ID or len(entry.toc_data) < 128:
                continue
            unit = UnitData.parse(entry.toc_data)
            if not (set(unit.name_hashes) & (hand_hashes if label.startswith('B-01') else ik_hashes)):
                continue
            resource = f'{fid:016x}'
            if resource in capture_resources:
                capture_resources[resource]['packages'].append(package)
                continue
            role = 'native_armor' if label.startswith('B-01') else ('weapon' if len(set(unit.name_hashes) & ik_hashes) == 2 else 'foregrip')
            row = describe(resource, entry.toc_data, role, package, label)
            capture_resources[resource] = dict(row, packages=[package])
    extended_archive = TocArchive.parse_parts(bytearray((P / 'animations/runtime/9ba626afa44a3aa3.patch_2').read_bytes()), load_external_data=False)
    extended_raw = extended_archive.entries[int(AVATAR,16), UNIT_TYPE_ID].toc_data
    extended = describe(AVATAR, extended_raw, 'test01_avatar', 'existing-v15', 'Current test01 Avatar')
    models = TocArchive.parse_parts(bytearray((P / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_0').read_bytes()), load_external_data=False)
    p = load(ROOT / 'outputs/native-v28-b20-20261105/B20-R.json')
    source_hashes = {n['hash'] for n in manifest['bones']}
    native_hands_in_test01_palette = []
    test01_rows = []
    for resource in p['modelLayouts']:
        row = describe(resource, models.entries[int(resource,16), UNIT_TYPE_ID].toc_data,
                       'test01_model', 'existing-test01-O3', 'Current test01 model')
        palette_hashes = {row['nodes'][i]['hash'] for i in row['skin']['skinNodeIndices']}
        row['skin']['sourceNamespaceInputs'] = len(palette_hashes & source_hashes)
        row['skin']['nativeHandInputs'] = [bone_names[h] for h in sorted(palette_hashes & hand_hashes)]
        native_hands_in_test01_palette.extend(row['skin']['nativeHandInputs'])
        test01_rows.append(row)
    native_prefix_diffs = [i for i in range(107) if native['nodes'][i]['hash'] != extended['nodes'][i]['hash']
                          or native['nodes'][i]['parentIndex'] != extended['nodes'][i]['parentIndex']
                          or native['nodes'][i]['localMatrix'] != extended['nodes'][i]['localMatrix']]
    mapping = []
    roles = ('l_clavicle','l_shoulder','l_elbow','l_hand','l_hand_twist','attach_hand_l',
             'r_clavicle','r_shoulder','r_elbow','r_hand','r_hand_twist','attach_hand_r','weapon_aim')
    for name in roles:
        h = bone_name_hash(name)
        native_index = native_by_hash.get(h)
        if native_index is None:
            continue
        source = next((b for b in manifest['bones'] if b['driver'] == name), None)
        mapping.append(dict(nativeName=name, nativeAvatarIndex=native_index,
            nativeParent=native['nodes'][native_index]['parentName'],
            sourceDriverName=None if source is None else source['name'],
            sourceAvatarIndex=None if source is None else 107+source['sourceIndex'],
            nativeArmor=[dict(resource=r['resource'], index=n['index'], parent=n['parentName'],
                              inSkinPalette=n['index'] in r['skin']['skinNodeIndices'])
                         for r in capture_resources.values() if r['kind']=='native_armor'
                         for n in r['nodes'] if n['hash']==h],
            test01NativeSlots=[dict(resource=r['resource'], index=n['index'],
                                    inSkinPalette=n['index'] in r['skin']['skinNodeIndices'])
                               for r in test01_rows for n in r['nodes'] if n['hash']==h]))
    with (W / 'native-hand-correspondence.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Native name','Avatar index (0-based)','Parent','Source driver','Source Avatar index',
                         'Native armor slots using this skin input','test01 native slots using this skin input'])
        for m in mapping:
            writer.writerow([m['nativeName'],m['nativeAvatarIndex'],m['nativeParent'],m['sourceDriverName'],m['sourceAvatarIndex'],
                             sum(x['inSkinPalette'] for x in m['nativeArmor']),sum(x['inSkinPalette'] for x in m['test01NativeSlots'])])
    save_json(W / 'native-reference-assets.json', dict(status='EXTRACTED', indexBase=0, dataRoot=str(DATA),
        gamePackageFingerprint=store.index_fingerprint(), packagePatchesExcluded=True,
        sdkSkinDecoderReference='stingray/unit.py: BoneInfo.GetRealIndex and MeshInfo.LodIndex',
        sdkSkinDecoderSha256=digest(SDK / 'stingray/unit.py'), resources=report_rows, handCorrespondence=mapping,
        nativePrefixDifferenceIndices=native_prefix_diffs, test01NativeHandSkinInputs=native_hands_in_test01_palette,
        gamePoseCaptured=False, originalDataWritten=False,
        limits='Serialized bind poses and skin remaps only. No claim that a static marker is the live IK target or that all remap entries have nonzero weights.'))
    save_json(W / 'native-capture-layouts.json', dict(nativeAvatar=native, test01Avatar=extended,
        resources=capture_resources, test01Models={r['resource']:r for r in test01_rows}))
    print('Original armor resources:', [(r['resource'],r['nodeCount'],r['friendlyName']) for r in capture_resources.values() if r['kind']=='native_armor'])
    print('Weapon / foregrip:', [(r['resource'],r['nodeCount']) for r in capture_resources.values() if r['kind']!='native_armor'])
    print('test01 native hand palette inputs:', native_hands_in_test01_palette)
    print('Native-prefix differences:', native_prefix_diffs)


if __name__ == '__main__':
    main()
