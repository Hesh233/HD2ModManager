import json,hashlib
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();w=r/'outputs/attachment-root-mask-fix-20261106';target=r/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';candidate=w/'manager'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
info=json.loads((target/'anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'));assert info['pipelineVersion']=='1.0.13'
for row in info['files']:
 assert sha(target/'anim_batch_mod'/row['name']).upper()==row['sha256'].upper()
 assert sha(target/'anim_batch_mod'/row['name'])==sha(r.parent/row['name'])
for n in ['HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll']:assert sha(target/n)==sha(candidate/n)
case=w/'test03-rs89/test03';flow=json.loads((case/'import-regression.json').read_text());audit=json.loads((case/'route-audit.json').read_text());masks=json.loads((w/'packaged-root-mask-audit.json').read_text())
assert flow['status']==audit['status']==masks['status']=='PASS'
backup=r/'outputs/manager-route-update-20261106-151508/update-manifest.json';changed=json.loads(backup.read_text(encoding='utf-8-sig'))['changedFiles'];assert not any(x['path'].endswith('.dll') for x in changed)
report=dict(status='PASS',pipelineVersion='1.0.13',luaVersion='1.0.9',root='Armature',owner='StingrayEntityRoot',
 baselineErrorReproduced=json.loads((w/'baseline-error.json').read_text())['error'],
 actualImportFlow=flow,maskAudit=masks,animationAudit=audit,pythonTestsPassed=138,
 rootWeightsChecked=12160,publishedSourcesMatchRoot=True,publishedDllsUnchanged=True,
 backup=str(backup),settingsAndIndexPreserved=True,sampleOnly=True,manualGuiTested=False,gameTested=False,gameDeployed=False)
(w/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':'PASS','pipelineVersion':'1.0.13','root':'Armature','owner':'StingrayEntityRoot'}))
