"""VRD wrist exclusion: semantic matching, cache, zero ownership, real rig readback.

Reuses the existing driver fake engine. --rig accepts read-only v1/v2/v3 sidecars;
no model, animation, library or game writes are made.
"""
import argparse
import contextlib
import copy
import io
import json
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
with contextlib.redirect_stdout(io.StringIO()):
    engine = runpy.run_path(str(ROOT / 'HD2PhysBoneCompat/test/driver-update-test.py'))
lua, compat, S = (engine[key] for key in ('lua', 'compat', 'S'))
state, nodes, lua_fn = (engine[key] for key in ('state', 'NODES', 'lua_fn'))
checks = 0


def check(ok, message):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(message)


def table(value):
    if isinstance(value, dict):
        return lua.table_from({k: table(v) for k, v in value.items()})
    if isinstance(value, list):
        return lua.table_from([table(v) for v in value])
    return value


def plain(value):
    if not hasattr(value, 'items'):
        return value
    fields = {k: plain(v) for k, v in value.items()}
    if fields and all(isinstance(k, int) for k in fields) and set(fields) == set(range(1, len(fields) + 1)):
        return [fields[i] for i in range(1, len(fields) + 1)]
    return fields


ns = 'hd2n_0123456789ab'
other = 'hd2n_abcdef012345'
positive = [
    dict(name='ValveBiped.handl', parentName='l_elbow', controlName='l_hand'),
    dict(name='ValveBiped.handr', parentName='r_elbow', controlName='r_hand'),
    dict(name='wrist_L', parentName='l_elbow', controlName='l_hand'),
    dict(name='wrist_R', parentName='r_elbow', controlName='r_hand'),
    dict(name='unlabelled_helper', parentName='L_Forearm', controlName='L_Hand'),
    dict(name='zhandtwist_r', parentName='r_forearm', controlName='r_hand'),
    dict(name=f'{ns}_aux_064_valvebiped_handl', parentName=f'{ns}_anim_007_l_elbow', controlName=f'{ns}_anim_008_l_hand'),
    dict(name=f'{ns}_aux_087_wrist_r', parentName=f'{ns}_anim_029_r_elbow', controlName=f'{ns}_anim_030_r_hand'),
    dict(name=f'{ns}_aux_124_zhandtwist_l', parentName=f'{ns}_anim_021_l_forearm', controlName=f'{ns}_anim_022_l_hand'),
]
negative = [
    dict(name='l_hand', parentName='l_elbow', controlName='l_hand'),
    dict(name='r_hand', parentName='r_elbow', controlName='r_hand'),
    dict(name='l_finger', parentName='l_hand', controlName='l_hand'),
    dict(name='skirt_wrist_label', parentName='hips', controlName='l_thigh'),
    dict(name='wrist_L', parentName='l_elbow', controlName='r_hand'),
    dict(name='wrist_R', parentName='r_elbow', controlName='l_hand'),
    dict(name=f'{ns}_aux_064_wrist_l', parentName=f'{other}_anim_007_l_elbow', controlName=f'{ns}_anim_008_l_hand'),
    dict(name=f'{ns}_aux_064_wrist_l', parentName=f'{ns}_anim_007_l_elbow', controlName=f'{other}_anim_008_l_hand'),
    dict(name=f'{ns}_anim_008_l_hand', parentName=f'{ns}_anim_007_l_elbow', controlName=f'{ns}_anim_008_l_hand'),
    dict(name=f'{ns}_aux_064_wrist_l', parentName=f'{ns}_aux_007_l_elbow', controlName=f'{ns}_anim_008_l_hand'),
    dict(name='hd2n_x_aux_064_wrist_l', parentName='hd2n_x_anim_007_l_elbow', controlName='hd2n_x_anim_008_l_hand'),
    dict(name=f'{ns}_aux_064_wrist_l', parentName='l_elbow', controlName='l_hand'),
    {}, dict(name='wrist_L'),
]
for bone in positive:
    check(compat.is_wrist_driver(table(bone)) is True, f'not excluded: {bone}')
for bone in negative:
    check(compat.is_wrist_driver(table(bone)) is False, f'false exclusion: {bone}')
check(compat.is_wrist_driver(None) is False, 'nil must not crash')

# Track direct wrist accesses, including cached has_node and release pose writes.
protected_names, protected_nodes, accesses = set(), set(), []
for method, named in [('has_node', True), ('node', True), ('local_pose', False),
                      ('world_rotation', False), ('set_local_rotation', False), ('set_local_pose', False)]:
    original = S.Unit[method]

    def tracked(unit, key, *args, method=method, named=named, original=original):
        if key in (protected_names if named else protected_nodes):
            accesses.append((method, key))
        return original(unit, key, *args)

    S.Unit[method] = lua_fn(tracked)

