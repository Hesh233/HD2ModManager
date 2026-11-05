"""Wait for this isolated build, then verify it with the published runtime."""
import json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v6-20261104'
while True:
    try:report=json.loads((W/'project/animations/build-report.json').read_text(encoding='utf-8'))
    except json.JSONDecodeError:time.sleep(1);continue
    if report['status']=='failed':raise RuntimeError(report.get('error','animation build failed'))
    if report['status']=='complete':break
    time.sleep(10)
python=W/'manager/anim_batch_mod/runtime/python.exe'
for name,log in [('audit_native_v6_animations.py','animation-final-audit.log'),('check_published_native_v6.py','published-generator-audit.log')]:
    print('Running',name,flush=True)
    with (W/log).open('w',encoding='utf-8') as output:
        subprocess.run([str(python),'-X','utf8',str(ROOT/'tools'/name)],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)
    print('Passed',name,flush=True)
