"""Audit serialized configured attachment chains under all production masks."""
import copy,json,math,struct,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import load_manifest,append_unit,append_bones,append_state_machine_masks,convert_clip
from anim_batch_mod.processor import WorldTransform,ModConfig,_compose_additive_local,_calculate_world_transforms,modify_animation_with_world_compensation
from anim_batch_mod.math3d import quat_slerp,quat_inverse,quat_multiply,quat_rotate,vec_sub
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=load_manifest(P/'source-skeleton.json')
profile=json.loads((P/'attachment-profile.json').read_text(encoding='utf-8'))
assert m['attachmentReferenceMode']=='blended-configured-chain'
eu=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
state,_=append_state_machine_masks((B/'state-machine.toc').read_bytes(),b,m)
cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
mapping=[u.name_hashes.index(h) for h in b.hashes];extended_mapping=[eu.name_hashes.index(h) for h in eb.hashes]
rawbase=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[i].position),list(u.transforms[i].rotation),[1.,1.,1.],False,False,False) for i in mapping],animation_length=.033,is_additive=False)
def configure(a):
    a=copy.deepcopy(a)
    if opts.get('apply_driver_config',True):
        modify_animation_with_world_compensation(a,b,u,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=opts.get('rotate_multipliers',False),apply_rotation_compensations=opts.get('rotation_compensation',False),apply_ik_correction=opts.get('ik_correction',False))
    # The actual converter serializes its configured result to float32 too.
    return AnimationData.parse(a.to_bytes())
def convert(a):return AnimationData.parse(convert_clip(a.to_bytes(),b,u,m,cfg,opts)[0])
def localpose(a,unit,indices):
    out=copy.deepcopy(unit.transforms)
    for i,s in zip(indices,a.initial_bone_states):out[i]=WorldTransform(s.position,s.rotation,s.scale)
    return out
def blended(base,delta,indices,weights):
    out=copy.deepcopy(base)
    for ai,(i,s) in enumerate(zip(indices,delta.initial_bone_states)):
        w=weights[ai];d=WorldTransform([v*w for v in s.position],quat_slerp([0.,0.,0.,1.],s.rotation,w),[v*w for v in s.scale])
        out[i]=_compose_additive_local(base[i],d)
    return out
def relative(world,anchor,target):
    a=world[anchor];t=world[target];qi=quat_inverse(a.rotation)
    return WorldTransform(quat_rotate(qi,vec_sub(t.position,a.position)),quat_multiply(qi,t.rotation),[1.,1.,1.])
def angle(a,c):
    dot=abs(sum(x*y for x,y in zip(a,c)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in c))
    return math.degrees(2*math.acos(min(1.,max(-1.,dot))))
base=convert(rawbase);cbase=configure(rawbase)
alocal=localpose(base,eu,extended_mapping);clocal=localpose(cbase,u,mapping)
ainitial=_calculate_world_transforms(alocal,eu.parents);cinitial=_calculate_world_transforms(clocal,u.parents)
count,offset=struct.unpack_from('<II',state,28);weights=[]
for mask in range(count):
    at=offset+struct.unpack_from('<I',state,offset+4+4*mask)[0];n=struct.unpack_from('<I',state,at)[0]
    assert n==len(eb.names);weights.append(struct.unpack_from(f'<{n}f',state,at+4))
refs=[r for r in profile['vpk'] if r.get('policy')=='source-blended-reference']
assert len(refs)==24
by_driver={r['index']:eu.name_hashes.index(r['hash']) for r in m['sourceAttachmentShadows']}
for r in refs:
    assert r['sourceReferenceIndex']==by_driver[r['index']]
    assert r['configuredAnchorIndex']==by_driver.get(r['driverAnchorIndex'],r['driverAnchorIndex'])
for r in m['sourceAttachmentShadows']:
    ai=eb.hashes.index(r['hash']);oi=r['animationChannel']
    if oi is not None:assert all(w[ai]==w[oi] for w in weights)
maximum_position=0.;maximum_angle=0.;suppression_max=0.;suppression_checks=0;worst=None;rows=[];cases=0
drivers=['r_clavicle','r_shoulder','r_elbow','r_hand','attach_weapon']+['cape'+str(i) for i in range(1,8)]
for driver in drivers:
    driver_index=b.names.index(driver)
    driver_max=0.
    for kind in ('rotation','translation'):
        for axis in range(3):
            delta=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in b.names],animation_length=.033,is_additive=True)
            if kind=='rotation':
                q=[0.,0.,0.,math.cos(math.radians(10)/2)];q[axis]=math.sin(math.radians(10)/2);delta.initial_bone_states[driver_index].rotation=q
            else:delta.initial_bone_states[driver_index].position[axis]=.1
            actual_delta=convert(delta);configured_delta=configure(delta)
            for mask,ws in enumerate(weights):
                aw=_calculate_world_transforms(blended(alocal,actual_delta,extended_mapping,ws),eu.parents)
                cw=_calculate_world_transforms(blended(clocal,configured_delta,mapping,ws[:len(b.names)]),u.parents)
                cases+=1
                for r in refs:
                    a=relative(aw,r['configuredAnchorIndex'],r['sourceReferenceIndex']);c=relative(cw,r['driverAnchorIndex'],r['index'])
                    dp=math.dist(a.position,c.position);dq=angle(a.rotation,c.rotation)
                    if dp>maximum_position:maximum_position=dp;worst={'driver':driver,'kind':kind,'axis':axis,'mask':mask,'attachment':r.get('standardName'),'positionErrorMetres':dp}
                    maximum_angle=max(maximum_angle,dq);driver_max=max(driver_max,dp)
                    ci=relative(cinitial,r['driverAnchorIndex'],r['index'])
                    if ws[driver_index]==0 and math.dist(c.position,ci.position)<1e-7 and angle(c.rotation,ci.rotation)<1e-4:
                        ai=relative(ainitial,r['configuredAnchorIndex'],r['sourceReferenceIndex'])
                        suppression_checks+=1;suppression_max=max(suppression_max,math.dist(a.position,ai.position))
    rows.append({'driver':driver,'maxRelativePositionErrorMetres':driver_max})
report={'validationStatus':'COMPLETE','attachmentFusionStatus':'PASS' if maximum_position<2e-6 and maximum_angle<1e-3 and suppression_max<2e-6 else 'FAIL','gameTested':False,'weaponConsumerTimingVerified':False,'maskCount':count,'cases':cases,'referenceComparisons':cases*len(refs),'configuredNodes':len(by_driver),'avatarNodes':len(eu.transforms),'channels':len(eb.names),'maxRelativePositionErrorMetres':maximum_position,'maxRelativeRotationErrorDegrees':maximum_angle,'suppressionChecks':suppression_checks,'maxSuppressedRelativeMovementMetres':suppression_max,'worst':worst,'drivers':rows,'scope':'production serialized Unit/Bones/masks and converter; single 10 degree / 10 cm additive inputs; compare post-blend configured copy relative poses against complete configured skeleton with identical masks; weapon game consumer and procedural timing not asserted'}
report['status']=report['attachmentFusionStatus']
(W/'attachment-fusion-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
assert report['attachmentFusionStatus']=='PASS'
