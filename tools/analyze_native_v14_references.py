"""Read-only comparison of requested working arm references and v13."""
import hashlib
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v10 import records,payload
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate,vec_sub
from anim_batch_mod.motion_skeleton import source_local

WORK=ROOT/'outputs/native-v14-20261104'
PROJECT=ROOT/'outputs/native-manual-20261103/project'
PATHS={'reference0':ROOT.parent/'output/9ba626afa44a3aa3.patch_0',
       'reference22':Path('I:/大部分缩肩打包/备份/初版nanoha/0909output/第3人称/9ba626afa44a3aa3.patch_22'),
       'v13':PROJECT/'animations/runtime/9ba626afa44a3aa3.patch_2'}

def angle(a,b):
    n=math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
    return math.degrees(2*math.acos(min(1.,abs(sum(x*y for x,y in zip(a,b)))/n)))

def summarize(values):
    values=sorted(values)
    return dict(max=max(values,default=0),p50=values[len(values)//2] if values else 0,
                p95=values[min(len(values)-1,int(len(values)*.95))] if values else 0)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate-directory',type=Path);parser.add_argument('--report-name');args=parser.parse_args()
    WORK.mkdir(exist_ok=True)
    base=ROOT/'outputs/native-fix-20261103'
    ub=(base/'avatar.toc').read_bytes();bb=(base/'bones.toc').read_bytes()
    unit=UnitData.parse(ub);bones=BonesData.parse(bb)
    manifest=native.load_manifest(PROJECT/'source-skeleton.json')
    extended=UnitData.parse(native.append_unit(ub,manifest))
    eb=BonesData.parse(native.append_bones(bb,manifest))
    indices={k:{r[0]:r for r in records(p) if r[1]==ANIMATION_TYPE_ID} for k,p in PATHS.items()}
    refids=set(indices['reference0'])&set(indices['reference22'])
    count=dict(common=len(refids),only0=len(set(indices['reference0'])-refids),only22=len(set(indices['reference22'])-refids))
    dmap=[unit.name_hashes.index(h) for h in bones.hashes]
    emap=[extended.name_hashes.index(h) for h in eb.hashes]
    byname={name:i for name,i in zip(bones.names,dmap)}
    smap={n['driver']:len(unit.transforms)+i for i,n in enumerate(manifest['bones']) if n['driver']}
    binds=[native.local_pose(source_local(n,i,manifest)) for i,n in enumerate(manifest['bones'])]
    dbind=_calculate_world_transforms(unit.transforms,unit.parents)
    refs,_=native._reference_rotations(manifest['bones'],binds,[native.row_pose(n['world']) for n in manifest['bones']],dbind,byname,manifest)
    calibrations={n['driver']:quat_multiply(quat_inverse(dbind[byname[n['driver']]].rotation),refs[i]) for i,n in enumerate(manifest['bones']) if n['driver']}
    clips=sorted(int(p.stem) for p in (ROOT/'outputs/native-v13-20261104/candidate-clips').glob('*.toc'))
    # Add evenly spaced shared clips, so the comparison is not limited to old elbow failures.
    shared=sorted(refids)
    clips=sorted(set(clips+[shared[int(i*(len(shared)-1)/23)] for i in range(24)]))
    def world(animation,t,is_source=False):
        u,mapping=(extended,emap) if is_source else (unit,dmap)
        local=list(u.transforms);tracks=_build_tracks(animation)
        for ch,i in enumerate(mapping):local[i]=WorldTransform(*(tr[ch].evaluate(t) for tr in tracks))
        return _calculate_world_transforms(local,u.parents)
    reports=[];metrics={}
    for clip in clips:
        animations={k:AnimationData.parse(payload(PATHS[k],idx[clip])) for k,idx in indices.items() if clip in idx}
        if args.candidate_directory and (args.candidate_directory/f'{clip}.toc').exists():
            animations['v13']=AnimationData.parse((args.candidate_directory/f'{clip}.toc').read_bytes())
        if any(a.is_additive for a in animations.values()):continue
        if max(a.animation_length for a in animations.values())-min(a.animation_length for a in animations.values())>.001:
            reports.append(dict(id=str(clip),durationMismatch={k:a.animation_length for k,a in animations.items()}));continue
        measured={}
        for frame in range(17):
            t=animations['v13'].animation_length*1000*frame/16
            worlds={k:world(a,t,k=='v13') for k,a in animations.items()}
            for side in ('l','r'):
                for joint,end in (('shoulder','elbow'),('elbow','hand')):
                    name=side+'_'+joint;endname=side+'_'+end
                    current=worlds['v13'];i,j=smap[name],smap[endname]
                    actual_vector=vec_sub(current[j].position,current[i].position)
                    source_offset=extended.transforms[j].position
                    for key in ('reference0','reference22'):
                        if key not in worlds:continue
                        expected=quat_multiply(worlds[key][byname[name]].rotation,calibrations[name])
                        expected_vector=quat_rotate(expected,source_offset)
                        swung=quat_multiply(native._swing_between(expected_vector,actual_vector),expected)
                        twist=angle(swung,current[i].rotation)
                        k=f'{key}_{name}_twistDegrees';measured.setdefault(k,[]).append(twist)
                        if joint=='elbow':
                            k=f'{key}_{side}_handPositionMetres'
                            measured.setdefault(k,[]).append(math.dist(current[j].position,worlds[key][byname[endname]].position))
                if 'reference22' in worlds:
                    for joint in ('clavicle','shoulder','elbow','hand'):
                        name=side+'_'+joint
                        k='reference0_vs_22_'+name
                        measured.setdefault(k,[]).append(angle(worlds['reference0'][byname[name]].rotation,worlds['reference22'][byname[name]].rotation))
        for k,v in measured.items():metrics.setdefault(k,[]).extend(v)
        reports.append(dict(id=str(clip),duration=animations['v13'].animation_length,measurements={k:summarize(v) for k,v in measured.items()}))
    result=dict(status='MEASURED',coverage=count,sampledClips=len(reports),sources={k:dict(path=str(p),animations=len(indices[k])) for k,p in PATHS.items()},
                measurements={k:summarize(v) for k,v in metrics.items()},clips=reports)
    filename=args.report_name or ('frame-reference-comparison.json' if args.candidate_directory else 'reference-comparison.json')
    (WORK/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('clips','sources')},indent=2),flush=True)

if __name__=='__main__':main()
