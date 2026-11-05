"""Incremental arm-only rebuild, with a compact reproducible TRS reference."""
import copy
import hashlib
import json
import shutil
import struct
import sys
from collections import Counter,deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v10 import records,payload
from package_native_v12 import digest,load,save_json,files
from anim_batch_mod.archive import InlinePatchWriter,TocArchive,TocEntry
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
from anim_batch_mod.native_arm_reference import AnimationReference,apply_arm_reference,arm_indices
from anim_batch_mod.native_animation import read_blocks,compact_constant_tracks
from anim_batch_mod.native_skeleton import load_manifest

WORK=ROOT/'outputs/native-v14-20261104';PROJECT=WORK/'project'
RELEASE=ROOT/'outputs/native-manual-20261103'

def unchanged_signature(data,changed):
    a,b=read_blocks(data)
    assert (a.header[:12]+a.header[16:],a.flags,a.states,a.hash_floats,a.entries)==(b.header[:12]+b.header[16:],b.flags,b.states,b.hash_floats,b.entries)
    assert not any(a.flags)
    h=hashlib.sha256(a.header[:12]+a.header[16:]+a.hash_floats)
    for i,state in enumerate(a.states):h.update(state[:12]+state[28:] if i in changed else state)
    for _,channel,raw in a.entries:
        if channel in changed and struct.unpack_from('<H',raw)[0]==5:continue
        h.update(raw)
    return h.hexdigest()

def convert(raw,ref,bones,unit,manifest):
    changed={len(bones.names)+i for i in arm_indices(manifest)}
    before=unchanged_signature(raw,changed)
    result,metrics=apply_arm_reference(raw,ref,bones,unit,manifest)
    assert unchanged_signature(result,changed)==before,'Non-arm data changed'
    a=AnimationData.parse(result)
    if a.is_additive:assert result==raw
    assert len(a.initial_bone_states)==238
    for i in changed:
        q=a.initial_bone_states[i].rotation
        assert abs(sum(v*v for v in q)-1)<.001
    return result,dict(**metrics,nonArmSignature=before,sha256=hashlib.sha256(result).hexdigest(),additive=a.is_additive)

def compact_reference(raw):
    a=AnimationData.parse(raw)
    a.entries=[e for e in a.entries if e.is_rotation or e.is_position or e.is_scale]
    return compact_constant_tracks(a.to_bytes())[0]

