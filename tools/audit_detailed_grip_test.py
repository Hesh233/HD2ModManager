"""Historical full regressions plus opt-in three-line test package regressions."""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/grip-rollback-ragdoll-test-20261108-v7'
sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'))
import lz4;sys.modules['utils.lz4_311']=lz4
import audit_test07_sidearm_111 as old
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
from prepare_native_v31_b23 import lua

def main():
 old.OUT=OUT/'legacy-fixtures'
 p,f,h=old.build_111_harness();h=h[:h.rindex('\nreturn {status=')]
 assets=json.loads((OUT/'equipment-fixtures.json').read_text(encoding='utf-8'))
 spec=json.loads((OUT/'verified-component-specs.json').read_text(encoding='utf-8'))
 test_profile=json.loads((OUT/'test01/B23-profile.json').read_text(encoding='utf-8'));config=test_profile['testRepairs'];beacon_spec=test_profile['consumers'][config['beacon']['resource']]
 tests=ROOT/'HD2PhysBoneCompat/test'
 prior=(tests/'native_grip_transfer_test01_weapons_harness.lua').read_text(encoding='utf-8-sig')
 prior=prior[:prior.rindex('\nreturn {status=')]
 # Original real_start also supports stock weapon resources with only boss.
 prior=prior.replace("weaponRoot=gun.names[hash_name('root')];under=", "weaponRoot=gun.names[hash_name('root')] or gun.names[hash_name('boss')];under=")
 h+='\nreturn (function()\nlocal weapon_assets='+lua(assets)+'\nlocal test_component_specs='+lua(spec)+'\nlocal test_beacon_spec='+lua(beacon_spec)+'\nlocal test_repair_configuration='+lua(config)+'\n'+prior+'\n'+(tests/'native_grip_three_line_test_harness.lua').read_text(encoding='utf-8-sig')+'\n'+(tests/'native_grip_beacon_test_harness.lua').read_text(encoding='utf-8-sig')+'\n'+(tests/'native_grip_sg225_aim_test_harness.lua').read_text(encoding='utf-8-sig')+'\n'+(tests/'native_grip_reload_parts_test_harness.lua').read_text(encoding='utf-8-sig')+'\n'+(tests/'native_grip_tracking_test_harness.lua').read_text(encoding='utf-8-sig')+'\n'+(tests/'native_grip_lifecycle_test_harness.lua').read_text(encoding='utf-8-sig')+'\nreturn {status="PASS_PENDING_GAME_TEST",checks=checks,weapons15=result15,logs=logs}\nend)()'
 source=(ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf-8-sig')
 result=plain(run_harness(p,f,h,source=source));logs=result.pop('logs',None)
 if logs:(OUT/'full-runtime-regression.log').write_text('\n'.join(logs),encoding='utf-8')
 controls={}
 for label,broken,expected in [
  ('markerOrientation',source.replace('test.lines and test.lines.handContact','test.lines and false',1),'TEST right consumed weapon marker orientation'),
 ]:
  assert broken!=source
  try:run_harness(p,f,h,source=broken)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing negative control '+label)
 for label,broken_h,expected in [
  ('stockPolicy',h.replace("integratedProfile.leftGrip.weaponTargets[rid].leftPolicy='always'","integratedProfile.leftGrip.weaponTargets[rid].leftPolicy='aim_only'",1),'TEST stock eight-centimetre native intent rejected'),
  ('componentCoverage',h.replace("local partBefore=copy(mag.locals);step(runtime,'render',9200,920)","integratedProfile.consumers['89cce4d15db88aa8']=nil;integratedProfile.allowedConsumers['89cce4d15db88aa8']=nil;local partBefore=copy(mag.locals);step(runtime,'render',9200,920)",1),'TEST AR61 exact magazine not discovered'),
 ]:
  assert broken_h!=h
  try:run_harness(p,f,broken_h,source=source)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing negative control '+label)
 broken=source.replace('row.preserveNative=true','row.preserveNative=false',1)
 assert broken!=source
 try:run_harness(p,f,h,source=broken)
 except Exception as e:
  assert 'TEST beacon attach_weapon native path moved' in str(e),str(e);controls['beaconNativePath']=True
 else:raise AssertionError('Missing beacon native-path negative control')
 for label,broken_h,broken_s,expected in [
  ('sg225Coverage',h.replace("local mag,muzzle=sg_start(row[1],row[2],row[3]);local inputs={}","local mag,muzzle=sg_start(row[1],row[2],row[3]);integratedProfile.consumers[mag.resource]=nil;integratedProfile.allowedConsumers[mag.resource]=nil;local inputs={}",1),source,'TEST SG225 magazine signature not discovered'),
  ('sg225RootProximity',h,source.replace("test and test.sg225Parts and test.sg225Parts.enabled and item.spec.repairFamily=='SG225'",'false',1),'TEST SG225 muzzle root cache stayed detached'),
  ('aimTelemetry',h,source.replace('if not (policy and policy.enabled) then return end','if true then return end',1),'TEST aim camera/roots trace missing'),
 ]:
  assert broken_h!=h or broken_s!=source
  try:run_harness(p,f,broken_h,source=broken_s)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing negative control '+label)
 for label,broken_h,broken_s,expected in [
  ('laserRigidCoverage',h.replace("local part=reload_start(row[1],row[2]);local input=copy(part.locals)","local part=reload_start(row[1],row[2]);if part.resource=='e3541de70b7ec1c0' then integratedProfile.consumers[part.resource]=nil;integratedProfile.allowedConsumers[part.resource]=nil end;local input=copy(part.locals)",1),source,'TEST laser reload module not discovered'),
  ('hmgMultiAnchor',h,source.replace("test and test.reloadParts and test.reloadParts.enabled and item.spec.repairFamily=='HMG_LAS'",'false',1),'TEST HMG multi-anchor cache recovery missing'),
 ]:
  assert broken_h!=h or broken_s!=source
  try:run_harness(p,f,broken_h,source=broken_s)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing negative control '+label)
 broken=source.replace('local policy=test and test.gripTracking','local policy=false',1)
 assert broken!=source
 try:run_harness(p,f,h,source=broken)
 except Exception as e:
  assert 'TEST tracking live gun-frame observation missing' in str(e),str(e);controls['independentGripTracking']=True
 else:raise AssertionError('Missing independent grip-tracking negative control')
 for label,broken,expected in [
  ('lifecycleNoAnimatorGate',source.replace('state.writeAllowed=false','state.writeAllowed=true',1),'TEST lifecycle continued driving no-FSM actor'),
  ('bodyLifecycleTelemetry',source.replace('local policy=test and test.bodyDiagnostics','local policy=false'),'TEST lifecycle weighted body telemetry missing'),
 ]:
  assert broken!=source
  try:run_harness(p,f,h,source=broken)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing negative control '+label)
 result.update(negativeControls=controls,status='PASS_PENDING_GAME_TEST',sourceSha256=hashlib.sha256(source.encode()).hexdigest(),gameTested=False)
 (OUT/'full-runtime-regression.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
