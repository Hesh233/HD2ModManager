"""A19 isolated hot-path experiments. No production edits, package export or game FPS.
Reuses the real-model fixture and actual Chef parser/sandbox. Candidate source is
substituted AFTER parsing the accepted ZIP and BEFORE sandbox startup; it is NOT
an exported or release-tested candidate ZIP. All outputs are write-once.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import math
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / 'outputs/physics-single-loader-size-fix-20261117'
TEST = ROOT / 'HD2PhysBoneCompat/test/single-consumer-runtime-test.py'
PROD = ROOT / 'HD2PhysBoneCompat/src/production'
NORMAL = ROOT / 'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def replace_once(text, old, new):
    assert text.count(old) == 1, ('Ambiguous source anchor', old[:100])
    return text.replace(old, new, 1)


def candidate(text, variant):
    if variant in ('baseline', 'mainline-policy'):
        return text
    if variant in ('sampled-health', 'dispatch-sampled-health'):
        # EXPERIMENT ONLY: non-writing sessions (empty consumers and policy-excluded
        # remotes) keep the per-frame pointer membership check above, but sample
        # Unit.alive + node identity every 30th frame. A consumer-mode or exclusion
        # change forces a full health check AND aligns the cadence counter so the
        # node-identity re-check runs on that same call. Writing sessions,
        # pre-write alive rechecks and pointer pruning are untouched.
        text = replace_once(text, '''		if not live then
			health = "gone"
		else
			health = Compat.session_health(session, runtime.frame)
		end''', '''		if not live then
			health = "gone"
		elseif session.singleMainline
			and (session.consumerMode == "empty" or session.singleRemotePhysicsExcluded == true)
			and (runtime.frame % 30) ~= 0
			and session.singleHealthMode == session.consumerMode
			and session.singleHealthExcluded == session.singleRemotePhysicsExcluded then
			health = "ok"
		else
			if session.singleHealthMode ~= session.consumerMode
				or session.singleHealthExcluded ~= session.singleRemotePhysicsExcluded then
				-- Mode/exclusion transition: align the cadence counter so THIS
				-- session_health call also runs the node-identity re-check.
				-- Without this, a rebuild during a long excluded/non-writing
				-- period could resume driving with stale cached node indices.
				session.healthFrames = (session.identityEvery or 30) - 1
			end
			health = Compat.session_health(session, runtime.frame)
			session.singleHealthMode = session.consumerMode
			session.singleHealthExcluded = session.singleRemotePhysicsExcluded
		end''')
    if variant == 'empty-first':
        text = replace_once(text,
            'due = session.singleDue == true and session.singleRemotePhysicsExcluded ~= true',
            'due = session.singleDue == true and session.singleRemotePhysicsExcluded ~= true and ConsumerRuntime.hasWork(session)')
    elif variant in ('active-dispatch', 'dispatch-sampled-health'):
        text = replace_once(text, '''	local chainTotal = 0
	for index = 1, #runtime.sessions do
		chainTotal = chainTotal + #(runtime.sessions[index].sessions or {})
	end''', '''	local chainTotal = 0
	-- EXPERIMENT ONLY: rebuild after proof/policy/preview updates each callback.
	-- The complete runtime.sessions remains the lifecycle and chain-count ledger.
	local dispatchSessions = runtime.experimentalDispatch or {}
	runtime.experimentalDispatch = dispatchSessions
	local dispatchCount = 0
	for index = 1, #runtime.sessions do
		local session = runtime.sessions[index]
		chainTotal = chainTotal + #(session.sessions or {})
		if session.singleMainline and options.singleMainline ~= false
			and (session.singleRemotePhysicsExcluded == true or not ConsumerRuntime.hasWork(session)) then
			session.skippedSame, session.engineCalls, session.pendingDt = 0, 0, 0
		else
			dispatchCount = dispatchCount + 1
			dispatchSessions[dispatchCount] = session
		end
	end
	for index = #dispatchSessions, dispatchCount + 1, -1 do dispatchSessions[index] = nil end''')
        text = replace_once(text, '''	for index = 1, #runtime.sessions do
		local session = runtime.sessions[index]
		-- compat''', '''	for index = 1, #dispatchSessions do
		local session = dispatchSessions[index]
		-- compat''')
        # The reusable array owns session/Unit references. Clear it on every
        # terminal ledger path, including early returns before dispatch rebuild.
        text = replace_once(text,
            'local function dropHandleGroup(runtime, reason, delay)\n',
            'local function dropHandleGroup(runtime, reason, delay)\n\truntime.experimentalDispatch = nil\n')
        text = replace_once(text,
            '\t\t\truntime.sessions = nil\n\t\t\truntime.reconcile = nil',
            '\t\t\truntime.sessions = nil\n\t\t\truntime.experimentalDispatch = nil\n\t\t\truntime.reconcile = nil')
        text = replace_once(text,
            '\t\truntime.sessions = nil\n\t\truntime.rearmAt = frame + 1',
            '\t\truntime.sessions = nil\n\t\truntime.experimentalDispatch = nil\n\t\truntime.rearmAt = frame + 1')
        text = replace_once(text,
            '\t\truntime.sessions = nil\n\t\truntime.zeroFrames = 0',
            '\t\truntime.sessions = nil\n\t\truntime.experimentalDispatch = nil\n\t\truntime.zeroFrames = 0')
        text = replace_once(text,
            '\truntime.installed = false\n\tConsumerRuntime.close(runtime)',
            '\truntime.installed = false\n\truntime.experimentalDispatch = nil\n\tConsumerRuntime.close(runtime)')
        # Keep the original ALL-session peak scan: consumer unapply may restore
        # old chain arrays and failed policy transitions may leave rotations.
    else:
        if variant != 'sampled-health':
            raise ValueError(variant)
    return text


def protected_files():
    paths = list(PROD.glob('*'))
    paths += [TEST, ROOT/'tools/analyze_a19_multiplayer_overhead.py',
              ROOT/'tools/chef_physics_patch_harness.py', LAB/'actual-chef-core-1.lua',
              LAB/'actual-chef-bit-shim.lua', NORMAL/'config.toml', NORMAL/'HD2ModCore.dll']
    paths += list((LAB/'release-candidate').rglob('*.zip'))
    paths += list((LAB/'release-candidate/A-extracted').glob('*.lua'))
    for folder in ['运行时配套', 'test-library/[单骨架模型]test01']:
        paths += [p for p in (NORMAL/folder).rglob('*') if p.is_file()]
    return {str(p): sha(p) for p in sorted(set(paths)) if p.is_file()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variant', choices=['baseline', 'empty-first', 'active-dispatch',
                                          'mainline-policy', 'sampled-health',
                                          'dispatch-sampled-health'], required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=600)
    a = ap.parse_args()
    out = a.output.resolve()
    assert out.is_relative_to(ROOT/'outputs') and not out.exists()
    out.mkdir(parents=True)
    script_bytes = Path(__file__).read_bytes()
    (out/'analysis-script-snapshot.py').write_bytes(script_bytes)
    frozen = protected_files()
    (out/'protected-before.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    original = (LAB/'release-candidate/A-extracted/physbone_runtime.lua').read_text('utf-8-sig')
    assert original == (PROD/'single_remote_A_runtime.lua').read_text('utf-8-sig')
    changed = candidate(original, a.variant)
    (out/'experimental-runtime.lua').write_text(changed, encoding='utf-8', newline='\n')
    api_counts = None
    traces = collections.defaultdict(hashlib.sha256)
    tracing = False

    def trace_write(u, name, values):
        if tracing:
            record = [int(u.id), name, [env['py'](v) for v in values]]
            traces[int(u.id)].update(json.dumps(record, sort_keys=True, separators=(',', ':')).encode())

    def instrument_api(S):
        nonlocal api_counts
        lua = env['lua']
        api_counts = lua.table()
        lua.eval('''function(S,c)
          for _,g in ipairs({'Unit','World','Application'})do
            for name,fn in pairs(S[g] or {})do
              if type(fn)=='function' then
                local key=g..'.'..name
                S[g][name]=function(...)c[key]=(c[key]or 0)+1;return fn(...)end
              end
            end
          end
        end''')(S, api_counts)

    def transform_scanned(lua):
        row = lua.globals().found_addons[1]
        src = row.src
        transformed = replace_once(src, original.rstrip(), changed.rstrip())
        row.src = transformed
        # Exact source spans allow sampling runtime Lua separately from the
        # solver, fake engine and wrappers. These are instructions, NOT time.
        first = transformed.index(changed.rstrip())
        first_line = transformed[:first].count('\n') + 1
        env['runtimeLines'] = (first_line, first_line + changed.count('\n'))
        env['addonSource'] = transformed
        (out/'sandbox-source-sha.json').write_text(json.dumps({
            'acceptedParsedSourceSha256': hashlib.sha256(src.encode()).hexdigest(),
            'executedSourceSha256': hashlib.sha256(transformed.encode()).hexdigest(),
            'sourceSubstitutionAfterParser': a.variant in ('empty-first', 'active-dispatch', 'sampled-health', 'dispatch-sampled-health'),
            'fixturePolicyOverride': a.variant == 'mainline-policy',
            'notCandidatePackageValidation': True}, indent=2), encoding='utf-8')

    prefix = TEST.read_text('utf-8-sig').split('rows=[s for s in state.sessions.values()]', 1)[0]
    if a.variant == 'mainline-policy':
        # Runtime source stays byte-identical. Disabling the formal policy in the
        # install options (same flag the formal mainline gates override) makes all
        # players driven in every scene: upstream-style mainline behavior.
        prefix = replace_once(prefix, "identityWatch=False,rescanFrames=300,mode='external'",
                              "identityWatch=False,rescanFrames=300,mode='external',singleFormalPolicy=False")
    prefix = replace_once(prefix, ' return S\n\ne.api=wrap(api)',
                          ' instrument_api(S)\n return S\n\ne.api=wrap(api)')
    prefix = replace_once(prefix, "if _name.startswith('set_'):writes[int(u.id)]+=1",
                          "if _name.startswith('set_'):\n    writes[int(u.id)]+=1\n    trace_write(u,_name,v)")
    prefix = replace_once(prefix, "core,scanReceipt=scan_patch(lua,a.chef_core,blob)",
                          "core,scanReceipt=scan_patch(lua,a.chef_core,blob)\n transform_scanned(lua)")
    env = {'__file__': str(TEST), '__name__': 'isolated_fixture',
           'instrument_api': instrument_api, 'transform_scanned': transform_scanned,
           'trace_write': trace_write}
    sys.argv = [str(TEST), '--source', str(LAB/'release-candidate/A-extracted'),
                '--output', str(out/'fixture'), '--vm', 'lua51',
                '--chef-bit', str(LAB/'actual-chef-bit-shim.lua'),
                '--chef-patch', str(LAB/'release-candidate/A-export/physics-runtime.zip'),
                '--chef-core', str(LAB/'actual-chef-core-1.lua')]
    exec(compile(prefix, str(TEST), 'exec'), env)
    lua, e, state, R, av = [env[k] for k in ['lua', 'e', 'state', 'R', 'av']]
    same = lua.eval('function(a,b)return a==b end')
    R.setOptions(lua.table_from({'identityWatch': True}))
    formal = a.variant != 'mainline-policy'
    phases = []
    checks = []

    def check(ok, msg):
        assert ok, msg
        checks.append(msg)

    def motion(frame):
        # All parts track their owner; no static preview is fabricated here.
        for owner, parts in zip(env['avatars'], env['parts']):
            if owner.alive:
                for u in parts:
                    if u.alive:
                        u.position.x = owner.position.x + .03 * math.sin(frame / 7)

    def sample(label, players, mission=True):
        nonlocal tracing
        check(state.consumerContext.done, label+': proof complete')
        env['updates'].clear(); env['writes'].clear(); traces.clear()
        for k in list(api_counts.keys()): api_counts[k] = 0
        fp_before = e.fpCalls
        attach_before = dict(env['attachCounts'])
        hf_before = {int(s.unit.id): int(s.healthFrames or 0) for s in state.sessions.values()}
        lo, hi = env['runtimeLines']
        lua.execute('''instructionSamples=0;runtimeSamples=0
          debug.sethook(function()
            instructionSamples=instructionSamples+1
            local i=debug.getinfo(2,'Sl')
            if i and i.currentline>='''+str(lo)+''' and i.currentline<='''+str(hi)+''' then
              runtimeSamples=runtimeSamples+1
            end
          end,'',1000)''')
        tracing = True
        e.advance(e, a.frames, .01, env['wrap'](motion))
        tracing = False
        lua.execute('debug.sethook()')
        sessions = list(state.sessions.values())
        check(len(state.avatars) == players and len(sessions) == players*7, label+': roster retained')
        evidence = []
        for s in sessions:
            uid = int(s.unit.id)
            own = bool(same(s.owner, av))
            evidence.append(dict(unitId=uid, localOwner=own, consumerMode=s.consumerMode,
                excluded=bool(s.singleRemotePhysicsExcluded), solverCalls=env['updates'][uid],
                successfulWrites=env['writes'][uid], writeTraceSha256=traces[uid].hexdigest(),
                healthFrames=int(s.healthFrames or 0), pendingDt=float(s.pendingDt or 0)))
        check(all(x['solverCalls'] == (a.frames if x['consumerMode'] != 'empty' and (not formal or x['localOwner'] or not mission) else 0) for x in evidence), label+': exact solver cadence')
        if mission and formal:
            check(all(x['excluded'] and x['successfulWrites'] == 0 and x['pendingDt'] == 0 for x in evidence if not x['localOwner']), label+': no remote writes or pending dt')
            check(e.fpCalls == fp_before, label+': no restarted FP queries')
        elif mission and not formal:
            check(all(not x['excluded'] for x in evidence), label+': mainline has no policy exclusion')
            check(all(x['successfulWrites'] > 0 for x in evidence if x['consumerMode'] != 'empty' and not x['localOwner']), label+': mainline drives remote sessions in mission')
        else:
            check(all(not x['excluded'] for x in evidence), label+': ship physics restored')
        if a.variant in ('sampled-health', 'dispatch-sampled-health'):
            for x in evidence:
                writing = x['consumerMode'] != 'empty' and not x['excluded']
                delta = x['healthFrames'] - hf_before[x['unitId']]
                if writing:
                    check(delta >= a.frames - 2, label+': writing session keeps per-frame health ('+str(x['unitId'])+')')
                else:
                    check(a.frames // 30 - 2 <= delta <= a.frames // 30 + 2, label+': non-writing session health sampled every 30 frames ('+str(x['unitId'])+')')
        check(dict(env['attachCounts']) == attach_before, label+': no steady reattach')
        phases.append(dict(label=label, frames=a.frames, sessions=len(sessions),
            instructionSamples=int(lua.globals().instructionSamples),
            runtimeInstructionSamples=int(lua.globals().runtimeSamples),
            apiCalls={str(k): int(v) for k, v in sorted(api_counts.items())},
            units=evidence, lastAttempted=int(state.lastAttempted),
            lastChainTotal=int(state.lastChainTotal), staticChains=int(state.staticChains),
            peakAngle=float(state.peakAngle or 0)))
        print(a.variant, label, 'alive', api_counts['Unit.alive'], 'samples', phases[-1]['instructionSamples'], flush=True)

    e.levels=900; e.advance(e,40); e.fp=True; e.advance(e,140)
    check(same(state.singleState.selfUnit,av), 'initial ADS owner')
    e.advance(e,360)
    sample('one-player',1)
    for i in range(1,4): env['player']('remote'+str(i),20*i)
    e.advance(e,660); env['wait_for_proof']('joined-four')
    sample('four-players',4)
    # Return to ship and mission exercises policy epoch and cleared-state re-entry.
    e.levels=1; e.fp=False; e.advance(e,90)
    sample('four-players-ship',4,False)
    e.levels=900; e.advance(e,40); e.fp=True; e.advance(e,140)
    check(same(state.singleState.selfUnit,av), 'ADS owner after ship round trip')
    sample('four-players-mission-again',4)
    for owner, parts in zip(env['avatars'][1:],env['parts'][1:]):
        for u in parts: e.remove(e,u)
        e.remove(e,owner)
    e.advance(e,660)
    sample('one-player-after-leave',1)
    # Positive plan-disable fallback must re-enable the original complete arrays.
    R.setOptions(lua.table_from({'consumerPlans':False})); e.advance(e,2)
    check(all(s.consumerMode is None for s in state.sessions.values()), 'disabled plans restore full arrays')
    check(int(state.lastAttempted)==7, 'full-array fallback dispatches all local sessions')
    R.setOptions(lua.table_from({'consumerPlans':True})); env['wait_for_proof']('re-enabled')
    check(sum(s.consumerMode=='empty' for s in state.sessions.values())==4, 're-enabled proof restores empty states')
    if a.variant in ('sampled-health', 'dispatch-sampled-health'):
        # Outside sample windows AND after the consumerPlans toggle (the toggle
        # must see undisturbed bind state): node-rebuild detection latency for a
        # non-writing (empty consumer) session that stays in the live inventory.
        # Immediate pointer pruning is exercised separately by the removal check.
        dead_before, stale_before = e.deadCalls, e.staleWorldCalls
        empty = [s for s in state.sessions.values() if s.consumerMode == 'empty' and same(s.owner, av)]
        check(len(empty) > 0, a.variant+' probe: local empty consumer present')
        target = empty[0]; tu = target.unit; original_nodes = int(tu.nodes)
        tu.nodes = original_nodes + 5
        detected = None
        for step in range(30):
            e.advance(e, 30)
            if not any(same(s, target) for s in state.sessions.values()):
                detected = (step + 1) * 30
                break
        check(detected is not None and detected <= 900,
              a.variant+': empty-consumer node rebuild detected within 900 frames')
        tu.nodes = original_nodes
        env['wait_for_proof']('rebuild-recovered')
        e.advance(e, 180)
        check(len(state.avatars) == 1 and len(state.sessions) == 7,
              a.variant+': roster recovered after rebuild probe')
        check(e.deadCalls == dead_before and e.staleWorldCalls == stale_before,
              a.variant+' probe introduces no dead Unit or stale World API calls')
        # Mode-change forcing: a rebuild the sampled cadence has not yet caught
        # must be detected on the first prune AFTER consumer-mode changes, not
        # after the full <=900-frame sampling latency. consumerPlans=False makes
        # every consumerMode nil on the next ConsumerRuntime.tick; the following
        # prune sees the change and forces the node-identity re-check.
        dead_before, stale_before = e.deadCalls, e.staleWorldCalls
        empty = [s for s in state.sessions.values() if s.consumerMode == 'empty' and same(s.owner, av)]
        check(len(empty) > 0, a.variant+' mode-force probe: local empty consumer present')
        target = empty[0]; tu = target.unit; original_nodes = int(tu.nodes)
        tu.nodes = original_nodes + 7
        R.setOptions(lua.table_from({'consumerPlans': False}))
        detected = None
        for step in range(4):
            e.advance(e, 1)
            if not any(same(s, target) for s in state.sessions.values()):
                detected = step + 1
                break
        check(detected is not None and detected <= 2,
              a.variant+': consumer-mode change forces identity re-check within 2 frames')
        tu.nodes = original_nodes
        R.setOptions(lua.table_from({'consumerPlans': True}))
        env['wait_for_proof']('mode-force-recovered')
        e.advance(e, 180)
        check(len(state.avatars) == 1 and len(state.sessions) == 7,
              a.variant+': roster recovered after mode-force probe')
        check(e.deadCalls == dead_before and e.staleWorldCalls == stale_before,
              a.variant+' mode-force probe introduces no dead Unit or stale World API calls')
    # Inventory removal must precede all calls on the now-dead instance.
    old=env['parts'][0][0]; e.remove(e,old); e.advance(e,1)
    check(all(not same(s.unit,old) for s in state.sessions.values()), 'removed live-list member pruned immediately')
    if a.variant in ('active-dispatch', 'dispatch-sampled-health'):
        # Outside timed/trace windows: test the extra array's ownership only.
        # Recovery uses the same real Chef hook, never a substitute installation.
        e.levels=1; e.fp=False; e.advance(e,90)
        def populated(label):
            check(state.experimentalDispatch is not None and len(state.experimentalDispatch)>0,
                  label+': dispatch references populated before trigger')
        def cleared(label):
            check(state.sessions is None and state.experimentalDispatch is None,
                  label+': full ledger and dispatch field cleared')
        worlds=e.worlds
        dead_before, stale_before=e.deadCalls, e.staleWorldCalls
        populated('world-gone'); e.worlds=lua.table(); e.advance(e,1)
        cleared('world-gone')
        e.worlds=worlds; env['wait_for_proof']('world-restored')
        populated('unreadable'); e.unreadable=True; e.advance(e,1)
        cleared('unreadable')
        e.unreadable=False; env['wait_for_proof']('inventory-restored')
        populated('loading-gap'); e.advance(e,1,1.0)
        cleared('loading-gap'); env['wait_for_proof']('gap-recovered')
        populated('all-parts-gone')
        for u in env['parts'][0]:
            if u.alive: e.remove(e,u)
        e.advance(e,1)
        cleared('all-parts-gone')
        check(state.avatars is not None and len(state.avatars)==1 and state.rearmAt>state.frame,
              'all-parts-gone: exercised empty-session backoff, not avatar/world drop')
        e.remove(e,av)
        av,_=env['player']('replacement',0); e.fpOwner=av
        env['wait_for_proof']('replacement-after-backoff')
        populated('zero-handled')
        # Deliberate solver no-work injection, outside equivalence windows.
        compat=env['C']; original_update=compat.update
        def zero_update(s,dt,*v):
            s.skippedSame=0; s.engineCalls=0
            return 0
        compat.update=env['wrap'](zero_update)
        original_limit=state.options.zeroLimit
        R.setOptions(lua.table_from({'zeroLimit':1})); e.advance(e,1)
        cleared('zero-handled')
        check(state.zeroFrames==0 and state.rearmAt>state.frame,
              'zero-handled: fault injection reached driver failure backoff')
        compat.update=original_update; state.options.zeroLimit=original_limit
        env['wait_for_proof']('zero-handled-recovered')
        # Keep a second avatar alive but give it no armor, so orphan cleanup in
        # tryAttach (not the all-avatar drop path) reaches no-plan waiting.
        unloaded,_=e.player(e,'unloaded-avatar',100,0); e.advance(e,120)
        check(len(state.avatars)==2, 'orphan: replacement avatar discovered before departure')
        populated('orphan-no-plan'); e.remove(e,av); e.advance(e,1)
        cleared('orphan-no-plan')
        check(state.avatars is not None and len(state.avatars)==1
              and same(state.avatars[1].unit,unloaded) and state.rearmAt==state.frame+1,
              'orphan: surviving armorless avatar and one-frame no-plan retry')
        e.remove(e,unloaded)
        av,_=env['player']('final-replacement',0); e.fpOwner=av
        env['wait_for_proof']('orphan-recovered')
        populated('uninstall')
        check(e.deadCalls==dead_before and e.staleWorldCalls==stale_before,
              'lifecycle probes introduce no dead Unit or stale World API calls')
    ctx=state.consumerContext
    R.uninstall()
    check(all(j.handle is None for j in ctx.jobs.values()), 'uninstall closes proof handles')
    if a.variant in ('active-dispatch', 'dispatch-sampled-health'):
        check(state.experimentalDispatch is None, 'uninstall clears dispatch even while fixture retains runtime state')
    logs='\n'.join(str(x) for x in lua.globals().logs.values())
    logs+='\n'+'\n'.join(p.read_text('utf-8',errors='replace') for p in (out/'fixture').glob('*.log'))
    (out/'captured-logs.txt').write_text(logs, encoding='utf-8')
    check(all(x not in logs for x in ['transition-error=','proof-error=','bind-error=','could not start','could not compile','驱动抛错','驱动失败','安装失败','stopped by the hang watchdog']), 'no suppressed errors')
    after=protected_files()
    check(after==frozen, 'protected source/config/accepted packages/model bytes unchanged')
    result=dict(status='PASS_ISOLATED_HOTPATH_NOT_RELEASE_NOT_FPS', variant=a.variant,
        actualChefParserForBaseline=True, actualChefSandboxForCandidate=True,
        candidateSourceSubstitutedAfterParser=a.variant in ('empty-first', 'active-dispatch', 'sampled-health', 'dispatch-sampled-health'),
        fixturePolicyOverride='singleFormalPolicy=false in install options; runtime bytes unchanged' if a.variant=='mainline-policy' else None,
        healthSamplingScope=('Non-writing sessions (empty consumers, policy-excluded remotes): per-frame pointer membership retained; '
            'Unit.alive + node identity sampled every 30th frame; consumer-mode/exclusion change forces immediate full health AND '
            'node-identity re-check (cadence aligned); writing sessions and pre-write alive rechecks unchanged. Node-rebuild detection '
            'latency for stable non-writing sessions widens from <=30 to <=900 frames; a mode/exclusion change is caught on the first '
            'prune after the change (probe <=2 frames). Residual ordering gap: prune runs before RemotePhysics.bind each callback, so the '
            'transition callback itself can drive once before the forced re-check (same structural ordering as baseline, which detects '
            'rebuilds within <=30 frames while excluded). Full closure would need a pre-write identity guard; NOT implemented. Offline '
            'call-count/equivalence evidence only, NOT a crash-safety proof; real-device churn validation required before any acceptance.') if a.variant in ('sampled-health', 'dispatch-sampled-health') else None,
        notCandidatePackageValidation=True, instructionSamplesIncludeFixture=True,
        writeTraceScope='Per-Unit successful setter sequence/node/value within each sample window only; excludes callback timing, cross-Unit ordering and transition/release/uninstall equivalence',
        dispatchCleanupScope='Explicit field-clearing assertions, not a whole-runtime garbage-collection or leak proof' if a.variant in ('active-dispatch', 'dispatch-sampled-health') else None,
        runtimeSampleAttribution='line-range sampling, not CPU timing',
        previewIdentityWatchEnabled=True, preservedHealthAndInventoryChecks=a.variant not in ('sampled-health', 'dispatch-sampled-health'),
        checks=checks, phases=phases, protectedFiles=len(frozen),
        runtimeSha256=hashlib.sha256(changed.encode()).hexdigest(),
        analysisScriptSha256=hashlib.sha256(script_bytes).hexdigest(), fixtureSourceSha256=sha(TEST),
        acceptedZipSha256=sha(LAB/'release-candidate/A-export/physics-runtime.zip'))
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'], len(checks), flush=True)


if __name__=='__main__':
    main()
