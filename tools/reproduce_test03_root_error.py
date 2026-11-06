import json,sys,types,shutil
from pathlib import Path
r=Path('anim_batch_mod/HD2ModManager').resolve();sys.path.insert(0,str(r.parents[1]));w=r/'outputs/attachment-root-mask-fix-20261106';inputs=w/'inputs'
before=inputs/'native-skeleton-before.py'
if not before.exists():shutil.copy2(r/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/anim_batch_mod/native_skeleton.py',before)
mod=types.ModuleType('before_root_fix');mod.__package__='anim_batch_mod';exec(compile(before.read_text(encoding='utf-8-sig'),str(before),'exec'),mod.__dict__)
from anim_batch_mod.formats import BonesData
m=json.loads((inputs/'source-skeleton.json').read_text());b=BonesData.parse((inputs/'bones.toc').read_bytes())
try:mod.append_state_machine_masks((inputs/'state-machine.toc').read_bytes(),b,m)
except ValueError as e:
 assert str(e)=='Source root has no blend-mask driver';print('REPRODUCED:',e)
 (w/'baseline-error.json').write_text(json.dumps({'error':str(e),'source':'installed 1.0.12 code','sourceName':'Armature'}),encoding='utf-8')
else:raise AssertionError('Expected original user failure')
