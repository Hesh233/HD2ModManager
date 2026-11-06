"""Run existing published-manager import simulation independently for test01--08."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/manager-parent-entry-fix-20261106'
INSTALLED=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'


def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    manager=OUT/'test-manager'
    if manager.exists():raise FileExistsError('Use a fresh isolated manager directory')
    shutil.copytree(OUT/'publish',manager)
    for name in ('HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll','anim_batch_mod/attachment_skeleton.py'):
        assert digest(manager/name)==digest(INSTALLED/name),name
    index=manager/'data/indexes/asset-index.sqlite';index.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect((INSTALLED/'data/indexes/asset-index.sqlite').as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(index) as target:source.backup(target)
    (manager/'config').mkdir(exist_ok=True)
    shutil.copy2(INSTALLED/'config/attachment-fix.json',manager/'config/attachment-fix.json')
    settings=json.loads((INSTALLED/'settings.json').read_text(encoding='utf-8-sig'))
    tool=ROOT/'tools/NativeReleaseTools/bin/Release/net10.0/NativeReleaseTools.exe'
    results=[]
    for i in range(1,9):
        name=f'test{i:02d}';case=OUT/(name+'-rs89')
        settings['ModLibraryFolder']=str(case/'isolated-library')
        settings['AutoImportToActiveProfile']=False
        (manager/'settings.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
        scale='1.05' if i==4 else '1.0'
        args=[str(tool),'--simulate-vpk-import-target',str(manager),str(case),
              settings['GameDataFolder'],'32','85d392768bf6a259',str(ROOT/'testVPK'/(name+'.vpk')),scale]
        print('START',name,'scale',scale,flush=True)
        started=datetime.now(timezone(timedelta(hours=8))).isoformat()
        with (OUT/(name+'-simulation.log')).open('w',encoding='utf-8') as log:
            run=subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
        result={'model':name,'scale':float(scale),'exitCode':run.returncode,'startedAsiaShanghai':started,
                'completedAsiaShanghai':datetime.now(timezone(timedelta(hours=8))).isoformat(),'output':str(case),'samples':32}
        results.append(result)
        (OUT/'simulation-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print('FINISH',name,'exit',run.returncode,flush=True)
        if run.returncode:raise RuntimeError(f'{name} simulation failed; see {name}-simulation.log')
    print('ALL EIGHT IMPORT SIMULATIONS PASSED',flush=True)

def verify_reimports():
    manager=OUT/'test-manager'
    tool=ROOT/'tools/NativeReleaseTools/bin/Release/net10.0/NativeReleaseTools.exe'
    settings=json.loads((manager/'settings.json').read_text(encoding='utf-8-sig'))
    results=[]
    for i in range(1,9):
        name=f'test{i:02d}';case=OUT/(name+'-rs89')
        settings['ModLibraryFolder']=str(case/'isolated-library')
        (manager/'settings.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
        args=[str(tool),'--verify-vpk-reimport',str(manager),str(case),settings['GameDataFolder'],
              str(ROOT/'testVPK'/(name+'.vpk')),'1.05' if i==4 else '1.0']
        with (OUT/(name+'-reimport.log')).open('w',encoding='utf-8') as log:
            run=subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        results.append({'model':name,'exitCode':run.returncode})
        (OUT/'reimport-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print('REIMPORT',name,'exit',run.returncode,flush=True)
        if run.returncode:raise RuntimeError(f'{name} reimport failed')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reimport-only',action='store_true')
    args=parser.parse_args()
    verify_reimports() if args.reimport_only else main()

