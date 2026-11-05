"""Controlled additive parent-motion probe using the actual mask table."""
import copy,json,math,struct,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import load_manifest,append_unit,append_bones,append_state_machine_masks,convert_clip
from anim_batch_mod.processor import WorldTransform,ModConfig,_compose_additive_local,_calculate_world_transforms
from anim_batch_mod.math3d import quat_slerp
from anim_batch_mod.constants import STATE_MACHINE_TYPE_ID
W=ROOT/'outputs/native-v6-analysis-20261104';P=ROOT/'outputs/native-v6-20261104/project';B=ROOT/'outputs/native-fix-20261103'
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=load_manifest(P/'source-skeleton.json')
eu=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
state,_=append_state_machine_masks((B/'state-machine.toc').read_bytes(),b,m)
with (P/'animations/runtime/9ba626afa44a3aa3.patch_2').open('rb') as f:
    header=f.read(72);nt,n=struct.unpack_from('<II',header,4);f.seek(72+nt*32)
    records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
    record=next(r for r in records if r[1]==STATE_MACHINE_TYPE_ID);f.seek(record[2]);actual=f.read(record[7])
assert actual==state
cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
rawbase=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[u.name_hashes.index(h)].position),list(u.transforms[u.name_hashes.index(h)].rotation),[1.,1.,1.],False,False,False) for h in b.hashes],animation_length=.033,is_additive=False)
base=AnimationData.parse(convert_clip(rawbase.to_bytes(),b,u,m,cfg,opts)[0])
alllocal=copy.deepcopy(eu.transforms)
for h,s in zip(eb.hashes,base.initial_bone_states):alllocal[eu.name_hashes.index(h)]=WorldTransform(s.position,s.rotation,s.scale)
initial=_calculate_world_transforms(alllocal,eu.parents)
def weights(i):
    _,o=struct.unpack_from('<II',state,28);s=o+struct.unpack_from('<I',state,o+4+4*i)[0]
    return struct.unpack_from('<232f',state,s+4)
rows=[]
for driver in ('boss','root','hips'):
    delta=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in b.names],animation_length=.033,is_additive=True)
    delta.initial_bone_states[b.names.index(driver)].rotation=[0.,math.sin(math.radians(10)/2),0.,math.cos(math.radians(10)/2)]
    converted=AnimationData.parse(convert_clip(delta.to_bytes(),b,u,m,cfg,opts)[0])
    for mask in (62,68):
        ws=weights(mask);local=copy.deepcopy(alllocal)
        for ai,(h,s) in enumerate(zip(eb.hashes,converted.initial_bone_states)):
            i=eu.name_hashes.index(h);w=ws[ai]
            d=WorldTransform([v*w for v in s.position],quat_slerp([0.,0.,0.,1.],s.rotation,w),[v*w for v in s.scale])
            local[i]=_compose_additive_local(alllocal[i],d)
        world=_calculate_world_transforms(local,eu.parents)
        row={'input':driver+' rotation 10 degrees about local Y','maskIndex0':mask,'nativeWeights':{n:ws[b.names.index(n)] for n in ('root','boss','hips','l_foot','r_foot')},'sourceHipsWeight':ws[90]}
        for n,source in [('l_foot','058'),('r_foot','062')]:
            native_i=eu.name_hashes.index(b.hashes[b.names.index(n)]);vpk_i=eu.name_hashes.index(m['bones'][int(source)]['hash'])
            row[n]={'nativeDisplacementMetres':math.dist(world[native_i].position,initial[native_i].position),'vpkDisplacementMetres':math.dist(world[vpk_i].position,initial[vpk_i].position)}
        rows.append(row)
report={'scope':'synthetic 10-degree parent rotation, production converter/config and actual mask weights; does not identify the mask active in the screenshot','stateMachineMatchesDeployedBytes':True,'results':rows}
(W/'mask-leak.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
