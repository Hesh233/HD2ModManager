"""Promote byte-identical user-accepted A/B archives without touching runtime/config/library."""
from pathlib import Path
import argparse, base64, hashlib, json, shutil, subprocess, sys, zipfile

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'outputs/physics-single-loader-size-fix-20261117'
OUT = ROOT / 'outputs/physics-single-loader-accepted-formal-20261117'
NORMAL = ROOT / 'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
PROD = ROOT / 'HD2PhysBoneCompat/src/production'
FEEDBACK = '继续之前中断任务，表现正常，ab打正式包，归档。之后分析已经开启物理并排除自身以外的物理的情况下，A包在战斗场景，为什么单玩家帧数要比4个玩家帧数高'
GATE = LAB / 'accepted-formal-gates'
EXPECTED_VERSIONS = {'A':'2.3.19','B':'2.3.20'}

def read(path): return json.loads(Path(path).read_text('utf-8-sig'))
def sha(path):
    with Path(path).open('rb') as file: return hashlib.file_digest(file, 'sha256').hexdigest()
def require(condition, message):
    if not condition: raise RuntimeError(message)
def snapshot(paths):
    return {str(p): {'exists': p.is_file(), 'bytes': p.stat().st_size if p.is_file() else None, 'sha256': sha(p) if p.is_file() else None} for p in sorted(set(map(Path, paths)))}
def write_new(path, content):
    path = Path(path)
    require(path.resolve().is_relative_to(ROOT.resolve()), 'Output outside workspace')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == content, 'Refuse overwrite of different artifact: ' + str(path))
    else:
        with path.open('xb') as file: file.write(content)
