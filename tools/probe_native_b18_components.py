"""Read exact weapon component layouts; no game or resource-index writes."""
import hashlib
import sqlite3
from pathlib import Path
from package_native_v12 import ROOT, save_json
from anim_batch_mod.archive import PackageStore, ResourceIndex, TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData

W = ROOT / 'outputs/native-v26-b18-20261105'
SPECS = {
    '9c22a90da9c79de3': dict(count=11, markerIndex=3, signature=[
        dict(name='StingrayEntityRoot', index=0), dict(name='FbxAxisSystem_ConvertNode', index=1),
        dict(name='game_mesh', index=3), dict(name='g_mag', index=8), dict(name='collision', index=9)]),
    '52ff81fcba0c059d': dict(count=12, markerIndex=8, signature=[
        dict(name='StingrayEntityRoot', index=0), dict(name='FbxAxisSystem_ConvertNode', index=1),
        dict(name='shadow_mesh', index=3), dict(name='collision', index=6), dict(name='game_mesh', index=8)]),
}


def main():
    assets = W / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    names = {int(a): b for a, b in (line.split(' ', 1) for line in
             (ROOT.parents[1] / 'hashlists/friendlynames.txt').read_text(encoding='utf-8-sig').splitlines() if ' ' in line)}
    bones = {int(a): b for a, b in (line.split(' ', 1) for line in
             (ROOT.parents[1] / 'hashlists/bonehash.txt').read_text(encoding='utf-8-sig').splitlines() if ' ' in line)}
    index_path = ROOT / 'outputs/native-v9-20261104/project/animations/resource-index.sqlite3'
    index = ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')))
    index.connection = sqlite3.connect(index_path.as_uri() + '?mode=ro', uri=True)
    rows = {}
    try:
        for resource in ('39ab99895147a3bf', '9c22a90da9c79de3', 'e8d5f49ad7780e54', '52ff81fcba0c059d'):
            package, entry = index.resolve(int(resource, 16), UNIT_TYPE_ID)
            unit = UnitData.parse(entry.toc_data)
            (assets / (resource + '.toc')).write_bytes(entry.toc_data)
            named = {bones.get(h): i for i, h in enumerate(unit.name_hashes) if h in bones}
            rows[resource] = dict(resource=resource, name=names.get(int(resource, 16)), package=package,
                nodeCount=len(unit.transforms), sha256=hashlib.sha256(entry.toc_data).hexdigest(),
                nodes=[dict(index=i, hash=h, name=bones.get(h), parentIndex=unit.parents[i]) for i, h in enumerate(unit.name_hashes)])
            if resource in SPECS:
                spec = SPECS[resource]
                assert len(unit.transforms) == spec['count']
                for node in spec['signature']:
                    assert named.get(node['name']) == node['index']
                assert named['game_mesh'] == spec['markerIndex'] and 'skeleton' not in named
                assert not ('IK_left' in named and 'IK_right' in named)
                rows[resource].update(legacyDiscoveryWouldExclude=True,
                    reason='No skeleton node and no paired hand IK markers; existing component gate is never entered.',
                    liveIdentityConfirmed=False, exactSignature=spec)
        for weapon, component in (('39ab99895147a3bf', '9c22a90da9c79de3'), ('e8d5f49ad7780e54', '52ff81fcba0c059d')):
            archive = TocArchive.load_toc_only(index.store, rows[weapon]['package'])
            entry = next(e for e in archive.entries_of_type(UNIT_TYPE_ID) if e.file_id == int(component, 16))
            assert hashlib.sha256(entry.toc_data).hexdigest() == rows[component]['sha256']
            rows[component]['weaponPackageContainingIdenticalResource'] = rows[weapon]['package']
    finally:
        index.close()
    rows['52ff81fcba0c059d']['role'] = 'Epoch same-package non-skeletal component; visual ammo identity remains unconfirmed.'
    save_json(W / 'component-layout-audit.json', dict(status='PASS', resources=rows, simpleWeaponComponents=SPECS,
        sourceIndex=str(index_path), indexOpenedReadOnly=True, gameDeployed=False, gameTested=False,
        scope='Serialized resource layouts prove the old classifier omits these resources if encountered. '
              'They do not prove the live linked parent, ownership, or that refresh alone fixes the observed parts.'))
    print('Verified 11-node flamethrower canister and 12-node Epoch component: both lack skeleton and are excluded by legacy discovery.')


if __name__ == '__main__':
    main()