seed = plain(engine['rig'])
rules = seed['drivers']['bones'][0]['rules']


def attach_check(bones, version, expected, label, seed_stale_cache=False):
    protected_names.clear()
    protected_nodes.clear()
    nodes.clear()
    for bone in seed['bones']:
        for name in (bone['name'], bone['parentName']):
            nodes.setdefault(name, len(nodes) + 1)
    for bone in bones:
        for name in (bone['name'], bone['parentName'], bone['controlName']):
            nodes.setdefault(name, len(nodes) + 1)
        if compat.is_wrist_driver(table(bone)):
            protected_names.add(bone['name'])
            protected_nodes.add(nodes[bone['name']])
    # Give all controls a covered identity trigger, without relying on one fixture name.
    def world_rotation(unit, node):
        if node in protected_nodes:
            accesses.append(('world_rotation', node))
        return lua.table(0, 0, 0, 1)
    S.Unit.world_rotation = lua_fn(world_rotation)
    rig = table(dict(bones=copy.deepcopy(seed['bones']), drivers=dict(version=version, bones=bones)))
    compat.clear_attach_cache()
    if seed_stale_cache:
        stale = lua.table()
        for i, bone in enumerate(bones, 1):
            stale[i] = table([nodes[bone['name']], nodes[bone['parentName']], nodes[bone['controlName']]])
        compat._attachCache['abc12345|128|drv'] = stale
    for instance in range(2):
        accesses.clear()
        state['rot_writes'].clear()
        state['pose_writes'].clear()
        logs = []
        logger = lua_fn(lambda fmt, *args: logs.append((fmt, args)))
        session = compat.attach(S, table(dict(unit='u')), rig, table(dict(logger=logger, world=lua.table())))
        check(len(session.drivers) == expected, f'{label}: active driver count')
        check(session.excludedWristDrivers == len(protected_names), f'{label}: exclusion count')
        driver_logs = [args for fmt, args in logs if 'driver' in fmt and len(args) == 3]
        check(driver_logs == [(expected, len(protected_names), 0)], f'{label}: exclusion diagnostic')
        check(not accesses, f'{label}: wrist accessed during attach/cache: {accesses}')
        if expected:
            check(compat.update_drivers(session, 1 / 60) == expected, f'{label}: unrelated drivers did not write')
            for _ in range(120):
                compat.update_drivers(session, 1 / 60)
            check(compat.update_drivers(session, 1 / 60) == 0, f'{label}: unrelated dedup changed')
        else:
            check(compat.update_drivers(session, 1 / 60) == 0, f'{label}: wrists still driven')
        for _ in range(10):
            compat.update_tip(session, 1 / 60)
        compat.release(session)
        check(not accesses, f'{label}: wrist accessed by update/release: {accesses}')
        check(not any(row[0] in protected_nodes for row in state['rot_writes']), f'{label}: wrist rotation written')
        check(not any(row[0] in protected_nodes for row in state['pose_writes']), f'{label}: wrist bind restored')
        if expected:
            check(any(row[0] not in protected_nodes for row in state['pose_writes']), f'{label}: release did not restore other nodes')
    return dict(label=label, version=version, records=len(bones), active=expected, excluded=len(protected_names))


results = []
for version in (1, 2, 3):
    synthetic = copy.deepcopy(positive)
    synthetic.append(dict(name='skirt_front_helper1', parentName='hips', controlName='l_thigh'))
    for bone in synthetic:
        bone.update(rules=copy.deepcopy(rules), controlBindQ=[0, 0, 0, 1])
    results.append(attach_check(synthetic, version, 1, f'synthetic-v{version}', seed_stale_cache=True))
    results.append(attach_check(synthetic[:-1], version, 0, f'wrist-only-v{version}'))

parser = argparse.ArgumentParser()
parser.add_argument('--rig', type=Path, action='append', default=[])
parser.add_argument('--report', type=Path)
args = parser.parse_args()
for path in args.rig:
    original_bytes = path.read_bytes()
    parsed = plain(compat.parse_driver_rig(original_bytes))
    check(isinstance(parsed, dict), f'cannot parse {path}')
    bones = parsed['bones']
    wrist_count = sum(compat.is_wrist_driver(table(bone)) is True for bone in bones)
    check(wrist_count == 2, f'{path}: expected two authored wrist helpers')
    results.append(attach_check(bones, parsed['version'], len(bones) - wrist_count, str(path)))
    check(path.read_bytes() == original_bytes, f'{path}: source sidecar modified')

report = dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE', checks=checks, cases=results,
              wristEngineAccesses=0, rigParsingPreserved=True)
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
