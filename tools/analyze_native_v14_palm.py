"""Measure the Source/HD2 palm basis and grip offset from skeletal landmarks."""
import json
import math
from pathlib import Path
from prepare_native_v13_arms import calibration
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.processor import _calculate_world_transforms,_cross
from anim_batch_mod.math3d import quat_rotate,quat_multiply,quat_inverse,quat_inverse_rotate,vec_sub

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'outputs/native-v14-20261104'

def dot(a,b):return sum(x*y for x,y in zip(a,b))
def norm(a):return math.sqrt(dot(a,a))
def normal(a):return [x/norm(a) for x in a]
def palm(worlds,ids,side):
    wrist=worlds[ids[side+'_hand']]
    middle=vec_sub(worlds[ids[side+'_middle_finger1']].position,wrist.position)
    width=vec_sub(worlds[ids[side+'_index_finger1']].position,worlds[ids[side+'_pinky_finger1']].position)
    x=normal(middle);y=normal(vec_sub(width,[a*dot(width,x) for a in x]));z=_cross(x,y)
    return wrist,(x,y,z),(norm(middle),norm(width))

def main():
    project=ROOT/'outputs/native-manual-20261103/project'
    manifest=native.load_manifest(project/'source-skeleton.json')
    chains,_,_=calibration(project)
    base=ROOT/'outputs/native-fix-20261103'
    unit=UnitData.parse((base/'avatar.toc').read_bytes());bones=BonesData.parse((base/'bones.toc').read_bytes())
    nw=_calculate_world_transforms(unit.transforms,unit.parents)
    sw=[native.row_pose(n['world']) for n in manifest['bones']]
    ni={name:unit.name_hashes.index(h) for name,h in zip(bones.names,bones.hashes)}
    si={n['driver']:i for i,n in enumerate(manifest['bones']) if n['driver']}
    result=[]
    for chain in chains:
        side=chain['side'];s,sa,ss=palm(sw,si,side);n,na,ns=palm(nw,ni,side)
        old=quat_multiply(n.rotation,chain['handCalibration'])
        swung=quat_multiply(native._swing_between(sa[0],na[0]),s.rotation)
        transformed_y=quat_rotate(quat_multiply(swung,quat_inverse(s.rotation)),sa[1])
        delta=quat_multiply(native._swing_between(transformed_y,na[1]),quat_multiply(swung,quat_inverse(s.rotation)))
        new=quat_multiply(delta,s.rotation)
        # Normalize the native palm contact point by palm length/width. Thickness
        # uses the mean linear scale; this remains an explicit game-test candidate.
        marker=unit.transforms[ni['attach_hand_'+side]].position
        native_offset=quat_rotate(n.rotation,marker)
        scales=[ss[0]/ns[0],ss[1]/ns[1],math.sqrt(ss[0]*ss[1]/(ns[0]*ns[1]))]
        src_world_offset=[sum(sa[j][k]*dot(native_offset,na[j])*scales[j] for j in range(3)) for k in range(3)]
        source_offset=quat_inverse_rotate(s.rotation,src_world_offset)
        old_world_offset=quat_rotate(old,source_offset)
        new_world_offset=quat_rotate(new,source_offset)
        difference=math.degrees(2*math.acos(min(1,abs(dot(old,new)))))
        row=dict(side=side,palmRollCorrectionDegrees=difference,
                 sourcePalmDimensions=ss,nativePalmDimensions=ns,dimensionRatios=scales,
                 sourceGripOffset=source_offset,nativeGripOffset=marker,
                 handCalibration=quat_multiply(quat_inverse(n.rotation),new),
                 wristTranslationForCoincidentPalm=vec_sub(native_offset,new_world_offset),
                 previousPalmWorldOffset=old_world_offset)
        result.append(row)
    (WORK/'palm-calibration.json').write_text(json.dumps(dict(status='MEASURED',gameTested=False,rows=result),indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
