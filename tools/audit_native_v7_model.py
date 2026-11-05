"""Independently inspect serialized v7 model changes against the shipped v6 model."""
import hashlib
import struct
from pathlib import Path

from package_native_v7 import BASE, PROJECT, WORK, load, save_json, records, payload, main_patches, digest
from anim_batch_mod.constants import STATE_MACHINE_TYPE_ID, UNIT_TYPE_ID


def block(data):
    start = struct.unpack_from('<I', data, 52)[0]
    count = struct.unpack_from('<I', data, start)[0]
    pos = start + 16
    locals_ = [data[pos + 64*i:pos + 64*(i+1)] for i in range(count)]
    pos += 64*count
    worlds = [data[pos + 64*i:pos + 64*(i+1)] for i in range(count)]
    pos += 64*count
    entries = [struct.unpack_from('<HH', data, pos + 4*i) for i in range(count)]
    pos += 4*count
    hashes = struct.unpack_from(f'<{count}I', data, pos)
    return count, locals_, worlds, entries, hashes


def compose_bind(locals_, entries):
    """Independent raw row-matrix FK, including forward references and rotations."""
    cache, active = {}, set()
    def resolve(i):
        if i in cache:
            return cache[i]
        assert i not in active, 'Parent cycle'
        active.add(i)
        local=struct.unpack('<16f',locals_[i])
        parent=entries[i][1]
        identity=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]
        p=identity if i==0 or parent in (i,65535) else resolve(parent)
        out=[0.]*16
        for row in range(3):
            for col in range(3):
                out[4*row+col]=sum(local[3*row+k]*local[12+k]*p[4*k+col] for k in range(3))
            out[12+row]=sum(local[9+k]*p[4*k+row] for k in range(3))+p[12+row]
        out[15]=1.
        active.remove(i);cache[i]=out
        return out
    return [resolve(i) for i in range(len(locals_))]


def audit():
    manifest = load(PROJECT / 'source-skeleton.json')
    rows = manifest['motionLayers']
    assert [r['driver'] for r in rows] == ['root', 'boss']
    assert manifest['modelScale'] == 1.08 and manifest['scaleOrigin'] == 'source'
    mapping = load(WORK / 'o3-mapping.json')
    old_mapping = load(BASE.parent / 'o3-mapping.json')
    assert mapping == old_mapping
    targets = {int(r['targetUnit'],16) for r in mapping['mappings']}
    changes, unchanged, companions, resources = [], [], [], 0
    for folder, expected in [('models/test01', 7), ('models-o3/test01-O3', 11)]:
        changed_ids = set()
        model_root, old_root = PROJECT / folder, BASE / folder
        assert {p.name for p in main_patches(model_root)} == {p.name for p in main_patches(old_root)}
        for new in main_patches(model_root):
            old = old_root / new.name
            before = {(r[0],r[1]):r for r in records(old)}
            after = {(r[0],r[1]):r for r in records(new)}
            assert before.keys() == after.keys()
            assert not any(k[1] == STATE_MACHINE_TYPE_ID for k in after)
            for key, nr in after.items():
                a, b = payload(old,before[key]), payload(new,nr)
                resources += 1
                if key[1] != UNIT_TYPE_ID or a == b:
                    assert a == b
                    if key[1] == UNIT_TYPE_ID:
                        unchanged.append({'folder':folder, 'unit':f'{key[0]:016x}', 'nodes':block(b)[0], 'sha256':hashlib.sha256(b).hexdigest()})
                    continue
                ac, al, aw, ae, ah = block(a)
                bc, bl, bw, be, bh = block(b)
                assert ac == 203 and bc == 205
                assert be[0][0] == 0, 'Entity-root flags changed'
                assert list(ah) == list(bh[:ac]) and aw == bw[:ac]
                original_prefix = bytearray(b[:len(a)])
                original_prefix[52:56] = a[52:56]
                assert original_prefix == a, 'Non-transform Unit bytes changed'
                changed_indices = {bh.index(manifest['bones'][int(k)]['hash']):v for k,v in manifest['motionParentOverrides'].items()}
                assert len(changed_indices) == 2
                for i in range(ac):
                    assert ae[i][0] == be[i][0]
                    if i in changed_indices:
                        assert be[i][1] == ac + changed_indices[i]
                    else:
                        assert ae[i] == be[i] and al[i] == bl[i]
                for i, layer in enumerate(rows):
                    assert bh[ac+i] == layer['hash']
                    assert be[ac+i] == (1,bh.index(layer['parentHash']))
                    driver_world = struct.unpack('<16f',bw[bh.index(layer['driverHash'])])
                    helper_world = struct.unpack('<16f',bw[ac+i])
                    assert max(abs(x-y) for x,y in zip(driver_world,helper_world)) < 2e-5
                fk = compose_bind(bl,be)
                old_fk = compose_bind(al,ae)
                inherited_exceptions=[]
                for i in range(bc):
                    stored = struct.unpack('<16f',bw[i])
                    error=max(abs(x-y) for x,y in zip(fk[i],stored))
                    if error>=2e-5:
                        assert i<ac and i not in changed_indices
                        old_error=max(abs(x-y) for x,y in zip(old_fk[i],struct.unpack('<16f',aw[i])))
                        assert error<=old_error+2e-5
                        assert max(abs(x-y) for x,y in zip(fk[i],old_fk[i]))<2e-5
                        inherited_exceptions.append({'index':i,'hash':bh[i],'oldError':old_error,'newError':error})
                changed_ids.add(key[0])
                changes.append({'folder':folder,'unit':f'{key[0]:016x}','nodes':bc,'originalBindBytesUnchanged':True,'originalFlagsUnchanged':True,'onlySourceHipsAndSpineReparented':True,'preexistingBindMatrixExceptions':inherited_exceptions})
            for suffix in ['.gpu_resources','.stream']:
                a, b = Path(str(old)+suffix), Path(str(new)+suffix)
                assert a.exists() == b.exists()
                if a.exists():
                    assert digest(a) == digest(b)
                    companions.append({'file':str(b.relative_to(PROJECT)),'sha256':digest(b)})
        assert len(changed_ids) == expected
        if folder.startswith('models-o3'):
            assert changed_ids == targets
        a, b = old_root/'physbone-rig.bin', model_root/'physbone-rig.bin'
        assert a.is_file() and digest(a) == digest(b)
        companions.append({'file':str(b.relative_to(PROJECT)),'sha256':digest(b)})
    assert len(unchanged) == 6 and all(r['nodes']==25 for r in unchanged)
    mesh = load(WORK/'model-mesh-comparison.json')
    floor = load(WORK/'serialized-floor-audit.json')
    assert mesh['status'] == floor['status'] == 'PASS'
    assert mesh['maxPositionError'] == 0 and mesh['topologyNormalsUvWeightsUnchanged']
    result = {'status':'PASS','resourcesChecked':resources,'changedUnits':changes,'unchangedHiddenUnits':unchanged,
        'binaryCompanions':companions,'mesh':mesh,'floor':floor,'o3MappingPreserved':True,
        'materialsTexturesAndPhysicsBytesUnchanged':True,'modelStateMachines':0,'gameTested':False}
    save_json(WORK/'model-final-audit.json',result)
    return {'status':'PASS','changedUnits':len(changes),'unchangedHiddenUnits':len(unchanged),'resourcesChecked':resources}


if __name__ == '__main__':
    print(audit())
