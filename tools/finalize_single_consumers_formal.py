"""Fail-closed final gates and NEW A/B ZIP delivery. No library/normal Core writes."""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, sys, zipfile
ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT/'outputs/physics-single-consumers-formal-20261117'
NORMAL = ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
PROD = ROOT/'HD2PhysBoneCompat/src/production'
ap = argparse.ArgumentParser()
ap.add_argument('--output', type=Path, default=LAB/'release-r2')
ap.add_argument('--deliver', action='store_true')
a = ap.parse_args()
OUT = a.output.resolve()
assert OUT.is_relative_to(LAB) and not OUT.is_relative_to(NORMAL)
def read(p): return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def require(ok, message):
    if not ok: raise RuntimeError(message)
# Protected inputs are compared, never restored to an older user configuration.
before = read(LAB/'protected-before.json')
after, changed = {}, []
for key, old in before.items():
    p = Path(key)
    now = dict(exists=p.is_file(), sha256=sha(p) if p.is_file() else None, bytes=p.stat().st_size if p.is_file() else None)
    after[key] = now
    if now != old: changed.append(key)
require(not changed, 'Protected inputs changed; refusing delivery without rollback: '+str(changed))
(OUT/'protected-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
configs = []
for argv in [['--source-config', str(ROOT.parent/'config.toml'), '--bundle-root', str(ROOT/'tools/native-python/anim_batch_mod')], ['--manager-root', str(NORMAL)]]:
    r = subprocess.run([sys.executable, '-B', str(ROOT/'tools/check_animation_config.py')]+argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    require(r.returncode == 0, 'Animation configuration gate: '+r.stdout+r.stderr)
    configs.append(json.loads(r.stdout))
(OUT/'configuration-gates.json').write_text(json.dumps(configs, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
# Re-read actual ZIP/IL/owner/source/template/profile checks rather than trust old PASS files.
r = subprocess.run([sys.executable, '-B', str(ROOT/'tools/verify_single_consumers_formal.py'), '--output', str(OUT)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
(OUT/'verify-final.log').write_text(r.stdout+r.stderr, encoding='utf-8')
require(r.returncode == 0, 'Actual formal ZIP verification failed: '+r.stdout+r.stderr)
manifest = read(PROD/'single_remote_release_manifest.json')
catalog = read(PROD/'single_consumer_catalog.json')
require(len(catalog['units']) == manifest['consumerProfiles'] == 61, 'Exact consumer profile count')
require(len({p['resource'] for p in catalog['units']}) == manifest['consumerDistinctResources'] == 39, 'Distinct resource count')
require(len(catalog['models']) == 4 and catalog['models'] == manifest['consumerModels'], 'Per-model consumer certificates')
modelProofs = []
for model in catalog['models']:
    folder = (NORMAL/'test-library'/model['modelName']/'sectional').resolve()
    require(folder.is_relative_to(NORMAL/'test-library'), 'Unsafe model path')
    for field, name in [('rigSha256', 'physbone-rig.bin'), ('driverRigSha256', 'physbone-driver-rig.bin'), ('bindSha256', 'single-hd2-bind.json'), ('configSha256', 'single-config.toml')]:
        require(sha(folder/name) == model[field], 'Actual model certificate changed: '+model['modelName']+'/'+name)
    for unit in catalog['units']:
        if unit['model'] == model['modelName']:
            require(unit['modelBindSha256'] == model['bindSha256'] and unit['effectiveConfigSha256'] == model['configSha256'], 'Unit/effective model certificate mismatch')
    modelProofs.append(model)
producer = read(LAB/'producer-finish-verification.json')
require(producer['status'] == 'PASS_FRESH_PRODUCER_AND_STALE_CERTIFICATE_REJECTION', 'Fresh producer verification missing')
require(producer['sourceSha256'] == manifest['templateSha256']['consumerProducer'], 'Producer source changed after verification')
require(len(producer['models']) == 4 and len(producer['negativeCases']) == 3, 'Producer coverage incomplete')
fk = read(LAB/'fk-release/result.json')
require(fk['status'] == 'PASS_PRODUCTION_CONSUMER_FK_AND_HANDBACK_NOT_FPS' and len(fk['cases']) == 290 and fk['profiles'] == 61, 'Full real bind/FK replay missing')
require(all(c['retainedStateAndWorldPose'] == 'bit-identical' and c['oneTimeHandback'] and c['wholeRigUnchanged'] for c in fk['cases']), 'Retained solver/handback drift')
require({c['vm'] for c in fk['cases']} == {'lua51', 'luajit21'}, 'FK replay requires both VMs')
require(fk['harnessSha256'] == sha(ROOT/'HD2PhysBoneCompat/test/single-consumer-fk-test.py'), 'FK harness changed after replay')
require(fk['nonMeshConsumersCompared'] and fk['catalogSha256'] == sha(PROD/'single_consumer_catalog.json') and all(e['compatSha256'] == fk['compatSha256'] for e in manifest['sources']), 'Full FK/non-mesh proof used a stale source or profile')
run = read(OUT/'gate-run.json')
require(run['status'] == 'PASS_ALL_ACTUAL_ZIP_CONSUMER_GATES' and len(run['tests']) == 37, 'Incomplete actual ZIP gate run')
for test in run['tests']:
    require(test['returncode'] == 0 and sha(test['command'][3]) == test['scriptSha256'] and sha(test['log']) == test['logSha256'], 'Gate script/log changed: '+test['label'])
expectedReal = {'test01': (84,12,42,6), 'cow': (182,29,14,2), 'test13': (98,14,35,10), 'test15': (203,29,98,14)}
require(run['inputs']['catalog'] == sha(PROD/'single_consumer_catalog.json'), 'Catalog changed after runtime tests')
runtimeChecks, inventoryChecks, epochChecks, packages = 0, 0, 0, []
for entry in manifest['sources']:
    v = entry['variant']
    require(run['inputs'][v+'Runtime'] == entry['runtimeSha256'] and run['inputs'][v+'Compat'] == entry['compatSha256'], 'Actual ZIP tests used different source bytes')
    require(sha(LAB/(v+'-source/physbone_compat.lua')) == entry['compatSha256'], 'Full FK source differs from final shared solver')
    verify = read(OUT/(v+'-formal-verification.json'))
    require(verify['status'] == 'PASS_ACTUAL_CONSUMER_FORMAL_ZIP' and verify['methodsChanged'] == 0 and len(verify['installers']) == 6, 'Actual exporter/loader verification incomplete')
    for vm in ['lua51', 'luajit21']:
        rt = read(OUT/('runtime-'+v+'-'+vm)/'result.json')
        require(rt['status'] == 'PASS_ACTUAL_RUNTIME_REAL_CONSUMER_DATA_NOT_FPS' and rt['checks'] >= 77 and rt['fpChecks'] == 3, 'Runtime lifecycle/ADS checks missing')
        require(rt['runtimeSha256'] == entry['runtimeSha256'] and rt['compatSha256'] == entry['compatSha256'], 'Runtime source SHA mismatch')
        runtimeChecks += rt['checks']
        inv = read(OUT/('inventory-'+v+'-'+vm)/'result.json')
        require(inv['status'] == 'PASS_REAL_LOADER_CONSUMER_INVENTORY_NOT_FPS' and len(inv['cases']) == 3, 'Real disk loader inventory coverage incomplete')
        require(inv['runtimeSha256'] == entry['runtimeSha256'] and inv['compatSha256'] == entry['compatSha256'], 'Inventory source SHA mismatch')
        require(inv['cases'][0]['mode'] == 'active' and all(c['mode'] is None and c['files'] == 3 for c in inv['cases'][1:]), 'Higher TOC/orphan inventory used stale mask')
        inventoryChecks += inv['checks']
        epoch = read(OUT/('epoch-'+v+'-'+vm)/'result.json')
        require(epoch['harnessSha256'] == sha(ROOT/'HD2PhysBoneCompat/test/single-consumer-epoch-test.py'), 'Epoch harness changed after replay')
        require(epoch['status'] == 'PASS_PENDING_PROOF_WORLD_OPTION_EPOCH_NOT_FPS' and epoch['checks'] == 12, 'Pending proof epoch coverage incomplete')
        require(epoch['runtimeSha256'] == entry['runtimeSha256'] and epoch['compatSha256'] == entry['compatSha256'] and epoch['worldInvalidationClosedPendingHandles'] and epoch['newWorldRestartsProof'] and epoch['pendingPoseWrites'] == 0, 'World/option epoch retained stale proof or pose writes')
        epochChecks += epoch['checks']
        for name, count in [('single-ship-formal-test.lua',45), ('single-ads-formal-test.lua',53), ('single-mainline-regression-test.lua',87), ('multiplayer-skeleton-regression-test.lua',51)]:
            baseline = '-full-baseline' if 'regression' in name else ''
            log = (OUT/(v+'-'+vm+'-'+name+baseline+'-actual-zip.log')).read_text('utf-8')
            require('FAIL ' not in log and 'ERROR ' not in log and log.count('PASS ') >= count, 'Actual ZIP baseline failed: '+name)
    proof = read(OUT/(v+'-export/physics-provenance.json'))
    z = OUT/(v+'-export/physics-runtime.zip')
    require(sha(z) == proof['zipSha256'] == verify['zipSha256'], 'ZIP SHA changed')
    with zipfile.ZipFile(z) as file:
        require(file.testzip() is None and len(file.infolist()) == 4, 'Formal ZIP CRC/member count')
    filename = ('物理运行时-单骨架-A-精确消费者舰船全开任务仅自己-2.3.15-正式版.zip' if v == 'A' else '物理运行时-单骨架-B-精确消费者舰船全开任务队友禁VRD-2.3.16-正式版.zip')
    dest = (NORMAL/'运行时配套'/filename).resolve()
    require(dest.parent == (NORMAL/'运行时配套').resolve(), 'Unsafe delivery destination')
    require(not dest.exists() or (dest.is_file() and sha(dest) == proof['zipSha256']), 'Refusing to overwrite different existing package: '+str(dest))
    packages.append(dict(variant=v, runtimeVersion=entry['runtimeVersion'], compatVersion='1.3.11', path=str(dest), bytes=z.stat().st_size, sha256=proof['zipSha256'], exportPath=str(z)))
require(len(packages) == 2 and {p['variant'] for p in packages} == {'A','B'}, 'Both variants must pass before any delivery')
compatSha = manifest['sources'][0]['compatSha256']
require(all(e['compatSha256'] == compatSha for e in manifest['sources']), 'A/B shared solver drift')
for vm in ['lua51', 'luajit21']:
    for name, expected in expectedReal.items():
        r = read(OUT/('real-'+name+'-'+vm)/'result.json')
        require(r['status'] == 'PASS_REAL_DEPLOYED_PAYLOAD_PROOF_NOT_FPS' and r['compatSha256'] == compatSha and len(r['unitRows']) == 7, 'Real model proof incomplete: '+name+'/'+vm)
        require(tuple(r[k] for k in ['fullChains','closedChains','fullDrivers','closedDrivers']) == expected, 'Real model consumer closure changed: '+name+'/'+vm)
for case in ['gpu','toc','higher','missing_gpu','bind']:
    r = read(OUT/('negative-'+case+'-luajit21')/'result.json')
    require(r['status'] == 'PASS_REAL_DEPLOYED_PAYLOAD_PROOF_NOT_FPS' and r['compatSha256'] == compatSha and r['mutation'] == case and r['unitRows'][0]['mode'] is None, 'Mismatch did not retain full solver: '+case)
if a.deliver:
    for package in packages:
        dest = Path(package['path'])
        if not dest.exists():
            with Path(package['exportPath']).open('rb') as src, dest.open('xb') as output: shutil.copyfileobj(src, output)
        require(sha(dest) == package['sha256'], 'Delivered ZIP byte mismatch')
result = dict(status='DELIVERED_TWO_CONSUMER_FORMAL_PACKAGES' if a.deliver else 'ALL_CONSUMER_FORMAL_GATES_PASSED', packages=packages,
              protectedPaths=len(before), protectedFiles=sum(x['exists'] for x in before.values()), protectedChanges=[],
              rootConfigSha256=sha(NORMAL/'config.toml'), normalCoreSha256=sha(NORMAL/'HD2ModCore.dll'),
              consumerProfiles=61, consumerResources=39, models=modelProofs, fkCases=290, fkChecks=fk['checks'],
              runtimeChecks=runtimeChecks, inventoryChecks=inventoryChecks, epochChecks=epochChecks, actualZipGateCommands=41,
              actualFpsMeasured=False, gameOrManagerLaunched=False, normalCoreUpdated=False,
              libraryOrModelsReimportedOrRebaked=False, defaultVariantSelected=False)
(OUT/('delivery.json' if a.deliver else 'final-gates.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
