"""Incremental regressions with real AR-11/P-92 signatures and negative controls."""
import json,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from audit_test07_sidearm_111 import build_111_harness
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
from prepare_native_v31_b23 import lua
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
REPORT='日志缩减-1.0.17'
def main():
 p,f,h=build_111_harness()
 assets=json.loads((TARGET/'test01-武器修正-资源审计.json').read_text(encoding='utf8'))
 assets={u['resource']:u for us in assets.values() for u in us}
 h=h[:h.rindex('\nreturn {status=')]
 h+='\nreturn (function()\nlocal weapon_assets='+lua(assets)+'\n'+(ROOT/'HD2PhysBoneCompat/test/native_grip_transfer_test01_weapons_harness.lua').read_text(encoding='utf-8-sig')+'\nend)()'
 s=(ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf8')
 r=plain(run_harness(p,f,h,source=s));logs=r.pop('logs')
 (TARGET/(REPORT+'-Lua测试.log')).write_text('\n'.join(logs),encoding='utf8')
 controls={}
 for name,old,new,expected in [('p92Reach','fixes.reachableRightIK and fixes.reachableRightIK[sidearm.resource]','false','unreachable P92 correction not applied'),('probeBudget','state.counted=false','state.counted=false;self.probeCount[path]=count+1','empty weapon observations consumed budget'),('rangeRetry','if recoverable and safe then','if false then','final mount excursion permanently disabled runtime'),('rangeRefresh','if requireRefresh then','if false then','range restore consumer refresh failure was swallowed')]:
  broken=s.replace(old,new,1);assert broken!=s
  try:run_harness(p,f,h,source=broken)
  except Exception as e:
   assert expected in str(e),str(e);controls[name]=True
  else:raise AssertionError('Missing negative control '+name)
 # Remove only the real underbarrel signature in this VM, not on disk.
 broken_h=h.replace(' new_start(rid)', " new_start(rid);integratedProfile.consumers['b9c209b4f99b5335']=nil;integratedProfile.allowedConsumers['b9c209b4f99b5335']=nil",1)
 assert broken_h!=h
 try:run_harness(p,f,broken_h,source=s)
 except Exception as e:
  assert 'AR11 actual attached shotgun was not selected' in str(e),str(e);controls['missingUnderbarrelSignature']=True
 else:raise AssertionError('Missing underbarrel negative control')
 r.update(luaVersion='1.0.17',negativeControls=controls,sourceSha256=hashlib.sha256(s.encode()).hexdigest(),gameTested=False)
 (TARGET/(REPORT+'-Lua验证.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(r,ensure_ascii=False))
if __name__=='__main__':main()
