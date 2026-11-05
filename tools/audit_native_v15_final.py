"""Verify final shoulder origins, elbow motion, preserved bytes and live evidence."""
import math
import re
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v12 import load,save_json,digest
from package_native_v10 import records,payload
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import vec_sub
from anim_batch_mod.native_arm_reference import AnimationReference,apply_arm_reference

W=ROOT/'outputs/native-v15-20261104';R=ROOT/'outputs/native-manual-20261103'

def angle(a,b):
    dot=sum(x*y for x,y in zip(a,b));norm=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(math.acos(max(-1,min(1,dot/norm))))

def main():
    raw=(ROOT/'outputs/native-fix-20261103/avatar.toc').read_bytes();br=(ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes()
    manifest=native.load_manifest(W/'project/source-skeleton.json')
    original_unit=UnitData.parse(raw);original_bones=BonesData.parse(br)
    unit=UnitData.parse(native.append_unit(raw,manifest));bones=BonesData.parse(native.append_bones(br,manifest))
    ids={n['driver']:107+i for i,n in enumerate(manifest['bones']) if n['driver']}
    paths={'v15':W/'project/animations/runtime/9ba626afa44a3aa3.patch_2',
        'v14':R/'project/animations/runtime/9ba626afa44a3aa3.patch_2',
        'v13':R/'backups/v14-before-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'}
    tables={k:{(r[0],r[1]):r for r in records(p)} for k,p in paths.items()}
    assert tables['v15'].keys()==tables['v14'].keys()
    from anim_batch_mod.constants import ANIMATION_TYPE_ID
    retained=[]
    for key,row in tables['v15'].items():
        if key[1]!=ANIMATION_TYPE_ID:
            assert payload(paths['v15'],row)==payload(paths['v14'],tables['v14'][key]);retained.append(str(key[0]))
    for suffix in ('.stream','.gpu_resources'):
        assert digest(Path(str(paths['v15'])+suffix))==digest(Path(str(paths['v14'])+suffix))
    mapping=[unit.name_hashes.index(h) for h in bones.hashes]
    def world(tracks,t):
        local=list(unit.transforms)
        for ch,index in enumerate(mapping):local[index]=WorldTransform(*(tr[ch].evaluate(t) for tr in tracks))
        return _calculate_world_transforms(local,unit.parents)
    worst_origin=worst_rotation=worst_flex=worst_portable=0.;samples=0;rows=[]
    portable=AnimationReference(R/'project/refs/arm-reference.patch_0')
    for i,row in enumerate(load(ROOT/'outputs/native-v14-20261104/candidate-audit.json')['clipsMeasured']):
        clip=int(row['id']);key=(clip,ANIMATION_TYPE_ID)
        data={k:payload(p,tables[k][key]) for k,p in paths.items()}
        animations={k:AnimationData.parse(d) for k,d in data.items()};tracks={k:_build_tracks(a) for k,a in animations.items()}
        if i<3 or clip==15679743041498935277:
            rebuilt,_=apply_arm_reference(data['v13'],portable.read(clip),original_bones,original_unit,manifest,preserve_clavicles=True)
            tracks['portable']=_build_tracks(AnimationData.parse(rebuilt))
        max_origin=0.;widths=[]
        for frame in range(61):
            t=animations['v15'].animation_length*1000*frame/60
            worlds={k:world(tr,t) for k,tr in tracks.items()}
            for side in ('l','r'):
                a,b,c=[ids[side+'_'+j] for j in ('shoulder','elbow','hand')]
                error=math.dist(worlds['v15'][a].position,worlds['v13'][a].position)
                worst_origin=max(worst_origin,error);max_origin=max(max_origin,error)
                for index in (a,b,c):
                    qa,qb=worlds['v15'][index].rotation,worlds['v14'][index].rotation
                    rotation=2*min(angle(qa,qb),180-angle(qa,qb))
                    worst_rotation=max(worst_rotation,rotation)
                    if 'portable' in worlds:worst_portable=max(worst_portable,math.dist(worlds['portable'][index].position,worlds['v15'][index].position))
                flex={k:angle(vec_sub(worlds[k][b].position,worlds[k][a].position),vec_sub(worlds[k][c].position,worlds[k][b].position)) for k in ('v15','v14')}
                worst_flex=max(worst_flex,abs(flex['v15']-flex['v14']));samples+=1
            widths.append(math.dist(worlds['v15'][ids['l_shoulder']].position,worlds['v15'][ids['r_shoulder']].position))
        rows.append(dict(id=str(clip),maxShoulderOriginErrorMetres=max_origin,widthRange=[min(widths),max(widths)]))
    assert worst_origin<2e-6 and worst_rotation<.25 and worst_flex<.01 and worst_portable<1e-5,(worst_origin,worst_rotation,worst_flex,worst_portable)
    save_json(W/'motion-audit.json',dict(status='PASS',gameTested=False,clips=len(rows),samples=samples,
        maxShoulderOriginErrorMetres=worst_origin,maxV14WorldArmRotationDifferenceDegrees=worst_rotation,
        maxV14ElbowFlexionDifferenceDegrees=worst_flex,maxPortableRebuildPositionDifferenceMetres=worst_portable,
        structureAndSidecarsMatchV14=True,retainedStructuralResources=retained,rows=rows))
    log=Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2/hd2physbone.log')
    lines=log.read_text(encoding='utf-8-sig').splitlines()
    active=False;seen=[];before=[];after=[]
    for line in lines:
        if 'variant=' in line:active='variant=test01-v14-B5' in line
        if active and 'arm_consumer_readback phase=' in line:
            values=re.search(r'nodes=(\d+) missing=(\d+) position_error=([\d.]+) rotation_error_degrees=([\d.]+)',line)
            if values:
                record=dict(nodes=int(values[1]),missing=int(values[2]),positionError=float(values[3]),rotationErrorDegrees=float(values[4]))
                (after if 'phase=after_' in line else before).append(record)
                if len(seen)<4:seen.append(line)
    assert after and all(x['nodes']==6 and x['missing']==0 for x in after)
    save_json(W/'runtime-evidence.json',dict(status='PASS',source=str(log),sha256=digest(log),beforeSamples=len(before),afterSamples=len(after),
        maxBeforePositionError=max(x['positionError'] for x in before),maxAfterPositionError=max(x['positionError'] for x in after),
        evidence=seen,userObservedVisualChange=False,skinning='unobserved',nextProbe='B6: same solver, Chef update callback'))
    print('PASS:',len(rows),'clips;',samples,'shoulder/elbow samples; max arm angle delta',worst_rotation,flush=True)

if __name__=='__main__':main()
