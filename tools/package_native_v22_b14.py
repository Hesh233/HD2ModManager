"""Reuse verified incremental delivery, retiring B13 for temporary-ID misuse."""
import sys
from pathlib import Path
source=Path(__file__).with_name('package_native_v21_b13.py').read_text(encoding='utf-8')
for old,new in (
    ('native-v21-b13-20261104','native-v22-b14-20261104'),
    ('v21-b13-before-20261104','v22-b14-before-20261104'),
    ('native-v21','native-v22'),
    ('native-v20','native-v21'),
    ('v21-B13','v22-B14'),
    ('B13','B14'),('b13','b14'),
    ('B12','B13'),('b12','b13'),
):
    source=source.replace(old,new)
source=source.replace('assert len(retired)==4','assert len(retired)==5')
source=source.replace("'retired-native-crash'","'retired-id-lifetime'")
source=source.replace("gameTested=group['group']!='B13-ALL'", "gameTested=group['group']=='B13-0'")
source=source.replace("result='A/B crashed before displacement; ALL shares defective numeric-ID path and is withdrawn.'",
    "result='B13-0 did not crash but disabled at first name query; cached temporary IDs affect all variants.'")
source=source.replace("report['priorUserResults']['B13']='A and B crashed; three matching native AVs before displacement.'",
    "report['priorUserResults']['B13-0']='No crash and clean exit, but probe disabled on boss_aim before validation completed.'")
source=source.replace("'id32-contract-audit.json','chef-compatibility-audit.json'", "'id32-contract-audit.json','id32-lifetime-audit.json','chef-compatibility-audit.json'")
source=source.replace("'analyze_native_b13_crashes.py'", "'analyze_native_b13_zero.py'")
# Include the wrapper dependencies without changing their real filenames.
source=source.replace("toolnames=[", "toolnames=['prepare_native_v21_b13.py','audit_native_v21_b13.py','audit_native_v21_b13_chef.py','package_native_v21_b13.py','audit_native_v20_b12.py','audit_native_v20_b12_chef.py',")
source=source.replace('native_v21_b14','native_v22_b14')
source=source.replace('native_v20_b13','native_v21_b13')
source=source.replace("retired='B13 A/B/ALL and source archive moved intact to backup'", "retired='B13 0/A/B/ALL and source archive moved intact to backup'")
source=source.replace('strict ID regression, four imports', 'strict ID and frame-lifetime regression, four imports')
# Deliver always requires actual successful imports, including exact package SHA.
source=source.replace("    report=load(W/'package-report.json');assert report['revision']=='native-v22'",
    "    assert load(W/'package-inspection.json')['status']=='PASS'\n    report=load(W/'package-report.json');assert report['revision']=='native-v22'")
if len(sys.argv)>1 and sys.argv[1]=='prepare-offline':
    sys.argv[1]='prepare'
    source=source.replace("'package-inspection.json']", "]")
    source=source.replace("    imported={r['package']:r['sha256'] for r in load(W/'package-inspection.json')['packages']}", "    imported={r['name']:r['sha256'] for r in load(W/'static-packages.json')}")
    source=source.replace("report.update(revision='native-v22'", "report.update(validationStage='offline-ready-import-pending',revision='native-v22'")
    source=source.replace('four imports', 'isolated imports pending')
# Repack code is standalone, kept beside this wrapper and in delivered diagnostics.
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
