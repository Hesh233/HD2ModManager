"""Run release gates against actual exported A/B Lua, never user/game state."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys
ROOT = Path(__file__).resolve().parents[1]
PROD = ROOT/'HD2PhysBoneCompat/src/production'
ap = argparse.ArgumentParser()
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
OUT = a.output.resolve()
assert OUT.is_relative_to(ROOT) and not OUT.is_relative_to(ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7')
OUT.mkdir(parents=True, exist_ok=True)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest = json.loads((PROD/'single_remote_release_manifest.json').read_text('utf-8-sig'))
inputs = {'catalog': sha(PROD/'single_consumer_catalog.json')}
for entry in manifest['sources']:
    v = entry['variant']
    folder = OUT/(v+'-extracted')
    assert sha(folder/'physbone_runtime.lua') == entry['runtimeSha256']
    assert sha(folder/'physbone_compat.lua') == entry['compatSha256']
    inputs[v+'Runtime'] = entry['runtimeSha256']
    inputs[v+'Compat'] = entry['compatSha256']
assert inputs['ACompat'] == inputs['BCompat'], 'Shared solver tests require byte-identical A/B compat'
records = []
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'
def run(label, argv):
    script = ROOT/argv[0]
    cmd = [sys.executable, '-u', '-B', str(script)] + [str(x) for x in argv[1:]]
    try:
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
        text = result.stdout + result.stderr
        code = result.returncode
    except subprocess.TimeoutExpired as e:
        text, code = 'TIMEOUT '+str(e), -1
    log = OUT/(label+'-runner.log')
    log.write_text(text, encoding='utf-8')
    records.append(dict(label=label, scriptSha256=sha(script), command=cmd, returncode=code, log=str(log), logSha256=sha(log)))
    (OUT/'gate-run.json').write_text(json.dumps(dict(status='RUNNING_ACTUAL_ZIP_CONSUMER_GATES' if code == 0 else 'FAILED_ACTUAL_ZIP_CONSUMER_GATE', inputs=inputs, tests=records), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(label, 'PASS' if code == 0 else 'FAIL', flush=True)
    if code != 0:
        print(text[-8000:], flush=True)
        raise SystemExit(code if code > 0 else 1)
for v in ['A', 'B']:
    for vm in ['luajit21', 'lua51']:
        run('runtime-'+v+'-'+vm, ['HD2PhysBoneCompat/test/single-consumer-runtime-test.py', '--source', OUT/(v+'-extracted'), '--output', OUT/('runtime-'+v+'-'+vm), '--vm', vm])
        run('inventory-'+v+'-'+vm, ['HD2PhysBoneCompat/test/single-consumer-inventory-test.py', '--source', OUT/(v+'-extracted'), '--output', OUT/('inventory-'+v+'-'+vm), '--vm', vm])
        for flag, baseline in [('--ship', None), (None, None), ('--full-baseline', 'single-mainline-regression-test.lua'), ('--full-baseline', 'multiplayer-skeleton-regression-test.lua')]:
            label = v+'-'+vm+'-'+('ship' if flag=='--ship' else baseline or 'ads')
            argv = ['tools/run_single_ship_formal_gates.py', '--variant', v, '--vm', vm, '--output', OUT, '--extracted']
            if flag: argv.append(flag)
            if baseline: argv.append(baseline)
            run(label, argv)
for vm in ['luajit21', 'lua51']:
    for model in ['test01', 'cow', 'test13', 'test15']:
        run('real-'+model+'-'+vm, ['HD2PhysBoneCompat/test/single-consumer-real-test.py', '--source', OUT/'A-extracted/physbone_compat.lua', '--output', OUT/('real-'+model+'-'+vm), '--model', model, '--vm', vm])
for case in ['gpu', 'toc', 'higher', 'missing_gpu', 'bind']:
    run('negative-'+case+'-luajit21', ['HD2PhysBoneCompat/test/single-consumer-real-test.py', '--source', OUT/'A-extracted/physbone_compat.lua', '--output', OUT/('negative-'+case+'-luajit21'), '--vm', 'luajit21', '--mutation', case])
assert len(records) == 37
(OUT/'gate-run.json').write_text(json.dumps(dict(status='PASS_ALL_ACTUAL_ZIP_CONSUMER_GATES', inputs=inputs, tests=records), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('PASS all 37 actual ZIP consumer gate commands', flush=True)
