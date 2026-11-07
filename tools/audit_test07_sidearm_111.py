"""Incremental 1.0.11 regression, retaining all prior B23/test07 cases."""
import json,sys,zipfile,copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from audit_test07_grip_fixes import build_harness
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
from prepare_native_v31_b23 import lua,matrices
from anim_batch_mod.attachment_skeleton import sidearm_right_outputs
from anim_batch_mod.native_config import apply_grip_fixes
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import BONE_TYPE_ID
from anim_batch_mod.formats import UnitData
OUT=ROOT/'outputs/test07-sidearm-fix-111-20261106'
def build_111_harness():
 profile,fixture,harness=build_harness()
 project=ROOT/'projects/test01-native-grip'
 with zipfile.ZipFile(project/'inputs/baseline-1.0.7.zip') as z:
  raw=z.read('runtime-avatar.toc');a=TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_5'),load_external_data=False)
  bones=next(e.toc_data for e in a.entries.values() if e.type_id==BONE_TYPE_ID)
 p=apply_grip_fixes(json.loads((project/'config/B23-profile.json').read_text(encoding='utf-8-sig')))
 p['logging']=dict(compact=False);p['logSeconds']=1.
 if p.get('sidearmDiagnostics'):p['sidearmDiagnostics']=dict(p['sidearmDiagnostics'],intervalSeconds=1.,maxSamplesPerPath=180)
 raw,bones,rig=sidearm_right_outputs(raw,bones,p);u=UnitData.parse(raw)
 f=dict(resource=fixture['avatar']['resource'],hashes=u.name_hashes,parents=u.parents,matrices=matrices(u))
 OUT.mkdir(exist_ok=True)
 (OUT/'synthetic-right-profile.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
 harness=harness[:harness.rindex('\nreturn {status=')]
 harness+='\nlocal right_profile='+lua(p)+'\nlocal right_fixture='+lua(f)+'\n'+(ROOT/'HD2PhysBoneCompat/test/native_grip_transfer_111_harness.lua').read_text(encoding='utf-8-sig')
 return profile,fixture,harness

def main():
 profile,fixture,harness=build_111_harness()
 r=plain(run_harness(profile,fixture,harness));logs=r.pop('logs')
 (OUT/'runtime-regression.log').write_text('\n'.join(logs),encoding='utf-8')
 (OUT/'runtime-regression.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
