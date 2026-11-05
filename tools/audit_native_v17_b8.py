"""B8 local-write contract and disabled-profile regressions on real layouts."""
import copy
import json
import os
import sys
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
sys.path.insert(0,os.environ['HD2_LUA_TEST_RUNTIME'])
from lupa.lua51 import LuaRuntime
from audit_native_attachment_layouts import units,shape,plain
from native_model_arm_locals import with_model_arm_locals
from anim_batch_mod.native_skeleton import bone_name_hash

W=ROOT/'outputs/native-v17-20261104'
P=ROOT/'outputs/native-manual-20261103/project'


def main():
    profile=load(W/'B8.json');control=load(P/'diagnostics/B7/B7.json')
    models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    generated=with_model_arm_locals(control,avatar,models);generated['revision']=profile['revision']
    assert generated==profile
    fixture=dict(avatar=shape(avatar),models={r:shape(models[r])for r in profile['modelLayouts']})
    base=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    prefix=base.split('check(armor.nodes~=A.nodes',1)[0]
    direct=(ROOT/'HD2PhysBoneCompat/test/model_arm_local_harness.lua').read_text(encoding='utf-8')
    current=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    before=(P/'diagnostics/B7/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    coverage=load(ROOT/'outputs/native-v16-20261104/consumer-coverage.json')['rows']
    weighted={r['resource']:next(n['name']for n in r['armWeights']if n['name'].endswith('_hand'))
              for r in coverage if r['part'].startswith(('LeftArm/','RightArm/'))}
    def run(source,program,p=profile,measure=False):
        vm=LuaRuntime(unpack_returned_tuples=True)
        vm.globals().adapter=vm.execute(source)
        vm.globals().profile=vm.table_from(p,recursive=True)
        vm.globals().fixture=vm.table_from(fixture,recursive=True)
        vm.globals().hash_name=bone_name_hash
        vm.globals().weighted_hand_resources=vm.table_from(weighted)
        vm.globals().measureOnly=measure
        return plain(vm.execute(program))
    result=run(current,prefix+direct)
    old_errors=run(before,prefix+direct,measure=True)
    assert old_errors['d154442f2e33fdee']>.01 and old_errors['e0b67b19ba91057b']>.01
    try:run(before,prefix+direct)
    except Exception as e:assert 'direct model local writes missing' in str(e),str(e)
    else:raise AssertionError('B7 unexpectedly satisfied the direct local-write contract')
    split=(ROOT/'HD2PhysBoneCompat/test/split_model_refresh_harness.lua').read_text(encoding='utf-8')
    unchanged=run(current,prefix+split,control)
    assert unchanged==run(before,prefix+split,control),'B7 disabled path changed'
    legacy=load(ROOT/'outputs/native-v12-20261104/project/attachment-profile.json')
    legacy['protectControllerParents']=False
    lifecycle=run(current,base,legacy)
    assert lifecycle==run(before,base,legacy),'legacy lifecycle changed'
    # Serialized topology, not a mocked name alone, authorizes local copying.
    resource='d154442f2e33fdee'
    wrong=copy.deepcopy(models)
    row=profile['modelArmLocalLayouts'][resource][0]
    wrong[resource].parents[row['index']]=0
    try:with_model_arm_locals(control,avatar,wrong)
    except ValueError as e:assert 'different parents' in str(e)
    else:raise AssertionError('Different serialized parent accepted')
    result.update(status='PASS',gameTested=False,profileMatchesSerializedUnits=True,
        parentMismatchRejected=True,B7DirectWriteOmissionReproduced=True,
        B7LocalMatrixErrors=old_errors,disabledB7Regression=unchanged,legacyLifecycle=lifecycle,
        sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'))
    save_json(W/'model-arm-local-audit.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
