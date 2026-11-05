"""Create an isolated v10 workspace from the delivered v9 inputs."""
import json, os, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/native-v10-20261104';V9=ROOT/'outputs/native-v9-20261104'
W.mkdir(exist_ok=True)
for name in ('project','manager'):
    if not (W/name).exists():
        shutil.copytree(V9/name,W/name,ignore=shutil.ignore_patterns('animations','reports','__pycache__','resource-index.sqlite3*') if name=='project' else shutil.ignore_patterns('__pycache__'))
before=W/'source-before';before.mkdir(exist_ok=True)
for name in ('processor.py','native_skeleton.py'):
    if not (before/name).exists():shutil.copy2(ROOT.parent/name,before/name)
for name in ('native_attachments.lua','physbone_runtime.lua'):
    if not (before/name).exists():shutil.copy2(ROOT/'HD2PhysBoneCompat/src'/name,before/name)
for name in ('unit-anim-reference.toc','a7ee1ebf58fcdf1f.toc','a9936cbe561e8180.toc','1c8764d62e12925a.toc','release-validation.json'):
    shutil.copy2(V9/name,W/name)
diagnosis=W/'runtime-diagnosis';diagnosis.mkdir(exist_ok=True)
for name in ('hd2physbone.log','chef_loader.log'):
    shutil.copy2(Path(os.environ['APPDATA'])/'Arrowhead/Helldivers2'/name,diagnosis/name)
scripts=('build_native_v9.py','finish_native_v9.py','package_native_v9.py','verify_native_v9_delivery.py',
 'audit_native_v9_import.py','audit_native_v9_animations.py','audit_native_v9_published.py','verify_native_v9_grip.py',
 'audit_native_v9_candidate.py','audit_native_v9_arms.py','audit_native_v9_feet.py','blender_native_v9_bone_names.py',
 'Rebuild-Native-v9-Animations.ps1','audit_native_v9_chef.py','audit_native_v9_model.py','audit_native_v9_fusion.py')
for name in scripts:
    source=ROOT/'tools'/name;target=ROOT/'tools'/name.replace('v9','v10')
    if not target.exists():target.write_text(source.read_text(encoding='utf-8-sig').replace('v9','v10'),encoding='utf-8')
(W/'user-observation.json').write_text(json.dumps(dict(reportedOn='2026-11-04',sourceVersion='v9',gripPosition='USER_CONFIRMED_CORRECT',footYCorrection='USER_CONFIRMED_CORRECT',sourceJoints='FROZEN_OR_TWISTED',nativeArmor='USER_CONFIRMED_NORMAL',weaponComponents='MUZZLE_SIGHT_MAGAZINE_DETACHED',gameTestedV10=False),ensure_ascii=False,indent=2),encoding='utf-8')
print(W)
