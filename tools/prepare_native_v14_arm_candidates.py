import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.native_arm_reference import AnimationReference,apply_arm_reference
from anim_batch_mod.native_skeleton import load_manifest
from anim_batch_mod.formats import UnitData,BonesData
from package_native_v10 import records,payload

def main():
    work=ROOT/'outputs/native-v14-20261104';project=ROOT/'outputs/native-manual-20261103/project'
    base=ROOT/'outputs/native-fix-20261103'
    unit=UnitData.parse((base/'avatar.toc').read_bytes());bones=BonesData.parse((base/'bones.toc').read_bytes())
    manifest=load_manifest(project/'source-skeleton.json')
    reference=AnimationReference(ROOT.parent/'output/9ba626afa44a3aa3.patch_0')
    path=project/'animations/runtime/9ba626afa44a3aa3.patch_2';old={r[0]:r for r in records(path)}
    clips=json.loads((work/'reference-comparison.json').read_text(encoding='utf-8'))['clips']
    output=work/'arm-candidates';output.mkdir(exist_ok=True)
    for row in clips:
        clip=int(row['id'])
        data,metrics=apply_arm_reference(payload(path,old[clip]),reference.read(clip),bones,unit,manifest)
        (output/f'{clip}.toc').write_bytes(data)
        print(clip,metrics,flush=True)

if __name__=='__main__':main()
