"""Verify B20 aiming preservation, left candidates, read-only telemetry and B19 regression."""
import copy
import math
import os
from package_native_v12 import ROOT, load, save_json, digest
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units, shape, plain
from audit_native_v20_b12 import raw
from anim_batch_mod.math3d import matrix3_columns_to_quaternion
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime

W = ROOT / 'outputs/native-v28-b20-20261105'
OLD = ROOT / 'outputs/native-v27-b19-20261105'
P = ROOT / 'outputs/native-manual-20261103/project'
SRC = ROOT / 'HD2PhysBoneCompat/src'
TEST = ROOT / 'HD2PhysBoneCompat/test'


def main():
    avatar = next(iter(units(P / 'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    models = units(P / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    source = (SRC / 'native_attachments.lua').read_text(encoding='utf-8')
    module = (SRC / 'native_grip_alignment.lua').read_text(encoding='utf-8')
    old_source = (W / 'baseline/native_attachments.lua').read_text(encoding='utf-8-sig')
    old_module = (W / 'baseline/native_grip_alignment.lua').read_text(encoding='utf-8-sig')
    strict = (TEST / 'strict_id32_fixture.lua').read_text(encoding='utf-8')
    module_harness = (TEST / 'native_grip_alignment_harness.lua').read_text(encoding='utf-8').replace('-- STRICT_ID_FIXTURE', strict)
    consumer_harness = module_harness.split('local instance=make();', 1)[0] + (TEST / 'native_grip_alignment_consumers_harness.lua').read_text(encoding='utf-8')
    prefix = (TEST / 'attachments_layout_harness.lua').read_text(encoding='utf-8').split('check(armor.nodes~=A.nodes', 1)[0]
    prefix = prefix.replace('local runtime=adapter.new', strict + '\n__auditLogs=logs\nlocal runtime=adapter.new')
    full_harness = prefix + (TEST / 'native_grip_alignment_adapter_harness.lua').read_text(encoding='utf-8')

    def run(profile, fixture, program, adapter_source=source, module_source=module):
        vm = LuaRuntime(unpack_returned_tuples=True)

        def quat(matrix):
            cols = [[matrix[i] for i in range(c, c + 3)] for c in (1, 4, 7)]
            cols = [[v / math.sqrt(sum(x*x for x in col)) for v in col] for col in cols]
            return vm.table_from(matrix3_columns_to_quaternion(cols))

        vm.globals().quat_from_matrix = quat
        vm.globals().adapter = vm.execute(adapter_source)
        vm.globals().module = vm.execute(module_source)
        vm.globals().fixture = vm.table_from(fixture, recursive=True)
        vm.globals().profile = vm.table_from(profile, recursive=True)
        vm.globals().hash_name = bone_name_hash
        try:
            return plain(vm.execute(program))
        except Exception:
            logs = vm.globals().__auditLogs
            if logs is not None:
                (W / 'failed-runtime.log').write_text('\n'.join(logs.values()), encoding='utf-8')
            raise

    def log_result(name, result):
        log = '\n'.join(result.pop('logs').values())
        (W / (name + '.log')).write_text(log, encoding='utf-8')
        result.pop('history', None)
        return log

    affine_fixture = dict(hashes=avatar.name_hashes, parents=[0 if x is None else x+1 for x in avatar.parents],
                          matrices=[raw(t) for t in avatar.transforms])

    def full_fixture(p):
        return dict(avatar=shape(avatar), models={r: shape(models[r]) for r in p['modelLayouts']})

    cases, full, consumers, regressions = {}, {}, {}, {}
    for variant in ('R', 'A', 'H', 'T'):
        p = load(W / ('B20-' + variant + '.json'))
        result = run(p, affine_fixture, module_harness)
        log = log_result('module-' + variant, result)
        assert 'event=rollback avatar=1 verified=true' in log and 'post_refresh_target_overwritten' in log
        assert result['nativeWorldBasisPreserved'] and result['independentAnimatedRotations']
        cases[variant] = result
        result = run(p, affine_fixture, consumer_harness)
        log_result('consumers-' + variant, result)
        consumers[variant] = result
        result = run(p, full_fixture(p), full_harness)
        log = log_result('adapter-' + variant, result)
        assert not any('event=' + event in log for event in ('disabled', 'rollback', 'validation_mismatch', 'restore_failed'))
        assert result['writes'] > 0 and result['consumerCount'] == 2 and result['consumerWrites'] == 0
        full[variant] = result
        print('B20-' + variant + ': affine, lifecycle, consumer and full adapter checks passed.', flush=True)

    for kind in ('probe', 'roundtrip', 'arms'):
        p = load(W / 'B20-R.json')
        if kind == 'arms':
            p['armSync'] = True
        else:
            p['attachmentProbe' if kind == 'probe' else 'sceneRoundtrip']['enabled'] = True
        program = full_harness.split('local history={}', 1)[0] + '''
for i=1,4 do runTick()end
check(A.writes==0 and B.writes==0,'conflicting config wrote bones')
for _,u in ipairs(parts)do check(u.writes==0,'conflicting config wrote models')end
check(hasLog('event=disabled stage=config'),'conflicting config not rejected')
return {checks=checks,logs=logs,writes=A.writes}
'''
        result = run(p, full_fixture(p), program)
        log_result('conflicting-' + kind, result)

    # Old B19 source-world rotation and the no-write control remain unchanged.
    for variant in ('0', 'R', 'LR'):
        p = load(OLD / ('B19-' + variant + '.json'))
        new = run(p, full_fixture(p), full_harness)
        old = run(p, full_fixture(p), full_harness, old_source, old_module)
        assert new['history'] == old['history'] and new['writes'] == old['writes']
        log_result('regression-B19-' + variant, new)
        if variant != '0':
            module_result = run(p, affine_fixture, module_harness)
            log_result('regression-module-B19-' + variant, module_result)
            new['affineSourceWorldRegression'] = module_result
        regressions['B19-' + variant] = new

    # Absence of the new feature keeps the original reverse solver unchanged.
    prior = load(P / 'diagnostics/B17/variants/R/profile.json')
    new = run(prior, full_fixture(prior), full_harness)
    old = run(prior, full_fixture(prior), full_harness, old_source, old_module)
    assert new['history'] == old['history'] and new['writes'] == old['writes']
    assert new['protectedRight'] and old['protectedRight']
    source_changed = []
    for chain in prior['armChains']:
        for index in (chain['root'], chain['mid'], chain['hand']):
            actual = new['history'][3][index+1]
            expected = shape(avatar)['localPoses'][index]
            if any(abs(actual[key][i+1] - value) > 1e-7
                   for key in ('p', 'q') for i, value in enumerate(expected[key])):
                source_changed.append(index)
    assert len(source_changed) == 6, source_changed
    log_result('regression-B17', new)
    regressions['B17'] = new
    save_json(W / 'grip-alignment-audit.json', dict(status='PASS', module=cases, fullAdapter=full,
        consumerObservation=consumers, regressions=regressions, oldB19Unchanged=True,
        legacyBehaviorUnchanged=True, legacySourceArmWritesReproduced=source_changed,
        sourceSha256=digest(SRC / 'native_attachments.lua'), moduleSha256=digest(SRC / 'native_grip_alignment.lua'),
        testSha256={name: digest(TEST / name) for name in
                    ('native_grip_alignment_harness.lua', 'native_grip_alignment_adapter_harness.lua',
                     'native_grip_alignment_consumers_harness.lua', 'attachments_layout_harness.lua', 'strict_id32_fixture.lua')},
        gameTested=False, scope='Actual Avatar/model topology, simulated engine matrices and existing consumer links, strict ephemeral IDs.'))
    print('PASS: B20 native-world aiming and telemetry; B19 source-world and B17 legacy regression unchanged.')
    (W / 'failed-runtime.log').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
