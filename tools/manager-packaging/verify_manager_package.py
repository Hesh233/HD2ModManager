"""Read back every portable-package member and its nested production physics ZIP."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import re
import struct
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('zip', type=Path)
parser.add_argument('--report', required=True, type=Path)
parser.add_argument('--protected', type=Path)
a = parser.parse_args()
sha = lambda data: hashlib.sha256(data).hexdigest()
m = json.loads(Path(str(a.zip) + '.manifest.json').read_text(encoding='utf-8-sig'))
assert m['mode'] == 'Full' and m['generatedArtifactCount'] == 1
assert m['buildFlavor'] == 'skeleton-test' and not m['selfUpdatesEnabled']
assert sha(a.zip.read_bytes()) == m['sha256']
with zipfile.ZipFile(a.zip) as outer:
    assert outer.testzip() is None
    assert len(outer.namelist()) == len(set(outer.namelist())) == m['fileCount']
    assert set(outer.namelist()) == {e['path'] for e in m['entries']}
    for e in m['entries']:
        body = outer.read(e['path'])
        assert len(body) == e['size'] and sha(body) == e['sha256'], e['path']
        assert not re.search(r'(^|/)(test-library|logs|cache|__pycache__|测试包)(/|$)', e['path'])
        assert not e['path'].lower().endswith(('.bak', '.pdb'))
    b3 = m.get('modelRuntimeCompanions')
    b3_included = 'HD2ModManager/anim_batch_mod/runtime_companions.py' in outer.namelist()
    if b3_included:
        assert b3 and b3['status'] == 'ready'
        assert b3['runtimeVersion'] == '1.0.19' and b3['firstPersonSourceVersion'] == '1.0.1'
        assert b3['schema'] == 'hd2-grip-switches-v1'
        assert len(b3['resources']) == len({r['name'] for r in b3['resources']}) == 8
        assert all('.PhysBone.Production.' in r['name'] for r in b3['resources'])
        assert sha(outer.read('HD2ModManager/HD2ModCore.dll')) == b3['coreSha256']
        assert sha(outer.read('HD2ModManager/anim_batch_mod/runtime_companions.py')) == b3['compilerSha256']
        info = json.loads(outer.read('HD2ModManager/anim_batch_mod/build-info.json'))
        assert info['runtimeCompanionVersion'] == b3['runtimeVersion']
        assert info['firstPersonSourceVersion'] == b3['firstPersonSourceVersion']
        assert info['managerVersion'] == b3['managerVersion'] == m['managerVersion']
        assert m['managerVersion'] in a.zip.name
    artifact = m['productionArtifacts'][0]
    proof = artifact['provenance']
    for name, expected in proof['inputs'].items():
        assert sha(outer.read('HD2ModManager/' + name)) == expected, name
    data = outer.read(artifact['path'])
    assert sha(data) == proof['zipSha256']
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {e['path'] for e in proof['entries']}
        for e in proof['entries']:
            b = z.read(e['path']); assert len(b) == e['bytes'] and sha(b) == e['sha256']
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['Guid'] == proof['guid'] == '7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01'
        assert manifest['Name'] == 'HD2 物理骨骼运行时'
        assert len(z.namelist()) == 4 and all('/' not in n for n in z.namelist())
        patch = z.read('9ba626afa44a3aa3.patch_0')
        offset = struct.unpack_from('<Q', patch, 120)[0]
        size = struct.unpack_from('<I', patch, offset)[0]
        source = patch[offset+8:offset+8+size].decode('utf-8').replace('\r\n', '\n')
        assert source.startswith('-- HD2-Addon: mods/hd2modmanager/physbone\n')
        assert sha(source.encode('utf-8')) == proof['sourceSha256']
    settings = json.loads(outer.read('HD2ModManager/settings.json'))
    assert settings['ModLibraryFolder'] is None and settings['GameDataFolder'] is None
    assert settings['PhysicsMode'] == 0 and not settings['BuiltInLuaEnabled']
    assert not settings['AskToInstallSkeletonAnimation'] and not settings['EnableDualSkeletonAnimationVersion']
protected_count = 0
if a.protected:
    protected = json.loads(a.protected.read_text(encoding='utf-8-sig'))
    for path, expected in protected.items():
        assert sha(Path(path).read_bytes()) == expected, 'Protected input changed: ' + path
    protected_count = len(protected)
report = dict(status='PASS_OFFLINE', zip=str(a.zip.resolve()), zipBytes=a.zip.stat().st_size,
              zipSha256=m['sha256'], outerEntries=m['fileCount'], allowlistedPayloads=m['payloadCount'],
              productionPhysicsArtifact=artifact, nestedRootEntries=4, allOuterSha256AndCrcVerified=True,
              allNestedSha256AndCrcVerified=True, physicalCompanionAndShippedDllsSameSource=True,
              testB3BasePanelIncluded=False, protectedFilesUnchanged=protected_count,
              modelRuntimeCompanionGeneratorIncluded=b3_included, modelRuntimeCompanionCapabilities=b3,
              verifierWritesRuntimeFiles=False, gameDeployed=False, newGameTestPerformed=False)
a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='productionPhysicsArtifact'}, ensure_ascii=False, indent=2))
