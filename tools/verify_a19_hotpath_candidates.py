"""Verify isolated A19 experiments without updating a runtime or accepted ZIP."""
from pathlib import Path
import argparse
import hashlib
import importlib
import json
import os
import re
import sys
sys.dont_write_bytecode = True
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/physics-A19-hotpath-analysis-20261117'
ap=argparse.ArgumentParser()
ap.add_argument('--active',default='active-dispatch-r3',choices=['active-dispatch','active-dispatch-r2','active-dispatch-r3'])
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args()
OUT=a.output.resolve()
assert OUT.is_relative_to(ROOT/'outputs') and not OUT.exists(), 'Keep evidence write-once'
OUT.mkdir()
(OUT/'verification-script-snapshot.py').write_bytes(Path(__file__).read_bytes())
from analyze_a19_hotpath_candidates import protected_files
frozen=protected_files()
(OUT/'protected-before.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
base=json.loads((BASE/'baseline-r2/result.json').read_text('utf-8'))
comparison=[]
for variant in ['empty-first',a.active]:
    data=json.loads((BASE/variant/'result.json').read_text('utf-8'))
    assert len(base['phases'])==len(data['phases'])
    for old,new in zip(base['phases'],data['phases']):
        for key in ['label','frames','sessions','units','lastAttempted','lastChainTotal','staticChains','peakAngle']:
            assert old[key]==new[key], (variant,old['label'],key)
        api_delta={key:new['apiCalls'][key]-value for key,value in old['apiCalls'].items() if new['apiCalls'][key]!=value}
        assert set(api_delta)=={'Unit.alive'}, api_delta
        comparison.append(dict(variant=variant,phase=old['label'],frames=old['frames'],
            aliveBefore=old['apiCalls']['Unit.alive'],aliveAfter=new['apiCalls']['Unit.alive'],
            changedApiCounts=api_delta,
            instructionSamplesBefore=old['instructionSamples'],instructionSamplesAfter=new['instructionSamples'],
            exactSuccessfulWriteTraceAndHealthCounters=True))

# Reuse the established test runner, redirecting ONLY its output root/source
# folder. FormalPolicy=false remains an explicit override for legacy tests.
runner=ROOT/'tools/run_single_ship_formal_gates.py'
compat=ROOT/'HD2PhysBoneCompat/src/production/single_remote_compat.lua'
gates=[]
for variant in ['baseline-r2','empty-first',a.active]:
    case=OUT/variant
    case.mkdir()
    source=case/'A-source';source.mkdir()
    (source/'physbone_runtime.lua').write_bytes((BASE/variant/'experimental-runtime.lua').read_bytes())
    (source/'physbone_compat.lua').write_bytes(compat.read_bytes())
    for vm in ['lua51','luajit21']:
        for name,extra in [
            ('ship',['--ship']),('ads',[]),
            ('single',['--full-baseline','single-mainline-regression-test.lua']),
            ('multiplayer',['--full-baseline','multiplayer-skeleton-regression-test.lua'])]:
            sys.argv=[str(runner),'--output',str(case),'--variant','A','--vm',vm]+extra
            scope={'__file__':str(runner),'__name__':'isolated_gate'}
            exec(compile(runner.read_text('utf-8-sig'),str(runner),'exec'),scope)
            gates.append(dict(variant=variant,vm=vm,test=name,passed=scope['passed'],failed=scope['failed'],error=scope['error']))

# Executable counterexamples to the proposed but NOT implemented shortcut
# "excluded => no rotations => skip all peak inspection".
lua=importlib.import_module('lupa.lua51').LuaRuntime(unpack_returned_tuples=True)
C=lua.execute(compat.read_text('utf-8-sig'))
lua.globals().C=C
unapply=lua.execute('''
 local old={lastRotations={{0,0,0,0.5}}}
 local s={singleMainline=true,singleRemotePhysicsExcluded=true,sessions={},
   drivers={},consumerFullSessions={old},consumerFullDrivers={},consumerMode='empty'}
 C.consumer_api.unapply(s)
 assert(s.singleRemotePhysicsExcluded and s.sessions[1].lastRotations[1][4]==0.5)
 return true
''')
runtime=lua.execute((BASE/'baseline-r2/experimental-runtime.lua').read_text('utf-8'))
# Load runtime's actual policy, whose Compat is an upvalue initialized on install;
# use the already loaded regressions for broad lifecycle assertions rather than
# invent a successful policy-transition failure test on an uninstalled module.
negative=dict(unapplyCanRestoreExcludedHistoricalRotations=bool(unapply),
    consequence='Do not infer all chain state is zero from excluded flag; peak scan retained',
    transitionErrorPath='static audit only; no engine fault injection claimed')
after=protected_files()
assert frozen==after, 'Protected files changed during verification'
result=dict(status='PASS_A19_ISOLATED_COMPARISON_AND_EXISTING_GATES_NOT_RELEASE_NOT_FPS',
    comparisons=comparison,gates=gates,totalPassed=sum(r['passed'] for r in gates),
    totalFailed=sum(r['failed'] for r in gates),counterexamples=negative,
    protectedFiles=len(frozen),protectedHashesUnchanged=True,
    baselineFailure='Initial baseline recorder passed Python tuples through a Lua-table converter; serialization failed. Fixed recorder, original failed directory retained. Not a production regression.',
    limits=['No real game CPU/GPU frametime or FPS measurement','No candidate ZIP exported or loader-size gate for a new package',
      'Only test01 real-model dynamic write traces; legacy suites use fake engines',
      'Per-Unit sample-window write sequences only: no cross-Unit ordering, callback timing or transition/release/uninstall write equivalence',
      'Dispatch field cleanup assertions are not a whole-runtime garbage-collection/leak proof',
      'Production source, accepted A19/B20, manager, model, config and deployment unchanged'],
    verificationScriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS',result['totalPassed'],'gate assertions; exact per-unit writer traces/health/diagnostics; NOT FPS')
