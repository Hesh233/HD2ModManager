"""Compare actual shoulder origins across v13, v14 and the accepted references."""
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v12 import load,save_json
from package_native_v10 import records,payload
from anim_batch_mod.native_arm_reference import AnimationReference
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import quat_inverse_rotate,vec_sub

R=ROOT/'outputs/native-manual-20261103';W=ROOT/'outputs/native-v15-20261104'

def main():
    W.mkdir(exist_ok=True)
    manifest=native.load_manifest(R/'project/source-skeleton.json')
    raw=(ROOT/'outputs/native-fix-20261103/avatar.toc').read_bytes()
    braw=(ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes()
    unit=UnitData.parse(raw);bones=BonesData.parse(braw)
    expanded=UnitData.parse(native.append_unit(raw,manifest));eb=BonesData.parse(native.append_bones(braw,manifest))
    si={n['driver']:len(unit.transforms)+i for i,n in enumerate(manifest['bones']) if n['driver']}
    ni={name:unit.name_hashes.index(h) for name,h in zip(bones.names,bones.hashes)}
    paths={'v14':R/'project/animations/runtime/9ba626afa44a3aa3.patch_2',
        'v13':R/'backups/v14-before-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2'}
    tables={k:{r[0]:r for r in records(p)} for k,p in paths.items()}
    refs={'ref0':AnimationReference(ROOT.parent/'output/9ba626afa44a3aa3.patch_0'),
        'ref22':AnimationReference(Path('I:/大部分缩肩打包/备份/初版nanoha/0909output/第3人称/9ba626afa44a3aa3.patch_22'))}
    def read_world(a,u,b,t):
        tracks=_build_tracks(a);local=list(u.transforms)
        for ch,h in enumerate(b.hashes):local[u.name_hashes.index(h)]=WorldTransform(*(tr[ch].evaluate(t) for tr in tracks))
        return _calculate_world_transforms(local,u.parents)
    def measured(world,ids):
        chest=world[ids['chest']]
        positions={n:quat_inverse_rotate(chest.rotation,vec_sub(world[ids[n]].position,chest.position))
            for n in ('l_clavicle','r_clavicle','l_shoulder','r_shoulder','l_elbow','r_elbow','l_hand','r_hand')}
        return dict(width=math.dist(positions['l_shoulder'],positions['r_shoulder']),positions=positions)
    result=[]
    for row in load(ROOT/'outputs/native-v14-20261104/candidate-audit.json')['clipsMeasured']:
        clip=int(row['id']);animations={k:AnimationData.parse(payload(p,tables[k][clip])) for k,p in paths.items()}
        animations.update({k:AnimationData.parse(r.read(clip)) for k,r in refs.items() if clip in r.entries})
        frames=[]
        for f in range(9):
            t=animations['v14'].animation_length*1000*f/8
            data={k:measured(read_world(a,expanded if k.startswith('v') else unit,eb if k.startswith('v') else bones,t),si if k.startswith('v') else ni) for k,a in animations.items()}
            frames.append(dict(time=t,**data))
        result.append(dict(id=str(clip),frames=frames,
            maxShoulderDisplacement=max(math.dist(f['v13']['positions'][s+'_shoulder'],f['v14']['positions'][s+'_shoulder']) for f in frames for s in ('l','r')),
            widthRangeV14=[min(f['v14']['width'] for f in frames),max(f['v14']['width'] for f in frames)],
            widthRangeV13=[min(f['v13']['width'] for f in frames),max(f['v13']['width'] for f in frames)]))
    source={n['driver']:dict(local=n['local'],world=n['world']) for n in manifest['bones'] if n['driver'] in ('chest','l_clavicle','r_clavicle','l_shoulder','r_shoulder')}
    save_json(W/'shoulder-analysis.json',dict(status='MEASURED',gameTested=False,sourceBind=source,clips=result))
    for row in sorted(result,key=lambda x:-x['maxShoulderDisplacement'])[:10]:print({k:v for k,v in row.items() if k!='frames'})
    print('first-frame',result[0]['id'],{k:{'width':v['width'],'leftShoulder':v['positions']['l_shoulder'],'rightShoulder':v['positions']['r_shoulder']} for k,v in result[0]['frames'][0].items() if isinstance(v,dict)})

if __name__=='__main__':main()
