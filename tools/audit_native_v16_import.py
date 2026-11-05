"""Import only the B7 diagnostic into a disposable library, never deploy it."""
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, digest, load, save_json
W=ROOT/'outputs/native-v16-20261104'
R=ROOT/'outputs/native-manual-20261103'
PATCH=re.compile(r'[0-9a-f]{16}\.patch_\d+(?:\.(?:stream|gpu_resources))?$')


def main(exe=None, sandbox_root=None):
    exe=Path(exe) if exe is not None else R/'test/hd2mod.exe'
    assert exe.is_file()
    sandbox=Path(tempfile.mkdtemp(prefix='import-audit-',dir=sandbox_root or W)).resolve()
    results=[]
    for index,package in enumerate(load(W/'static-packages.json')):
        folder=sandbox/str(index);manager=folder/'manager';library=folder/'library'
        manager.mkdir(parents=True);library.mkdir()
        save_json(manager/'settings.json',dict(ModLibraryFolder=str(library),GameDataFolder=r'E:\Steam\steamapps\common\Helldivers 2\data'))
        def call(label,args):
            cp=subprocess.run([str(exe),*args,'--manager-root',str(manager),'--library',str(library),'--json'],
                cwd=manager,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=900)
            (folder/(label+'.log')).write_text(cp.stdout+cp.stderr,encoding='utf-8')
            assert cp.returncode==0,(label,cp.returncode,cp.stdout[-2500:],cp.stderr[-1000:])
            return json.loads(cp.stdout.lstrip('\ufeff'))
        path=W/package['name'];assert digest(path)==package['sha256']
        inspection=call('inspect',['import','inspect',str(path)])['import']
        assert inspection['items'] and not any(d.get('isBlocking') for d in inspection.get('diagnostics',[]))
        assert not any(d.get('isBlocking') for item in inspection['items'] for d in item.get('diagnostics',[]))
        plan=folder/'plan.json'
        assert call('plan',['import','plan',str(path),'--output',str(plan)])['ok']
        validation=call('validate',['import','validate','--plan',str(plan)])
        assert validation['ok'] and validation['validation']['isValid']
        target=validation['validation']['target']
        assert Path(target['libraryRoot']).resolve()==library and not target['runningManagerProcessIds']
        applied=call('apply',['import','apply','--plan',str(plan),'--confirm'])
        assert applied['ok'] and applied['applied']['deployment']=='not-performed' and applied['applied']['importedNodeIds']
        imported={}
        for f in library.rglob('*'):
            if f.is_file() and PATCH.fullmatch(f.name):imported.setdefault(digest(f),[]).append(f)
        checked=[]
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            for name in z.namelist():
                if PATCH.fullmatch(Path(name).name):
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
    save_json(W/'package-inspection.json',dict(status='PASS',packages=results,sandbox=str(sandbox),
        importer=str(exe),importerSha256=digest(exe),
        gameDeployed=False,gameTested=False,dailyLibraryModified=False,managerProcessGuardRespected=True))


if __name__=='__main__':
    try:main()
    except Exception as error:
        save_json(W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
