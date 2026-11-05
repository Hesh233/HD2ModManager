# Historical failure reproduction: uses the saved pre-chain-fix manifest/config.
# For the final v7 acceptance audit run audit_native_v7_attachment_fusion.py.
"""Isolate motion leaking through reparented Source attachment references."""
import copy,json,math,struct,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import load_manifest,append_unit,append_bones,append_state_machine_masks,convert_clip
from anim_batch_mod.processor import WorldTransform,ModConfig,_compose_additive_local,_calculate_world_transforms
from anim_batch_mod.math3d import quat_slerp
W=ROOT/'outputs/native-v7-20261104';P=W/'attempts/animations-before-additive-basis';B=ROOT/'outputs/native-fix-20261103'
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=load_manifest(P/'source-skeleton.json')
if m.get('attachmentReferenceMode')=='blended-configured-chain':
    raise SystemExit('This is the legacy baked-offset reproducer. Use audit_native_v7_attachment_fusion.py for blended-configured-chain; pre-fix evidence is attachment-mask-pre-fix-review.json.')
eu=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
state,_=append_state_machine_masks((B/'state-machine.toc').read_bytes(),b,m)
cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
rawbase=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[u.name_hashes.index(h)].position),list(u.transforms[u.name_hashes.index(h)].rotation),[1.,1.,1.],False,False,False) for h in b.hashes],animation_length=.033,is_additive=False)
base=AnimationData.parse(convert_clip(rawbase.to_bytes(),b,u,m,cfg,opts)[0])
alllocal=copy.deepcopy(eu.transforms)
for h,s in zip(eb.hashes,base.initial_bone_states):alllocal[eu.name_hashes.index(h)]=WorldTransform(s.position,s.rotation,s.scale)
initial=_calculate_world_transforms(alllocal,eu.parents)
count,offset=struct.unpack_from('<II',state,28);weights=[]
for mask in range(count):
    at=offset+struct.unpack_from('<I',state,offset+4+4*mask)[0];n=struct.unpack_from('<I',state,at)[0]
    assert n==len(eb.names);weights.append(struct.unpack_from(f'<{n}f',state,at+4))
wr=next(r for r in m['sourceAttachmentShadows'] if r['standardName']=='attach_weapon')
sourcehand=next(n for n in m['bones'] if n['driver']=='r_hand')
watched={'nativeHand':eu.name_hashes.index(b.hashes[b.names.index('r_hand')]),'nativeWeapon':wr['index'],'sourceHand':eu.name_hashes.index(sourcehand['hash']),'sourceWeapon':eu.name_hashes.index(wr['hash'])}
def angle(a,c):
    dot=abs(sum(x*y for x,y in zip(a,c)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in c))
    return math.degrees(2*math.acos(min(1.,max(-1.,dot))))
rows=[]
for driver in ('r_shoulder','r_elbow','r_hand'):
    for axis in range(3):
        delta=AnimationData(initial_bone_states=[AnimationBoneState([0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.],False,False,False) for _ in b.names],animation_length=.033,is_additive=True)
        q=[0.,0.,0.,math.cos(math.radians(10)/2)];q[axis]=math.sin(math.radians(10)/2)
        delta.initial_bone_states[b.names.index(driver)].rotation=q
        converted=AnimationData.parse(convert_clip(delta.to_bytes(),b,u,m,cfg,opts)[0])
        for mask,ws in enumerate(weights):
            if not all(ws[b.names.index(n)]==0 for n in ('r_shoulder','r_elbow','r_hand')) or ws[b.names.index('attach_weapon')]!=1:continue
            local=copy.deepcopy(alllocal)
            for ai,(h,s) in enumerate(zip(eb.hashes,converted.initial_bone_states)):
                i=eu.name_hashes.index(h);w=ws[ai]
                d=WorldTransform([v*w for v in s.position],quat_slerp([0.,0.,0.,1.],s.rotation,w),[v*w for v in s.scale])
                local[i]=_compose_additive_local(alllocal[i],d)
            world=_calculate_world_transforms(local,eu.parents)
            row={'driver':driver,'axis':axis,'mask':mask,'inputRotationDegrees':10,'weights':{n:ws[b.names.index(n)] for n in ('chest','r_shoulder','r_elbow','r_hand','attach_weapon')}}
            for name,i in watched.items():row[name]={'positionMetres':math.dist(world[i].position,initial[i].position),'rotationDegrees':angle(world[i].rotation,initial[i].rotation)}
            assert max(row[n]['positionMetres'] for n in ('nativeHand','nativeWeapon','sourceHand'))<1e-6
            rows.append(row)
maxpos=max(r['sourceWeapon']['positionMetres'] for r in rows);maxrot=max(r['sourceWeapon']['rotationDegrees'] for r in rows)
report={'validationStatus':'COMPLETE','attachmentMaskStatus':'FAIL_LEAKAGE' if maxpos>1e-6 or maxrot>1e-3 else 'PASS','gameTested':False,'sourceWeaponParent':wr['driverAnchorName'],'nativeWeaponParentIndex':u.parents[wr['index']],'cases':len(rows),'maxSourceWeaponPositionMetres':maxpos,'maxSourceWeaponRotationDegrees':maxrot,'scope':'10 degree additive right arm rotation under real masks which disable the full right arm while keeping attach_weapon enabled; all three hands/native weapon must remain stationary','results':rows}
(W/'attachment-mask-pre-fix-review.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2));print(json.dumps(rows[0],indent=2))
