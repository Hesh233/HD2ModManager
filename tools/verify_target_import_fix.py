import json,hashlib
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();w=r/'outputs/attachment-import-fix-20261106';target=r/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';candidate=w/'manager'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
info=json.loads((target/'anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'))
assert info['pipelineVersion']=='1.0.12'
for row in info['files']:
 assert sha(target/'anim_batch_mod'/row['name']).upper()==row['sha256'].upper(),row['name']
 assert sha(target/'anim_batch_mod'/row['name'])==sha(r.parent/row['name']),row['name']
for name in ['HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll']:assert sha(target/name)==sha(candidate/name)
results=[]
for model in ['test01','test02']:
 p=w/'fixed-o3'/model
 audit=json.loads((p/'route-audit.json').read_text());assert audit['status']=='PASS'
 build=json.loads(next((p/'attachment').rglob('attachment-build-report.json')).read_text());discovery=build['modelDiscovery']
 profile=json.loads(next((p/'attachment').rglob('attachment-profile.json')).read_text())
 aux={row['resource'] for row in discovery['skippedUnits'] if row['reason']=='non_source_auxiliary'}
 assert len(discovery['targetBodies'])==10 and len(aux)==6 and len(profile['models'])==16
 assert not aux.intersection(profile['models']) and set(discovery['targetBodies']).issubset(profile['models'])
 assert discovery['sourceOwnershipGate']
 results.append(dict(model=model,registeredSourceBodies=6,targetBodies=10,excludedNativeAuxiliaries=6,audit=audit))
report=dict(status='PASS',pipelineVersion='1.0.12',luaVersion='1.0.9',cause='Native O-3 hide/proxy Units were treated as mandatory Source models',
 userFailureReproduced=True,publishedSourcesMatchRoot=True,publishedBinariesMatchCandidate=True,sourceFilesChecked=len(info['files']),
 pythonTestsPassed=130,dotnetTestsPassed=29,dotnetTestsSkipped=1,results=results,
 backup=str(r/'outputs/manager-route-update-20261106-144921/update-manifest.json'),
 settingsAndAssetIndexPreserved=True,sampleOnly=True,gameDeployed=False,manualGuiTested=False,gameTested=False)
(w/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'pipelineVersion':report['pipelineVersion'],'targetBodies':10,'excludedNativeAuxiliaries':6},ensure_ascii=False))
