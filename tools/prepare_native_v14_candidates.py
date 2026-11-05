"""Isolate fixed-bind hinge roll from full-frame IK using current game clips."""
import json
import sys
import tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import ModConfig

def main():
    work=ROOT/'outputs/native-v14-20261104';project=ROOT/'outputs/native-manual-20261103/project'
    manifest=native.load_manifest(project/'source-skeleton.json')
    config=ModConfig.load(project/'config.toml')
    options=tomllib.loads((project/'config.toml').read_text(encoding='utf-8'))['native_skeleton']
    base=ROOT/'outputs/native-fix-20261103'
    unit=UnitData.parse((base/'avatar.toc').read_bytes());bones=BonesData.parse((base/'bones.toc').read_bytes())
    build=json.loads((project/'animations/build-report.json').read_text(encoding='utf-8'))
    packages={int(r['id']):r['package'] for r in build['animations']}
    store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'));archives={}
    old=native._apply_two_bone_ik
    def solve(*args,**kwargs):
        kwargs.pop('hinge_axis',None)
        return old(*args,**kwargs)
    native._apply_two_bone_ik=solve
    ids=sorted(int(p.stem) for p in (ROOT/'outputs/native-v13-20261104/candidate-clips').glob('*.toc'))
    compare=json.loads((work/'reference-comparison.json').read_text(encoding='utf-8'))
    ids+= [int(row['id']) for row in compare['clips'] if 'measurements' in row and any(
        v['max']>150 for k,v in row['measurements'].items() if 'shoulder_twist' in k)]
    out=work/'frame-candidates';out.mkdir(exist_ok=True);reports=[]
    for clip in sorted(set(ids)):
        package=packages[clip]
        if package not in archives:archives[package]=TocArchive.load_toc_only(store,package)
        raw=archives[package].entries[clip,ANIMATION_TYPE_ID].toc_data
        data,metrics=native.convert_clip(raw,bones,unit,manifest,config,options)
        (out/f'{clip}.toc').write_bytes(data)
        reports.append(dict(id=str(clip),**metrics))
        print('frame candidate',clip,flush=True)
    (work/'frame-candidates.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')

if __name__=='__main__':main()
