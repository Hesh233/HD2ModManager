"""Verify the health-sampling isolated experiments against baseline-r2 and
active-dispatch-r3, then run the existing formal gates on each candidate runtime.
No production edits, no package export, no game FPS measurement. Write-once output.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'outputs/physics-A19-hotpath-analysis-20261117'
ap = argparse.ArgumentParser()
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args()
OUT = a.output.resolve()
assert OUT.is_relative_to(ROOT/'outputs') and not OUT.exists(), 'Keep evidence write-once'
OUT.mkdir()
(OUT/'verification-script-snapshot.py').write_bytes(Path(__file__).read_bytes())
from analyze_a19_hotpath_candidates import protected_files
frozen = protected_files()
(OUT/'protected-before.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')

VARIANTS = ['sampled-health-r3', 'dispatch-sampled-health-r2']
# Health sampling changes ONLY liveness/identity read cadence. Every other API
# count, every solver call and every successful write trace must stay identical.
ALLOWED_API_DELTA = {'Unit.alive', 'Unit.num_scene_graph_items', 'Unit.has_node'}
UNIT_KEYS = ['unitId', 'localOwner', 'consumerMode', 'excluded', 'solverCalls',
             'successfulWrites', 'writeTraceSha256', 'pendingDt']
PHASE_KEYS = ['label', 'frames', 'sessions', 'lastAttempted', 'lastChainTotal',
              'staticChains', 'peakAngle']

refs = {name: json.loads((BASE/name/'result.json').read_text('utf-8'))
        for name in ['baseline-r2', 'active-dispatch-r3', 'mainline-policy']}
comparison = []
alive_summary = {}
for name, data in list(refs.items()) + [(v, json.loads((BASE/v/'result.json').read_text('utf-8'))) for v in VARIANTS]:
    assert data['status'].startswith('PASS'), (name, data['status'])
    alive_summary[name] = {p['label']: p['apiCalls']['Unit.alive'] for p in data['phases']}

for variant in VARIANTS:
    data = json.loads((BASE/variant/'result.json').read_text('utf-8'))
    runtime_bytes = (BASE/variant/'experimental-runtime.lua').read_bytes()
    assert hashlib.sha256(runtime_bytes).hexdigest() == data['runtimeSha256'], variant+': runtime hash mismatch'
    text = runtime_bytes.decode('utf-8')
    assert 'singleHealthMode' in text, variant+': missing health-sampling patch'
    if variant.startswith('dispatch-sampled-health'):
        assert 'experimentalDispatch' in text, variant+': missing dispatch patch'
    else:
        assert 'experimentalDispatch' not in text, variant+': unexpected dispatch patch'
    assert any('empty-consumer node rebuild detected within 900 frames' in c for c in data['checks']), \
        variant+': rebuild-latency probe not recorded'
    assert any('consumer-mode change forces identity re-check within 2 frames' in c for c in data['checks']), \
        variant+': mode-change identity-forcing probe not recorded'
    assert any('probe introduces no dead Unit or stale World API calls' in c for c in data['checks']), \
        variant+': dead-call guard probe not recorded'
    for ref_name in ['baseline-r2', 'active-dispatch-r3']:
        ref = refs[ref_name]
        assert len(ref['phases']) == len(data['phases'])
        for old, new in zip(ref['phases'], data['phases']):
            for key in PHASE_KEYS:
                assert old[key] == new[key], (variant, ref_name, old['label'], key)
            assert len(old['units']) == len(new['units'])
            for ou, nu in zip(old['units'], new['units']):
                for key in UNIT_KEYS:
                    assert ou[key] == nu[key], (variant, ref_name, old['label'], ou['unitId'], key)
            # healthFrames is intentionally NOT compared: its cadence is the experiment.
            api_delta = {k: new['apiCalls'].get(k, 0) - v for k, v in old['apiCalls'].items()
                         if new['apiCalls'].get(k, 0) != v}
            for k in new['apiCalls']:
                if k not in old['apiCalls']:
                    api_delta[k] = new['apiCalls'][k]
            assert set(api_delta) <= ALLOWED_API_DELTA, (variant, ref_name, old['label'], api_delta)
            comparison.append(dict(variant=variant, reference=ref_name, phase=old['label'],
                frames=old['frames'], aliveReference=old['apiCalls']['Unit.alive'],
                aliveCandidate=new['apiCalls']['Unit.alive'], changedApiCounts=api_delta,
                exactWriteTraceSolverAndDiagnostics=True,
                healthFramesExcluded='cadence is the experiment; in-window deltas asserted by the analysis tool'))

# Reuse the established formal-gate runner unchanged; only the runtime source
# folder is redirected to each candidate. Production compat stays byte-identical.
runner = ROOT/'tools/run_single_ship_formal_gates.py'
compat = ROOT/'HD2PhysBoneCompat/src/production/single_remote_compat.lua'
gates = []
for variant in VARIANTS:
    case = OUT/variant
    case.mkdir()
    source = case/'A-source'; source.mkdir()
    (source/'physbone_runtime.lua').write_bytes((BASE/variant/'experimental-runtime.lua').read_bytes())
    (source/'physbone_compat.lua').write_bytes(compat.read_bytes())
    for vm in ['lua51', 'luajit21']:
        for name, extra in [
            ('ship', ['--ship']), ('ads', []),
            ('single', ['--full-baseline', 'single-mainline-regression-test.lua']),
            ('multiplayer', ['--full-baseline', 'multiplayer-skeleton-regression-test.lua'])]:
            sys.argv = [str(runner), '--output', str(case), '--variant', 'A', '--vm', vm] + extra
            scope = {'__file__': str(runner), '__name__': 'isolated_gate'}
            try:
                exec(compile(runner.read_text('utf-8-sig'), str(runner), 'exec'), scope)
            except SystemExit as ex:
                scope.setdefault('passed', 0); scope.setdefault('failed', 0)
                scope['error'] = scope.get('error') or ('gate exit '+str(ex.code))
            gates.append(dict(variant=variant, vm=vm, test=name, passed=scope['passed'],
                              failed=scope['failed'], error=scope['error']))

after = protected_files()
assert frozen == after, 'Protected files changed during verification'
total_failed = sum(g['failed'] for g in gates)
total_error = sum(1 for g in gates if g['error'])
result = dict(status='PASS_HEALTH_SAMPLING_ISOLATED_EQUIVALENCE_AND_GATES_NOT_RELEASE_NOT_FPS' if not total_failed and not total_error
              else 'FAIL_HEALTH_SAMPLING_VERIFICATION',
    comparisons=comparison, aliveSummary=alive_summary, gates=gates,
    totalPassed=sum(g['passed'] for g in gates), totalFailed=total_failed, gateErrors=total_error,
    allowedApiDelta=sorted(ALLOWED_API_DELTA),
    safetyBoundary=('Non-writing sessions (empty consumers, policy-excluded remotes) keep per-frame pointer '
        'membership pruning; Unit.alive + node identity sampled every 30th frame; consumer-mode/exclusion change '
        'forces immediate full health AND node-identity re-check (cadence aligned, probe <=2 frames); writing '
        'sessions and pre-write alive rechecks unchanged. Node-rebuild detection latency for stable non-writing '
        'sessions widens from <=30 to <=900 frames (probe-verified). Residual ordering gap: prune runs before '
        'RemotePhysics.bind each callback, so the transition callback itself can drive once before the forced '
        're-check (baseline has the same ordering but <=30-frame detection while excluded). Full closure would '
        'need a pre-write identity guard; NOT implemented. Offline call-count/trace equivalence and legacy gates '
        'are NOT a crash-safety proof; real-device churn validation is required before any acceptance.'),
    limits=['No real game CPU/GPU frametime or FPS measurement',
        'No candidate ZIP exported; no loader-size gate for a new package',
        'Only test01 real-model dynamic write traces; legacy suites use fake engines',
        'Per-Unit sample-window write sequences only: no cross-Unit ordering, callback timing or transition/release/uninstall write equivalence',
        'Production source, accepted A19/B20, manager, model, config and deployment unchanged'],
    protectedFiles=len(frozen), protectedHashesUnchanged=True,
    verificationScriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(OUT/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(result['status'], result['totalPassed'], 'gate assertions;', len(comparison), 'phase comparisons; NOT FPS')
if total_failed or total_error:
    raise SystemExit(1)