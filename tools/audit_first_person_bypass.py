"""Full prior grip suites plus FP bypass; all outputs reuse the fixed manager folder."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from audit_test07_sidearm_111 import build_111_harness
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def main():
 profile,fixture,harness=build_111_harness()
 harness=harness[:harness.rindex('\nreturn {status=')]
 # The production guard runs in the SAME VM/strict temporary-ID fixture.
 guard=(ROOT/'HD2PhysBoneCompat/src/native_first_person_guard.lua').read_text(encoding='utf-8-sig')
 extra=(ROOT/'HD2PhysBoneCompat/test/native_grip_first_person_harness.lua').read_text(encoding='utf-8-sig').replace('local fpGuardModule=fp_guard_module','local fpGuardModule=__fp_guard_module')
 harness+='\n__fp_guard_module=(function()\n'+guard+'\nend)()\nreturn (function()\n'+extra+'\nend)()'
 source=(ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf-8-sig')
 # Negative control lives only in a Lua VM: remove body-cache refresh, retaining
 # all pose bypass logic, and prove that the new moving-cache test catches it.
 negative=harness[:harness.index('-- The graph may live in a mirrored FP World')]+harness[harness.index('-- Reproduce the missing lifecycle'):]
 broken=source.replace('identity(item);W.update_unit(item.world,item.unit)',
  "identity(item);if kind~='model' then W.update_unit(item.world,item.unit) end",1)
 assert broken!=source
 try:run_harness(profile,fixture,negative,source=broken)
 except Exception as e:
  assert 'FP body receiver frozen in world space' in str(e),str(e)
 else:raise AssertionError('Moving body-cache regression did not detect missing receiver refresh')
 r=plain(run_harness(profile,fixture,harness,source=source));logs=r.pop('logs')
 r.update(luaVersion='1.0.13',sourceSha256=hashlib.sha256(source.encode()).hexdigest(),
  missingBodyRefreshNegativeControlDetected=True)
 (TARGET/'第一人称门禁-Lua测试.log').write_text('\n'.join(logs),encoding='utf-8')
 (TARGET/'第一人称门禁-Lua验证.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
