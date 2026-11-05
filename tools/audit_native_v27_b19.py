"""Verify real topology, one-way ownership, affine math and exclusive routing."""
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

W = ROOT / 'outputs/native-v27-b19-20261105'
P = ROOT / 'outputs/native-manual-20261103/project'
SRC = ROOT / 'HD2PhysBoneCompat/src'
TEST = ROOT / 'HD2PhysBoneCompat/test'


def main():
    avatar = next(iter(units(P / 'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    models = units(P / 'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    source = (SRC / 'native_attachments.lua').read_text(encoding='utf-8')
    module = (SRC / 'native_grip_alignment.lua').read_text(encoding='utf-8')
    strict = (TEST / 'strict_id32_fixture.lua').read_text(encoding='utf-8')
    module_harness = (TEST / 'native_grip_alignment_harness.lua').read_text(encoding='utf-8').replace('-- STRICT_ID_FIXTURE', strict)
    prefix = (TEST / 'attachments_layout_harness.lua').read_text(encoding='utf-8').split('check(armor.nodes~=A.nodes', 1)[0]
    prefix = prefix.replace('local runtime=adapter.new', strict + '\nlocal runtime=adapter.new')
    full_harness = prefix + (TEST / 'native_grip_alignment_adapter_harness.lua').read_text(encoding='utf-8')
    def run(profile, fixture, program, adapter_source=source):
        vm = LuaRuntime(unpack_returned_tuples=True)
        def quat(matrix):
            cols = [[matrix[i] for i in range(c, c + 3)] for c in (1, 4, 7)]
            cols = [[v / math.sqrt(sum(x*x for x in col)) for v in col] for col in cols]
            return vm.table_from(matrix3_columns_to_quaternion(cols))
        vm.globals().quat_from_matrix = quat
        vm.globals().adapter = vm.execute(adapter_source)
        vm.globals().module = vm.execute(module)
        vm.globals().fixture = vm.table_from(fixture, recursive=True)
        vm.globals().profile = vm.table_from(profile, recursive=True)
        vm.globals().hash_name = bone_name_hash
        return plain(vm.execute(program))
    def log_result(name, result):
        log = '\n'.join(result.pop('logs').values())
        (W / (name + '.log')).write_text(log, encoding='utf-8')
        return log
    cases, full = {}, {}
    for variant in ('R', 'LR'):
        p = load(W / ('B19-' + variant + '.json'))
        fixture = dict(hashes=avatar.name_hashes, parents=[0 if x is None else x+1 for x in avatar.parents], matrices=[raw(t) for t in avatar.transforms])
        result = run(p, fixture, module_harness)
        log = log_result('module-' + variant, result)
        assert 'event=rollback avatar=1 verified=true' in log
        assert 'post_refresh_target_overwritten' in log
        cases[variant] = result
    for variant in ('0', 'R', 'LR'):
        p = load(W / ('B19-' + variant + '.json'))
        fixture = dict(avatar=shape(avatar), models={r: shape(models[r]) for r in p['modelLayouts']})
        result = run(p, fixture, full_harness)
        log = log_result('adapter-' + variant, result)
        assert not any('event=' + event in log for event in ('disabled', 'rollback', 'validation_mismatch', 'restore_failed'))
        assert (result['writes'] == 0) == (variant == '0')
        full[variant] = result
    # A conflicting configuration must fail closed across the entire adapter,
    # including diagnostic writers outside the normal attachment branch.
    for kind in ('probe', 'roundtrip', 'arms'):
        p = load(W / 'B19-R.json')
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
        result = run(p, fixture, program)
        log_result('conflicting-' + kind, result)
    # With no new configuration, the existing B17 behavior must be identical.
    prior = load(P / 'diagnostics/B17/variants/R/profile.json')
    fixture = dict(avatar=shape(avatar), models={r: shape(models[r]) for r in prior['modelLayouts']})
    new = run(prior, fixture, full_harness)
    old = run(prior, fixture, full_harness, (W / 'baseline/native_attachments.lua').read_text(encoding='utf-8-sig'))
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
    save_json(W / 'grip-alignment-audit.json', dict(status='PASS', module=cases, fullAdapter=full,
        legacyBehaviorUnchanged=True, legacySourceArmWritesReproduced=source_changed,
        sourceSha256=digest(SRC / 'native_attachments.lua'), moduleSha256=digest(SRC / 'native_grip_alignment.lua'),
        gameTested=False, scope='Real exported topology with simulated engine matrices, cached model graphs, and strict ephemeral ID tokens.'))
    print('PASS: affine alignment, 61 continuous frames, read-only Source bones, faults, lifecycle, 11 model graphs, conflicts, and unchanged legacy behavior.')


if __name__ == '__main__':
    main()
