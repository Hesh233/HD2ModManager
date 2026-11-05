"""Inspect, plan, validate and import all three v10 packages into a fresh test library.

The manager's own process guard is authoritative. A running desktop manager
leaves a BLOCKED report; this script neither kills it nor bypasses its guard.
No deployment commands are executed.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from package_native_v10 import ROOT, WORK, digest, load, save_json

PACKAGES = {'model':'test01-模型材质.zip', 'animation':'test01-配套动画.zip',
            'physics':'test01-物理运行时-v10.zip'}
PATCH = re.compile(r'[0-9a-f]{16}\.patch_\d+(?:\.(?:stream|gpu_resources))?$')


class ProcessGuardBlocked(RuntimeError):
    pass


def verify_normalized_groups(checked):
    # Import may renumber patch_2 to patch_0. Tie both external files to the
    # imported main file, so equal empty-file hashes cannot hide a missing sidecar.
    mains={}
    for row in checked:
        if re.fullmatch(r'[0-9a-f]{16}\.patch_\d+',Path(row['file']).name):
            paths=[p for p in row['importedPaths'] if re.fullmatch(r'[0-9a-f]{16}\.patch_\d+',Path(p).name)]
            assert paths, row
            mains[row['package'],row['file']]=paths
    for row in checked:
        suffix=next((s for s in ('.gpu_resources','.stream') if row['file'].endswith(s)),None)
        if suffix:
            paths=mains[row['package'],row['file'][:-len(suffix)]]
            assert any(p+suffix in row['importedPaths'] for p in paths), ('Missing normalized sidecar',row)
    return len(mains)


def run(game_data,static_only=False):
    exe=WORK/'manager/hd2mod.exe'
    assert exe.is_file()
    packages={kind:name for kind,name in PACKAGES.items() if not static_only or kind!='animation'}
    hashes={name:digest(WORK/name) for name in packages.values()}
    sandbox=Path(tempfile.mkdtemp(prefix='import-audit-',dir=WORK)).resolve()
    assert sandbox.is_relative_to(WORK.resolve())
    manager=sandbox/'manager';library=sandbox/'library'
    manager.mkdir();library.mkdir()
    save_json(manager/'settings.json',{'ModLibraryFolder':str(library),'GameDataFolder':str(game_data)})
    results={}

    def call(label,args):
        command=[str(exe),*args,'--manager-root',str(manager),'--library',str(library),'--json']
        result=subprocess.run(command,cwd=manager,capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=600)
        output=result.stdout.lstrip('\ufeff')
        (sandbox/(label+'.log')).write_text(output+result.stderr,encoding='utf-8')
        if 'ManagerProcessRunning' in output+result.stderr:
            raise ProcessGuardBlocked(f'{label}: manager process guard blocked isolated import; see {sandbox}')
        assert result.returncode==0, (label,result.returncode,output,result.stderr)
        data=json.loads(output)
        save_json(sandbox/(label+'.json'),data)
        return data

    for kind,name in packages.items():
        inspected=call(kind+'-inspection',['import','inspect',str(WORK/name)])
        tree=inspected['import']
        assert tree['items']
        assert not any(d.get('isBlocking') for d in tree.get('diagnostics',[]))
        for item in tree['items']:
            assert not any(d.get('isBlocking') for d in item.get('diagnostics',[]))
        results[kind]={'inspectionItems':len(tree['items']),
            'patchGroups':sum(len(item['patchGroups']) for item in tree['items'])}
    if static_only:
        report={'status':'PASS','scope':'Static model and physics inspect only; full import verification pending',
            'sandbox':str(sandbox),'packageSha256':hashes,'packages':results,
            'gameDeployed':False,'gameTested':False}
        save_json(WORK/'static-import-inspection.json',report)
        print(json.dumps({'status':'PASS','inspectedPackages':2,'sandbox':str(sandbox)},indent=2))
        return
    for kind,name in packages.items():
        plan=sandbox/(kind+'-plan.json')
        planned=call(kind+'-plan-result',['import','plan',str(WORK/name),'--output',str(plan)])
        assert planned['ok']
        validated=call(kind+'-validation',['import','validate','--plan',str(plan)])
        assert validated['ok'] and validated['validation']['isValid']
        target=validated['validation']['target']
        assert Path(target['libraryRoot']).resolve()==library and not target['runningManagerProcessIds']
        applied=call(kind+'-apply',['import','apply','--plan',str(plan),'--confirm'])
        assert applied['ok'] and applied['applied']['deployment']=='not-performed'
        assert Path(applied['applied']['libraryRoot']).resolve()==library
        assert applied['applied']['importedNodeIds']
        results[kind].update(importedNodeIds=applied['applied']['importedNodeIds'],deployment='not-performed')
        print(f'Isolated {kind} inspect/plan/validate/apply passed',flush=True)
    imported={}
    for path in library.rglob('*'):
        if path.is_file() and PATCH.fullmatch(path.name):
            imported.setdefault(digest(path),[]).append(str(path.relative_to(library)))
    checked=[]
    for name in packages.values():
        assert digest(WORK/name)==hashes[name], 'Package changed during import validation'
        with zipfile.ZipFile(WORK/name) as archive:
            for info in archive.infolist():
                if not info.is_dir() and PATCH.fullmatch(Path(info.filename).name):
                    with archive.open(info) as f:
                        sha=hashlib.file_digest(f,'sha256').hexdigest()
                    assert sha in imported, ('Imported patch bytes missing or changed',name,info.filename)
                    checked.append({'package':name,'file':info.filename,'sha256':sha,'importedPaths':imported[sha]})
    assert checked
    normalized_groups=verify_normalized_groups(checked)
    report={'status':'PASS','sandbox':str(sandbox),'managerRoot':str(manager),'libraryRoot':str(library),
        'cliSha256':digest(exe),'packageSha256':hashes,'packages':results,
        'verifiedPatchFiles':checked,'gameDeployed':False,'gameTested':False,
        'dailyLibraryModified':False,'managerProcessGuardRespected':True,
        'normalizedPatchGroupsVerified':normalized_groups}
    save_json(WORK/'package-inspection.json',report)
    print(json.dumps({'status':'PASS','packages':3,'verifiedPatchFiles':len(checked),'sandbox':str(sandbox)},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-data',type=Path,default=Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
    parser.add_argument('--inspect-static',action='store_true',help='Inspect ready model/physics packages while animation is building')
    args=parser.parse_args()
    try:
        run(args.game_data,args.inspect_static)
    except Exception as error:
        save_json(WORK/('static-import-inspection.json' if args.inspect_static else 'package-inspection.json'),{'status':'BLOCKED' if isinstance(error,ProcessGuardBlocked) else 'FAIL',
            'error':str(error),'gameDeployed':False,'gameTested':False})
        raise
