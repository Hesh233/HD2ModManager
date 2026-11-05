"""Independent FK checks for actual sampled GUI-generated model/animation/Lua packages."""
import json,sys,math,zipfile,hashlib
from pathlib import Path
from prepare_native_v31_b23 import ROOT
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform,_compose_additive_local
from anim_batch_mod.math3d import quat_multiply,quat_rotate
from anim_batch_mod.native_skeleton import bone_name_hash

for folder in map(Path,sys.argv[1:]):
    folder=folder.resolve();manifest_path=folder/'animations/source-skeleton.json'
    m=json.loads(manifest_path.read_text(encoding='utf-8-sig'));cal=m['weaponGripCalibration']
    patch=next((folder/'animations/runtime').glob('*.patch_2'));a=TocArchive.parse_parts(patch.read_bytes(),Path(str(patch)+'.gpu_resources').read_bytes(),Path(str(patch)+'.stream').read_bytes())
    u=UnitData.parse(next(e.toc_data for e in a.entries.values() if e.type_id==UNIT_TYPE_ID))
    b=BonesData.parse(next(e.toc_data for e in a.entries.values() if e.type_id==BONE_TYPE_ID))
    mapping=[u.name_hashes.index(h) for h in b.hashes];tested=0;maxError=0
    for e in a.entries.values():
        if e.type_id!=ANIMATION_TYPE_ID:continue
        clip=AnimationData.parse(e.toc_data)
        if clip.is_additive:continue
        tracks=_build_tracks(clip)
        for time in [0.,clip.animation_length*500.,clip.animation_length*1000.]:
            local=list(u.transforms)
            for channel,node in enumerate(mapping):local[node]=WorldTransform(*(t[channel].evaluate(time) for t in tracks))
            world=_calculate_world_transforms(local,u.parents)
            for row in cal['rows']:
                hand=world[u.name_hashes.index(m['bones'][row['handIndex']]['hash'])]
                original=next(s for s in m['attachmentShadows'] if s['index']==row['nativeIndex'])
                ref=u.name_hashes.index(original['hash']);output=row['nativeIndex']
                expected=[x+y for x,y in zip(hand.position,quat_rotate(quat_multiply(hand.rotation,row['axes']),local[ref].position))]
                carrier=u.name_hashes.index(m['bones'][row['manifestIndex']]['hash'])
                maxError=max(maxError,math.dist(world[output].position,expected),math.dist(world[carrier].position,world[ref].position));tested+=2
    assert maxError<1e-4,(folder,maxError)
    profile=json.loads(next((folder/'attachment').rglob('attachment-profile.json')).read_text(encoding='utf-8'))
    assert profile['leftGrip']['intent']['enabled'] and profile['performance']['strictConsumers'] and profile['previewGuard']['enabled']
    assert profile['runtimePolicyVersion']=='b23-1.0.8'
    naming=json.loads((folder/'animation-package/manifest.json').read_text(encoding='utf-8'))
    assert naming['Name']==f"[原比例混合动画]({Path(json.loads((folder/'simulation.json').read_text(encoding='utf-8'))['vpk']).stem})"
    assert naming['Description']=='[全量动作文件]'
    report={'status':'PASS','independentWorldChecks':tested,'maximumGripAndSwapPositionError':maxError,
        'runtimePoliciesEnabled':True,'animationName':naming['Name'],'description':naming['Description'],'gameTested':False}
    (folder/'independent-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
