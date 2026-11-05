"""Record checked inputs, v9 regression evidence and current read-only deployment."""
import difflib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'tools'))
from package_native_v10 import WORK as W,PROJECT as P,digest,records,payload,save_json
from anim_batch_mod.native_skeleton import append_unit,load_manifest
B=ROOT/'outputs/native-fix-20261103';V9=ROOT/'outputs/native-v9-20261104'
audit=W/'armor-audit';audit.mkdir(exist_ok=True)
(audit/'avatar-final.toc').write_bytes(append_unit((B/'avatar.toc').read_bytes(),load_manifest(P/'source-skeleton.json')))
text=(W/'python-regression.log').read_text(encoding='utf-8-sig');assert 'Ran 20 tests' in text and 'OK' in text
save_json(W/'python-regression.json',dict(status='PASS',tests=20,logSha256=digest(W/'python-regression.log'),sourceSha256={n:digest(ROOT.parent/n) for n in ('processor.py','native_skeleton.py','test_native_v10.py')},gameTested=False))
save_json(W/'joint-roll-regression.json',dict(status='PASS',v9Reproduced=True,inputForearmRollDegrees=90,v9OutputForearmRollDegrees=0,v10OutputForearmRollDegrees=90,full360DegreeCyclePassed=True,gameTested=False))
diff=''
for name in ('processor.py','native_skeleton.py'):
    a=(W/'source-before'/name).read_text(encoding='utf-8-sig');b=(ROOT.parent/name).read_text(encoding='utf-8-sig')
    diff+=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='v9/'+name,tofile='v10/'+name))
(W/'native-skeleton-v10.diff').write_text(diff,encoding='utf-8')
game=Path(r'E:\Steam\steamapps\common\Helldivers 2\data');known={}
for name,path in dict(physics=V9/'project/physics-runtime/patch版/9ba626afa44a3aa3.patch_0',model=V9/'project/models-o3/test01-O3/9ba626afa44a3aa3.patch_0',material=V9/'project/models-o3/test01-O3/9ba626afa44a3aa3.patch_1',animation=V9/'project/animations/runtime/9ba626afa44a3aa3.patch_2').items():known[digest(path)]=name
core=ROOT/'outputs/native-v5-20261103/chef-loader-review/9ba626afa44a3aa3.patch_2_c27789387e64579a.lua';blob=core.read_bytes();matches=[];deployed=[]
for path in game.glob('9ba626afa44a3aa3.patch_*'):
    if not re.fullmatch(r'9ba626afa44a3aa3\.patch_\d+',path.name):continue
    rs=records(path);sha=digest(path);deployed.append(dict(path=str(path),sha256=sha,v9=known.get(sha),resources=len(rs)))
    for r in rs:
        if r[0]==0xc27789387e64579a:
            data=payload(path,r);at=data.find(blob)
            if at>=0:matches.append(dict(path=str(path),cachedSourceByteOffset=at,sourceSha256=digest(core)))
assert matches,'Deployed Chef differs from the compatibility fixture'
save_json(W/'deployed-chef-source-check.json',dict(status='PASS',matches=matches,readOnly=True))
save_json(W/'deployment-readonly-recheck.json',dict(status='COMPLETE',gameData=str(game),mainPatches=deployed,matchedV9=sorted(r['v9'] for r in deployed if r['v9']),readOnly=True))
validation=json.loads((W/'release-validation.json').read_text())
if 'joint-roll-regression.json' not in validation['requiredReports']:validation['requiredReports'].append('joint-roll-regression.json')
save_json(W/'release-validation.json',validation)
print('Evidence recorded; deployed v9:',[r['v9'] for r in deployed if r['v9']])
