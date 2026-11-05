"""Regenerate six fixed real clips with the manager's embedded Python runtime.

Run only after final publish and animation build. Reads game originals, never
imports/deploys a mod or starts the desktop manager.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'outputs/native-v9-20261104'
PROJECT = WORK / 'project'
MANAGER = WORK / 'manager'
BASE = ROOT / 'outputs/native-fix-20261103'
IDS = (18307702697579710200, 16381641002705108128, 7781841632278966152,
       16374892322597155811, 2300190009223786134, 16559285465095148)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def child(spec_path):
    import tomllib
    spec = load(spec_path)
    sys.path.insert(0, str(MANAGER))
    for filename in spec['modules']:
        name = 'anim_batch_mod' if filename == '__init__.py' else 'anim_batch_mod.' + filename[:-3]
        importlib.import_module(name)
    from anim_batch_mod.native_skeleton import load_manifest, convert_clip
    from anim_batch_mod.archive import TocArchive, PackageStore
    from anim_batch_mod.constants import ANIMATION_TYPE_ID
    from anim_batch_mod.formats import UnitData, BonesData, AnimationData
    from anim_batch_mod.processor import ModConfig
    loaded = []
    for name, module in sorted(sys.modules.items()):
        if name == 'anim_batch_mod' or name.startswith('anim_batch_mod.'):
            location = Path(module.__file__).resolve()
            assert location.is_relative_to(MANAGER.resolve()), ('Imported source instead of published module',name,location)
            loaded.append({'module':name,'path':str(location),'sha256':digest(location)})
    assert Path(sys.executable).resolve() == Path(spec['python']).resolve()
    build = load(PROJECT/'animations/build-report.json')
    by_id = {int(r['id']):r for r in build['animations']}
    manifest = load_manifest(PROJECT/'source-skeleton.json')
    config_path = PROJECT/'config.toml'
    config = ModConfig.load(config_path)
    options = tomllib.loads(config_path.read_text(encoding='utf-8-sig'))['native_skeleton']
    unit = UnitData.parse((BASE/'avatar.toc').read_bytes())
    bones = BonesData.parse((BASE/'bones.toc').read_bytes())
    archives = {}
    result = []
    with Path(spec['patch']).open('rb') as f:
        header=f.read(72)
        types,count=struct.unpack_from('<II',header,4)
        f.seek(72+32*types)
        records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
        records={(r[0],r[1]):r for r in records}
        for id in IDS:
            row=by_id[id]
            package=row['package']
            if package not in archives:
                archives[package]=TocArchive.load_toc_only(PackageStore(Path(spec['gameData'])),package)
            original=archives[package].entries[id,ANIMATION_TYPE_ID].toc_data
            source=AnimationData.parse(original)
            assert source.is_additive == row['additive']
            record=records[id,ANIMATION_TYPE_ID]
            f.seek(record[2]);shipped=f.read(record[7])
            generated,metrics=convert_clip(original,bones,unit,manifest,config,options)
            assert generated==shipped, ('Published generator differs from final payload',id,
                hashlib.sha256(generated).hexdigest(),hashlib.sha256(shipped).hexdigest())
            parsed=AnimationData.parse(generated)
            result.append({'id':str(id),'sourcePackage':package,'bytes':len(generated),
                'sha256':hashlib.sha256(generated).hexdigest(),'sourceSha256':hashlib.sha256(original).hexdigest(),
                'additive':source.is_additive,'channels':len(parsed.initial_bone_states),
                'exactPayloadMatch':True,'metrics':metrics})
            print(f"Exact published payload match: {id} ({len(result)}/6)",flush=True)
    assert any(r['additive'] for r in result)
    assert any(r['metrics'].get('standard_grip_chains',0)>0 for r in result)
    report={'status':'PASS','scope':'Deterministic published generator parity; this is not an in-game grip/IK acceptance test',
        'pythonExecutable':sys.executable,'pythonVersion':sys.version,'loadedModules':loaded,
        'exactGeneratedClips':result,'fixedSampleIds':[str(i) for i in IDS],
        'inputs':spec['inputs'],'manager':str(MANAGER),'gameTested':False}
    save(WORK/'published-generator-audit.json',report)


def run(game_data):
    from package_native_v9 import runtime_modules
    python=MANAGER/'anim_batch_mod/runtime/python.exe'
    assert python.is_file()
    modules=runtime_modules()
    assert {'native_skeleton.py','native_animation.py','attachment_skeleton.py','motion_skeleton.py'} <= set(modules)
    for name in modules:
        assert digest(MANAGER/'anim_batch_mod'/name)==digest(ROOT.parent/name), ('Stale published module',name)
    build=load(PROJECT/'animations/build-report.json')
    assert build['status']=='complete'
    assert set(IDS) <= {int(r['id']) for r in build['animations']}
    patches=[p for p in (PROJECT/'animations/runtime').iterdir() if re.fullmatch(r'[0-9a-f]{16}\.patch_\d+',p.name)]
    assert len(patches)==1
    paths=[PROJECT/'source-skeleton.json',PROJECT/'config.toml',PROJECT/'animations/build-report.json',patches[0],
           BASE/'avatar.toc',BASE/'bones.toc']+[MANAGER/'anim_batch_mod'/n for n in modules]
    inputs={str(p):digest(p) for p in paths}
    spec={'python':str(python),'patch':str(patches[0]),'gameData':str(game_data),'modules':modules,'inputs':inputs}
    spec_path=WORK/'published-generator-spec.json';save(spec_path,spec)
    result=subprocess.run([str(python),'-X','utf8',str(Path(__file__).resolve()),'--child',str(spec_path)],
        cwd=MANAGER,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600)
    (WORK/'published-generator-audit.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:
        save(WORK/'published-generator-audit.json',{'status':'FAIL','returncode':result.returncode,
            'log':'published-generator-audit.log','gameTested':False})
        raise RuntimeError(result.stdout+result.stderr)
    assert all(digest(Path(p))==sha for p,sha in inputs.items()), 'Inputs changed during verification'
    report=load(WORK/'published-generator-audit.json')
    assert report['status']=='PASS' and len(report['exactGeneratedClips'])==6
    print(json.dumps({'status':'PASS','exactGeneratedClips':6,'modules':len(report['loadedModules']),
        'report':str(WORK/'published-generator-audit.json')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-data',type=Path,default=Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
    parser.add_argument('--child',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.child:child(args.child)
    else:
        try:
            run(args.game_data)
        except Exception as error:
            save(WORK/'published-generator-audit.json',{'status':'FAIL','error':str(error),'gameTested':False})
            raise
