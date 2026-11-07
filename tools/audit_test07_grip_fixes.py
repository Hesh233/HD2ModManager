"""Regress test07 fixes using existing 1.0.7/1.0.8 harnesses, never deploy/rebake."""
import copy,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
from prepare_native_v31_b23 import lua
from anim_batch_mod.native_config import apply_grip_fixes
OUT=ROOT/'outputs/test07-grip-fix-20261106'

def build_harness():
    project=ROOT/'projects/test01-native-grip'
    with zipfile.ZipFile(project/'inputs/baseline-1.0.7.zip') as z:
        profile=json.loads(z.read('B23-profile.json').decode('utf-8-sig'))
        fixture=json.loads(z.read('runtime-fixture.json').decode('utf-8-sig'))
        harness=z.read('test/native_grip_transfer_harness.lua').decode('utf-8-sig').replace(
            '-- STRICT_ID_FIXTURE',z.read('test/strict_id32_fixture.lua').decode('utf-8-sig'))
    candidate=json.loads((project/'config/B23-profile.json').read_text(encoding='utf-8-sig'))
    components=json.loads((project/'inputs/components.json').read_text(encoding='utf-8-sig'))
    fixes=apply_grip_fixes(copy.deepcopy(candidate),version='test07-1.0.10')
    # Freeze the historical diagnostic fixture; compact logging has its own sink/format tests.
    fixes['logging']=dict(compact=False)
    fixes['logSeconds']=1.
    if fixes.get('sidearmDiagnostics'):fixes['sidearmDiagnostics']=dict(fixes['sidearmDiagnostics'],intervalSeconds=1.,maxSamplesPerPath=180)
    newcomponents=json.loads((OUT/'component-fixtures.json').read_text(encoding='utf-8-sig'))
    test=ROOT/'HD2PhysBoneCompat/test'
    extension=(test/'native_grip_transfer_108_harness.lua').read_text(encoding='utf-8-sig')
    extension=extension[:extension.rindex('\nreturn {status=')]
    harness=harness[:harness.rindex('\nreturn {integratedCases=')]
    harness+='\nlocal candidate_profile='+lua(candidate)+'\nlocal candidate_components='+lua(components)+'\n'+extension
    harness+='\nlocal grip_fixed_profile='+lua(fixes)+'\nlocal test07_components='+lua(newcomponents)+'\n'+(test/'native_grip_transfer_test07_harness.lua').read_text(encoding='utf-8-sig')
    return profile,fixture,harness

def main():
    profile,fixture,harness=build_harness()
    result=plain(run_harness(profile,fixture,harness));logs=result.pop('logs')
    (OUT/'runtime-regression.log').write_text('\n'.join(logs),encoding='utf-8')
    (OUT/'runtime-regression.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    return result
if __name__=='__main__':main()
