"""Publish already-verified TEST packages; never imports, enables or deploys."""
from pathlib import Path
import json,hashlib,zipfile,shutil
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/grip-equipment-perf-test-20261108-v9';BASE=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 report=json.loads((OUT/'full-runtime-regression.json').read_text(encoding='utf-8'))
 assert report['sourceSha256']==hashlib.sha256((ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest()
 assert report['status']=='PASS_PENDING_GAME_TEST' and set(report['negativeControls'])=={'markerOrientation','stockPolicy','componentCoverage','beaconNativePath','sg225Coverage','sg225RootProximity','aimTelemetry','laserRigidCoverage','hmgMultiAnchor','independentGripTracking','lifecycleNoAnimatorGate','bodyLifecycleTelemetry','sourceFkRefresh','jarForegripRoot'}
 verified=json.loads((OUT/'package-readback-validation.json').read_text(encoding='utf-8'));assert verified['status']=='PASS_PENDING_GAME_TEST'
 entries=json.loads((OUT/'entry-chef-validation.json').read_text(encoding='utf-8'));assert entries['status']=='PASS_PENDING_GAME_TEST'
 rows=json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
 for row in rows:
  assert row['sha256']==sha(row['package'])
  assert row['luaSha256']==next(r['luaSha256'] for r in verified['packages'] if r['model']==row['model'])
  assert row['luaSha256']==next(r['sourceSha256'] for r in entries['entries'] if r['model']==row['model'])
 # Protect actual configuration and existing production companion packages.
 protected=[BASE/'settings.json',BASE/'config.toml',BASE/'test-library/library.json',BASE/'test-library/profiles.json']
 for name in ('test01','test06'):
  protected+=list((BASE/f'test-library/[骨骼挂点修正]{name}').glob('*.patch_*'))
  protected+=[BASE/f'test-library/[骨骼挂点修正]{name}/attachment-profile.json',BASE/f'test-library/[原比例模型]{name}/vpk2patch/source-skeleton.json']
 before={str(p):sha(p) for p in protected if p.is_file()}
 doc=(ROOT/'docs/grip-equipment-perf-test-20261108-v9.md').read_text(encoding='utf-8-sig')
 (OUT/'测试用低负载日志版-使用说明.md').write_text(doc,encoding='utf-8')
 toolkit=OUT/'Lua测试工具与重打包工程-1.0.18-test.performance.9.zip'
 with zipfile.ZipFile(toolkit,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  z.writestr('使用说明.md','本合集是源码/重打包工程，不要直接导入管理器。安装测试请使用单独的test01或test06测试ZIP。\n\n'+doc)
  for name in ('test01','test06'):
   for part in ('vpk','overwrite'):
    source=ROOT/f'outputs/grip-ragdoll-followup-20261108/{name}-skin-{part}.json'
    z.write(source,'实际蒙皮骨审计/'+source.name)
   folder=OUT/name
   for file in folder.iterdir():
    if file.is_file() and file.name!='测试用详细日志版说明.md' and not file.name.startswith('chef-readback-'):z.write(file,f'{name}/{file.name}')
   z.write(ROOT/'tools/repack_native_b23.py',f'{name}/repack.py')
  for file in ('full-runtime-regression.json','package-readback-validation.json','build-report.json','component-provenance.json','entry-chef-validation.json'):
   z.write(OUT/file,'验证记录/'+file)
  for file in ('native_grip_three_line_test_harness.lua','native_grip_beacon_test_harness.lua','native_grip_sg225_aim_test_harness.lua','native_grip_reload_parts_test_harness.lua','native_grip_tracking_test_harness.lua','native_grip_lifecycle_test_harness.lua','native_grip_source_fk_test_harness.lua','native_grip_equipment_v9_harness.lua'):
   z.write(ROOT/'HD2PhysBoneCompat/test'/file,'仓库生成与测试源码/测试/'+file)
  for file in ('native_grip_transfer_test.lua','native_grip_transfer_test_entry.lua'):
   z.write(ROOT/'HD2PhysBoneCompat/src'/file,'仓库生成与测试源码/运行时/'+file)
  for file in ('single-ragdoll-audit.json','v8-equipment-analysis.json','new-equipment-fixtures.json'):
   z.write(ROOT/'outputs/grip-equipment-followup-20261108'/file,'审计证据/'+file)
  for file in ('build_detailed_grip_test.py','audit_detailed_grip_test.py','validate_detailed_grip_test.py','verify_grip_equipment_v9_entry.py'):
   z.write(ROOT/'tools'/file,'仓库生成与测试源码/'+file)
 with zipfile.ZipFile(toolkit) as z:assert z.testzip() is None
 dest=BASE/'测试包/握持装备追加修复-测试用低负载日志-1.0.18-v9'
 dest.mkdir(parents=True,exist_ok=True)
 files=[Path(r['package']) for r in json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))]+[toolkit,OUT/'测试用低负载日志版-使用说明.md']
 published=[]
 for source in files:
  target=dest/source.name
  if target.exists():assert sha(target)==sha(source),'Refusing to replace an independently changed delivery file'
  else:shutil.copyfile(source,target)
  assert sha(source)==sha(target);published.append(dict(path=str(target),sha256=sha(target),bytes=target.stat().st_size))
 after={str(p):sha(p) for p in protected if p.is_file()};assert before==after
 result=dict(status='PASS_PENDING_GAME_TEST',version='1.0.18-test.performance.9',runtimeChecks=report['checks'],negativeControls=report['negativeControls'],published=published,
   protectedInputsUnchanged=before,modelRebaked=False,animationRebaked=False,productionManagerUpdated=False,gameDeployed=False,gameTested=False)
 (OUT/'delivery-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='protectedInputsUnchanged'},ensure_ascii=False,indent=2))
if __name__=='__main__':import sys;sys.stdout.reconfigure(encoding='utf-8');main()
