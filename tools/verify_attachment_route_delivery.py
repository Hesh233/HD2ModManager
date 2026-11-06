from pathlib import Path
import json,hashlib,tomllib
root=Path('anim_batch_mod/HD2ModManager').resolve();w=root/'outputs/attachment-routes-20261106';target=root/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';candidate=w/'manager'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
info=json.loads((target/'anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'))
assert info['pipelineVersion']=='1.0.11'
for row in info['files']:
 assert sha(target/'anim_batch_mod'/row['name']).upper()==row['sha256'].upper(),row['name']
 assert sha(root.parent/row['name'])==sha(target/'anim_batch_mod'/row['name']),row['name']
for name in ['HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll']:
 assert sha(target/name)==sha(candidate/name),name
assert tomllib.loads((target/'config.toml').read_text(encoding='utf-8-sig'))['native_skeleton']['attachment_swap'] is False
assert len(json.loads((target/'config/attachment-fix.json').read_text(encoding='utf-8-sig'))['bones'])==21
reports=[json.loads((w/route/model/'route-audit.json').read_text()) for route in ['dual-verified','single-final'] for model in ['test01','test02']]
assert all(p['status']=='PASS' for p in reports)
verification=dict(status='PASS',pipelineVersion='1.0.11',luaVersion='1.0.9',runtimePolicy='b23-1.0.8',target=str(target),
 packagedSourceHashesMatchRoot=True,packagedBinaryHashesMatchVerifiedPublish=True,
 binaries={name:sha(target/name) for name in ['HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll']},
 sourceFilesChecked=len(info['files']),sampledRouteReports=reports,lua=json.loads((w/'lua-route-audit.json').read_text()),
 pythonTests=121,dotnetTestsPassed=118,dotnetTestsSkipped=1,
 backups=[str(p) for p in sorted(root.glob('outputs/manager-route-update-20261106-*/update-manifest.json'))],
 sampleOnly=True,gameDeployed=False,gameTested=False,manualGuiTested=False)
(w/'delivery-verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:verification[k] for k in ['status','pipelineVersion','sourceFilesChecked','packagedBinaryHashesMatchVerifiedPublish','gameDeployed']},ensure_ascii=False))
