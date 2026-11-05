"""Run the manager import contract in isolated v14 libraries, never deploy."""
import audit_native_v12_import as audit
from package_native_v14 import ROOT,WORK
from package_native_v12 import load,save_json,digest
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

audit.ROOT=ROOT
audit.WORK=WORK

def resume(folder,refresh_static=False):
    sandbox=Path(folder).resolve()
    assert sandbox.parent==WORK.resolve() and sandbox.name.startswith('import-audit-')
    exe=WORK/'manager/hd2mod.exe'
    packages=load(WORK/'static-packages.json')+[load(WORK/'animation-package.json')]
    results=[]
    for number,package in enumerate(packages):
        directory=sandbox/str(number+3 if refresh_static and number<2 else number)
        manager=directory/'manager';library=directory/'library'
        path=WORK/package['name'];plan=directory/'plan.json'
        assert digest(path)==package['sha256']
        def call(label,args):
            cp=subprocess.run([str(exe),*args,'--manager-root',str(manager),'--library',str(library),'--json'],
                cwd=manager,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900)
            (directory/(label+'-resumed.log')).write_text(cp.stdout+cp.stderr,encoding='utf-8')
            assert cp.returncode==0,(label,cp.returncode,cp.stdout[-1800:],cp.stderr[-1000:])
            return json.loads(cp.stdout.lstrip('\ufeff'))
        if not plan.exists():
            assert refresh_static and number<2 and not directory.exists()
            manager.mkdir(parents=True);library.mkdir()
            save_json(manager/'settings.json',{'ModLibraryFolder':str(library),'GameDataFolder':r'E:\Steam\steamapps\common\Helldivers 2\data'})
            inspection=call('inspect',['import','inspect',str(path)])['import']
            assert inspection['items'] and not any(d.get('isBlocking') for d in inspection.get('diagnostics',[]))
            assert call('plan',['import','plan',str(path),'--output',str(plan)])['ok']
        document=load(plan)
        assert Path(document['source']['requestedPath']).resolve()==path.resolve()
        assert document['sourceFingerprint']['value'].lower()==package['sha256']
        applied_path=directory/'apply-resumed.log'
        if not applied_path.exists():applied_path=directory/'apply.log'
        applied=load(applied_path) if applied_path.exists() else {}
        if not applied.get('ok'):
            validation=call('validate',['import','validate','--plan',str(plan)])
            assert validation['ok'] and validation['validation']['isValid']
            target=validation['validation']['target']
            assert Path(target['libraryRoot']).resolve()==library and not target['runningManagerProcessIds']
            applied=call('apply',['import','apply','--plan',str(plan),'--confirm'])
        assert applied['ok'] and applied['applied']['deployment']=='not-performed' and applied['applied']['importedNodeIds']
        imported={}
        for f in library.rglob('*'):
            if f.is_file() and audit.PATCH.fullmatch(f.name):imported.setdefault(digest(f),[]).append(f)
        checked=[]
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if audit.PATCH.fullmatch(Path(name).name):
                    with z.open(name) as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
                    assert sha in imported,(package['name'],name)
                    checked.append(dict(name=name,sha256=sha,imported=[str(p.relative_to(sandbox)) for p in imported[sha]]))
        mains=[r for r in checked if re.fullmatch(r'[0-9a-f]{16}\.patch_\d+',Path(r['name']).name)]
        assert mains
        for row in mains:
            for suffix in ('.stream','.gpu_resources'):
                sidecar=next(r for r in checked if r['name']==row['name']+suffix)
                assert any(p+suffix in sidecar['imported'] for p in row['imported'])
        results.append(dict(package=package['name'],sha256=package['sha256'],verifiedPatchFiles=checked,gameDeployed=False))
        print('Verified isolated import:',package['name'],flush=True)
    save_json(WORK/'package-inspection.json',dict(status='PASS',packages=results,sandbox=str(sandbox),gameDeployed=False,
        gameTested=False,dailyLibraryModified=False,managerProcessGuardRespected=True,resumedExistingPlans=True))

if __name__=='__main__':
    try:
        if len(sys.argv)==3 and sys.argv[1] in ('--resume','--refresh-static'):resume(sys.argv[2],refresh_static=sys.argv[1]=='--refresh-static')
        else:audit.main()
    except Exception as error:
        audit.save_json(WORK/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
