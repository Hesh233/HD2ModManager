"""Read-only test06 VRD skirt audit: live logs, compiled rules and bind/delta frames.

Writes evidence only under --out in this workspace. Never changes runtime code,
models, animations, the managed library or game deployment. Requires numpy/lupa.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, re, struct, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if ROOT.name == 'HD2ModManager_main': ROOT = ROOT.parent
sys.path.insert(0, str(ROOT.parents[1]))
import numpy as np
from lupa.lua51 import LuaRuntime
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from anim_batch_mod.math3d import (
    matrix3_columns_to_quaternion, quat_conjugate, quat_multiply, quat_normalize,
)
from anim_batch_mod.native_skeleton import bone_name_hash

INSTALL = ROOT / 'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
MODEL = INSTALL / 'test-library/[原比例模型]test06/vpk2patch'
LOGS = Path(r'C:\Users\Administrator\AppData\Roaming\Arrowhead\Helldivers2')
GAME = Path(r'E:\Steam\steamapps\common\Helldivers 2\data')
FOCUS = 'eaa587b00a8e53ec'
IDENTITY = (0., 0., 0., 1.)
checks = 0

def check(ok, text):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(text)

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def py(value):
    if not hasattr(value, 'items'):
        return value
    d = {k: py(v) for k, v in value.items()}
    if d and set(d) == set(range(1, len(d) + 1)):
        return [d[i] for i in range(1, len(d) + 1)]
    return d

def table(lua, value):
    if isinstance(value, dict):
        return lua.table_from({k: table(lua, v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return lua.table_from([table(lua, v) for v in value])
    return value

def angle(a, b=IDENTITY):
    a, b = quat_normalize(a), quat_normalize(b)
    dot = abs(sum(x * y for x, y in zip(a, b)))
    return math.degrees(2 * math.acos(min(1., dot)))

def q9(v):
    return matrix3_columns_to_quaternion([v[:3], v[3:6], v[6:9]])

def qm(v):
    return matrix3_columns_to_quaternion([tuple(v[:3, k]) for k in range(3)])

def patch_rows(path):
    with path.open('rb') as f:
        header = f.read(72)
        check(len(header) == 72, f'patch header: {path}')
        nt, n = struct.unpack_from('<II', header, 4)
        f.seek(72 + 32 * nt)
        return [struct.unpack('<QQQQQQQIIIIII', f.read(80)) for _ in range(n)]

def payload(path, row):
    with path.open('rb') as f:
        f.seek(row[2])
        raw = f.read(row[7])
    check(len(raw) == row[7], 'short payload')
    return raw

def units(path):
    return {f'{r[0]:016x}': UnitData.parse(payload(path, r))
            for r in patch_rows(path) if r[1] == UNIT_TYPE_ID}

def source_mdl(vpk):
    with vpk.open('rb') as f:
        magic, version, size = struct.unpack('<III', f.read(12))
        check(magic == 0x55AA1234 and version in (1, 2), 'VPK header')
        head = 12 if version == 1 else 28
        f.seek(head)
        tree = f.read(size)
        at, found = 0, []
        def text():
            nonlocal at
            end = tree.index(0, at)
            s = tree[at:end].decode('utf-8')
            at = end + 1
            return s
        while (ext := text()):
            while (directory := text()):
                while (name := text()):
                    _, pre, archive, off, length, term = struct.unpack_from('<IHHIIH', tree, at)
                    at += 18
                    check(term == 0xffff, 'VPK entry terminator')
                    prefix = tree[at:at + pre]
                    at += pre
                    if ext == 'mdl' and directory == 'models/survivors':
                        found.append((f'{directory}/{name}.{ext}', archive, off, length, prefix))
        check(at == size and len(found) == 1, 'complete VPK tree / one survivor')
        name, archive, off, length, prefix = found[0]
        check(archive == 0x7fff, 'inline survivor MDL')
        f.seek(head + size + off)
        mdl = prefix + f.read(length)
    check(mdl[:4] == b'IDST' and struct.unpack_from('<I', mdl, 4)[0] == 49, 'MDL v49')
    n, start = struct.unpack_from('<ii', mdl, 156)
    bones = []
    for i in range(n):
        a = start + i * 216
        inverse = np.eye(4)
        inverse[:3, :] = np.array(struct.unpack_from('<12f', mdl, a + 96)).reshape(3, 4)
        kind, off = struct.unpack_from('<ii', mdl, a + 164)
        b = dict(index=i, parent=struct.unpack_from('<i', mdl, a + 4)[0],
                 world=np.linalg.inv(inverse), kind=kind)
        if kind == 2:
            block = a + off
            control, count, rules_off = struct.unpack_from('<iii', mdl, block)
            b.update(control=control, rules=[struct.unpack_from('<12f', mdl, block + rules_off + k * 48)
                                             for k in range(count)])
        bones.append(b)
    return name, bones

def container_records(path):
    with path.open('rb') as f:
        f.seek(0, 2)
        length = f.tell()
        if length < 104:
            return None
        f.seek(-56, 2)
        footer = f.read(56)
        if footer[:8] != b'HD2PBFT1':
            return None
        size = struct.unpack_from('<Q', footer, 16)[0]
        check(104 <= size <= length, 'container length')
        f.seek(length - size)
        data = f.read(size)
    check(data[:8] == b'HD2PBX01', 'container magic')
    at = struct.unpack_from('<Q', data, 24)[0]
    n = struct.unpack_from('<I', data, 40)[0]
    records = {}
    for _ in range(n):
        name_size = struct.unpack_from('<H', data, at)[0]
        off, size = struct.unpack_from('<QQ', data, at + 4)
        name = data[at + 56:at + 56 + name_size].decode('utf-8')
        records[name] = data[off:off + size]
        at += 56 + name_size
    return records

def summary(values):
    if not values:
        return dict(count=0)
    return dict(count=len(values), min=float(min(values)), median=float(np.median(values)),
                p95=float(np.percentile(values, 95)), max=float(max(values)))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=ROOT / 'outputs/test06-vrd-skirt-analysis-20261109')
    ap.add_argument('--logs-dir', type=Path, default=LOGS)
    ap.add_argument('--deployment-snapshot', type=Path, help='Replay resolved test06 targets from a saved audit, without changing current deployment')
    ap.add_argument('--overwrite-report', action='store_true', help='Replace only tool-generated evidence outputs')
    args = ap.parse_args()
    out = args.out.resolve()
    check(out.is_relative_to(ROOT), 'evidence output stays in workspace')
    check(args.overwrite_report or not (out / 'audit.json').exists(), 'do not overwrite existing evidence')
    out.mkdir(parents=True, exist_ok=True)
    sources = [ROOT / f'HD2PhysBoneCompat/src/{n}' for n in (
        'physbone_compat.lua', 'physbone_runtime.lua', 'native_grip_transfer_test.lua',
        'native_grip_transfer_test_entry.lua')]
    protected = sources + list(p for p in MODEL.iterdir() if p.is_file()) + [
        ROOT / 'testVPK/test06.vpk', INSTALL / 'settings.json',
        INSTALL / 'test-library/library.json', INSTALL / 'test-library/profiles.json']
    before = {str(p): sha(p) for p in protected}
    lua = LuaRuntime(unpack_returned_tuples=True)
    mod = lua.execute(sources[0].read_text(encoding='utf-8-sig'))
    spring = py(mod.parse_rig((MODEL / 'physbone-rig.bin').read_bytes()))
    drivers = py(mod.parse_driver_rig((MODEL / 'physbone-driver-rig.bin').read_bytes()))
    check(drivers['version'] == 2 and len(drivers['bones']) == 7, 'test06 v2 / seven drivers')
    manifest = json.loads((MODEL / 'source-skeleton.json').read_text(encoding='utf-8-sig'))
    names = {b['name']: b for b in manifest['bones']}
    original = units(MODEL / '9ba626afa44a3aa3.patch_0')
    check(len(original) == 7, 'seven original Units')
    canonical = next(iter(original.values()))
    idx = lambda name, model=canonical: model.name_hashes.index(bone_name_hash(name))
    mdl_name, mdl_bones = source_mdl(ROOT / 'testVPK/test06.vpk')
    facts, bindings = [], {}
    for b in drivers['bones']:
        source_index = names[b['name']]['sourceIndex']
        raw = mdl_bones[source_index]
        check(raw['kind'] == 2 and raw['control'] == names[b['controlName']]['sourceIndex'], 'source driver/control')
        check(len(raw['rules']) == len(b['rules']), 'rule count preserved')
        source_control = qm(np.linalg.inv(mdl_bones[raw['parent']]['world']) @ mdl_bones[raw['control']]['world'])
        raw_bind = raw['rules'][0][8:12]
        errors = []
        for r, orig in zip(b['rules'], raw['rules']):
            tq = quat_multiply(orig[1:5], quat_conjugate(source_control))
            dq = quat_multiply(orig[8:12], quat_conjugate(raw_bind))
            errors.append((angle(tq, r['trigger']), angle(dq, r['rotation'])))
            check(max(errors[-1]) < .001, 'raw MDL -> v2 bake preserved')
            check(abs(r['invTolerance'] - orig[0]) < 1e-7, 'tolerance preserved')
            source_position = [v * .0254 * manifest['modelScale'] for v in orig[5:8]]
            check(math.dist(source_position, r['position']) < 1e-7, 'original Source positions preserved')
        bind = canonical.transforms[idx(b['name'])].rotation
        bind_p = canonical.transforms[idx(b['name'])].position
        positions = [r['position'] for r in b['rules']]
        spread = max(math.dist(a, c) for a in positions for c in positions) * 1000
        drift = max(math.dist(bind_p, p) for p in positions) * 1000
        check(spread == 0 and drift < .001, 'no authored translation omitted')
        check(angle(bind, raw_bind) < .001, 'helper authored bind preserved')
        wrist = bool(mod.is_wrist_driver(table(lua, b)))
        children = [x for x in spring['bones'] if x['parentName'] == b['name']]
        flags = [int(x['flags']) for x in children]
        check(not children or flags == [0x31], 'test06 skirt has no fixed-world yaw/pitch gate')
        facts.append(dict(sourceIndex=source_index, name=b['name'], parent=b['parentName'],
            control=b['controlName'], controlSourceIndex=raw['control'], excludedWrist=wrist,
            ruleCount=len(b['rules']), bindRotation=list(bind), positionsSpreadMm=spread,
            positionsVsLocalBindMaxMm=drift, bakedRuleErrorDegrees=max(max(v) for v in errors),
            springChildren=[dict(name=c['name'], sourceIndex=names[c['name']]['sourceIndex'],
                                 flags=f'0x{int(c["flags"]):02x}') for c in children]))
        if not wrist:
            bindings[b['name']] = dict(bind=bind, rules=b, sourceIndex=source_index)
    check(len(bindings) == 5, 'five skirt drivers / accepted wrist exclusion')

    # Read current winners, never write game files or change symlinks.
    deployed, focus_model, focus_winner, containers = [], None, None, []
    physical_payloads = []
    snapshot = json.loads(args.deployment_snapshot.read_text(encoding='utf-8')) if args.deployment_snapshot else None
    patch_paths = sorted([p for p in GAME.glob('9ba626afa44a3aa3.patch_*')
                          if re.fullmatch(r'9ba626afa44a3aa3\.patch_\d+', p.name)],
                         key=lambda p: int(p.name.rsplit('_', 1)[1]))
    if snapshot is not None:
        patch_paths = [Path(r['resolved']) for r in snapshot['deployment']['patches']]
    for p in patch_paths:
        target = p.resolve()
        deployed.append(dict(path=str(p), resolved=str(target)))
        for row in patch_rows(p):
            if row[1] == UNIT_TYPE_ID and f'{row[0]:016x}' == FOCUS:
                focus_model, focus_winner = UnitData.parse(payload(p, row)), str(p)
            if '物理运行时-弹簧自由度补全' in str(target) and row[1] == 0xa14e8dfa2cd117e2:
                physical_payloads.append(payload(p, row).replace(b'\r\n', b'\n'))
        gpu = Path(str(p) + '.gpu_resources')
        if gpu.exists():
            records = container_records(gpu)
            if records and 'hd2_driver_rig.bin' in records:
                check(records['hd2_driver_rig.bin'] == (MODEL / 'physbone-driver-rig.bin').read_bytes(), 'deployed driver rig exact')
                check(records['hd2_spring_rig.bin'] == (MODEL / 'physbone-rig.bin').read_bytes(), 'deployed spring rig exact')
                containers.append(dict(path=str(gpu), records={k: hashlib.sha256(v).hexdigest() for k, v in records.items()}))
    check(focus_model is not None and len(containers) == 1, 'current hips winner / one matching physics container')
    for name, fact in bindings.items():
        fn = focus_model.name_hashes.index(bone_name_hash(name))
        check(angle(focus_model.transforms[fn].rotation, fact['bind']) < .001, 'final winner keeps helper bind')
    check(bool(physical_payloads), 'deployed physics Lua present')
    lua_exact = {}
    for path in sources[:2]:
        raw = path.read_bytes().replace(b'\r\n', b'\n')
        present = any(raw in body for body in physical_payloads)
        check(present, f'deployed physics Lua matches {path.name}')
        lua_exact[path.name] = dict(normalizedSha256=hashlib.sha256(raw).hexdigest(), embeddedExact=True)

    compact = (args.deployment_snapshot.parent / 'hd2physbone_compact.snapshot.log') if snapshot is not None else args.logs_dir / 'hd2physbone_compact.log'
    compact_data = compact.read_bytes()
    (out / 'hd2physbone_compact.snapshot.log').write_bytes(compact_data)
    compact_text = compact_data.decode('utf-8-sig', errors='replace')
    attaches = [tuple(map(int, v)) for v in re.findall(r'driver：可驱动 (\d+) 根（主动排除手腕 (\d+)、缺节点/控制骨/bind (\d+)）', compact_text)]
    check(len(attaches) == 7 and set(attaches) == {(5, 2, 0)}, 'latest seven successful driver attaches')
    latest_perf = (args.deployment_snapshot.parent / Path(snapshot['latestSession']['perfPath']).name) if snapshot is not None else sorted(args.logs_dir.glob('hd2_grip_TEST_PERF_test06_LEFT_ITEMS_V10_*.log'))[-1]
    perf_bytes = latest_perf.read_bytes()
    (out / latest_perf.name).write_bytes(perf_bytes)
    perf_events = collections.Counter()
    loaded = complete = None
    for line in perf_bytes.decode('utf-8-sig').splitlines():
        if '{' not in line:
            continue
        event = json.loads(line[line.index('{'):])
        perf_events[event.get('event')] += 1
        if event.get('event') == 'loaded': loaded = event
        if event.get('event') == 'complete': complete = event
    check(loaded['rigExpectedNodes'] == 267 and not loaded['detailedLog'], 'latest layout / compact evidence limit')

    # Older V8 logged the actual weighted hips mesh nodes. Every observation is
    # matched by exact resource/name, not an assumed index or a GUI bone label.
    stats = {name: collections.defaultdict(list) for name in bindings}
    historical, examples, event_counts = [], [], collections.Counter()
    sample_path = out / 'weighted-hips-samples.jsonl'
    with sample_path.open('w', encoding='utf-8') as sample_file:
        for log in sorted(args.logs_dir.glob('hd2_grip_TEST_DETAILED_test06_SOURCE_FK_V8_*.part*.log')):
            accepted = 0
            with log.open(encoding='utf-8-sig', errors='replace') as f:
                for line in f:
                    start = line.find('{')
                    if start < 0:
                        continue
                    event = json.loads(line[start:])
                    if event.get('event') != 'test_body_lifecycle_probe' or not event.get('models'):
                        continue
                    if event['stage'] not in ('final_output', 'next_render_input'):
                        continue
                    model = next((v for v in event['models'] if v['resource'] == FOCUS), None)
                    if model is None:
                        continue
                    poses = model['weightedBonePoses']
                    event_counts[event['stage']] += 1
                    accepted += 1
                    records = []
                    for name, fact in bindings.items():
                        b, bind = fact['rules'], fact['bind']
                        if not all(n in poses for n in (name, b['parentName'], b['controlName'])):
                            continue
                        parent = q9(poses[b['parentName']]['world'])
                        observed_delta = q9(poses[name]['localPose'])
                        observed_relative = quat_multiply(quat_conjugate(parent), q9(poses[name]['world']))
                        engine_post = quat_multiply(bind, observed_delta)
                        parent_delta_order = quat_multiply(observed_delta, bind)
                        corrected_local = quat_multiply(quat_conjugate(bind), quat_multiply(observed_delta, bind))
                        corrected_relative = quat_multiply(bind, corrected_local)
                        formula_error = angle(observed_relative, engine_post)
                        counterfactual_error = angle(observed_relative, parent_delta_order)
                        correction_error = angle(corrected_relative, parent_delta_order)
                        check(formula_error < .001, 'observed world = parent * bind * localDelta')
                        check(correction_error < .00001, 'bone-frame conjugation numerical equivalence')
                        st = stats[name]
                        st['enginePostBindFormulaErrorDegrees'].append(formula_error)
                        st['frameOrderDifferenceDegrees'].append(counterfactual_error)
                        st['conjugatedReplayErrorDegrees'].append(correction_error)
                        moving = angle(observed_delta) > .1
                        if moving:
                            st['movingFrameOrderDifferenceDegrees'].append(counterfactual_error)
                        records.append(dict(name=name, sourceIndex=fact['sourceIndex'],
                            localPose=poses[name]['localPose'], helperWorld=poses[name]['world'],
                            parentWorld=poses[b['parentName']]['world'],
                            enginePostBindFormulaErrorDegrees=formula_error,
                            frameOrderDifferenceDegrees=counterfactual_error,
                            conjugatedReplayErrorDegrees=correction_error))
                    if records:
                        row = dict(log=log.name, wallTime=line[:19], frame=event['frame'],
                                   stage=event['stage'], instance=model['instance'], resource=FOCUS, records=records)
                        sample_file.write(json.dumps(row, ensure_ascii=False) + '\n')
                        if len(examples) < 8:
                            examples.append(row)
            historical.append(dict(path=str(log), sha256=sha(log), observedSamples=accepted))
    check(bool(historical) and all(v['frameOrderDifferenceDegrees'] for v in stats.values()), 'real weighted helper observations')
    measured = [dict(name=name, sourceIndex=bindings[name]['sourceIndex'],
                     **{field: summary(values) for field, values in st.items()})
                for name, st in stats.items()]

    # Independent real-rule runtime fixtures: attach/reference depends on the
    # first animated pose in native v2; uncovered poses leave the last write.
    exercise = lua.eval('''function(m, rules, startAngle, targetAngle, outsideAngle)
        local function rx(a) return {math.sin(a/2),0,0,math.cos(a/2)} end
        local current, result = rx(startAngle), {0,0,0,1}
        local S={Unit={},Quaternion={}}
        S.Unit.world_rotation=function(_,n) if n==1 then return {0,0,0,1} end return current end
        S.Quaternion.to_elements=function(q) return q[1],q[2],q[3],q[4] end
        S.Quaternion.from_elements=function(x,y,z,w) return {x,y,z,w} end
        S.Unit.set_local_rotation=function(_,_,q) result={q[1],q[2],q[3],q[4]} end
        local row={name='test06-skirt-fixture',node=3,parentNode=1,controlNode=2,rules=rules,
                   base={bindQ={0,0,0,1},px=0,py=0,pz=0}}
        local session={S=S,unit={},rig={drivers={version=2}},drivers={row}}
        m._fastWrite=true
        m.update_drivers(session,1/60)
        current=rx(targetAngle); local targetWrites=m.update_drivers(session,1/60)
        local target={result[1],result[2],result[3],result[4]}
        current=rx(outsideAngle); local outsideWrites=m.update_drivers(session,1/60)
        return target, result, targetWrites, outsideWrites
    end''')
    procedural = next(v['rules'] for v in bindings.values() if v['sourceIndex'] == 74)
    rx = lambda degrees: (math.sin(math.radians(degrees) / 2), 0, 0, math.cos(math.radians(degrees) / 2))
    target_expected = mod.quatinterp(table(lua, rx(-60)), table(lua, procedural))
    fixture = []
    for start in (-30, 0, 30):
        target, outside, target_writes, outside_writes = exercise(mod, table(lua, procedural['rules']),
            math.radians(start), math.radians(-60), math.radians(130))
        target, outside = py(target), py(outside)
        check(outside_writes == 0 and angle(target, outside) < .00001, 'v2 uncovered result really latches')
        fixture.append(dict(firstControlDeltaDegrees=start, targetControlDeltaDegrees=-60,
            outputDegrees=angle(target), vsCanonicalOutputErrorDegrees=angle(target, target_expected),
            uncoveredControlDeltaDegrees=130, uncoveredWrites=outside_writes,
            latchedOutputDegrees=angle(outside)))
    frame_exercise = lua.eval('''function(m, rules, target)
        local current, written={0,0,0,1},{0,0,0,1}
        local S={Unit={},Quaternion={}}
        S.Unit.world_rotation=function(_,n) if n==1 then return {0,0,0,1} end return current end
        S.Quaternion.to_elements=function(q) return q[1],q[2],q[3],q[4] end
        S.Quaternion.from_elements=function(x,y,z,w) return {x,y,z,w} end
        S.Unit.set_local_rotation=function(_,_,q) written={q[1],q[2],q[3],q[4]} end
        local row={name='test06-native-frame',node=3,parentNode=1,controlNode=2,rules=rules,
            base={bindQ={0,0,0,1},px=0,py=0,pz=0}}
        local session={S=S,unit={},rig={drivers={version=2}},drivers={row}}
        m._fastWrite=true; m.update_drivers(session,1/60)
        current=target; m.update_drivers(session,1/60)
        return written
    end''')
    frame_fixtures=[]
    for name, fact in bindings.items():
        b, bind=fact['rules'],fact['bind']
        for rule_index, rule in enumerate(b['rules']):
            written=py(frame_exercise(mod,table(lua,b['rules']),table(lua,rule['trigger'])))
            authored_delta=mod.quatinterp(table(lua,quat_normalize(rule['trigger'])),table(lua,b))
            check(angle(written,authored_delta)<.001, 'real native v2 writer emits parent delta directly')
            actual_world=quat_multiply(bind,written)
            source_expected=quat_multiply(authored_delta,bind)
            corrected=quat_multiply(quat_conjugate(bind),quat_multiply(written,bind))
            corrected_world=quat_multiply(bind,corrected)
            corrected_error=angle(corrected_world,source_expected)
            check(corrected_error<.001, 'conjugated setter reproduces authored Source helper orientation')
            frame_fixtures.append(dict(name=name,sourceIndex=fact['sourceIndex'],rule=rule_index,
                canonicalFirstPose=True,unmodifiedWriterWorldErrorDegrees=angle(actual_world,source_expected),
                conjugatedSetterWorldErrorDegrees=corrected_error))
    save(out / 'native-write-frame-fixtures.json', frame_fixtures)
    check(fixture[1]['vsCanonicalOutputErrorDegrees'] < .001, 'fixture canonical start control')
    check(max(r['vsCanonicalOutputErrorDegrees'] for r in fixture) > 20, 'first-pose reference counterexample')
    after = {str(p): sha(p) for p in protected}
    check(before == after, 'all protected files byte-identical after audit')
    protection = dict(unchanged=True, count=len(before), before=before, after=after)
    save(out / 'protected-files.json', protection)
    save(out / 'real-rule-runtime-fixtures.json', fixture)
    report = dict(status='READ_ONLY_AUDIT_PASS', checks=checks,
        date='2026-11-09', timezone='Asia/Shanghai', sourceMdl=mdl_name,
        modelScale=manifest['modelScale'], driverVersion=drivers['version'], drivers=facts,
        latestSession=dict(physicsHeader=compact_text.splitlines()[0], driverAttachResults=attaches,
            physicsLogSha256=hashlib.sha256(compact_data).hexdigest(),
            perfPath=str(latest_perf), perfSha256=hashlib.sha256(perf_bytes).hexdigest(),
            perfEvents=perf_events, complete=complete,
            limitation='Latest V10 is compact: no per-frame skirt driver control/bind/weight matrices.'),
        deployment=dict(evidenceMode='captured-resolved-targets' if snapshot is not None else 'current-game-links',
            snapshotSource=str(args.deployment_snapshot) if snapshot is not None else None,
            patches=deployed, hipsWinner=focus_winner, hipsResource=FOCUS,
            hipsNodes=len(focus_model.transforms), containers=containers, physicsLua=lua_exact),
        historicalEvidence=dict(session='2026-11-08 22:21:14 SOURCE_FK_V8; not latest session',
            logs=historical, phases=event_counts, helperMeasurements=measured,
            observation='worldRelative = authoredBind * observedLocalDelta',
            counterfactual='Same observed parent-space VRD delta should compose delta * authoredBind; current setter frame does not commute.',
            conjugatedReplay='localDelta = inverse(authoredBind) * deltaParent * authoredBind',
            limitations=['CPU matrices, not GPU skin/polygon penetration depth or live L4D2 observations.',
                         'Snapshots are not a trace of update_drivers.controlQ0/rule weights; first-pose magnitude is a separate offline counterexample.',
                         'Changing multiplication order is replayed in memory only, not a deployed fix.']),
        runtimeFixtures=fixture, nativeWriteFrameFixtures=frame_fixtures,
        protectedFileCount=len(before), productionChanges=False)
    save(out / 'audit.json', report)
    peak=max(r['frameOrderDifferenceDegrees']['max'] for r in measured)
    print(json.dumps(dict(status=report['status'], checks=checks, protectedFiles=len(before),
        historicalFiles=len(historical), phases=event_counts,
        frameOrderPeakDegrees=peak,
        helpers=[dict(sourceIndex=r['sourceIndex'], samples=r['frameOrderDifferenceDegrees']['count'],
            engineFormulaMaxDegrees=r['enginePostBindFormulaErrorDegrees']['max'],
            frameOrder=r['movingFrameOrderDifferenceDegrees'],
            conjugatedReplayMaxDegrees=r['conjugatedReplayErrorDegrees']['max']) for r in measured],
        fixtures=fixture, report=str(out / 'audit.json')), ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()