def json_new(path, value): write_new(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
def check_config():
    results = []
    for args in [['--source-config', str(ROOT.parent/'config.toml'), '--bundle-root', str(ROOT/'tools/native-python/anim_batch_mod')], ['--manager-root', str(NORMAL)]]:
        run = subprocess.run([sys.executable, '-B', str(ROOT/'tools/check_animation_config.py')] + args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
        require(run.returncode == 0, run.stdout + run.stderr)
        results.append(json.loads(run.stdout))
    return results

def prepare():
    require(not OUT.exists(), 'Preparation already exists; use its preserved snapshot, do not rebase protection')
    m = read(PROD/'single_remote_release_manifest.json')
    require(m['realGameAcceptanceStatus'] == 'loader-size-candidate-pending-physics-and-FPS', 'Unexpected source release status')
    delivery = read(LAB/'delivery.json')
    # The accepted B digest is deliberately cross-checked with both prior delivery and exporter provenance.
    for entry in delivery['packages']:
        v = entry['variant']; require(entry['runtimeVersion'] == EXPECTED_VERSIONS[v], 'Wrong accepted version')
        require(sha(entry['path']) == entry['sha256'] == sha(entry['exportPath']), 'Previously delivered payload changed')
    paths = list(read(LAB/'protected-before.json'))
    paths += [x['path'] for x in delivery['packages']]
    paths += [p for p in PROD.iterdir() if p.is_file() and p.name != 'single_remote_release_manifest.json']
    paths += list((NORMAL/'非运行文件/归档').glob('*.zip'))
    paths += [ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs', ROOT/'HD2PhysBoneCompat/test/single-consumer-fk-test.py']
    OUT.mkdir()
    json_new(OUT/'protected-before.json', snapshot(paths))
    before = OUT/'before'
    for p in [PROD/'single_remote_release_manifest.json', ROOT/'AGENTS.md', ROOT/'docs/agent/physics-single-loader-size-fix-20261117.md', Path(__file__)]:
        write_new(before/p.relative_to(ROOT), p.read_bytes())
    json_new(OUT/'configuration-before.json', check_config())
    log_root = Path.home()/'AppData/Roaming/Arrowhead/Helldivers2'
    logs = []
    for p in sorted(log_root.iterdir()):
        if p.is_file() and ('chef' in p.name or 'physbone' in p.name):
            b = p.read_bytes(); target = OUT/'logs'/p.name; write_new(target,b)
            digest=hashlib.sha256(b).hexdigest()
            logs.append({'path':str(p),'snapshot':str(target),'bytes':len(b),'sha256':digest,'stableDuringRead':digest==sha(p)})
    json_new(OUT/'log-snapshot.json', logs)
    current = {x['path']: x for x in logs}
    chef=(OUT/'logs/chef_loader.log').read_text('utf-8-sig')
    starts=[line for line in chef.splitlines() if 'started mods/hd2modmanager/physbone 2.3.19 ' in line or 'started mods/hd2modmanager/physbone 2.3.20 ' in line]
    require(len(starts)==2, 'Expected actual A19/B20 start evidence')
    for v in ['A','B']:
        text=(OUT/'logs'/('hd2physbone_'+v+'_identity.log')).read_text('utf-8-sig')
        require('SHIP_VRD_ENABLED' in text and 'LOCKED_NO_MORE_ID_CHECKS' in text, 'Actual scene/ADS logs missing')
    json_new(OUT/'user-acceptance.json', {'schema':'hd2-physics-user-acceptance-v1','date':'2026-11-17','timezone':'Asia/Shanghai','userWords':FEEDBACK,'scope':'user-reported normal behavior of A19/B20; no controlled 1-vs-4 FPS measurement','actualChefStarts':starts,'inputManifestSha256':sha(PROD/'single_remote_release_manifest.json'),'packages':delivery['packages'],'normalCoreNotUpdated':True,'controlledMultiplayerFpsAccepted':False})
    gate=GATE; require(not gate.exists(), 'Existing formal regression must not be overwritten'); gate.mkdir()
    for v in ['A','B']:
        for p in (LAB/'release-candidate'/(v+'-export')).iterdir():
            if p.is_file(): write_new(gate/(v+'-export')/p.name,p.read_bytes())
        p=LAB/'release-candidate'/(v+'-core-audit.json');write_new(gate/p.name,p.read_bytes())
    print('PREPARED current-state protection, actual logs, acceptance, isolated candidate exports', flush=True)

def validate_evidence():
    m=read(OUT/'before/HD2PhysBoneCompat/src/production/single_remote_release_manifest.json')
    catalog=read(PROD/'single_consumer_catalog.json')
    require(sha(PROD/'single_consumer_catalog.json')==m['consumerCatalogSha256'], 'Catalog drift')
    require(len(catalog['units'])==61 and len({p['resource'] for p in catalog['units']})==39, 'Consumer inventory changed')
    for model in catalog['models']:
        folder=NORMAL/'test-library'/model['modelName']/'sectional'
        for key,name in [('bindSha256','single-hd2-bind.json'),('configSha256','single-config.toml'),('rigSha256','physbone-rig.bin'),('driverRigSha256','physbone-driver-rig.bin')]:
            require(sha(folder/name)==model[key], 'Actual model/bind/config drift '+str(folder/name))
    probe=read(LAB/'palette-probe.json')
    for p in catalog['units']:
        row=next(x for x in probe if x['model']==p['model'] and x['resource']==p['resource'] and 'error' not in x)
        require(set(p['skinPaletteNodes'])==set(row['allRealPalette']) and set(p['weightedNodes'])<=set(p['skinPaletteNodes']), 'All-TOC palette mismatch')
        require(hashlib.sha256(base64.b64decode(p['tocExactBase64'],validate=True)).hexdigest()==p['tocSha256'], 'Exact TOC mismatch')
    fk=read(LAB/'fk-release/result.json')
    require(fk['status']=='PASS_PRODUCTION_CONSUMER_FK_AND_HANDBACK_NOT_FPS' and len(fk['cases'])==290 and fk['checks']==8744894 and fk['profiles']==61 and fk['nonMeshConsumersCompared'], 'Incomplete FK evidence')
    require(fk['harnessSha256']==sha(ROOT/'HD2PhysBoneCompat/test/single-consumer-fk-test.py') and fk['catalogSha256']==m['consumerCatalogSha256'] and fk['compatSha256']==m['sources'][0]['compatSha256'], 'FK input drift')
    require(all(x['retainedStateAndWorldPose']=='bit-identical' and x['oneTimeHandback'] and x['wholeRigUnchanged'] for x in fk['cases']), 'FK/handback drift')
    prod=read(LAB/'producer-finish-verification.json')
    require(prod['status']=='PASS_FRESH_PRODUCER_AND_STALE_CERTIFICATE_REJECTION' and prod['sourceSha256']==m['templateSha256']['consumerProducer']==sha(ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs') and len(prod['negativeCases'])==3, 'Producer proof drift')
    run=read(GATE/'gate-run.json')
    require(run['status']=='PASS_49_CORRECTION_CANDIDATE_GATES_NOT_GAME_FPS' and len(run['tests'])==49, 'Missing fresh actual ZIP gates')
    require(run['inputs']['catalog']==m['consumerCatalogSha256'] and run['inputs']['actualChefBit']==sha(LAB/'actual-chef-bit-shim.lua'), 'Fresh gate input drift')
    for t in run['tests']:
        require(t['returncode']==0 and sha(t['command'][3])==t['scriptSha256'] and sha(t['log'])==t['logSha256'], 'Fresh gate evidence drift')
    runtime_checks=0
    for v in ['A','B']:
        proof=read(GATE/(v+'-formal-verification.json'))
        require(proof['methodsChanged']==0 and len(proof['installers'])==6 and proof['luaResourceBytes']<=4194304, 'Actual ZIP/IL/installer drift')
        for profile in ['jit','plain','chef','chef-patch']:
            r=read(GATE/('runtime-'+v+'-'+profile)/'result.json');runtime_checks+=r['checks']
            require(r['status'].startswith('PASS') and r['boneWriteCountMode']=='successful-setter-return', 'Incomplete runtime writes')
            if profile=='chef-patch':
                require(r['chefStart']['state']=='running' and r['chefStart']['version']==proof['runtimeVersion'], 'Actual Chef did not start')
                for scene in ['shipWriteEvidence','adsWriteEvidence']:
                    require(all(x['solverCallbacks']>0 and x['successfulBoneWrites']>0 for x in r[scene]), 'Successful writes missing')
    return {'consumerProfiles':61,'consumerResources':39,'fullFkCases':290,'fullFkChecks':8744894,'fullFkEvidenceSha256':sha(LAB/'fk-release/result.json'),'freshGateCommands':49,'runtimeChecks':runtime_checks,'producerProofSha256':sha(LAB/'producer-finish-verification.json')}


def seal():
    require((OUT/'protected-before.json').is_file(),'Prepare first')
    require(snapshot(read(OUT/'protected-before.json').keys())==read(OUT/'protected-before.json'), 'Protected current-state changed; no rollback attempted')
    gates=validate_evidence()
    json_new(OUT/'configuration-after.json', check_config())
    acceptance=read(OUT/'user-acceptance.json'); packages=[]
    for row in acceptance['packages']:
        v=row['variant']; source=Path(row['exportPath'])
        require(sha(source)==row['sha256'], 'Accepted ZIP drift')
        name='物理运行时-单骨架-'+v+'-Chef加载上限修复-'+row['runtimeVersion']+'-正式版.zip'
        dest=NORMAL/'运行时配套'/name;write_new(dest,source.read_bytes())
        with zipfile.ZipFile(dest) as z:
            require(z.testzip() is None and len(z.namelist())==4, 'Formal ZIP CRC/member failure')
        packages.append({'variant':v,'runtimeVersion':row['runtimeVersion'],'compatVersion':'1.3.13','path':str(dest),'bytes':dest.stat().st_size,'sha256':sha(dest),'byteIdenticalToAcceptedCandidate':True})
    release={'schema':'hd2-single-loader-accepted-formal-v1','status':'USER_ACCEPTED_TWO_FORMAL_PACKAGES','date':'2026-11-17','timezone':'Asia/Shanghai','acceptanceSha256':sha(OUT/'user-acceptance.json'),'packages':packages,'gates':gates,'normalCoreSha256':sha(NORMAL/'HD2ModCore.dll'),'rootConfigSha256':sha(NORMAL/'config.toml'),'normalEmbeddedExporterHasNewSizeGuard':False,'gameOrManagerLaunched':False,'automaticallyImportedOrDeployed':False,'modelOrAnimationRebaked':False,'controlledMultiplayerFpsMeasured':False}
    json_new(OUT/'formal-release.json',release)
    # Update only release metadata, never solver/source bytes or installed normal Core.
    manifest_path=PROD/'single_remote_release_manifest.json'
    old=read(OUT/'before/HD2PhysBoneCompat/src/production/single_remote_release_manifest.json')
    updated=json.loads(json.dumps(old))
    updated['realGameAcceptanceStatus']='user-accepted-A19-B20-formal-not-controlled-multiplayer-FPS'
    updated['acceptedFeedback']={'userWords':FEEDBACK,'acceptedDate':'2026-11-17','timezone':'Asia/Shanghai','scope':'A19/B20 normal behavior accepted; 1-vs-4 combat FPS still under analysis','priorFeedback':old['acceptedFeedback']}
    updated['formalRelease']={'path':str(OUT/'formal-release.json'),'sha256':sha(OUT/'formal-release.json'),'packages':packages}
    b=(json.dumps(updated,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    require(manifest_path.read_bytes() in [(OUT/'before/HD2PhysBoneCompat/src/production/single_remote_release_manifest.json').read_bytes(),b], 'Unexpected concurrent release metadata edit')
    manifest_path.write_bytes(b)
    json_new(OUT/'protected-after.json',snapshot(read(OUT/'protected-before.json').keys()))
    require(read(OUT/'protected-after.json')==read(OUT/'protected-before.json'),'Protected inputs changed during promotion')
    json_new(OUT/'promotion-verification.json',{'status':'PASS_BYTE_IDENTICAL_FORMAL_PROMOTION_CURRENT_USER_STATE_PRESERVED','productionManifestSha256':sha(manifest_path),'formalReleaseSha256':sha(OUT/'formal-release.json'),'protectedPaths':len(read(OUT/'protected-before.json')),'protectedChanges':[],'packages':packages,'gates':gates})
    print(json.dumps(release,ensure_ascii=False,indent=2), flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','seal']);args=ap.parse_args()
    {'prepare':prepare,'seal':seal}[args.mode]()
