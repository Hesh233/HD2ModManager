import copy
from pathlib import Path
from package_native_v12 import load,save_json,lua
from prepare_native_v13_arms import calibration
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_inverse_rotate,vec_sub
from anim_batch_mod.processor import _calculate_world_transforms,_cross
from anim_batch_mod.formats import UnitData,BonesData

ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'outputs/native-v14-20261104';PROJECT=WORK/'project'

def main():
    profile=load(PROJECT/'attachment-profile.json')
    chains,_,_=calibration(PROJECT)
    base=ROOT/'outputs/native-fix-20261103'
    unit=UnitData.parse((base/'avatar.toc').read_bytes());bones=BonesData.parse((base/'bones.toc').read_bytes())
    names={n:unit.name_hashes.index(h) for n,h in zip(bones.names,bones.hashes)}
    world=_calculate_world_transforms(unit.transforms,unit.parents)
    palms={r['side']:r for r in load(WORK/'palm-calibration.json')['rows']}
    for chain in chains:
        palm=palms[chain['side']]
        chain['armFrame']='reference'
        a,b,c=[world[chain[k]] for k in ('nativeUpper','nativeForearm','nativeHand')]
        normal=_cross(vec_sub(b.position,a.position),vec_sub(c.position,b.position))
        chain['forearmHingeAxis']=quat_inverse_rotate(quat_multiply(b.rotation,chain['forearmCalibration']),normal)
        chain['nativeGrip']=names['attach_hand_'+chain['side']]
        chain['nodes'].append(dict(name='attach_hand_'+chain['side'],index=chain['nativeGrip']))
        chain['handCalibration']=palm['handCalibration']
        chain['sourceGripOffset']=palm['sourceGripOffset']
        chain['sourceGripRotation']=quat_multiply(quat_inverse(chain['handCalibration']),unit.transforms[chain['nativeGrip']].rotation)
    profile.update(revision='test01-v14-A',armSync=False,armGripSync=False,armChains=chains)
    save_json(PROJECT/'attachment-profile.json',profile)
    for label,enabled in [('A',False),('B5',True)]:
        p=copy.deepcopy(profile);p.update(revision='test01-v14-'+label,armSync=enabled,armGripSync=enabled)
        save_json(PROJECT/'ab-profiles'/f'{label}.json',p)
    (ROOT/'HD2PhysBoneCompat/src/native_attachment_profile.lua').write_text('-- Generated test01 v14 A profile.\nreturn '+lua(profile)+'\n',encoding='utf-8')
    print('v14 A / B5 arm and palm profiles prepared')

if __name__=='__main__':main()
