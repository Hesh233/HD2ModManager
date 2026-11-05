"""Finish validation and package preparation once the active build completes."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v9-20261104';P=W/'project';T=ROOT/'tools'
PY=W/'manager/anim_batch_mod/runtime/python.exe'
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def run(label,args):
    print('Starting',label,flush=True);start=time.monotonic()
    with (W/(label+'.log')).open('w',encoding='utf-8') as f:
        result=subprocess.run([str(a) for a in args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=2400)
    if result.returncode:raise RuntimeError(f'{label} failed ({result.returncode}); see {W/(label+".log")}')
    print('Passed',label,round(time.monotonic()-start,1),'s',flush=True)
start=time.monotonic()
while True:
    try:build=load(P/'animations/build-report.json')
    except (OSError,json.JSONDecodeError):build={}
    if build.get('status')=='complete':break
    if build.get('status')=='failed':raise RuntimeError(build.get('error','Animation build failed'))
    if time.monotonic()-start>3600:raise TimeoutError('Animation build did not finish within one hour')
    time.sleep(20)
print('Build complete:',len(build['animations']),'clips',flush=True)
run('animation-final-audit',[PY,'-X','utf8',T/'audit_native_v9_animations.py'])
run('published-generator-check',[sys.executable,'-X','utf8',T/'audit_native_v9_published.py'])
run('grip-validation',[sys.executable,'-X','utf8',T/'verify_native_v9_grip.py'])
grip=load(W/'grip-validation-audit.json');old=load(ROOT/'outputs/native-v8-20261104/grip-validation-audit.json')
prior={r['id']:r for r in old['samples']}
summary={'validationStatus':grip['validationStatus'],'gripStatus':grip['gripStatus'],'gameTested':False,
    'maxLeftToRightAnchoredReferenceMetres':grip['maxLeftToRightAnchoredReferenceMetres'],
    'v8SampleMaximumMetres':old['maxLeftToRightAnchoredReferenceMetres'],
    'exceedingClipIds':grip['exceedingClipIds'],'sampleCount':grip['sampleCount'],'samplesPerClip':grip['samplesPerClip'],
    'commonClipComparison':[{'id':r['id'],'v9':r['maxima']['leftToRightAnchoredReferenceMetres'],'v8':prior[r['id']]['maxima']['leftToRightAnchoredReferenceMetres']} for r in grip['samples'] if r['id'] in prior],
    'scope':'Sampled offline geometry only; worst-clip selection may differ between versions. Live weapon contact and aiming remain unverified.'}
save(W/'grip-validation-summary.json',summary)
run('attachment-runtime-final',[sys.executable,'-X','utf8',T/'audit_native_attachment_layouts.py','--profile',P/'attachment-profile.json','--model-patch',P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0','--avatar-patch',P/'animations/runtime/9ba626afa44a3aa3.patch_2','--consumer-unit','a7ee1ebf58fcdf1f='+str(W/'a7ee1ebf58fcdf1f.toc'),'--consumer-unit','a9936cbe561e8180='+str(W/'a9936cbe561e8180.toc'),'--output',W/'attachment-runtime-audit.json'])
(W/'armor-audit/layout-runtime-final.json').write_bytes((W/'attachment-runtime-audit.json').read_bytes())
run('animation-package',[sys.executable,'-X','utf8',T/'package_native_v9.py','--animation'])
run('package-import',[sys.executable,'-X','utf8',T/'audit_native_v9_import.py'])
run('package-prepare',[sys.executable,'-X','utf8',T/'package_native_v9.py','--prepare'])
print('All packages prepared. Review package-report.json before delivery.',flush=True)
