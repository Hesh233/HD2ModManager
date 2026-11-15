"""Reuse historical TP/FP suites in new evidence directories; never overwrite prior reports."""
from pathlib import Path
import argparse, hashlib, inspect, json, shutil, sys
import build_detailed_grip_test as b
from build_first_person_source_test import ROOT,OUT,VERSION

def main(argv=None):
 global OUT
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--full',action='store_true');parser.add_argument('--out',type=Path,default=OUT);args=parser.parse_args(argv);OUT=args.out.resolve()
 old=ROOT/'outputs/grip-left-items-test-20261109-v10/v12';tp=OUT/'legacy-tp-regression';tp.mkdir(parents=True,exist_ok=True)
 for name in ('equipment-fixtures.json','verified-component-specs.json','throwables.json','test01/B23-profile.json','test06/B23-profile.json'):
  target=tp/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/name,target)
 import build_grip_left_items_v10 as builder
 import audit_grip_left_items_v10 as tp_audit
 builder.configure_revision(12);builder.OUT=tp
 previous_argv=sys.argv;sys.argv=['a2-historical-regression']+([] if args.full else ['--quick'])
 tp_audit.main();sys.argv=previous_argv
 tp_report=b.load(tp/('full-runtime-regression.json' if args.full else 'quick-runtime-regression.json'))
 import audit_first_person_bypass as fp_audit
 import audit_test07_sidearm_111 as old_fixture
 fp=OUT/'legacy-fp-regression';fp.mkdir(parents=True,exist_ok=True);old_fixture.OUT=fp/'fixtures';old_fixture.OUT.mkdir(parents=True,exist_ok=True)
 fn=inspect.getsource(fp_audit.main)
 needle=' r=plain(run_harness(profile,fixture,harness,source=source));logs=r.pop(\'logs\')'
 extra=''' wrong=source.replace("actualVisible>0 and 'fp_arm_source_receiver_visible' or 'fp_arm_source_receiver_not_visible'", "'fp_arm_source_receiver_visible'",1)
 assert wrong!=source
 try:run_harness(profile,fixture,harness,source=wrong)
 except Exception as e:assert 'all-hidden source receiver falsely reported visible' in str(e),str(e)
 else:raise AssertionError('All-hidden visibility negative control not detected')
'''
 assert needle in fn;fn=fn.replace(needle,extra+needle,1)
 env=dict(fp_audit.__dict__);env['TARGET']=fp;exec(compile(fn,'<a2-historical-fp>','exec'),env);env['main']()
 fp_report=b.load(fp/'第一人称门禁-Lua验证.json');fp_report.update(allHiddenMaskFalseVisibleNegativeControlDetected=True,testedSharedTransferVersion='1.0.17',historicalSuiteLabelNotFpModuleVersion=True)
 (fp/'第一人称门禁-Lua验证.json').write_text(json.dumps(fp_report,ensure_ascii=False,indent=2),encoding='utf-8')
 normalized=(ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf-8-sig').encode();assert hashlib.sha256(normalized).hexdigest()==tp_report['sourceSha256']==fp_report['sourceSha256'],'Tested transfer source changed during regression'
 report=dict(testedNormalizedTransferSha256=tp_report['sourceSha256'],status='PASS_PENDING_GAME_TEST',testVersion=VERSION,tpChecks=tp_report['checks'],tpNegativeControls=tp_report.get('negativeControls',{}),tpNegativeControlsNotRun=tp_report.get('negativeControlsNotRun',False),fpChecks=fp_report['checks'],fpNegativeControls=3,fpAllHiddenMaskObserved=fp_report['firstPerson']['allHiddenMeshMaskReportedNotVisible'],tpMeleeCaptureVerified=tp_report['weapons15']['leftItemsV12']['a2MeleeNativeAndSourceCapture'],sourceSha256=hashlib.sha256((ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_bytes()).hexdigest(),historicalOutputsNotOverwritten=True,gameDeployed=False,gameTested=False)
 (OUT/'historical-regression-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
