"""Production B3 companions: model-calibrated FP graph and immutable option markers.

Uses only the bundled standard library/math stack. No test model IDs, NumPy,
prototype logs, runtime scene changes or game-data writes.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import struct
from .formats import UnitData, BonesData
from .native_skeleton import bone_name_hash
from .processor import _calculate_world_transforms, WorldTransform
from .motion_skeleton import relative, matrix
from .math3d import quat_rotate, quat_inverse, quat_multiply, matrix3_columns_to_quaternion

SCHEMA = 'hd2-grip-switches-v1'
VERSION = '1.0.19'
FP_RESOURCE = 'd0cf4d493ca08bed'  # Audited engine FP avatar, not a model-specific ID.


def _affine(p):
    return [v for axis in ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)) for v in quat_rotate(p.rotation, axis)] + list(p.position)


def _norm(v):
    n = math.sqrt(sum(x*x for x in v))
    if not math.isfinite(n) or n < 1e-7:
        raise ValueError('Degenerate Source/native arm or palm frame')
    return [x/n for x in v]


def _palm(hand, middle, index, pinky):
    f = _norm([a-b for a,b in zip(middle,hand)])
    across = [a-b for a,b in zip(index,pinky)]
    dot = sum(a*b for a,b in zip(across,f))
    x = _norm([a-dot*b for a,b in zip(across,f)])
    cross = [f[1]*x[2]-f[2]*x[1],f[2]*x[0]-f[0]*x[2],f[0]*x[1]-f[1]*x[0]]
    return matrix3_columns_to_quaternion([f,x,cross])


def compile_dual_fp_graph(fp_raw, bones_raw, models, manifest, arm_roles, model_label):
    """Append a fresh unanimated Source domain, preserving native FP63/47 byte-for-byte.

    All verified arm resources may be alternative receivers. The runtime must
    identify exactly one native-matched arm per side, never require TP and FP
    alternatives to be simultaneously present.
    """
    fp, bones = UnitData.parse(fp_raw), BonesData.parse(bones_raw)
    if len(fp.parents)!=63 or len(bones.hashes)!=47 or len(set(fp.name_hashes))!=63:
        raise ValueError('Unsupported native FP graph: expected audited FP63/47')
    if not set(bones.hashes).issubset(fp.name_hashes):
        raise ValueError('FP channel identity mismatch')
    nodes = manifest['bones']
    for i, node in enumerate(nodes):
        parent = node['parent']
        if parent is not None and (type(parent) is not int or not 0 <= parent < i):
            raise ValueError('FP Source bones must be in parent-first order')
    assigned = [n.get('driver') for n in nodes if n.get('driver')]
    if len(set(assigned)) != len(assigned):
        raise ValueError('Duplicate FP Source driver assignment')
    arms = {k:v for k,v in arm_roles.items() if k in models and v in ('LeftArm','RightArm')}
    for resource in arms:
        if len(set(models[resource].name_hashes)) != len(models[resource].name_hashes):
            raise ValueError('Ambiguous FP receiver node hashes: ' + resource)
    if not arms or not all(any(v==role for v in arms.values()) for role in ('LeftArm','RightArm')):
        raise ValueError('Both verified Source arm consumers are required for FP packaging')
    # Prefer the target receivers with explicit sourceUnit provenance over prototypes.
    preferred = manifest.get('_fpPreferredArmTargets', {})
    right = preferred.get('RightArm')
    if right not in arms or arms[right]!='RightArm':
        right = sorted(k for k,v in arms.items() if v=='RightArm')[0]
    primary = models[right]
    mw = _calculate_world_transforms(primary.transforms,primary.parents)
    fw = _calculate_world_transforms(fp.transforms,fp.parents)
    lookup = {h:i for i,h in enumerate(primary.name_hashes)}
    children = {}
    for i,n in enumerate(nodes): children.setdefault(n['parent'],[]).append(i)
    selected = set()
    drivers = {n.get('driver'):i for i,n in enumerate(nodes) if n.get('driver')}
    for side in ('r','l'):
        if side+'_clavicle' not in drivers: raise ValueError('Source clavicle missing: '+side)
        stack = [drivers[side+'_clavicle']]
        while stack:
            i=stack.pop();n=nodes[i]
            if n.get('physics') or '_phys_' in n['name']: continue
            selected.add(i); stack.extend(children.get(i,[]))
    for i in list(selected):
        parent=nodes[i]['parent']
        while parent is not None:
            if nodes[parent].get('physics'): raise ValueError('FP Source arm has a physics-only ancestor')
            selected.add(parent);parent=nodes[parent]['parent']
    selected=sorted(selected)
    if not selected or len(selected)+64>65535: raise ValueError('Invalid FP Source graph size')
    names={bone_name_hash(n):n for n in bones.names}
    names.update({bone_name_hash(n):n for n in ('root','camera','recoil_offset','skeleton','boss','chest','l_clavicle','r_clavicle')})
    def native(name):
        h=bone_name_hash(name)
        if h not in fp.name_hashes: raise ValueError('Native FP node missing: '+name)
        idx=fp.name_hashes.index(h)
        return dict(name=name,hash=h,index=idx,parent=fp.parents[idx],bindWorld=_affine(fw[idx]))
    for i in selected:
        h=nodes[i]['hash']
        if h not in lookup or h in fp.name_hashes: raise ValueError('Source model node missing/hash collision')
        if any(abs(x-1.)>1e-4 for x in mw[lookup[h]].scale): raise ValueError('FP Source non-unit bone scale unsupported')
    shoulder_i=lookup[nodes[drivers['r_shoulder']]['hash']]
    native_shoulder=native('r_shoulder');recoil=native('recoil_offset')
    if recoil['index']!=7: raise ValueError('Native FP recoil entry changed')
    alignment=quat_multiply(fw[native_shoulder['index']].rotation,quat_inverse(mw[shoulder_i].rotation))
    worlds={}
    for i in selected:
        pose=copy.deepcopy(mw[lookup[nodes[i]['hash']]])
        delta=quat_rotate(alignment,[a-b for a,b in zip(pose.position,mw[shoulder_i].position)])
        pose.position=[a+b for a,b in zip(fw[native_shoulder['index']].position,delta)]
        pose.rotation=quat_multiply(alignment,pose.rotation);worlds[i]=pose
    entry_world=copy.deepcopy(fw[native_shoulder['index']]);entry_local=relative(fw[7],entry_world)
    entry_name='__hd2_fp_source_entry_'+manifest['boneNamespace']+'_r'
    entry_hash = bone_name_hash(entry_name)
    if entry_hash in fp.name_hashes or entry_hash in {nodes[i]['hash'] for i in selected}:
        raise ValueError('FP Source entry hash collision')
    entry=dict(name=entry_name,hash=entry_hash,index=63,parent=7,bindLocal=_affine(entry_local),bindWorld=_affine(entry_world))
    indices={i:64+j for j,i in enumerate(selected)};descriptors=[]
    for i in selected:
        n=nodes[i];parent=n['parent'];pi=indices.get(parent,63)
        local=relative(worlds[parent] if parent in indices else entry_world,worlds[i])
        driver=n.get('driver');fp_node=None
        if driver and driver[:2] in ('r_','l_') and bone_name_hash(driver) in bones.hashes:fp_node=native(driver)
        if driver is None and any(n['name'].endswith('zhandtwist_'+s) for s in ('r','l')):
            fp_node=native(('r' if n['name'].endswith('_r') else 'l')+'_hand_twist')
        model_indices={}
        for resource in arms:
            u=models[resource]
            if n['hash'] not in u.name_hashes: raise ValueError('FP receiver does not belong to Source rig: '+resource)
            model_indices[resource]=u.name_hashes.index(n['hash'])
        descriptors.append(dict(name=n['name'],hash=n['hash'],index=indices[i],parent=pi,modelIndex=lookup[n['hash']],modelParent=primary.parents[lookup[n['hash']]],driver=driver,native=fp_node,
                                bindLocal=_affine(local),bindWorld=_affine(worlds[i]),modelBindWorld=_affine(mw[lookup[n['hash']]]),modelIndices=model_indices))
    by_driver={n['driver']:n for n in descriptors if n['driver']};by_index={n['index']:n for n in descriptors};arm_specs={}
    for side in ('r','l'):
        keys=[side+'_'+k for k in ('hand','middle_finger1','index_finger1','pinky_finger1')]
        if any(k not in by_driver for k in keys+[side+'_shoulder',side+'_elbow']): raise ValueError('Complete Source arm/finger drivers required: '+side)
        source_positions=[mw[by_driver[k]['modelIndex']].position for k in keys]
        native_positions=[fw[native(k)['index']].position for k in keys]
        registration=quat_multiply(_palm(*native_positions),quat_inverse(_palm(*source_positions)))
        hand=by_driver[side+'_hand'];hand_pose=mw[hand['modelIndex']]
        descendants=set();stack=[hand['index']]
        while stack:
            idx=stack.pop();descendants.add(idx);stack.extend(n['index'] for n in descriptors if n['parent']==idx)
        for n in descriptors:
            if n['index'] in descendants and n['native']:
                q=quat_multiply(registration,mw[n['modelIndex']].rotation)
                n['rotationReferenceWorld']=_affine(WorldTransform(n['bindWorld'][9:],q,[1.,1.,1.]))
        contact=[(a+b)/2-c for a,b,c in zip(source_positions[2],source_positions[1],hand_pose.position)]
        contact=quat_rotate(quat_inverse(hand_pose.rotation),contact)
        elbow=by_driver[side+'_elbow'];forearm_q=quat_multiply(quat_inverse(hand_pose.rotation),mw[elbow['modelIndex']].rotation)
        twists=[]
        for n in descriptors:
            if n['name'].endswith('zhandtwist_'+side):
                q=quat_multiply(quat_inverse(hand_pose.rotation),mw[n['modelIndex']].rotation)
                twists.append(dict(index=n['index'],handToTwistRotation=_affine(WorldTransform([0.,0.,0.],q,[1.,1.,1.]))))
        upper=math.sqrt(sum(v*v for v in elbow['bindLocal'][9:]));lower=math.sqrt(sum(v*v for v in hand['bindLocal'][9:]))
        if min(upper,lower)<.001: raise ValueError('Degenerate FP Source limb length')
        arm_specs[side]=dict(shoulder=by_driver[side+'_shoulder']['index'],elbow=elbow['index'],hand=hand['index'],sourceContactLocal=contact,
                            nativeContactIndices=[native(side+'_index_finger1')['index'],native(side+'_middle_finger1')['index']],upperMetres=upper,forearmMetres=lower,maxShoulderShift=.25,
                            handToForearmRotation=_affine(WorldTransform([0.,0.,0.],forearm_q,[1.,1.,1.])),twistNodes=twists)
    def wire(v): return v[:3]+[0.]+v[3:6]+[0.]+v[6:9]+[0.]+v[9:]+[1.]
    rows=[dict(name=n['name'],hash=n['hash'],index=0,sourceParent=n['parent'],localMatrix=wire(n['bindLocal']),worldMatrix=wire(n['bindWorld'])) for n in [entry]+descriptors]
    from .attachment_skeleton import append_unit_shadows
    expanded=append_unit_shadows(fp_raw,{'sourceAttachmentShadows':rows});after=UnitData.parse(expanded)
    if after.name_hashes[:63]!=fp.name_hashes or after.parents[:63]!=fp.parents or after.bones_ref!=fp.bones_ref or after.state_machine_ref!=fp.state_machine_ref:
        raise ValueError('FP native hierarchy/animation references changed')
    old,new=struct.unpack_from('<I',fp_raw,52)[0],struct.unpack_from('<I',expanded,52)[0]
    for block in (0,1):
        if fp_raw[old+16+block*63*64:old+16+block*63*64+63*64]!=expanded[new+16+block*len(after.parents)*64:new+16+block*len(after.parents)*64+63*64]:raise ValueError('FP native bind matrix changed')
    prefix = bytearray(expanded[:len(fp_raw)]); prefix[52:56] = fp_raw[52:56]
    if prefix != fp_raw or len(after.parents) != 64 + len(selected):
        raise ValueError('FP native payload changed outside the transform pointer')
    old_parents = old + 16 + 128 * 63
    new_parents = new + 16 + 128 * len(after.parents)
    if fp_raw[old_parents:old_parents+4*63] != expanded[new_parents:new_parents+4*63]:
        raise ValueError('FP native parent records changed')
    if set(n['hash'] for n in [entry]+descriptors)&set(bones.hashes):raise ValueError('FP Source output accidentally animated')
    receivers=[]
    for rid,role in sorted(arms.items()):
        side='r' if role=='RightArm' else 'l';u=models[rid];matches=[]
        for joint in ('shoulder','elbow','hand'):
            name=side+'_'+joint;h=bone_name_hash(name)
            if h not in u.name_hashes:raise ValueError('FP receiver native identity missing: '+rid)
            matches.append(dict(name=name,index=u.name_hashes.index(h),fpIndex=native(name)['index']))
        receivers.append(dict(resource=rid,count=len(u.parents),nativeMatches=matches,sourceRole=side))
    primary_receiver=next(x for x in receivers if x['resource']==right)
    contract=dict(version='1.0.1',modelLabel=model_label,side='both',phase='production-b3',avatar=dict(resource=FP_RESOURCE,count=len(after.parents),nativeCount=63,
                  nativeGraph=[dict(index=i,hash=h,parent=fp.parents[i],name=names.get(h),inAnimationChannel=h in bones.hashes) for i,h in enumerate(fp.name_hashes)],outputs=[entry]+descriptors,cacheViewWithinCallback=True),
                  entry=entry,sourceNodes=descriptors,model=primary_receiver,models=receivers,arms=arm_specs,originalUnitSha256=hashlib.sha256(fp_raw).hexdigest(),expandedUnitSha256=hashlib.sha256(expanded).hexdigest(),
                  originalBonesSha256=hashlib.sha256(bones_raw).hexdigest(),animationChannels=47,animationChannelsAdded=0,originalNativeIndicesPreserved=True,sourceSegmentStretchAllowed=False,
                  modelChanged=False,physicsNodesDriven=False,visibleAfterReceiverProof=True,receiverTolerance=.002,modelMatchTolerance=.01,minProofFrames=3,motionProofMetres=.002,
                  logSeconds=5.,holdThroughUpdate=True,finalStageDiagnostics=True,performanceMode=True,focusedPresentation=True,diagnosticSeconds=5.,diagnosticsEnabled=False,
                  cacheViewWithinCallback=True,wristContinuityPolicy='fixed_hand_contact__forearm_palm_roll__hand_relative_twist')
    return expanded,contract


def prepare_option_profile(profile, manifest, settings, fp_contract):
    """Stable model package identity, but a new marker namespace for every calibration.

    Target-armor resources and scale belong to the calibration identity, not the
    model package identity. Never borrow another model's option markers on re-export.
    """
    from .attachment_skeleton import source_attachment_drivers
    if 'testRepairs' in profile:
        raise ValueError('Test profile cannot be released as a production companion')
    namespace = manifest.get('boneNamespace')
    if not isinstance(namespace, str) or not namespace:
        raise ValueError('Production companion requires a stable Source bone namespace')
    bones = settings.get('bones')
    if (settings.get('version') != 1 or type(settings.get('enabled')) is not bool
            or settings.get('excludeHeadDescendants') is not True or not isinstance(bones, list)
            or any(not isinstance(b, str) or b not in source_attachment_drivers() for b in bones)
            or len(set(bones)) != len(bones)):
        raise ValueError('Invalid production companion attachment settings')
    fingerprint = copy.deepcopy(profile)
    for key in ('optionSwitches', 'firstPersonSource', 'runtimeCompanionVersion', 'variant', 'logging'):
        fingerprint.pop(key, None)
    fp_fingerprint = {k:v for k,v in fp_contract.items() if k != 'modelLabel'}
    seed = json.dumps(dict(schema=SCHEMA, version=VERSION, namespace=namespace,
        scale=manifest.get('modelScale'), profile=fingerprint, fpSource=fp_fingerprint,
        attachmentFix=settings), sort_keys=True, separators=(',', ':'), allow_nan=False)
    identity = hashlib.sha256(seed.encode('utf-8')).hexdigest()[:20]
    model_identity = hashlib.sha256(('b3-model:' + namespace).encode('utf-8')).hexdigest()[:20]
    specs = [dict(key='fp_arms', label='开启第一人称手臂', folder='options/00-fp-arms',
        description='启用：第一人称双臂握点及腕部修正；关闭：仅隐藏原生匹配双臂，不构造 Source 求解器，不写 Source pose 或相关刷新。与 TP 开关独立。')]
    for i, bone in enumerate(bones, 1):
        specs.append(dict(key='bone:' + bone, bone=bone, label=bone,
            folder='options/' + str(i).zfill(2) + '-' + bone,
            description='第三人称 ' + bone + ' 独立挂点开关；第一人称总开关独立。'))
    for spec in specs:
        spec['owner'] = 'mods/hd2modmanager/grip_switches/m' + identity + '/' + spec['key'].replace(':', '_')
    profile['optionSwitches'] = dict(schema=SCHEMA, modelIdentity=model_identity,
        enabled=settings['enabled'], identity=identity, bones=list(bones), specs=specs,
        fpIndependentOfTpBones=True, markerIdentityBoundToCalibration=True,
        snapshotAt='first_callback_after_all_addons_start')
    profile['firstPersonSource'] = fp_contract
    profile['runtimeCompanionVersion'] = VERSION
    profile['variant'] = namespace + '-production-b3-' + VERSION
    profile['logging'] = dict(compact=True, detailed=False, recordSeconds=120,
        maxBytes=8388608, exceptionIntervalSeconds=.25)
    return identity
