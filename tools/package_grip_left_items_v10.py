"""Publish verified V10 and additive SINGLE observer into isolated test folders only."""
from pathlib import Path
import json,hashlib,zipfile,shutil,sys
from build_grip_left_items_v10 import OUT,BASE,ROOT,VERSION
from build_single_ragdoll_probe_test import OUT as SINGLE
import build_grip_left_items_v10 as grip_builder
import build_single_ragdoll_probe_test as single_builder

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 global OUT,VERSION,SINGLE
 OUT,VERSION=grip_builder.OUT,grip_builder.VERSION;SINGLE=single_builder.OUT
 revision=grip_builder.REVISION
 full=load(OUT/'full-runtime-regression.json');assert full['status']=='PASS_PENDING_GAME_TEST' and len(full['negativeControls'])==(22 if revision>=12 else 20 if revision==11 else 16) and all(full['negativeControls'].values())
 assert full['sourceSha256']==hashlib.sha256((ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf-8-sig').encode()).hexdigest()
 checks=load(OUT/'package-readback-validation.json');chef=load(OUT/'entry-chef-validation.json');single=load(SINGLE/'observer-validation.json');singleChef=load(SINGLE/'chef-observer-validation.json');assert single['status']=='PASS_PENDING_GAME_TEST' and singleChef['status']=='PASS' and singleChef['poseWrites']==0
 rows=load(OUT/'build-report.json');sr=load(SINGLE/'build-report.json');assert sha(Path(sr['package']))==sr['sha256'] and singleChef['sourceSha256']==sr['luaSha256']
 protected={}
 for p in [BASE/'config.toml',BASE/'settings.json',BASE/'test-library/library.json',BASE/'test-library/profiles.json']+[Path(p) for p in sr['originalInputs']]:
  if p.is_file():protected[str(p)]=sha(p)
 for path in sr['originalInputs']:
  for suffix in ('.gpu_resources','.stream'):
   file=Path(path+suffix)
   if file.is_file():protected[str(file)]=sha(file)
 for row in rows:
  assert row['sha256']==sha(Path(row['package']))
  assert row['luaSha256']==next(v['luaSha256'] for v in checks['packages']if v['model']==row['model'])==next(v['sourceSha256'] for v in chef['entries']if v['model']==row['model'])
  folder=OUT/row['model'];shutil.copyfile(OUT/'assembly'/row['model']/'native-parenting.json',folder/'native-parenting.json')
  with zipfile.ZipFile(row['package'])as z:
   for name in ('attachment-fix.json','attachment-profile.json'):(folder/name).write_bytes(z.read(name))
  for suf in ('','.gpu_resources','.stream'):
   f=BASE/f"test-library/[骨骼挂点修正]{row['model']}/9ba626afa44a3aa3.patch_1{suf}";protected[str(f)]=sha(f)
 doc=ROOT/('docs/grip-left-items-v12-and-single-probe-s3-20261109.md' if revision>=12 else 'docs/grip-left-items-v11-and-single-probe-s2-20261109.md' if revision==11 else 'docs/grip-left-items-v10-and-single-probe-20261109.md')
 toolkit=OUT/(f'Lua测试源码与验证记录-V12及单骨骼S3防崩溃诊断.zip' if revision>=12 else 'Lua测试源码与验证记录-V11及单骨骼S2只读诊断.zip' if revision==11 else 'Lua测试源码与验证记录-V10及单骨骼布娃娃只读诊断.zip')
 with zipfile.ZipFile(toolkit,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  z.write(doc,'使用说明.md')
  for folder in (OUT/'test01',OUT/'test06'):
   for p in folder.iterdir():
    if p.is_file() and not p.name.startswith('chef-readback-'):z.write(p,'双骨骼重打包/'+folder.name+'/'+p.name)
   z.write(ROOT/'tools/repack_native_b23.py','双骨骼重打包/'+folder.name+'/repack.py')
  for name in ('build-report.json','full-runtime-regression.json','package-readback-validation.json','entry-chef-validation.json','component-provenance.json','throwables.json','verified-component-specs.json','equipment-fixtures.json'):z.write(OUT/name,'双骨骼验证与fixture/'+name)
  for name in ('observer-entry.lua','single-observer-profile.json','build-report.json','observer-validation.json','chef-observer-validation.json','测试说明.md'):z.write(SINGLE/name,'单骨骼额外观测/'+name)
  for name in ('native_grip_transfer_test.lua','native_grip_transfer_test_entry.lua','single_ragdoll_probe_test.lua'):z.write(ROOT/'HD2PhysBoneCompat/src'/name,'源码/运行时/'+name)
  for name in (('native_grip_left_items_v10_harness.lua','native_grip_equipment_v9_harness.lua','native_grip_left_items_v11_harness.lua')+ (('native_grip_left_items_v12_harness.lua',) if revision>=12 else ()) if revision>=11 else ('native_grip_left_items_v10_harness.lua','native_grip_equipment_v9_harness.lua')):z.write(ROOT/'HD2PhysBoneCompat/test'/name,'源码/测试/'+name)
  for name in ('build_grip_left_items_v10.py','audit_grip_left_items_v10.py','validate_grip_left_items_v10.py','build_single_ragdoll_probe_test.py','verify_single_ragdoll_probe_test.py','verify_single_ragdoll_chef_test.py'):z.write(ROOT/'tools'/name,'源码/工具/'+name)
  z.write(ROOT/'outputs/grip-left-items-analysis-20261109/latest-v9-analysis.json','原日志分析/latest-v9-analysis.json')
  if revision>=12:
   z.write(ROOT/'outputs/grip-left-items-analysis-20261109/v12/v11-followup-analysis.json','原日志分析/v11-followup-analysis.json')
   z.write(ROOT/'outputs/grip-left-items-analysis-20261109/v12/s2-native-crash-analysis.json','原日志分析/s2-native-crash-analysis.json')
  if revision>=11:
   z.write(ROOT/'outputs/grip-left-items-analysis-20261109/live-v10-and-s1-analysis.json','原日志分析/live-v10-and-s1-analysis.json')
   z.write(ROOT/'tools/analyze_left_items_and_single_live.py','源码/工具/analyze_left_items_and_single_live.py')
 dest=BASE/'测试包/左手与随身装备修复-测试用低负载日志-1.0.18-v10';singleDest=BASE/'测试包/test01单骨骼布娃娃额外观测-测试用详细只读-1.0.0-s1'
 old_delivery={}
 if revision>=11:
  assert dest.is_dir() and singleDest.is_dir(),'Reuse existing delivery directories; do not create a new release directory'
  for folder in (dest,singleDest):
   for file in folder.iterdir():
    if file.is_file() and not file.name.startswith((f'V{revision}-',('S3-' if revision>=12 else 'S2-'),f'grip-left-items-v{revision}-')) and f'items.{revision}' not in file.name and ('single-ragdoll.3' if revision>=12 else 'single-ragdoll.2') not in file.name and f'V{revision}及' not in file.name:
     old_delivery[str(file)]=sha(file)
 previous=load(OUT/'delivery-validation.json') if (OUT/'delivery-validation.json').exists() else {}
 known={r['path']:r['sha256'] for r in previous.get('published',[])}
 published=[]
 for targetDir,files in ((dest,[Path(r['package'])for r in rows]+[toolkit,doc,OUT/'full-runtime-regression.json',OUT/'package-readback-validation.json']),(singleDest,[Path(sr['package']),SINGLE/'测试说明.md',SINGLE/'observer-validation.json',SINGLE/'chef-observer-validation.json'])):
  targetDir.mkdir(parents=True,exist_ok=True)
  for source in files:
   if source.suffix=='.zip':
    with zipfile.ZipFile(source)as z:assert z.testzip()is None
   name=source.name
   if revision>=11 and source.suffix!='.zip' and source!=doc:
    name=(('S3-' if revision>=12 else 'S2-') if targetDir==singleDest else f'V{revision}-')+name
   target=targetDir/name
   if target.exists() and sha(target)!=sha(source):
    assert sha(target)==known.get(str(target)),'refusing to overwrite unrelated delivery'
    shutil.copyfile(source,target)
   elif not target.exists():shutil.copyfile(source,target)
   assert sha(source)==sha(target);published.append(dict(path=str(target),sha256=sha(target),bytes=target.stat().st_size))
 for p,h in protected.items():assert sha(Path(p))==h
 for p,h in old_delivery.items():assert sha(Path(p))==h,'Old V10/S1 delivery changed'
 report=dict(status='PASS_PENDING_GAME_TEST',version=VERSION,runtimeChecks=full['checks'],negativeControls=len(full['negativeControls']),singleObserverPoseWrites=0,oldDeliveryFilesPreserved=old_delivery,protectedInputsUnchanged=protected,published=published,gameDeployed=False,gameTested=False,modelRebaked=False,animationRebaked=False,singleRagdollFixed=False)
 (OUT/'delivery-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items()if k!='protectedInputsUnchanged'},ensure_ascii=False,indent=2))
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,choices=(10,11,12),default=10);args=parser.parse_args()
 grip_builder.configure_revision(args.revision);single_builder.configure_revision('s3' if args.revision>=12 else 's2' if args.revision==11 else 's1')
 sys.stdout.reconfigure(encoding='utf-8');main()
