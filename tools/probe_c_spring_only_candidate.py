"""Real-model five-phase C spring-only DIAGNOSTIC probe (test01, 7 instances/player).

Modes:
  a22    -> baseline = full A22 runtime (driver+VRD active in ship/self)
  c      -> candidate = C runtime (A22 base + spring-only policy)
  actual -> the exported C ZIP, parsed by the real Chef scanner then executed

C removes driver-bone writes AND VRD skirt chains, keeping regular springs. This
probe proves the diagnostic contract at NODE level: VRD-exclusive and driver-exclusive
nodes receive ZERO successful writes in C, regular-spring nodes still write, every
session has evaluateDrivers=false and VRD chains disabled, certificates stay intact,
remote-mission exclusion matches A22, and the A22-inherited health-sampling / projection
/ lifecycle safety probes still pass. It also records the A22-vs-C write decomposition
that isolates the driver+VRD cost. Instruction/API counts are NOT FPS. Write-once.
"""
from pathlib import Path
import argparse, collections, hashlib, json, math, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import replace_once, protected_files
from build_a22_health_sampling_candidate import build_runtime as a22_build
from build_c_spring_only_candidate import build_runtime as c_build
LAB = ROOT / 'outputs/physics-C-spring-only-diagnostic-20261117'
OLD = ROOT / 'outputs/physics-single-loader-size-fix-20261117'
A22 = ROOT / 'outputs/physics-A22-health-sampling-candidate-20261117'
TEST = ROOT / 'HD2PhysBoneCompat/test/single-consumer-runtime-test.py'
PROD = ROOT / 'HD2PhysBoneCompat/src/production'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# Per-session node-category classifier over the ACTIVE consumer lists (s.sessions /
# s.drivers = the keep set that actually writes). VRD = chain anchored on a NON-WRIST
# driver bone name; regular = every other chain; driver = driver row node/parent/control.
# (The disabled audit below uses consumerFullSessions because C disables ALL VRD chains,
# including ones the consumer dropped; only the keep set can produce writes.)
CLASSIFY = '''function(s, iswrist)
  local vrd, regular, driver = {}, {}, {}
  local dnames = {}
  local rig = s.rig
  if rig and rig.drivers and rig.drivers.bones then
    for _, b in ipairs(rig.drivers.bones) do
      if not iswrist(b) then dnames[b.name] = true end
    end
  end
  for _, item in ipairs(s.sessions or {}) do
    local cn = item.chain and item.chain[1]
    local anchor = cn and cn.parentName
    local target = (anchor and dnames[anchor]) and vrd or regular
    for _, n in ipairs(item.nodes or {}) do target[n] = true end
  end
  for _, d in ipairs(s.drivers or {}) do
    if d.node then driver[d.node] = true end
    if d.parentNode then driver[d.parentNode] = true end
    if d.controlNode then driver[d.controlNode] = true end
  end
  return vrd, regular, driver
end'''

