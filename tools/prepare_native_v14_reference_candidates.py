"""Evaluate accepted arm rotations before adding any new grip correction."""
import copy
import json
import sys
import tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
from anim_batch_mod.processor import ModConfig
from package_native_v10 import records,payload

def main():
    work=ROOT/'outputs/native-v14-20261104';project=ROOT/'outputs/native-manual-20261103/project'
    manifest=native.load_manifest(project/'source-skeleton.json');config=ModConfig.load(project/'config.toml')
    options=tomllib.loads((project/'config.toml').read_text(encoding='utf-8'))['native_skeleton'];options['align_standard_grips']=False
    base=ROOT/'outputs/native-fix-20261103';unit=UnitData.parse((base/'avatar.toc').read_bytes());bones=BonesData.parse((base/'bones.toc').read_bytes())
    build=json.loads((project/'animations/build-report.json').read_text(encoding='utf-8'));packages={int(r['id']):r['package'] for r in build['animations']}
    store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'));archives={}
    refpath=ROOT.parent/'output/9ba626afa44a3aa3.patch_0';refs={r[0]:r for r in records(refpath)}
    current=None
    def reference(animation,*args,**kwargs):animation.__dict__.update(copy.deepcopy(current.__dict__))
    native.modify_animation_with_world_compensation=reference
    compare=json.loads((work/'reference-comparison.json').read_text(encoding='utf-8'))
    ids=[int(row['id']) for row in compare['clips']]
    out=work/'reference-candidates';out.mkdir(exist_ok=True)
    for clip in sorted(set(ids)):
        package=packages[clip]
        if package not in archives:archives[package]=TocArchive.load_toc_only(store,package)
        raw=archives[package].entries[clip,ANIMATION_TYPE_ID].toc_data
        current=AnimationData.parse(payload(refpath,refs[clip]))
        data,metrics=native.convert_clip(raw,bones,unit,manifest,config,options)
        (out/f'{clip}.toc').write_bytes(data)
        print('reference candidate',clip,flush=True)

if __name__=='__main__':main()