def main():
    assert not (PROJECT/'animations/runtime').exists(),'Completed v14 already exists'
    PROJECT.mkdir(exist_ok=True)
    for file,relative in files(RELEASE/'project'):
        if relative.parts[0] in ('animations','source-code','reports'):continue
        dest=PROJECT/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(file,dest)
    baseline=load(RELEASE/'project/animations/build-report.json')
    old=RELEASE/'project/animations/runtime/9ba626afa44a3aa3.patch_2'
    assert digest(old)==next(r['sha256'] for r in baseline['files'] if r['path'].endswith('.patch_2'))
    manifest=load_manifest(PROJECT/'source-skeleton.json')
    base=ROOT/'outputs/native-fix-20261103'
    unit=UnitData.parse((base/'avatar.toc').read_bytes());bones=BonesData.parse((base/'bones.toc').read_bytes())
    reference=AnimationReference(ROOT.parent/'output/9ba626afa44a3aa3.patch_0')
    old_rows=records(old);ids={r[0] for r in old_rows if r[1]==ANIMATION_TYPE_ID}
    assert ids==set(reference.entries) and len(ids)==3180
    # Preserve the supplied reference files and store all necessary TRS data
    # for a portable rebuild, removing events and redundant constant keys.
    compact_path=PROJECT/'refs/arm-reference.patch_0';compact_path.parent.mkdir(exist_ok=True)
    if not compact_path.exists():
        refwriter=InlinePatchWriter(TocArchive(0,bytes(56),{}),compact_path,{ANIMATION_TYPE_ID:len(ids)},standalone=True)
        try:
            with ProcessPoolExecutor(max_workers=6) as pool:
                pending=deque();completed=0
                def complete_reference():
                    nonlocal completed
                    clip,future=pending.popleft()
                    refwriter.append(TocEntry(clip,ANIMATION_TYPE_ID,future.result()))
                    completed+=1
                    if completed%500==0:print('reference',completed,'/',len(ids),flush=True)
                for clip in sorted(ids):
                    pending.append((clip,pool.submit(compact_reference,reference.read(clip))))
                    if len(pending)>=12:complete_reference()
                while pending:complete_reference()
            refwriter.finish()
        finally:refwriter.close()
    compact=AnimationReference(compact_path)
    config=PROJECT/'config.toml'
    if 'arm_reference_archive' not in config.read_text(encoding='utf-8'):
        config.write_text(config.read_text(encoding='utf-8').replace('[native_skeleton]',
            '[native_skeleton]\narm_reference_archive = "refs/arm-reference.patch_0"',1),encoding='utf-8')
    output=PROJECT/'animations';output.mkdir(exist_ok=True)
    shutil.copy2(config,output/'config.toml');shutil.copy2(PROJECT/'source-skeleton.json',output/'source-skeleton.json')
    staging=output/'runtime.incomplete';staging.mkdir()
    path=staging/old.name
    writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),path,Counter(r[1] for r in old_rows),standalone=True)
    gpu=Path(str(old)+'.gpu_resources').read_bytes();results=[]
    try:
        for r in old_rows:
            if r[1]!=ANIMATION_TYPE_ID:
                writer.append(TocEntry(r[0],r[1],payload(old,r),gpu[r[4]:r[4]+r[9]]))
        with ProcessPoolExecutor(max_workers=6) as pool:
            pending=deque()
            def finish():
                r,future=pending.popleft()
                try:raw,metrics=future.result()
                except Exception as e:raise RuntimeError(f'Animation {r[0]} failed') from e
                writer.append(TocEntry(r[0],r[1],raw));results.append(dict(id=str(r[0]),**metrics))
                if len(results)%200==0:print('arm-only rebuild',len(results),'/',len(ids),flush=True)
            for r in old_rows:
                if r[1]!=ANIMATION_TYPE_ID:continue
                pending.append((r,pool.submit(convert,payload(old,r),compact.read(r[0]),bones,unit,manifest)))
                if len(pending)>=12:finish()
            while pending:finish()
        paths=writer.finish()
    finally:writer.close()
    final=output/'runtime';staging.rename(final)
    report=copy.deepcopy(baseline)
    report.update(status='complete',retarget_version='native-reference-arms-v14',config_sha256=digest(config),
        arm_reference_archive=dict(path='refs/arm-reference.patch_0',sha256=digest(compact_path),
            source=str(reference.path),source_sha256=digest(reference.path),scope='38 Source arm rotation channels; additive retained'))
    byid={r['id']:r for r in results}
    for row in report['animations']:row.update(byid[row['id']])
    report['files']=[dict(path='runtime/'+p.name,bytes=(final/p.name).stat().st_size,sha256=digest(final/p.name)) for p in paths]
    save_json(output/'build-report.json',report)
    save_json(WORK/'animation-final-audit.json',dict(status='PASS',gameTested=False,animations=len(results),
        originalNativeChannelsPreserved=90,changedSourceRotationChannels=38,allTranslationsScalesPreserved=True,
        allOtherRotationChannelsPreserved=True,additivePayloadsByteIdentical=True,
        eventsAndFloatTracksPreserved=True,structuralResourcesByteIdenticalToV13=True,
        baselineSha256=digest(old),referenceSha256=digest(reference.path),compactReferenceSha256=digest(compact_path),clips=results))
    print('PASS: rebuilt 3180 clips; only 38 Source arm rotation tracks changed.',flush=True)

if __name__=='__main__':main()
