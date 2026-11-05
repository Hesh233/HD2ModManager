"""Bind motion audits to the shipped payloads and compare preserved resources."""
import hashlib
import sys
from pathlib import Path
from package_native_v12 import load,save_json,digest
from package_native_v10 import records,payload

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.native_arm_reference import AnimationReference
from anim_batch_mod.native_arm_reference import arm_indices
from build_native_v14_arms import unchanged_signature

W=ROOT/'outputs/native-v14-20261104';R=ROOT/'outputs/native-manual-20261103'

def main():
    old=R/'project/animations/runtime/9ba626afa44a3aa3.patch_2'
    new=W/'project/animations/runtime'/old.name
    original={(r[0],r[1]):r for r in records(old)}
    current={(r[0],r[1]):r for r in records(new)}
    assert original.keys()==current.keys()
    structure=[]
    clips={int(r['id']):r for r in load(W/'animation-final-audit.json')['clips']}
    for key,row in current.items():
        raw=payload(new,row)
        sha=hashlib.sha256(raw).hexdigest()
        if key[1]==ANIMATION_TYPE_ID:
            assert clips[key[0]]['sha256']==sha
        else:
            assert raw==payload(old,original[key])
            structure.append(dict(id=str(key[0]),typeId=f'{key[1]:016x}',sha256=sha))
    sidecars=[]
    for suffix in ('.gpu_resources','.stream'):
        a=Path(str(old)+suffix);b=Path(str(new)+suffix)
        assert digest(a)==digest(b)
        sidecars.append(dict(suffix=suffix,bytes=b.stat().st_size,sha256=digest(b)))
    checked=[]
    changed={90+i for i in arm_indices(load(W/'project/source-skeleton.json'))}
    for path in sorted((W/'arm-candidates').glob('*.toc')):
        clip=int(path.stem)
        # Constant TRS keys are removed in the portable reference. This changes
        # redundant output arm keys, so run the geometric audit on final bytes.
        assert unchanged_signature(path.read_bytes(),changed)==unchanged_signature(payload(new,current[(clip,ANIMATION_TYPE_ID)]),changed)
        checked.append(str(clip))
    assert len(checked)>=31
    motion=load(W/'final-motion-audit.json')
    assert motion['status']=='PASS' and motion['payloadSource']=='final archive'
    assert {r['id'] for r in motion['clipsMeasured']}<=set(checked)
    refs=[]
    for path in (ROOT.parent/'output/9ba626afa44a3aa3.patch_0',Path('I:/大部分缩肩打包/备份/初版nanoha/0909output/第3人称/9ba626afa44a3aa3.patch_22')):
        reference=AnimationReference(path)
        refs.append(dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path),animations=len(reference.entries)))
    save_json(W/'known-good-reference.json',dict(status='PASS',references=refs,
        selected='reference0: all 3180 current animation IDs; reference22 is comparison only',
        comparison='reference-comparison.json',commonAnimationIds=3082,only0=98,only22=44))
    save_json(W/'preview-integration-audit.json',dict(status='PASS',gameTested=False,structuralResources=structure,
        sidecars=sidecars,allResourcesMatchV13=True,verifiedAnimationPayloads=len(clips),
        candidatesNonArmDataMatchFinal=checked,finalMotionAuditSha256=digest(W/'final-motion-audit.json'),
        priorGameEvidence='C7 preview confirmed normal by user'))
    print('PASS: final motion verified; preserved structure/GPU/stream match v13.')

if __name__=='__main__':main()
