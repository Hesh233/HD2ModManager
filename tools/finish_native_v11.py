"""Complete the authorized local v11 release after its animation build."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v11-20261104'
def status(stage,**extra):
    (W/'finish-status.json').write_text(json.dumps(dict(stage=stage,**extra),indent=2),encoding='utf-8')
    print(stage,flush=True)
def run(stage,script,*args):
    status(stage)
    with (W/(stage+'.log')).open('w',encoding='utf-8') as out:
        subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools'/script),*args],cwd=ROOT,stdout=out,stderr=subprocess.STDOUT,timeout=7200,check=True)
try:
    status('waiting-for-animation-build')
    while True:
        try:data=json.loads((W/'project/animations/build-report.json').read_text(encoding='utf-8-sig'))
        except (OSError,json.JSONDecodeError):data={}
        if data.get('status')=='complete':break
        if data.get('status')=='failed':raise RuntimeError(data.get('error','Animation build failed'))
        time.sleep(10)
    run('animation-final-audit','audit_native_v11_animations.py')
    run('animation-package','package_native_v11.py','animation')
    run('package-import','audit_native_v11_import.py')
    run('final-package','package_native_v11.py','finalize')
    run('delivery','package_native_v11.py','deliver')
    status('complete',gameTested=False)
except Exception as error:
    status('failed',error=str(error));raise
