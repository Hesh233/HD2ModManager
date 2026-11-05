"""Exercise real 80 blend masks against separated root/boss/hips motion."""
import copy,json,math,struct,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import load_manifest,append_unit,append_bones,append_state_machine_masks,convert_clip
from anim_batch_mod.processor import WorldTransform,ModConfig,_compose_additive_local,_calculate_world_transforms
from anim_batch_mod.math3d import quat_slerp
W=ROOT/'outputs/native-v7-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=load_manifest(P/'source-skeleton.json')
eu=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
state,_=append_state_machine_masks((B/'state-machine.toc').read_bytes(),b,m)
cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
rawbase=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[u.name_hashes.index(h)].position),list(u.transforms[u.name_hashes.index(h)].rotation),[1.,1.,1.],False,False,False) for h in b.hashes],animation_length=.033,is_additive=False)
base=AnimationData.parse(convert_clip(rawbase.to_bytes(),b,u,m,cfg,opts)[0])
assert len(base.initial_bone_states)==len(eb.names)
alllocal=copy.deepcopy(eu.transforms)
for h,s in zip(eb.hashes,base.initial_bone_states):alllocal[eu.name_hashes.index(h)]=WorldTransform(s.position,s.rotation,s.scale)
initial=_calculate_world_transforms(alllocal,eu.parents)
count,offset=struct.unpack_from('<II',state,28)
weights=[]
for mask in range(count):
    at=offset+struct.unpack_from('<I',state,offset+4+4*mask)[0];n=struct.unpack_from('<I',state,at)[0]
    assert n==len(eb.names);weights.append(struct.unpack_from(f'<{n}f',state,at+4))
rows=[];checks=0;max_suppressed=0.;max_angle_error=0.
for driver in ('root','boss','hips'):
    for axis in range(3):
        delta=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in b.names],animation_length=.033,is_additive=True)
        q=[0.,0.,0.,math.cos(math.radians(10)/2)];q[axis]=math.sin(math.radians(10)/2)
        delta.initial_bone_states[b.names.index(driver)].rotation=q
        converted=AnimationData.parse(convert_clip(delta.to_bytes(),b,u,m,cfg,opts)[0])
        for mask,ws in enumerate(weights):
            local=copy.deepcopy(alllocal)
            for ai,(h,s) in enumerate(zip(eb.hashes,converted.initial_bone_states)):
                i=eu.name_hashes.index(h);w=ws[ai]
                d=WorldTransform([v*w for v in s.position],quat_slerp([0.,0.,0.,1.],s.rotation,w),[v*w for v in s.scale])
                local[i]=_compose_additive_local(alllocal[i],d)
            world=_calculate_world_transforms(local,eu.parents)
            result={'driver':driver,'axis':axis,'mask':mask,'weight':ws[b.names.index(driver)]}
            for name,source_i in [('l_foot',58),('r_foot',62),('spine1',1)]:
                ni=eu.name_hashes.index(b.hashes[b.names.index(name)]);si=eu.name_hashes.index(m['bones'][source_i]['hash'])
                nd=math.dist(world[ni].position,initial[ni].position);sd=math.dist(world[si].position,initial[si].position)
                result[name]={'nativeMetres':nd,'sourceMetres':sd}
                if ws[b.names.index(driver)]==0 or driver=='hips' and name=='spine1':
                    checks+=1;max_suppressed=max(max_suppressed,sd)
                    assert sd<1e-6,(driver,axis,mask,name,nd,sd)
            if mask in (62,68) and axis==1:rows.append(result)
neutral=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in b.names],animation_length=.033,is_additive=True)
neutral=AnimationData.parse(convert_clip(neutral.to_bytes(),b,u,m,cfg,opts)[0])
neutral_error=max([abs(v) for s in neutral.initial_bone_states[90:] for v in s.position]+[abs(1-abs(s.rotation[3])) for s in neutral.initial_bone_states[90:]])
assert neutral_error<1e-6
report={'status':'PASS','gameTested':False,'maskCount':count,'cases':count*9,'suppressionChecks':checks,'maxSuppressedSourceMovementMetres':max_suppressed,'neutralAdditiveError':neutral_error,'modelScale':1.08,'motionLayers':2,'avatarNodes':len(eu.transforms),'channels':len(eb.names),'selectedCases':rows,'scope':'production converter/config with synthetic additive rotations across all actual blend masks; game state/consumer timing unverified'}
(W/'fusion-layer-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
