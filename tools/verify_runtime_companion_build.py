"""Verify the shipped Python -> production Core -> two ZIPs -> isolated Core import chain.
Reads supplied model/game data only. Does not bake animations, edit source models,
write an active library, deploy to the game, or borrow a prebuilt test ZIP.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData


def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--install', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--game-data', type=Path, required=True)
    p.add_argument('--model', type=Path, action='append', required=True)
    a = p.parse_args()
    install, output = a.install.resolve(), a.output.resolve()
    if output.exists(): raise FileExistsError('Choose a new real-model verification directory')
    output.mkdir(parents=True)
    runner = install/'anim_batch_mod/runtime/python.exe'
    script = install/'anim_batch_mod/main.py'
    helper = ROOT/'tools/ManagerPackageSupport/bin/Release/net10.0/ManagerPackageSupport.dll'
    checks = 0; results = []; package_guids = set()
    def run(command, log):
        result = subprocess.run([str(x) for x in command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding='utf-8', errors='strict', timeout=300)
        Path(log).write_text(result.stdout, encoding='utf-8')
        if result.returncode: raise RuntimeError('Command failed; see ' + str(log) + '\n' + result.stdout[-1500:])
        return result.stdout
    for model in a.model:
        model = model.resolve()
        manifests = list(model.rglob('source-skeleton.json'))
        if len(manifests) != 1: raise ValueError('Need one Source manifest per supplied model: ' + str(model))
        manifest = manifests[0]; m = load(manifest)
        label = model.name.removeprefix('[原比例模型]')
        folder = output/label; folder.mkdir()
        snapshot = folder/'config.toml'
        source_config = manifest.parent/'config.toml'
        source_hashes = {str(f): sha(f.read_bytes()) for f in model.rglob('*') if f.is_file()}
        run([runner, '-X', 'utf8', script, 'prepare-config', '--config', source_config,
            '--output', snapshot, '--manifest', manifest, '--model-scale', m['modelScale']], folder/'config-snapshot.log')
        run([runner, '-X', 'utf8', script, 'prepare-native-model', '--manifest', manifest,
            '--model-directory', manifest.parent, '--config', snapshot, '--check-only'], folder/'model-check.log')
        calibration = folder/'calibration'
        run([runner, '-X', 'utf8', script, 'attachment-runtime', '--manifest', manifest,
            '--model-directory', manifest.parent, '--mod-directory', model, '--game-data', a.game_data,
            '--config', snapshot, '--attachment-config', install/'config/attachment-fix.json',
            '--output', calibration, '--runtime-companions', '--model-label', label], folder/'python-build.log')
        exported = json.loads(run(['dotnet', helper, 'companion-export', install, calibration, folder/'delivery', label], folder/'core-export.log'))
        report = load(exported['Report']); profile = load(calibration/'attachment-profile.json')
        assert report['status'] == 'complete' and report['publishedTogether']; checks += 2
        assert report['version'] == '1.0.19' and report['firstPersonSourceVersion'] == '1.0.1'; checks += 2
        assert report['boneOrder'] == profile['optionSwitches']['bones']; checks += 1
        assert report['optionCount'] == len(profile['optionSwitches']['bones']) + 1; checks += 1
        assert not report['physicalRuntimeEmbedded'] and not report['gameTested']; checks += 2
        zip_checks = 0
        for kind, filename in [('basePackage', exported['BaseZip']), ('panelPackage', exported['PanelZip'])]:
            assert sha(Path(filename).read_bytes()) == report[kind]['sha256']; checks += 1
            with zipfile.ZipFile(filename) as z:
                assert z.testzip() is None; checks += 1
                assert len(z.namelist()) == len(set(z.namelist())) == len(report[kind]['entries']); checks += 1
                assert 'manifest.json' in z.namelist(); checks += 1
                for entry in report[kind]['entries']:
                    data = z.read(entry['path'])
                    assert len(data) == entry['size'] and sha(data) == entry['sha256']; checks += 2; zip_checks += 2
                manifest_data = json.loads(z.read('manifest.json'))
                assert manifest_data['Guid'] not in package_guids; checks += 1
                package_guids.add(manifest_data['Guid'])
                assert manifest_data['Nodes'][0]['Guid'] == manifest_data['Guid']; checks += 1
                if kind == 'basePackage':
                    assert not any('.patch_6' in n for n in z.namelist()); checks += 1
                    entry = next(iter(TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_4'), load_external_data=False).entries.values()))
                    length = struct.unpack_from('<I', entry.toc_data)[0]
                    runtime = bytes(entry.toc_data[8:8+length])
                    assert sha(runtime) == report['runtimeSourceSha256']; checks += 1
                    text = runtime.decode('utf-8')
                    assert 'local OptionSwitches=' in text and 'local FirstPersonSource=' in text and 'local HiddenFirstPerson=' in text; checks += 3
                    assert '1.0.18-test' not in text and 'local PhysBoneRuntime' not in text and '-- INSERT ' not in text; checks += 3
                    from lupa.lua51 import LuaRuntime
                    compiled, why = LuaRuntime(unpack_returned_tuples=True).eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(text)
                    assert compiled, why; checks += 1
                else:
                    options = manifest_data['Options']
                    assert len(options) == report['optionCount']; checks += 1
                    assert options[0]['Include'] == ['options/00-fp-arms']; checks += 1
                    assert [o['Include'][0] for o in options] == [s['folder'] for s in profile['optionSwitches']['specs']]; checks += 1
                    fp_names = [n for n in z.namelist() if '.patch_6' in n]
                    assert len(fp_names) == 3 and all(n.startswith('options/00-fp-arms/') for n in fp_names); checks += 1
                    raw = z.read('options/00-fp-arms/9ba626afa44a3aa3.patch_6')
                    toc = TocArchive.parse_parts(raw, load_external_data=False)
                    assert len(toc.entries) == 1; checks += 1
                    fp_entry = next(iter(toc.entries.values()))
                    assert fp_entry.type_id == UNIT_TYPE_ID; checks += 1
                    assert f'{fp_entry.file_id:016x}' == profile['firstPersonSource']['avatar']['resource']; checks += 1
                    unit = UnitData.parse(fp_entry.toc_data)
                    assert len(unit.parents) == report['firstPersonSourceCount']; checks += 1
                    assert sha(bytes(fp_entry.toc_data)) == profile['firstPersonSource']['expandedUnitSha256']; checks += 1
        imported = json.loads(run(['dotnet', helper, 'companion-import-check', install, exported['BaseZip'],
            exported['PanelZip'], folder/'isolated-import'], folder/'core-import.log'))
        assert imported['importedStandardCount'] == 2 and imported['importedOptionCount'] == report['optionCount']; checks += 2
        assert imported['fpGraphOnlyInFpOption'] and imported['tpOptionsMarkerOnly'] and not imported['gameDeployed']; checks += 3
        assert imported['coreSha256'] == sha((install/'HD2ModCore.dll').read_bytes()); checks += 1
        for file, before in source_hashes.items():
            assert sha(Path(file).read_bytes()) == before, file; checks += 1
        results.append(dict(model=label, sourceBones=len(m['bones']), tpAvatarCount=profile['avatar']['count'],
            fpAvatarCount=report['firstPersonSourceCount'], optionCount=report['optionCount'],
            baseZip=exported['BaseZip'], panelZip=exported['PanelZip'], importProof=imported,
            sourceFilesUnchanged=len(source_hashes), zipEntryHashChecks=zip_checks, gameDeployed=False))
        print(label, 'complete', 'FP', report['firstPersonSourceCount'], 'options', report['optionCount'], flush=True)
    result = dict(status='complete', scope='shipped Python -> chosen production Core -> fresh ZIP pair -> isolated archive import',
        checks=checks, models=results, installedCoreSha256=sha((install/'HD2ModCore.dll').read_bytes()),
        noPrebuiltTestZipUsed=True, noAnimationsRebaked=True, gameDeployed=False)
    (output/'real-model-generation-validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(status=result['status'], models=len(results), checks=checks, gameDeployed=False)))

if __name__ == '__main__': main()
