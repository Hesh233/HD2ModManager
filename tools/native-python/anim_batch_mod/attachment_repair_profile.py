"""Production TP repair data + per-model bind calibration. No prototype profile copying."""
from __future__ import annotations
import copy, hashlib, json, math
from pathlib import Path
from .formats import UnitData, BonesData
from .processor import _calculate_world_transforms
from .math3d import quat_inverse, quat_rotate

VERSION = '1.0.19'
SCHEMA = 'hd2-attachment-repair-policy-v1'
REVISION = 'accepted-tp-profile-r1-20261112'

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')

def load_policy():
    path=Path(__file__).with_name('attachment_repair_policy.json')
    raw=path.read_bytes(); policy=json.loads(raw)
    if policy.get('schema')!=SCHEMA or policy.get('version')!=VERSION or policy.get('revision')!=REVISION:
        raise ValueError('Missing or stale production attachment repair policy')
    for rid in ('16051937941bb709','7372947782b91123','503c0e01fbafa86a','005c2262f672caf4','07d605bd50c98461'):
        if not policy['allowedConsumers'].get(rid) or rid not in policy['fixedConsumers']:
            raise ValueError('Production attachment consumer coverage incomplete: '+rid)
    return policy,hashlib.sha256(raw).hexdigest()

def _contact(unit, indices, side):
    world=_calculate_world_transforms(unit.transforms,unit.parents)
    hand=indices[side+'_hand']; points=[]
    for finger in ('index','middle'):
        joint=indices[side+'_'+finger+'_finger1']
        points.append(quat_rotate(quat_inverse(world[hand].rotation),[world[joint].position[j]-world[hand].position[j] for j in range(3)]))
    result=[sum(p[j] for p in points)/2 for j in range(3)]
    if not all(math.isfinite(v) for v in result) or not .001<math.sqrt(sum(v*v for v in result))<.3:
        raise ValueError('Invalid model-specific hand contact')
    return result

def apply_repair_policy(profile, manifest, original_raw, bones_raw, model_units, avatar_raw, resolve_unit=None):
    """Derive hand contacts from actual native/model Unit binds, FK indices from generated avatar."""
    if 'testRepairs' in profile: raise ValueError('Prototype repair profile is not production input')
    shared,sha=load_policy(); original=UnitData.parse(original_raw); bones=BonesData.parse(bones_raw)
    native={n:original.name_hashes.index(h) for n,h in zip(bones.names,bones.hashes)}
    drivers={n['driver']:n['hash'] for n in manifest['bones'] if n.get('driver')}
    contacts={}; source_evidence={}
    for side,label in (('l','left'),('r','right')):
        candidates=[]
        required=[side+'_hand',side+'_index_finger1',side+'_middle_finger1']
        for rid,unit in sorted(model_units.items()):
            if all(drivers.get(n) in unit.name_hashes for n in required):
                indices={n:unit.name_hashes.index(drivers[n]) for n in required}
                candidate=_contact(unit,indices,side); candidates.append(candidate)
                source_evidence[rid]=dict(hashes=unit.name_hashes,parents=unit.parents,
                    bind=[dict(position=p.position,rotation=p.rotation,scale=p.scale) for p in _calculate_world_transforms(unit.transforms,unit.parents)])
        if not candidates:raise ValueError('No actual model bind for '+side+' hand contact')
        if any(max(abs(a-b) for a,b in zip(c,candidates[0]))>1e-4 for c in candidates):
            raise ValueError('Conflicting actual model hand binds: '+side)
        contacts[label]=dict(native=_contact(original,native,side),source=candidates[0],
            units='metres_already_model_scaled',quality='skeleton_proxy_not_mesh_surface')
    repair=copy.deepcopy(shared['settings'])
    repair.update(enabled=True,version=VERSION,schema=SCHEMA,revision=REVISION,sharedPolicySha256=sha,contacts=contacts)
    avatar=UnitData.parse(avatar_raw); levels=[]
    for driver in ('neck','l_clavicle','r_clavicle'):
        row=next(n for n in manifest['bones'] if n.get('driver')==driver)
        i=avatar.name_hashes.index(row['hash'])
        levels.append(dict(name=row['name'],hash=row['hash'],index=i,parent=avatar.parents[i]))
    repair['sourceFkRefresh']=dict(enabled=True,levels=[levels],maxPasses=2,
        stages=['after_body_sync','after_restore'],positionTolerance=.0002,basisTolerance=.0002,
        sameLocalValuesOnly=True,nativeBonesReadOnly=True,entryRootsOnly=True)
    repair['calibration']=dict(namespace=manifest['boneNamespace'],nativeBindSha256=hashlib.sha256(original_raw).hexdigest(),
        sourceBindsSha256=hashlib.sha256(canonical(source_evidence)).hexdigest(),
        contactsSha256=hashlib.sha256(canonical(contacts)).hexdigest(),avatarBindSha256=hashlib.sha256(avatar_raw).hexdigest(),
        sourceFingerPolicy=manifest.get('fingerSegmentPolicy','actual-source-bind'),modelSpecific=True)
    profile.setdefault('consumers',{}).update(copy.deepcopy(shared['fixedConsumers']))
    profile.setdefault('allowedConsumers',{}).update(copy.deepcopy(shared['allowedConsumers']))
    weapon=shared['weaponPolicies']
    for rid,policy in weapon['leftPolicies'].items():
        if rid in profile['leftGrip']['weaponTargets']:profile['leftGrip']['weaponTargets'][rid]['leftPolicy']=policy
    profile['leftGrip']['intent'].setdefault('weaponThresholds',{}).update(copy.deepcopy(weapon['intentWeaponThresholds']))
    profile['gripFixes']['sidearms'].update(copy.deepcopy(weapon['sidearms']))
    from .native_skeleton import bone_name_hash
    from .motion_skeleton import relative, matrix
    for rid,spec in weapon['nativeRightTargets'].items():
        if resolve_unit is None:raise ValueError('Native right target requires current game Unit bind')
        unit=resolve_unit(rid);world=_calculate_world_transforms(unit.transforms,unit.parents)
        root=unit.name_hashes.index(bone_name_hash(spec['rootName']))
        target=unit.name_hashes.index(bone_name_hash('IK_right'))
        m=matrix(relative(world[root],world[target]))
        row=copy.deepcopy(spec);row['rootToIKRight']=m[:3]+m[4:7]+m[8:11]+m[12:15]
        profile['leftGrip']['weaponTargets'][rid]=row
    profile['repairPolicy']=repair
    return repair