# Structural VRD-disabled audit: every VRD chain item.disabled==true, every regular
# chain item.disabled~=true, and evaluateDrivers==false. Returns counts.
VRD_AUDIT = '''function(s, iswrist)
  local dnames = {}
  local rig = s.rig
  if rig and rig.drivers and rig.drivers.bones then
    for _, b in ipairs(rig.drivers.bones) do
      if not iswrist(b) then dnames[b.name] = true end
    end
  end
  local vrdDisabled, vrdTotal, regularDisabled, regularTotal = 0, 0, 0, 0
  for _, item in ipairs(s.consumerFullSessions or s.sessions or {}) do
    local cn = item.chain and item.chain[1]
    local anchor = cn and cn.parentName
    if anchor and dnames[anchor] then
      vrdTotal = vrdTotal + 1
      if item.disabled == true then vrdDisabled = vrdDisabled + 1 end
    else
      regularTotal = regularTotal + 1
      if item.disabled == true then regularDisabled = regularDisabled + 1 end
    end
  end
  return vrdDisabled, vrdTotal, regularDisabled, regularTotal, s.evaluateDrivers == false
end'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['a22', 'c', 'actual'], required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--frames', type=int, default=600)
    a = ap.parse_args()
    out = a.output.resolve()
    assert out.is_relative_to(ROOT/'outputs') and not out.exists()
    out.mkdir(parents=True)
    is_c = a.mode in ('c', 'actual')
    (out/'probe-script-snapshot.py').write_bytes(Path(__file__).read_bytes())
    frozen = protected_files()
    (out/'protected-before.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')

    if a.mode == 'actual':
        source_dir = LAB/'release-candidate/C-extracted'
        chef_zip = LAB/'release-candidate/C-export/physics-runtime.zip'
        original = (LAB/'C-source/physbone_runtime.lua').read_text('utf-8-sig')
        changed = original
    else:
        source_dir = OLD/'release-candidate/A-extracted'
        chef_zip = OLD/'release-candidate/A-export/physics-runtime.zip'
        original = (OLD/'release-candidate/A-extracted/physbone_runtime.lua').read_text('utf-8-sig')
        assert original == (PROD/'single_remote_A_runtime.lua').read_text('utf-8-sig')
        changed = a22_build(original) if a.mode == 'a22' else c_build(a22_build(original))
    (out/'experimental-runtime.lua').write_text(changed, encoding='utf-8', newline='\n')

    api_counts = None
    traces = collections.defaultdict(hashlib.sha256)
    node_writes = collections.defaultdict(int)
    tracing = False

    def trace_write(u, name, values):
        if tracing:
            vals = [env['py'](v) for v in values]
            record = [int(u.id), name, vals]
            traces[int(u.id)].update(json.dumps(record, sort_keys=True, separators=(',', ':')).encode())
            if vals:
                try: node_writes[(int(u.id), int(vals[0]))] += 1
                except (TypeError, ValueError): pass

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
        first = transformed.index(changed.rstrip())
        first_line = transformed[:first].count('\n') + 1
        env['runtimeLines'] = (first_line, first_line + changed.count('\n'))
        env['addonSource'] = transformed
        (out/'sandbox-source-sha.json').write_text(json.dumps({
            'parsedSourceSha256': hashlib.sha256(src.encode()).hexdigest(),
            'executedSourceSha256': hashlib.sha256(transformed.encode()).hexdigest(),
            'sourceSubstitutionAfterParser': a.mode != 'actual',
            'notCandidatePackageValidation': a.mode != 'actual'}, indent=2), encoding='utf-8')

    prefix = TEST.read_text('utf-8-sig').split('rows=[s for s in state.sessions.values()]', 1)[0]
    prefix = replace_once(prefix, ' return S\n\ne.api=wrap(api)',
                          ' instrument_api(S)\n return S\n\ne.api=wrap(api)')
    prefix = replace_once(prefix, "if _name.startswith('set_'):writes[int(u.id)]+=1",
                          "if _name.startswith('set_'):\n    writes[int(u.id)]+=1\n    trace_write(u,_name,v)")
    prefix = replace_once(prefix, "core,scanReceipt=scan_patch(lua,a.chef_core,blob)",
                          "core,scanReceipt=scan_patch(lua,a.chef_core,blob)\n transform_scanned(lua)")
    env = {'__file__': str(TEST), '__name__': 'isolated_fixture',
           'instrument_api': instrument_api, 'transform_scanned': transform_scanned,
           'trace_write': trace_write}
    sys.argv = [str(TEST), '--source', str(source_dir),
                '--output', str(out/'fixture'), '--vm', 'lua51',
                '--chef-bit', str(OLD/'actual-chef-bit-shim.lua'),
                '--chef-patch', str(chef_zip),
                '--chef-core', str(OLD/'actual-chef-core-1.lua')]
    try:
        exec(compile(prefix, str(TEST), 'exec'), env)
    except Exception as ex:
        dbg = env.get('lua')
        if dbg is not None:
            try:
                logs = '\n'.join(str(x) for x in dbg.globals().logs.values())
                (out/'failure-logs.txt').write_text(logs, encoding='utf-8')
                st = env.get('state')
                if st is not None and st.sessions:
                    reasons = [(int(s.unit.id), s.consumerMode, s.consumerReason, bool(s.consumerPending)) for s in st.sessions.values()]
                    (out/'failure-reasons.json').write_text(json.dumps(reasons, ensure_ascii=False, indent=2), encoding='utf-8')
                    print('FAILURE reasons', reasons[:8], flush=True)
                print('FAILURE logs tail:\n', logs[-2000:], flush=True)
            except Exception as ex2:
                print('debug dump failed', ex2, flush=True)
        raise
    lua, e, state, R, av = [env[k] for k in ['lua', 'e', 'state', 'R', 'av']]
    C = env['C']
    same = lua.eval('function(a,b)return a==b end')
    classify = lua.eval(CLASSIFY)
    vrd_audit = lua.eval(VRD_AUDIT)
    iswrist = C.is_wrist_driver
    # Direct driver instrumentation: update_drivers returns the number of driver bones
    # written and is the sole driver-write path. C sets evaluateDrivers=false (so the
    # spring loop never calls it) AND singleRemoteVrdExcluded=true (so it returns 0
    # immediately if reached). Counting calls + returned writes measures driver cost
    # exactly, independent of node-index overlap between driver/VRD/regular bones.
    driver_calls = collections.Counter()
    driver_bone_writes = collections.Counter()
    old_ud = C.update_drivers
    def ud(s, dt, *v):
        r = old_ud(s, dt, *v)
        if tracing and s is not None and s.unit is not None:
            driver_calls[int(s.unit.id)] += 1
            driver_bone_writes[int(s.unit.id)] += int(r or 0)
        return r
    C.update_drivers = env['wrap'](ud)
    R.setOptions(lua.table_from({'identityWatch': True}))
    phases, checks = [], []

    def check(ok, msg):
        assert ok, msg
        checks.append(msg)

    def motion(frame):
        for owner, parts in zip(env['avatars'], env['parts']):
            if owner.alive:
                for u in parts:
                    if u.alive:
                        u.position.x = owner.position.x + .03 * math.sin(frame / 7)

    def node_sets(s):
        v, r, d = classify(s, iswrist)
        return (set(int(k) for k in v), set(int(k) for k in r), set(int(k) for k in d))

    def sample(label, players, mission=True):
        nonlocal tracing
        check(state.consumerContext.done, label+': proof complete (certificates intact)')
        env['updates'].clear(); env['writes'].clear(); traces.clear(); node_writes.clear()
        driver_calls.clear(); driver_bone_writes.clear()
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
        # Projection identity / empty retired buffers (A22-inherited).
        check_projection = lua.eval("""function(s)
            local b=s.projectionBuffers; local p=s.projectionSlot
            assert(b and p and s.projectionScratch)
            for _,map in pairs(s.projectionScratch) do assert(next(map)==nil) end
            for _,map in pairs(b[3-p]) do assert(next(map)==nil) end
            assert(s.wrappers==b[p].wrappers)
            for source,view in pairs(s.wrappers) do
                assert(view.source==source and getmetatable(view).__index==source)
            end
            return true
        end""")
        check(check_projection(state.singleState), label+': projection identity/empty retired buffers')
        sessions = list(state.sessions.values())
        check(len(state.avatars) == players and len(sessions) == players*7, label+': roster retained')
        evidence = []
        for s in sessions:
            uid = int(s.unit.id)
            own = bool(same(s.owner, av))
            vrd, regular, driver = node_sets(s)
            vrd_excl = vrd - regular
            drv_excl = driver - regular - vrd
            vw = sum(c for (u, n), c in node_writes.items() if u == uid and n in vrd_excl)
            dw = sum(c for (u, n), c in node_writes.items() if u == uid and n in drv_excl)
            rw = sum(c for (u, n), c in node_writes.items() if u == uid and n in regular)
            vd, vt, rd, rt, driversOff = vrd_audit(s, iswrist)
            dcalls, dwrites = driver_calls[uid], driver_bone_writes[uid]
            active = s.consumerMode != 'empty' and not bool(s.singleRemotePhysicsExcluded)
            if is_c:
                check(driversOff, label+': C evaluateDrivers==false ('+str(uid)+')')
                check(vd == vt, label+': C all VRD chains disabled ('+str(uid)+')')
                check(rd == 0, label+': C no regular chain disabled ('+str(uid)+')')
                check(vw == 0, label+': C zero VRD-exclusive node writes ('+str(uid)+')')
                check(dcalls == 0, label+': C zero driver solver calls ('+str(uid)+')')
                check(dwrites == 0, label+': C zero driver bone writes ('+str(uid)+')')
                if active and len(regular) > 0:
                    check(rw > 0, label+': C regular springs still write ('+str(uid)+')')
            else:
                # A22 reference: regular springs must write for active self/ship.
                # VRD/driver writes are recorded per-unit and asserted at phase level
                # (aggregate) below, avoiding per-unit node-overlap edge cases.
                if active and len(regular) > 0:
                    check(rw > 0, label+': A22 regular springs write ('+str(uid)+')')
            evidence.append(dict(unitId=uid, localOwner=own, consumerMode=s.consumerMode,
                excluded=bool(s.singleRemotePhysicsExcluded), solverCalls=env['updates'][uid],
                successfulWrites=env['writes'][uid], writeTraceSha256=traces[uid].hexdigest(),
                healthFrames=int(s.healthFrames or 0), pendingDt=float(s.pendingDt or 0),
                vrdChains=vt, vrdDisabled=vd, regularChains=rt, regularDisabled=rd,
                evaluateDriversOff=driversOff, vrdNodeWrites=vw, driverExclusiveNodeWrites=dw,
                regularNodeWrites=rw, driverSolverCalls=dcalls, driverBoneWrites=dwrites))
        check(all(x['solverCalls'] == (a.frames if x['consumerMode'] != 'empty' and (x['localOwner'] or not mission) else 0) for x in evidence), label+': exact solver cadence')
        if mission:
            check(all(x['excluded'] and x['successfulWrites'] == 0 and x['pendingDt'] == 0 for x in evidence if not x['localOwner']), label+': no remote writes or pending dt (exclusion matches A22)')
            check(e.fpCalls == fp_before, label+': no restarted FP queries')
        else:
            check(all(not x['excluded'] for x in evidence), label+': ship physics restored')
        # A22-inherited health cadence: writing per-frame, non-writing sampled /30.
        for x in evidence:
            writing = x['consumerMode'] != 'empty' and not x['excluded']
            delta = x['healthFrames'] - hf_before[x['unitId']]
            if writing:
                check(delta >= a.frames - 2, label+': writing session keeps per-frame health ('+str(x['unitId'])+')')
            else:
                check(a.frames // 30 - 2 <= delta <= a.frames // 30 + 2, label+': non-writing health sampled every 30 frames ('+str(x['unitId'])+')')
        check(dict(env['attachCounts']) == attach_before, label+': no steady reattach')
        tot_vrd = sum(x['vrdNodeWrites'] for x in evidence)
        tot_drv = sum(x['driverBoneWrites'] for x in evidence)
        tot_reg = sum(x['regularNodeWrites'] for x in evidence)
        tot_dcalls = sum(x['driverSolverCalls'] for x in evidence)
        if not is_c and not mission:
            # A22 ship reference: VRD springs write and the driver solver runs.
            # NOTE: driver BONE writes are 0 in this test01 fixture because the fake
            # engine leaves driver control bones static/unresolved (quatinterp yields
            # no valid delta), so the measurable driver cost here is solver-call
            # overhead, not bone writes. C removes those calls entirely.
            check(tot_vrd > 0, label+': A22 aggregate VRD spring writes > 0')
            check(tot_dcalls > 0, label+': A22 aggregate driver solver calls > 0')
        if is_c:
            check(tot_vrd == 0 and tot_drv == 0 and tot_dcalls == 0, label+': C aggregate zero VRD/driver writes and driver solver calls')
            check(tot_reg > 0, label+': C aggregate regular spring writes > 0')
        phases.append(dict(label=label, frames=a.frames, sessions=len(sessions),
            instructionSamples=int(lua.globals().instructionSamples),
            runtimeInstructionSamples=int(lua.globals().runtimeSamples),
            apiCalls={str(k): int(v) for k, v in sorted(api_counts.items())},
            units=evidence, lastAttempted=int(state.lastAttempted),
            lastChainTotal=int(state.lastChainTotal), staticChains=int(state.staticChains),
            peakAngle=float(state.peakAngle or 0),
            totalVrdNodeWrites=tot_vrd, totalDriverBoneWrites=tot_drv,
            totalDriverSolverCalls=tot_dcalls, totalRegularNodeWrites=tot_reg))
        print(a.mode, label, 'alive', api_counts['Unit.alive'],
              'vrdW', tot_vrd, 'drvW', tot_drv, 'drvCalls', tot_dcalls, 'regW', tot_reg, flush=True)

    e.levels=900; e.advance(e,40); e.fp=True; e.advance(e,140)
    check(same(state.singleState.selfUnit,av), 'initial ADS owner')
    e.advance(e,360)
    sample('one-player',1)
    for i in range(1,4): env['player']('remote'+str(i),20*i)
    e.advance(e,660); env['wait_for_proof']('joined-four')
    sample('four-players',4)
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
    R.setOptions(lua.table_from({'consumerPlans':False})); e.advance(e,2)
    check(all(s.consumerMode is None for s in state.sessions.values()), 'disabled plans restore full arrays')
    check(int(state.lastAttempted)==7, 'full-array fallback dispatches all local sessions')
    R.setOptions(lua.table_from({'consumerPlans':True})); env['wait_for_proof']('re-enabled')
    check(sum(s.consumerMode=='empty' for s in state.sessions.values())==4, 're-enabled proof restores empty states')
    # A22-inherited rebuild-detection latency for a stable non-writing (empty) session.
    dead_before, stale_before = e.deadCalls, e.staleWorldCalls
    empty = [s for s in state.sessions.values() if s.consumerMode == 'empty' and same(s.owner, av)]
    check(len(empty) > 0, 'local empty consumer present')
    target = empty[0]; tu = target.unit; original_nodes = int(tu.nodes)
    tu.nodes = original_nodes + 5
    detected = None
    for step in range(30):
        e.advance(e, 30)
        if not any(same(s, target) for s in state.sessions.values()):
            detected = (step + 1) * 30; break
    check(detected is not None and detected <= 900, 'empty-consumer node rebuild detected within 900 frames')
    tu.nodes = original_nodes
    env['wait_for_proof']('rebuild-recovered'); e.advance(e, 180)
    check(len(state.avatars) == 1 and len(state.sessions) == 7, 'roster recovered after rebuild probe')
    check(e.deadCalls == dead_before and e.staleWorldCalls == stale_before, 'rebuild probe introduces no dead Unit or stale World calls')
    # A22-inherited mode-change forcing.
    dead_before, stale_before = e.deadCalls, e.staleWorldCalls
    empty = [s for s in state.sessions.values() if s.consumerMode == 'empty' and same(s.owner, av)]
    check(len(empty) > 0, 'mode-force probe: local empty consumer present')
    target = empty[0]; tu = target.unit; original_nodes = int(tu.nodes)
    tu.nodes = original_nodes + 7
    R.setOptions(lua.table_from({'consumerPlans': False}))
    detected = None
    for step in range(4):
        e.advance(e, 1)
        if not any(same(s, target) for s in state.sessions.values()):
            detected = step + 1; break
    check(detected is not None and detected <= 2, 'consumer-mode change forces identity re-check within 2 frames')
    tu.nodes = original_nodes
    R.setOptions(lua.table_from({'consumerPlans': True}))
    env['wait_for_proof']('mode-force-recovered'); e.advance(e, 180)
    check(len(state.avatars) == 1 and len(state.sessions) == 7, 'roster recovered after mode-force probe')
    check(e.deadCalls == dead_before and e.staleWorldCalls == stale_before, 'mode-force probe introduces no dead Unit or stale World calls')
    old=env['parts'][0][0]; e.remove(e,old); e.advance(e,1)
    check(all(not same(s.unit,old) for s in state.sessions.values()), 'removed live-list member pruned immediately')
    # A22-inherited lifecycle / dispatch-ownership probes (activeDispatch field).
    e.levels=1; e.fp=False; e.advance(e,90)
    def populated(label):
        check(state.activeDispatch is not None and len(state.activeDispatch)>0, label+': dispatch references populated before trigger')
    def cleared(label):
        check(state.sessions is None and state.activeDispatch is None, label+': full ledger and dispatch field cleared')
        check(state.singleState is None or (state.singleState.projectionBuffers is None and state.singleState.projectionScratch is None), label+': projection pool detached on terminal path')
    worlds=e.worlds
    dead_before, stale_before=e.deadCalls, e.staleWorldCalls
    populated('world-gone'); e.worlds=lua.table(); e.advance(e,1); cleared('world-gone')
    e.worlds=worlds; env['wait_for_proof']('world-restored')
    populated('unreadable'); e.unreadable=True; e.advance(e,1); cleared('unreadable')
    e.unreadable=False; env['wait_for_proof']('inventory-restored')
    populated('loading-gap'); e.advance(e,1,1.0); cleared('loading-gap'); env['wait_for_proof']('gap-recovered')
    populated('all-parts-gone')
    for u in env['parts'][0]:
        if u.alive: e.remove(e,u)
    e.advance(e,1); cleared('all-parts-gone')
    check(state.avatars is not None and len(state.avatars)==1 and state.rearmAt>state.frame, 'all-parts-gone: empty-session backoff, not avatar/world drop')
    e.remove(e,av)
    av,_=env['player']('replacement',0); e.fpOwner=av
    env['wait_for_proof']('replacement-after-backoff')
    populated('zero-handled')
    compat=env['C']; original_update=compat.update
    def zero_update(s,dt,*v):
        s.skippedSame=0; s.engineCalls=0; return 0
    compat.update=env['wrap'](zero_update)
    original_limit=state.options.zeroLimit
    R.setOptions(lua.table_from({'zeroLimit':1})); e.advance(e,1); cleared('zero-handled')
    check(state.zeroFrames==0 and state.rearmAt>state.frame, 'zero-handled: fault injection reached driver failure backoff')
    compat.update=original_update; state.options.zeroLimit=original_limit
    env['wait_for_proof']('zero-handled-recovered')
    unloaded,_=e.player(e,'unloaded-avatar',100,0); e.advance(e,120)
    check(len(state.avatars)==2, 'orphan: replacement avatar discovered before departure')
    populated('orphan-no-plan'); e.remove(e,av); e.advance(e,1); cleared('orphan-no-plan')
    check(state.avatars is not None and len(state.avatars)==1 and same(state.avatars[1].unit,unloaded) and state.rearmAt==state.frame+1, 'orphan: surviving armorless avatar and one-frame no-plan retry')
    e.remove(e,unloaded)
    av,_=env['player']('final-replacement',0); e.fpOwner=av
    env['wait_for_proof']('orphan-recovered')
    populated('uninstall')
    check(e.deadCalls==dead_before and e.staleWorldCalls==stale_before, 'lifecycle probes introduce no dead Unit or stale World calls')
    ctx=state.consumerContext
    R.uninstall()
    check(all(j.handle is None for j in ctx.jobs.values()), 'uninstall closes proof handles')
    check(state.activeDispatch is None, 'uninstall clears dispatch even while fixture retains runtime state')
    check(state.singleState is None, 'uninstall releases projection pool with singleState')
    logs='\n'.join(str(x) for x in lua.globals().logs.values())
    logs+='\n'+'\n'.join(p.read_text('utf-8',errors='replace') for p in (out/'fixture').glob('*.log'))
    (out/'captured-logs.txt').write_text(logs, encoding='utf-8')
    check(all(x not in logs for x in ['transition-error=','proof-error=','bind-error=','could not start','could not compile','驱动抛错','驱动失败','安装失败','stopped by the hang watchdog']), 'no suppressed errors')
    after=protected_files()
    check(after==frozen, 'protected source/config/accepted packages/model bytes unchanged')
    result=dict(status='PASS_C_SPRING_ONLY_DIAGNOSTIC_NOT_RELEASE_NOT_FPS' if is_c else 'PASS_A22_BASELINE_FOR_C_COMPARISON_NOT_FPS',
        mode=a.mode, diagnosticOnly=is_c, actualChefParserForCandidate=True,
        sourceSubstitutionAfterParser=a.mode!='actual', notCandidatePackageValidation=a.mode!='actual',
        instructionSamplesIncludeFixture=True, runtimeSampleAttribution='line-range sampling, not CPU timing',
        writeTraceScope='Successful setters include runtime callback frame/Unit/order/node/value within each sample window; node-level decomposition partitions writes into VRD-exclusive / driver-exclusive / regular-spring nodes; transition/release/uninstall writes excluded',
        decompositionContract='C: VRD-exclusive node writes == 0; driver solver calls == 0 and driver bone writes == 0; regular-spring node writes > 0 for active self/ship; evaluateDrivers==false; all VRD chains disabled; no regular chain disabled. A22 reference: VRD spring writes > 0 and driver solver calls > 0 in ship. Driver BONE writes are 0 in this test01 fixture (fake engine leaves driver control bones static/unresolved), so the driver cost isolated here is solver-call overhead plus the VRD spring-write removal; a model/scene with actively-driven control bones would be needed to measure driver bone-write cost separately. The C-vs-A22 delta isolates driver+VRD cost.',
        diagnosticSafety='C is DIAGNOSTIC ONLY; skirt physics intentionally absent (visual difference vs A EXPECTED); inherits A22 <=900-frame rebuild detection + residual transition ordering gap + no pre-write identity guard; NOT a crash-safety proof; NOT for production acceptance; real-device churn validation required.',
        checks=checks, phases=phases, protectedFiles=len(frozen),
        runtimeSha256=hashlib.sha256(changed.encode()).hexdigest(),
        probeScriptSha256=sha(Path(__file__)), fixtureSourceSha256=sha(TEST),
        chefZipSha256=sha(chef_zip))
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'], len(checks), flush=True)


if __name__=='__main__':
    main()