"""Restore v13 shoulder origins in v14; retain all other serialized tracks."""
import copy
import hashlib
import shutil
import sys
from collections import Counter,deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v12 import load,save_json,digest
from package_native_v10 import records,payload
from build_native_v14_arms import unchanged_signature
from anim_batch_mod.archive import InlinePatchWriter,TocArchive,TocEntry
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import AnimationData,BonesData
from anim_batch_mod.native_arm_reference import restore_clavicle_motion

W=ROOT/'outputs/native-v15-20261104';R=ROOT/'outputs/native-manual-20261103';P=W/'project'

def convert(raw,original,bones,manifest):
    ids={n['driver']:i+len(bones.names) for i,n in enumerate(manifest['bones']) if n['driver']}
    changed={ids[s+'_'+j] for s in ('l','r') for j in ('clavicle','shoulder')}
    signature=unchanged_signature(raw,changed)
    result=restore_clavicle_motion(raw,original,bones,manifest)
    assert unchanged_signature(result,changed)==signature
    additive=AnimationData.parse(result).is_additive
    if additive:assert result==raw
    return result,dict(sha256=hashlib.sha256(result).hexdigest(),nonFourChannelSignature=signature,additive=additive)

def main():
    output=P/'animations';output.mkdir(parents=True,exist_ok=True)
    assert not (output/'runtime').exists()
    for name in ('source-skeleton.json','config.toml'):
        shutil.copy2(R/'project'/name,P/name)
    config=P/'config.toml'
    config.write_text(config.read_text(encoding='utf-8').replace('[native_skeleton]',
        '[native_skeleton]\npreserve_arm_reference_clavicles = true',1),encoding='utf-8')
    shutil.copy2(config,output/'config.toml');shutil.copy2(P/'source-skeleton.json',output/'source-skeleton.json')
    manifest=load(P/'source-skeleton.json');bones=BonesData.parse((ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes())
    old=R/'project/animations/runtime/9ba626afa44a3aa3.patch_2'
    clavicle=R/'backups/v14-before-20261104/project/animations/runtime'/old.name
    baseline=load(R/'project/animations/build-report.json')
    assert digest(old)==next(r['sha256'] for r in baseline['files'] if r['path'].endswith('.patch_2'))
    rows=records(old);originals={r[0]:r for r in records(clavicle)}
    staging=output/'runtime.incomplete';staging.mkdir()
    writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),staging/old.name,Counter(r[1] for r in rows),standalone=True)
    gpu=Path(str(old)+'.gpu_resources').read_bytes();results=[]
    try:
        for r in rows:
            if r[1]!=ANIMATION_TYPE_ID:writer.append(TocEntry(r[0],r[1],payload(old,r),gpu[r[4]:r[4]+r[9]]))
        with ProcessPoolExecutor(max_workers=6) as pool:
            pending=deque()
            def finish():
                r,future=pending.popleft();data,metrics=future.result()
                writer.append(TocEntry(r[0],r[1],data));results.append(dict(id=str(r[0]),**metrics))
                if len(results)%400==0:print('Shoulder origins',len(results),'/ 3180',flush=True)
            for r in rows:
                if r[1]!=ANIMATION_TYPE_ID:continue
                pending.append((r,pool.submit(convert,payload(old,r),payload(clavicle,originals[r[0]]),bones,manifest)))
                if len(pending)>=12:finish()
            while pending:finish()
        paths=writer.finish()
    finally:writer.close()
    final=output/'runtime';staging.rename(final)
    report=copy.deepcopy(baseline);report.update(retarget_version='native-reference-arms-v15',config_sha256=digest(config),
        preserve_arm_reference_clavicles=True,clavicleBaselineSha256=digest(clavicle))
    byid={r['id']:r for r in results}
    for row in report['animations']:
        row.update(byid[row['id']]);row.update(clavicle_motion='original',arm_reference='accepted-segment-frame-v15',arm_reference_channels=0 if row['additive'] else 36)
    report['files']=[dict(path='runtime/'+p.name,bytes=(final/p.name).stat().st_size,sha256=digest(final/p.name)) for p in paths]
    save_json(output/'build-report.json',report)
    save_json(W/'animation-final-audit.json',dict(status='PASS',gameTested=False,animations=len(results),
        changedSourceRotationChannels=4,allTranslationsScalesPreserved=True,allOtherRotationsPreserved=True,
        native90AndEventsPreserved=True,additivePayloadsByteIdentical=True,clips=results))
    print('PASS: 3180 animations; only clavicle/shoulder rotations changed.',flush=True)

if __name__=='__main__':main()
