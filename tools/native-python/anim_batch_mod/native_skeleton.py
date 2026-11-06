"""Source bind skeleton and HD2 animation bridge. No mesh deformation or bone merging.

Animation indices are Bones-resource indices, NOT Unit TransformInfo indices.
Both skeletons use synchronized float32 tracks; original driver poses/events are retained.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
import struct
import sys
import tomllib
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .archive import PackageStore, ResourceIndex, TocArchive, InlinePatchWriter
from .constants import ANIMATION_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID, UNIT_TYPE_ID
from .formats import AnimationBoneState, AnimationData, AnimationEntry, BonesData, UnitData, LocalTransform, parse_state_machine_animation_ids
from .math3d import matrix3_columns_to_quaternion, quat_inverse, quat_inverse_rotate, quat_multiply, quat_rotate, quat_normalize, vec_add, vec_mul, vec_sub
from .processor import ModConfig, WorldTransform, _build_tracks, _calculate_world_transforms, _compose_additive_local, _decompose_additive_position, _apply_two_bone_ik, modify_animation_with_world_compensation
from .native_animation import read_blocks, compact_constant_tracks
from .attachment_skeleton import shadows,append_unit_shadows,append_shadow_animation,append_source_attachment_animation,ensure_hand_references,attachment_swap_plan
from .motion_skeleton import layers,source_local as source_bind_local,source_parent,apply_unit_layers,append_motion_animation


def bone_name_hash(name):
    data = name.encode('utf-8'); mix = 0xc6a4a7935bd1e995; mask = (1 << 64) - 1
    h = len(data) * mix & mask
    end = len(data) // 8 * 8
    for offset in range(0, end, 8):
        word = int.from_bytes(data[offset:offset+8], 'little') * mix & mask
        word ^= word >> 47
        h = (h ^ (word * mix & mask)) * mix & mask
    if end < len(data): h = (h ^ int.from_bytes(data[end:], 'little')) * mix & mask
    h ^= h >> 47; h = h * mix & mask; h ^= h >> 47
    return h >> 32


def animation_nodes(manifest):
    # Keep channel indices stable. Physics subtrees exist only under private names
    # on the avatar, so name-based armor linking cannot overwrite Lua transforms.
    result = []
    for node in manifest['bones']:
        if node.get('physics', False):
            name = '__hd2_anim_reserved__' + node['name']
            result.append({**node, 'name': name, 'hash': bone_name_hash(name)})
        else:
            result.append(node)
    return result


def load_manifest(path):
    path = Path(path)
    manifest = json.loads(path.read_text(encoding='utf-8-sig'))
    sidecar = path.with_name('physbone-rig.bin')
    if sidecar.exists():
        data = sidecar.read_bytes()
        if len(data) < 32 or data[:8] != b'HD2SRG01': raise ValueError('Invalid physics rig sidecar')
        version, count, offset, size, stride = struct.unpack_from('<5I', data, 8)
        if version != 2 or stride != 148 or offset < 32+count*stride or offset+size != len(data):
            raise ValueError('Unsupported physics rig sidecar layout')
        names = set()
        for i in range(count):
            at = offset + struct.unpack_from('<I', data, 32+i*stride+8)[0]
            if not offset <= at < offset+size: raise ValueError('Invalid physics rig name offset')
            names.add(data[at:data.index(b'\0', at, offset+size)].decode('utf-8'))
        if names - {n['name'] for n in manifest['bones']}: raise ValueError('Physics rig and manifest differ')
        for node in manifest['bones']:
            parent = node['parent']
            node['physics'] = node.get('physics', False) or node['name'] in names or (
                parent is not None and manifest['bones'][parent].get('physics', False))
    validate_manifest(manifest)
    return manifest


def row_pose(row):
    return WorldTransform(list(row[12:15]), matrix3_columns_to_quaternion([row[0:3], row[4:7], row[8:11]]), [1., 1., 1.])


def local_pose(value):
    r = value['rotation']
    return LocalTransform(list(value['position']), matrix3_columns_to_quaternion([r[:3], r[3:6], r[6:9]]), list(value['scale']))


def validate_manifest(manifest):
    if manifest.get('version') != 1 or not manifest.get('bones'):
        raise ValueError('Unsupported or empty source-skeleton.json')
    driver_hashes = manifest['driverHashes']
    if not driver_hashes or len(set(driver_hashes)) != len(driver_hashes):
        raise ValueError('Empty or duplicate HD2 driver hashes')
    if len(driver_hashes) + len(manifest['bones'])+len(layers(manifest))+len(shadows(manifest)) > 65535:
        raise ValueError('Source rig exceeds Unit parent-index capacity')
    hashes, names, source_indices = set(driver_hashes), set(), set()
    for index, node in enumerate(manifest['bones']):
        if node['hash'] in hashes or node['name'] in names or '\0' in node['name']:
            raise ValueError('Duplicate/colliding Source bone name or hash')
        if not node['name'] or not isinstance(node['hash'], int) or not 0 <= node['hash'] <= 0xffffffff:
            raise ValueError('Invalid Source bone name/hash')
        if node['sourceIndex'] in source_indices:
            raise ValueError('Duplicate Source bone index')
        source_indices.add(node['sourceIndex'])
        hashes.add(node['hash']); names.add(node['name'])
        parent = node['parent']
        if parent is not None and (not isinstance(parent, int) or not 0 <= parent < index):
            raise ValueError('Source bones must be in parent-first order')
        for values, length in [(node['world'], 16), (node['local']['rotation'], 9),
                               (node['local']['position'], 3), (node['local']['scale'], 3)]:
            if len(values) != length or not all(math.isfinite(v) for v in values):
                raise ValueError('Invalid Source bind matrix')
        if max(abs(v-1) for v in node['local']['scale']) > 1e-6:
            raise ValueError('Source bind scale must be identity')
        for r in (node['local']['rotation'], [node['world'][i] for i in (0,1,2,4,5,6,8,9,10)]):
            determinant = r[0]*(r[4]*r[8]-r[5]*r[7])-r[1]*(r[3]*r[8]-r[5]*r[6])+r[2]*(r[3]*r[7]-r[4]*r[6])
            if abs(determinant-1) > .002 or any(
                abs(sum(r[i*3+k]*r[j*3+k] for k in range(3))-(1 if i==j else 0)) > .002
                for i in range(3) for j in range(3)):
                raise ValueError('Source bind must be a rigid rotation without reflection')
    if source_indices != set(range(len(manifest['bones']))):
        raise ValueError('Source bone indices are not complete')
    if len(manifest['driverHashes']) != len(manifest['driverWorld']):
        raise ValueError('Driver matrix/hash count mismatch')
    runtime_hashes = set(manifest['driverHashes'])
    source_hashes = {n['hash'] for n in manifest['bones']}
    for node, runtime in zip(manifest['bones'], animation_nodes(manifest)):
        physics = node.get('physics', False)
        if not isinstance(physics, bool) or (physics and node['driver'] is not None):
            raise ValueError('Physics nodes cannot also be animation drivers')
        if node['parent'] is not None and manifest['bones'][node['parent']].get('physics', False) and not physics:
            raise ValueError('Physics descendants must remain unlinked')
        if runtime['hash'] in runtime_hashes or (physics and runtime['hash'] in source_hashes):
            raise ValueError('Physics animation alias hash collision')
        runtime_hashes.add(runtime['hash'])
    for world in manifest['driverWorld']:
        if len(world['values']) != 16 or not all(math.isfinite(v) for v in world['values']):
            raise ValueError('Invalid driver world matrix')
    layer_hashes=set(driver_hashes)
    for i,row in enumerate(layers(manifest)):
        if row['hash'] in hashes or row['hash'] in runtime_hashes or row['hash']!=bone_name_hash(row['name']):
            raise ValueError('Motion layer hash collision')
        if row['parentHash'] not in layer_hashes or row['driverHash'] not in driver_hashes or driver_hashes[row['driverUnitIndex']]!=row['driverHash']:
            raise ValueError('Invalid motion driver or parent')
        hashes.add(row['hash']);runtime_hashes.add(row['hash']);layer_hashes.add(row['hash'])
    overrides=manifest.get('motionParentOverrides',{})
    if set(overrides)!=set(manifest.get('motionLocalOverrides',{})):
        raise ValueError('Missing motion bind override')
    for key,layer in overrides.items():
        if not 0<=int(key)<len(manifest['bones']) or not isinstance(layer,int) or not 0<=layer<len(layers(manifest)):
            raise ValueError('Invalid motion parent override')
    shadow_indices=set()
    for row in shadows(manifest):
        key=('sourceParent' in row,row['index'])
        if key in shadow_indices or not 0<=row['index']<len(driver_hashes):
            raise ValueError('Invalid attachment shadow index')
        if row['hash'] in hashes or row['hash'] in runtime_hashes or row['hash']!=bone_name_hash(row['name']):
            raise ValueError('Attachment shadow hash collision')
        shadow_indices.add(key);hashes.add(row['hash'])


def append_unit(data, manifest):
    """Relocate only TransformInfo; retain every other byte/offset in the Unit."""
    validate_manifest(manifest)
    unit = UnitData.parse(data)
    if unit.name_hashes != manifest['driverHashes']:
        raise ValueError('Avatar TransformInfo differs from the model conversion; reconvert the model')
    count = len(unit.transforms)
    offset = struct.unpack_from('<I', data, 52)[0]
    world_start = offset + 16 + count * 64
    for index, expected in enumerate(manifest['driverWorld']):
        actual = struct.unpack_from('<16f', data, world_start + index * 64)
        if max(abs(a-b) for a,b in zip(actual, expected['values'])) > 1e-5:
            raise ValueError('Avatar bind changed since model conversion')
    nodes = animation_nodes(manifest)
    block = bytearray(struct.pack('<I', count + len(nodes)) + data[offset+4:offset+16])
    block.extend(data[offset+16:world_start])
    for node in nodes:
        local = node['local']
        block.extend(struct.pack('<16f', *local['rotation'], *local['position'], *local['scale'], 0.))
    block.extend(data[world_start:world_start + count * 64])
    for node in nodes:
        block.extend(struct.pack('<16f', *node['world']))
    entries_start = world_start + count * 64
    block.extend(data[entries_start:entries_start + count * 4])
    for node in nodes:
        block.extend(struct.pack('<HH', 1, 0 if node['parent'] is None else count + node['parent']))
    block.extend(struct.pack(f'<{count}I', *unit.name_hashes))
    block.extend(struct.pack(f'<{len(nodes)}I', *(n['hash'] for n in nodes)))
    output = bytearray(data)
    output.extend(b'\0' * (-len(output) % 16))
    struct.pack_into('<I', output, 52, len(output))
    output.extend(block)
    # Independently run FK on serialized locals, including all sixteen world components' translation/rotation.
    parsed = UnitData.parse(output)
    worlds = _calculate_world_transforms(parsed.transforms, parsed.parents)
    for index, node in enumerate(nodes, count):
        expected = row_pose(node['world'])
        if max(abs(a-b) for a,b in zip(worlds[index].position, expected.position)) > 1e-4:
            raise ValueError('Source local/world position mismatch')
        if abs(sum(a*b for a,b in zip(worlds[index].rotation, expected.rotation))) < 1 - 1e-5:
            raise ValueError('Source local/world rotation mismatch')
    return append_unit_shadows(apply_unit_layers(output,manifest),manifest)


def append_bones(data, manifest):
    bones = BonesData.parse(data)
    validate_manifest(manifest)
    nodes = animation_nodes(manifest)+layers(manifest)+shadows(manifest)
    if set(bones.hashes) & {node['hash'] for node in nodes}:
        raise ValueError('Source bones already present in Bones resource')
    count, lods = struct.unpack_from('<II', data)
    total = count + len(nodes)
    # Same LOD contract as SDK StingrayBones.Serialize: every LOD includes every node.
    return bytearray(struct.pack('<II', total, lods) + data[8:8+4*lods]
        + struct.pack(f'<{total}I', *bones.hashes, *(n['hash'] for n in nodes))
        + struct.pack(f'<{lods}I', *([total]*lods))
        + b''.join(name.encode('utf-8') + b'\0' for name in [*bones.names, *(n['name'] for n in nodes)]))



def source_blend_mask_owners(bones,manifest):
    """Mask channels follow driver names or the actual published parent graph.

    Source exports can contain valid disconnected Armature/helper roots with
    no HD2 driver. append_unit/source_parent publish those under native Unit
    node 0; inherit that parent's Bones channel by HASH, not Unit index/name.
    Do not remove the root or replace its mask with an arbitrary hips/zero mask.
    """
    indices={name:i for i,name in enumerate(bones.names)}
    by_hash={h:i for i,h in enumerate(bones.hashes)}
    native_count=len(manifest['driverHashes']);nodes=manifest['bones'];motion=layers(manifest)
    def channel(driver):
        if driver not in indices:raise ValueError('Missing blend-mask driver channel: '+str(driver))
        return indices[driver]
    owners=[]
    for i,node in enumerate(nodes):
        if node['driver'] is not None:owner=channel(node['driver'])
        else:
            parent=source_parent(i,node,manifest,native_count)
            if parent<native_count:
                h=manifest['driverHashes'][parent]
                if h not in by_hash:
                    raise ValueError('Unmapped Source root '+node['name']+' has no animated published-parent mask channel')
                owner=by_hash[h]
            elif parent<native_count+len(nodes):
                pi=parent-native_count
                if pi>=i:raise ValueError('Source mask parent must precede its child: '+node['name'])
                owner=owners[pi]
            else:
                mi=parent-native_count-len(nodes)
                if not 0<=mi<len(motion):raise ValueError('Invalid published Source mask parent: '+node['name'])
                owner=channel(motion[mi]['driver'])
        owners.append(owner)
    for row in motion+shadows(manifest):
        owner=channel(row['driver']) if row in motion else row['maskChannel']
        if not isinstance(owner,int) or not 0<=owner<len(bones.names):raise ValueError('Invalid attachment mask channel')
        owners.append(owner)
    return owners


def append_state_machine_masks(data, bones, manifest):
    """Relocate only the blend-mask table; all states/events/unknown blocks retain their offsets."""
    validate_manifest(manifest)
    if len(data) < 76:
        raise ValueError('StateMachine header is truncated')
    count, offset = struct.unpack_from('<II', data, 28)
    if not count:
        return bytearray(data), 0
    if offset < 76 or offset + 4 + count * 4 > len(data) or struct.unpack_from('<I', data, offset)[0] != count:
        raise ValueError('Invalid StateMachine blend-mask table')
    owners = source_blend_mask_owners(bones,manifest)
    table = bytearray(struct.pack('<I', count) + b'\0' * (count * 4))
    for i in range(count):
        relative = struct.unpack_from('<I', data, offset + 4 + 4 * i)[0]
        start = offset + relative
        if start + 4 > len(data):
            raise ValueError('Blend-mask offset is out of bounds')
        channels = struct.unpack_from('<I', data, start)[0]
        if channels != len(bones.names) or start + 4 + channels * 4 > len(data):
            raise ValueError('StateMachine/Bones channel count mismatch')
        weights = struct.unpack_from(f'<{channels}f', data, start + 4)
        if not all(math.isfinite(w) and 0 <= w <= 1 for w in weights):
            raise ValueError('Invalid blend-mask weight')
        struct.pack_into('<I', table, 4 + 4*i, len(table))
        table.extend(struct.pack('<I', channels + len(owners)))
        table.extend(data[start+4:start+4+channels*4])
        table.extend(struct.pack(f'<{len(owners)}f', *(weights[j] for j in owners)))
    output = bytearray(data)
    output.extend(b'\0' * (-len(output) % 4))
    struct.pack_into('<I', output, 32, len(output))
    output.extend(table)
    return output, count


def _swing_between(a, b):
    la, lb = math.sqrt(sum(v*v for v in a)), math.sqrt(sum(v*v for v in b))
    if min(la, lb) < 1e-4:
        return [0., 0., 0., 1.]
    a, b = [v/la for v in a], [v/lb for v in b]
    dot = max(-1., min(1., sum(x*y for x,y in zip(a,b))))
    cross = lambda x,y: [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
    if dot < -1 + 1e-7:
        axis = min(([1.,0.,0.], [0.,1.,0.], [0.,0.,1.]), key=lambda v: abs(sum(x*y for x,y in zip(a,v))))
        return quat_normalize([*cross(a,axis), 0.])
    return quat_normalize([*cross(a,b), 1+dot])


def _reference_rotations(nodes, source_bind, source_world_bind, driver_bind, driver_by_name, manifest=None):
    """Match anatomical segment directions without changing the saved Source bind or bone lengths."""
    successors = {'hips':'spine1', 'spine1':'spine2', 'spine2':'chest', 'chest':'neck', 'neck':'head'}
    for side in ('l','r'):
        successors.update({f'{side}_clavicle':f'{side}_shoulder', f'{side}_shoulder':f'{side}_elbow',
                           f'{side}_elbow':f'{side}_hand', f'{side}_hand':f'{side}_middle_finger1',
                           f'{side}_thigh':f'{side}_knee', f'{side}_knee':f'{side}_foot'})
        for finger in ('thumb','index','middle','ring','pinky'):
            for joint in (1,2):
                successors[f'{side}_{finger}_finger{joint}'] = f'{side}_{finger}_finger{joint+1}'
    source_by_driver = {n['driver']:i for i,n in enumerate(nodes) if n['driver'] is not None}
    # Coincident spine joints cannot define a direction. Use the body's up and
    # left/right axes to anchor pelvis twist, then fit each nonzero limb segment.
    body_names = ('hips', 'neck', 'l_thigh', 'r_thigh')
    body_delta = None
    if all(n in source_by_driver and n in driver_by_name for n in body_names):
        def axes(poses, lookup):
            up = vec_sub(poses[lookup['neck']].position, poses[lookup['hips']].position)
            side = vec_sub(poses[lookup['r_thigh']].position, poses[lookup['l_thigh']].position)
            return up, side
        source_up, source_side = axes(source_world_bind, source_by_driver)
        target_up, target_side = axes(driver_bind, driver_by_name)
        swing = _swing_between(source_up, target_up)
        length = math.sqrt(sum(v*v for v in target_up))
        if length > 1e-4:
            axis = [v/length for v in target_up]
            def project(v):
                dot = sum(a*b for a,b in zip(v,axis))
                return [a-dot*b for a,b in zip(v,axis)]
            body_delta = quat_multiply(_swing_between(project(quat_rotate(swing,source_side)), project(target_side)), swing)
    worlds, locals_ = [], []
    for i,node in enumerate(nodes):
        layer=(manifest or {}).get('motionParentOverrides',{}).get(str(i))
        parent = driver_bind[layers(manifest)[layer]['driverUnitIndex']].rotation if layer is not None else driver_bind[0].rotation if node['parent'] is None else worlds[node['parent']]
        driver, successor = node['driver'], successors.get(node['driver'])
        desired = quat_multiply(parent, source_bind[i].rotation)
        if driver is None:
            desired = quat_multiply(parent, source_bind[i].rotation)
        elif driver == 'hips' and body_delta is not None:
            desired = quat_multiply(body_delta, source_world_bind[i].rotation)
        elif successor in source_by_driver and successor in driver_by_name:
            a = vec_sub(source_world_bind[source_by_driver[successor]].position, source_world_bind[i].position)
            b = vec_sub(driver_bind[driver_by_name[successor]].position, driver_bind[driver_by_name[driver]].position)
            # The segment is measured in the original world bind. Apply its
            # correction there, not to a parent that has already been corrected.
            if min(math.sqrt(sum(v*v for v in a)), math.sqrt(sum(v*v for v in b))) >= 1e-4:
                desired = quat_multiply(_swing_between(a,b), source_world_bind[i].rotation)
        worlds.append(desired)
        locals_.append(quat_multiply(quat_inverse(parent),desired))
    return worlds, locals_


def append_animation(animation, bones, unit, manifest, fps=30, sample_times=None, grip_animation=None,
                     align_standard_feet=False, align_standard_grips=True, foot_animation=None,
                     translation_reference=None, stable_grip_pole=False, grip_soft_distance=0.,
                     foot_y_degrees=None):
    """Retarget world rotation deltas onto Source axes; source local translations stay fixed.

    Only Source roots receive driver translation. Helpers inherit their local bind.
    Additive rotations are relative to the calibrated reference, so a neutral
    additive clip cannot reapply the bind correction to the waist or arms.
    """
    validate_manifest(manifest)
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError('Sampling fps must be an integer between 1 and 120')
    original_count = len(animation.initial_bone_states)
    if original_count != len(bones.names):
        raise ValueError('Animation/Bones channel count mismatch')
    transform_by_hash = {h: i for i, h in enumerate(unit.name_hashes)}
    anim_to_unit = [transform_by_hash[h] for h in bones.hashes]
    driver_by_name = dict(zip(bones.names, anim_to_unit))
    nodes = manifest['bones']
    foot_corrections = {}
    for name, degrees in (foot_y_degrees or {}).items():
        if name not in ('l_foot', 'r_foot') or isinstance(degrees, bool) or not isinstance(degrees, (int,float)) or not math.isfinite(degrees) or abs(degrees)>90:
            raise ValueError('foot_y_degrees accepts l_foot/r_foot angles between -90 and 90')
        if not any(n['driver']==name for n in nodes):
            raise ValueError('Source skeleton lacks configured foot: '+name)
        angle = math.radians(degrees) / 2.
        foot_corrections[name] = [0., math.sin(angle), 0., math.cos(angle)]
    drivers = [None if n['driver'] is None else driver_by_name[n['driver']] for n in nodes]
    source_bind = [local_pose(source_bind_local(n,i,manifest)) for i,n in enumerate(nodes)]
    source_world_bind = [row_pose(n['world']) for n in nodes]
    driver_bind = _calculate_world_transforms(unit.transforms, unit.parents)
    reference_world, reference_local = _reference_rotations(nodes, source_bind, source_world_bind, driver_bind, driver_by_name,manifest)
    tracks = _build_tracks(animation)
    original_tracks = _build_tracks(grip_animation) if grip_animation is not None else None
    foot_tracks = _build_tracks(foot_animation) if foot_animation is not None else original_tracks
    source_by_driver = {n['driver']:i for i,n in enumerate(nodes) if n['driver'] is not None}
    grip_chains = []
    for side in ('l','r'):
        names = [f'{side}_shoulder',f'{side}_elbow',f'{side}_hand']
        if all(n in source_by_driver for n in names):
            a,b,c = [source_by_driver[n] for n in names]
            if nodes[b]['parent']==a and nodes[c]['parent']==b:
                grip_chains.append((a,b,c,driver_by_name[names[-1]]))
    foot_chains=[]
    for side in ('l','r'):
        names=[f'{side}_thigh',f'{side}_knee',f'{side}_foot']
        if all(n in source_by_driver for n in names):
            a,b,c=[source_by_driver[n] for n in names]
            if nodes[b]['parent']==a and nodes[c]['parent']==b:
                foot_chains.append((a,b,c,driver_by_name[names[-1]]))
    offset=len(unit.transforms)
    motion=layers(manifest);motion_by_hash={r['hash']:offset+len(nodes)+i for i,r in enumerate(motion)}
    parents=unit.parents+[source_parent(i,n,manifest,offset) for i,n in enumerate(nodes)]
    parents += [motion_by_hash.get(r['parentHash'],transform_by_hash.get(r['parentHash'])) for r in motion]
    motion_bind=[unit.transforms[r['driverUnitIndex']] for r in motion]
    reference_source=_calculate_world_transforms(list(unit.transforms)+[
        WorldTransform(list(bind.position),list(rotation),[1.,1.,1.])
        for bind,rotation in zip(source_bind,reference_local)]+motion_bind,parents)[offset:offset+len(nodes)]
    # The calibrated reference supplies the model's elbow hinge. Deriving it
    # again from each retargeted frame lets a near-straight driver or a blend
    # reverse the upper-arm frame, even when the elbow path is smooth.
    grip_hinges = {}
    for a,b,c,_ in grip_chains:
        first = vec_sub(reference_source[b].position, reference_source[a].position)
        second = vec_sub(reference_source[c].position, reference_source[b].position)
        normal = [first[1]*second[2]-first[2]*second[1],
                  first[2]*second[0]-first[0]*second[2],
                  first[0]*second[1]-first[1]*second[0]]
        length = math.sqrt(sum(v*v for v in normal))
        if length > 1e-8:
            grip_hinges[a] = quat_inverse_rotate(reference_source[a].rotation, [v/length for v in normal])
    locomotion_root=driver_by_name.get('root',0)
    duration = max([animation.animation_length * 1000., *[e.time for e in animation.entries if e.is_position or e.is_rotation or e.is_scale]])
    times = sample_times if sample_times is not None else sorted({0., duration,
        *(frame * 1000. / fps for frame in range(1, math.ceil(duration * fps / 1000))),
        *(e.time for e in animation.entries if e.is_position or e.is_rotation or e.is_scale)})
    def original_world_at(time,tracks_=None):
        tracks_=original_tracks if tracks_ is None else tracks_
        local=list(unit.transforms)
        for ai,ui in enumerate(anim_to_unit):
            sample=WorldTransform(*(track[ai].evaluate(time) for track in tracks_))
            local[ui]=_compose_additive_local(unit.transforms[ui],sample) if animation.is_additive else sample
        return _calculate_world_transforms(local,unit.parents)
    planted=False
    pelvis=source_by_driver.get('hips')
    if align_standard_feet and original_tracks is not None and len(foot_chains)==2 and pelvis is not None and nodes[pelvis]['parent'] is None:
        samples=[original_world_at(duration*i/8,foot_tracks) for i in range(9)]
        planted=all(math.dist(row[d].position,samples[0][d].position)<.02 and
            row[driver_by_name['hips']].position[2]-row[d].position[2]>.3
            for row in samples for _,_,_,d in foot_chains)
    previous = [None] * len(nodes)
    grip_poles = {a:{} for a,_,_,_ in grip_chains}
    maximum_length_error = 0.
    maximum_grip_error = 0.
    maximum_foot_error = 0.
    maximum_pelvis_drop = 0.
    for time_index, time in enumerate(times):
        local = [WorldTransform(list(t.position), list(t.rotation), list(t.scale)) for t in unit.transforms]
        for anim_index, unit_index in enumerate(anim_to_unit):
            sample = WorldTransform(tracks[0][anim_index].evaluate(time), tracks[1][anim_index].evaluate(time), tracks[2][anim_index].evaluate(time))
            local[unit_index] = _compose_additive_local(unit.transforms[unit_index], sample) if animation.is_additive else sample
        world = _calculate_world_transforms(local, unit.parents)
        source_world, source_local = [], []
        for index, node in enumerate(nodes):
            layer=manifest.get('motionParentOverrides',{}).get(str(index))
            parent = world[motion[layer]['driverUnitIndex']] if layer is not None else world[0] if node['parent'] is None else source_world[node['parent']]
            bind = source_bind[index]
            driver = drivers[index]
            if driver is None:
                rotation = list(bind.rotation)
            else:
                delta = quat_multiply(world[driver].rotation, quat_inverse(driver_bind[driver].rotation))
                desired = quat_multiply(delta, reference_world[index])
                rotation = quat_multiply(quat_inverse(parent.rotation), desired)
            position = list(bind.position)
            if layer is not None and driver is not None:
                # Source bind already supplies its proportions. Measure motion
                # from the configured driver bind, not its original dimensions.
                # Otherwise spine1's static height adjustment is applied twice.
                reference=(translation_reference or {}).get(driver,unit.transforms[driver].position)
                position=vec_add(bind.position,vec_sub(local[driver].position,reference))
            elif node['parent'] is None and driver is not None:
                desired_position = vec_add(source_world_bind[index].position, vec_sub(world[driver].position, driver_bind[driver].position))
                position = quat_inverse_rotate(parent.rotation, vec_sub(desired_position, parent.position))
            actual_world = WorldTransform(vec_add(parent.position, quat_rotate(parent.rotation, position)),
                                          quat_multiply(parent.rotation, rotation), [1.,1.,1.])
            source_world.append(actual_world)
            source_local.append(WorldTransform(position, rotation, [1.,1.,1.]))
            if node['parent'] is not None and layer is None:
                maximum_length_error = max(maximum_length_error, abs(math.dist(actual_world.position, parent.position) - math.sqrt(sum(v*v for v in bind.position))))
        if original_tracks is not None:
            original_world = original_world_at(time)
            combined = local + source_local + [local[r['driverUnitIndex']] for r in motion]
            active_grips=grip_chains if align_standard_grips and not animation.is_additive else []
            foot_targets=[]
            if align_standard_feet:
                foot_world=original_world_at(time,foot_tracks)
                root_delta=quat_multiply(foot_world[locomotion_root].rotation,quat_inverse(driver_bind[locomotion_root].rotation))
                for a,b,c,driver in foot_chains:
                    # Keep this model's stance/sole offset, while following the
                    # original animated foot path. Never freeze moving feet.
                    baseline_offset=vec_sub(reference_source[c].position,driver_bind[driver].position)
                    target=vec_add(foot_world[driver].position,quat_rotate(root_delta,baseline_offset))
                    rotation=quat_multiply(foot_world[driver].rotation,
                        quat_multiply(quat_inverse(driver_bind[driver].rotation),reference_world[c]))
                    foot_targets.append((a,b,c,target,rotation))
                if planted:
                    current=_calculate_world_transforms(combined,parents);drop=0.
                    for a,b,c,target,_ in foot_targets:
                        hip=current[offset+a].position
                        reach=math.dist(hip,current[offset+b].position)+math.dist(current[offset+b].position,current[offset+c].position)-1e-6
                        horizontal=sum((hip[i]-target[i])**2 for i in (0,1))
                        if horizontal<reach*reach:
                            drop=max(drop,hip[2]-target[2]-math.sqrt(reach*reach-horizontal))
                    drop=min(drop,.1)
                    if drop>0:
                        change=quat_inverse_rotate(current[0].rotation,[0.,0.,-drop])
                        source_local[pelvis].position=vec_add(source_local[pelvis].position,change)
                        maximum_pelvis_drop=max(maximum_pelvis_drop,drop)
                for a,b,c,target,rotation in foot_targets:
                    _apply_two_bone_ik(combined,parents,offset+a,offset+b,offset+c,target,rotation)
            for a,b,c,driver in active_grips:
                target_rotation = quat_multiply(original_world[driver].rotation,
                    quat_multiply(quat_inverse(driver_bind[driver].rotation),reference_world[c]))
                _apply_two_bone_ik(combined,parents,offset+a,offset+b,offset+c,
                    original_world[driver].position,target_rotation,
                    pole_state=grip_poles[a] if stable_grip_pole else None,
                    hinge_axis=grip_hinges.get(a) if stable_grip_pole else None,
                    soft_distance=grip_soft_distance,
                    delta_time=(time-times[time_index-1])/1000. if time_index else 1./fps)
            aligned = _calculate_world_transforms(combined,parents)
            for _,_,c,driver in active_grips:
                maximum_grip_error = max(maximum_grip_error,
                    math.dist(aligned[offset+c].position,original_world[driver].position))
            for _,_,c,target,_ in foot_targets:
                maximum_foot_error=max(maximum_foot_error,math.dist(aligned[offset+c].position,target))
        for index,node in enumerate(nodes):
            bind=source_bind[index]
            position,rotation=source_local[index].position,source_local[index].rotation
            if animation.is_additive:
                # Non-additive Source poses use calibrated reference axes.
                # Translation deltas must use those same axes when composed.
                basis=WorldTransform(bind.position,reference_local[index],bind.scale)
                position = _decompose_additive_position(basis, position)
                rotation = quat_multiply(quat_inverse(reference_local[index]), rotation)
            correction = foot_corrections.get(node['driver'])
            if correction is not None:
                if animation.is_additive:
                    # Base B becomes B*C. Rebase additive D to C^-1*D*C;
                    # zero additive stays zero and stacked layers add no twist.
                    position = quat_inverse_rotate(correction, position)
                    rotation = quat_multiply(quat_multiply(quat_inverse(correction),rotation),correction)
                else:
                    rotation = quat_multiply(rotation, correction)
            # q and -q represent the same pose; ensure interpolation follows the short arc.
            if previous[index] is not None and sum(a*b for a,b in zip(rotation, previous[index])) < 0:
                rotation = [-v for v in rotation]
            previous[index] = rotation
            channel = original_count + index
            if time_index == 0:
                animation.initial_bone_states.append(AnimationBoneState(position, rotation,
                    [0.,0.,0.] if animation.is_additive else [1.,1.,1.], False, False, False))
            else:
                animation.entries.extend([AnimationEntry(0, 4, channel, time, position), AnimationEntry(0, 5, channel, time, rotation)])
    animation.entries.sort(key=lambda e: e.time)  # stable: event order at each time is retained
    return {'samples': len(times), 'added_channels': len(nodes), 'max_bone_length_error': maximum_length_error,
            'standard_grip_chains':len(grip_chains) if original_tracks is not None and align_standard_grips and not animation.is_additive else 0,
            'max_standard_grip_error':maximum_grip_error,
            'standard_foot_chains':len(foot_chains) if original_tracks is not None and align_standard_feet else 0,
            'max_standard_foot_error':maximum_foot_error,'planted_feet':planted,'max_pelvis_drop':maximum_pelvis_drop}


def progress(phase, done, total, message):
    print(f'#progress {phase} {done} {total} {message}', file=sys.stderr, flush=True)


def _swap_graph(bones, unit, manifest):
    """挂点对调用的求值图：native 单位节点 + 追加 Source 节点 + 运动层节点的绑定/父级/通道号。

    运动层节点必须建模：motionParentOverrides 把脊柱链的父级改挂到运动层节点，
    武器骨链的祖先可能经过它们（打包数据里的真实拓扑）。
    """
    count = len(bones.names)
    offset = len(unit.transforms)
    nodes = manifest['bones']
    motion = layers(manifest)
    transform_by_hash = {h: i for i, h in enumerate(unit.name_hashes)}
    channel_by_unit = {transform_by_hash[h]: i for i, h in enumerate(bones.hashes)}
    parents = list(unit.parents)
    bind_by_nid = {}
    for i in range(len(nodes)):
        bind = local_pose(source_bind_local(nodes[i], i, manifest))
        bind_by_nid[offset + i] = WorldTransform(list(bind.position), list(bind.rotation), [1., 1., 1.])
        parents.append(source_parent(i, nodes[i], manifest, offset))
    motion_base = offset + len(nodes)
    bind_worlds = _calculate_world_transforms(unit.transforms, unit.parents)
    motion_hash_to_nid = {row['hash']: motion_base + k for k, row in enumerate(motion)}
    motion_bind_world = {}
    for k, row in enumerate(motion):
        nid = motion_base + k
        # 运动层的 parentHash 可能指向**另一个运动层**（boss 层挂在 root 层下），
        # 与 append_animation 的 motion_by_hash 优先解析一致。
        parent = motion_hash_to_nid.get(row['parentHash'])
        if parent is None:
            parent = transform_by_hash[row['parentHash']]
        target = bind_worlds[transform_by_hash[row['driverHash']]]
        anchor = bind_worlds[parent] if parent < offset else motion_bind_world[parent]
        parents.append(parent)
        bind_by_nid[nid] = WorldTransform(
            quat_rotate(quat_inverse(anchor.rotation), vec_sub(target.position, anchor.position)),
            quat_multiply(quat_inverse(anchor.rotation), target.rotation), [1., 1., 1.])
        motion_bind_world[nid] = target
    channel_by_nid = dict(channel_by_unit)
    for i in range(len(nodes)):
        channel_by_nid[offset + i] = count + i
    for k in range(len(motion)):
        channel_by_nid[motion_base + k] = count + len(nodes) + k
    return {
        'count': count, 'offset': offset, 'motion_base': motion_base, 'nodes': nodes,
        'transform_by_hash': transform_by_hash, 'channel_by_nid': channel_by_nid,
        'parents': parents, 'bind_by_nid': bind_by_nid, 'native_count': len(unit.transforms),
    }


def _swap_world(graph, tracks, nid, time, cache):
    """按打包动画通道 + Unit 绑定，求节点 nid 在 time 的世界姿态。"""
    cached = cache.get(nid)
    if cached is not None:
        return cached
    chain, cursor = [], nid
    while cursor is not None and cache.get(cursor) is None:
        chain.append(cursor)
        cursor = graph['parents'][cursor] if cursor < len(graph['parents']) else None
    for node in reversed(chain):
        if node < graph['native_count']:
            bind = graph['_unit_transforms'][node]
        else:
            bind = graph['bind_by_nid'][node]
        channel = graph['channel_by_nid'].get(node)
        local_position, local_rotation, local_scale = list(bind.position), list(bind.rotation), list(bind.scale)
        if channel is not None:
            local_position = list(tracks[0][channel].evaluate(time))
            local_rotation = list(tracks[1][channel].evaluate(time))
            local_scale = list(tracks[2][channel].evaluate(time))
        parent = graph['parents'][node] if node < len(graph['parents']) else None
        if parent is None:
            world = WorldTransform(local_position, local_rotation, local_scale)
        else:
            parent_world = cache[parent]
            world = WorldTransform(
                vec_add(parent_world.position,
                        quat_rotate(parent_world.rotation, vec_mul(parent_world.scale, local_position))),
                quat_multiply(parent_world.rotation, local_rotation),
                [a * b for a, b in zip(parent_world.scale, local_scale)])
        cache[node] = world
    return cache[nid]


def _swap_local_position(parent,world_position):
    """Invert the same scaled-parent FK used by _swap_world (no hidden scale loss)."""
    if any(not math.isfinite(v) or abs(v)<1e-8 for v in parent.scale):
        raise ValueError('Attachment swap parent has singular/nonfinite scale')
    rotated=quat_inverse_rotate(parent.rotation,vec_sub(world_position,parent.position))
    return [v/scale for v,scale in zip(rotated,parent.scale)]


def apply_attachment_swap(animation, bones, unit, manifest, swap, times):
    """挂点对调（B22「动画侧节点级互换」）：在打包动画的通道级互换两侧挂点的世界路径。

    每对 (native, source)：
      · native（引擎武器挂点，如 attach_hand_r）逐帧携带 source（test01 的
        ValveBiped 武器骨）互换前的世界位置——引擎武器跟随 test01 动画的持枪路径；
      · source 武器骨逐帧携带 native 互换前的世界路径——test01 骨架默认使用的挂点
        变为原生骨架挂点（原生握点）。
    policy='position' 只互换位置、各自保留原朝向；'pose' 连朝向一起互换。
    父级拓扑、Unit/Bones 资源、缩放与事件均不变；加性动画跳过（其通道值不是直接的
    世界姿态，交换数学不成立，原生挂点在该类剪辑里保持原生行为）。
    """
    if animation.is_additive:
        return {'attachment_swap': {'applied': 0, 'skipped': 'additive'}}
    if not swap or not swap.get('pairs'):
        return None
    graph = _swap_graph(bones, unit, manifest)
    graph['_unit_transforms'] = unit.transforms
    policy = swap.get('policy', 'position')
    if policy not in ('position', 'pose'):
        raise ValueError('attachment_swap.policy must be position or pose')
    tracks = _build_tracks(animation)
    resolved, notes = [], []
    for pair in swap['pairs']:
        native_name, source_key = pair['native'], pair['source']
        if native_name not in bones.names:
            notes.append(f'native {native_name} missing from Bones; pair skipped')
            continue
        native_channel = bones.names.index(native_name)
        native_unit = graph['transform_by_hash'][bones.hashes[native_channel]]
        source_index = None
        wanted = source_key.lower()
        exact=[i for i,node in enumerate(graph['nodes']) if
            (node.get('sourceName') or '').lower()==wanted or node['name'].lower()==wanted]
        matches=exact or [i for i,node in enumerate(graph['nodes']) if
            node['name'].lower().endswith('.'+wanted) or node['name'].lower().endswith('_'+wanted.replace(' ','_'))]
        if len(matches)>1:
            raise ValueError('Ambiguous Source attachment alias; use its full sourceName: '+source_key)
        if matches:source_index=matches[0]
        if source_index is None:
            notes.append(f'source {source_key} missing from manifest; pair skipped')
            continue
        resolved.append({
            'native': native_name, 'native_channel': native_channel, 'native_unit': native_unit,
            'source': source_key, 'source_index': source_index,
            'source_channel': graph['count'] + source_index, 'source_unit': graph['offset'] + source_index,
        })
    if not resolved:
        return {'attachment_swap': {'applied': 0, 'skipped': 'no-pair-resolved', 'notes': notes}}
    channels=[channel for pair in resolved for channel in (pair['native_channel'],pair['source_channel'])]
    if len(channels)!=len(set(channels)):
        raise ValueError('Attachment swap pairs overlap: each channel may be swapped only once')
    native_channels = [pair['native_channel'] for pair in resolved]
    source_channels = [pair['source_channel'] for pair in resolved]
    swapped = set(native_channels + source_channels)
    keep = [entry for entry in animation.entries
            if not (entry.bone in swapped and (entry.is_position or entry.is_rotation))]
    updates = {channel: {} for channel in swapped}
    maximum_error = 0.
    for time in times:
        cache = {}  # 世界姿态按采样时刻缓存，绝不能跨时刻复用。
        for pair in resolved:
            native_world = _swap_world(graph, tracks, pair['native_unit'], time, cache)
            source_world = _swap_world(graph, tracks, pair['source_unit'], time, cache)
            native_parent = _swap_world(graph, tracks, graph['parents'][pair['native_unit']], time, cache)
            source_parent_world = _swap_world(graph, tracks, graph['parents'][pair['source_unit']], time, cache)
            native_channel, source_channel = pair['native_channel'], pair['source_channel']
            native_local_position = _swap_local_position(native_parent,source_world.position)
            native_local_rotation = tracks[1][native_channel].evaluate(time)
            if policy == 'pose':
                native_local_rotation = quat_multiply(quat_inverse(native_parent.rotation), source_world.rotation)
            source_local_position = _swap_local_position(source_parent_world,native_world.position)
            source_local_rotation = tracks[1][source_channel].evaluate(time)
            if policy == 'pose':
                source_local_rotation = quat_multiply(quat_inverse(source_parent_world.rotation), native_world.rotation)
            # 复核：新局部在父级下复原出对方互换前的世界位置。
            check_native = vec_add(native_parent.position,
                quat_rotate(native_parent.rotation, vec_mul(native_parent.scale,native_local_position)))
            check_source = vec_add(source_parent_world.position,
                quat_rotate(source_parent_world.rotation, vec_mul(source_parent_world.scale,source_local_position)))
            maximum_error = max(maximum_error,
                math.dist(check_native, source_world.position),
                math.dist(check_source, native_world.position))
            updates[native_channel][time] = (list(native_local_position), list(native_local_rotation))
            updates[source_channel][time] = (list(source_local_position), list(source_local_rotation))
    if maximum_error > 1e-4:
        raise ValueError(f'attachment swap world round-trip error {maximum_error:.3e} exceeds 1e-4')
    new_entries = []
    previous = {channel: None for channel in sorted(swapped)}
    for channel in sorted(swapped):
        initial = animation.initial_bone_states[channel]
        position, rotation = updates[channel][times[0]]
        rotation = list(rotation)
        animation.initial_bone_states[channel] = AnimationBoneState(
            position, rotation, list(initial.scale), False, False, False)
        previous[channel] = rotation
    for time in times[1:]:
        for channel in sorted(swapped):
            position, rotation = updates[channel][time]
            rotation = list(rotation)
            if previous[channel] is not None and sum(a * b for a, b in zip(rotation, previous[channel])) < 0:
                rotation = [-value for value in rotation]
            previous[channel] = rotation
            new_entries.append(AnimationEntry(0, 4, channel, time, position))
            new_entries.append(AnimationEntry(0, 5, channel, time, rotation))
    animation.entries = keep + new_entries
    return {'attachment_swap': {
        'applied': len(resolved), 'policy': policy,
        'pairs': [{'native': pair['native'], 'source': pair['source'],
                   'native_channel': pair['native_channel'], 'source_channel': pair['source_channel']}
                  for pair in resolved],
        'notes': notes, 'max_round_trip_error': maximum_error,
    }}


def calibrate_weapon_animation(animation,bones,unit,manifest,times):
    """Place original Source weapon channels on accurate grips BEFORE world-path swap."""
    info=manifest.get('weaponGripCalibration')
    if not info:return None
    graph=_swap_graph(bones,unit,manifest);graph['_unit_transforms']=unit.transforms;tracks=_build_tracks(animation)
    channels={graph['count']+row['manifestIndex'] for row in info['rows']}
    updates={c:[] for c in channels}
    for time in times:
        cache={}
        for row in info['rows']:
            hand=_swap_world(graph,tracks,graph['offset']+row['handIndex'],time,cache)
            ni=row['nativeIndex'];channel=graph['channel_by_nid'][ni]
            p,q=(tracks[k][channel].evaluate(time) for k in (0,1))
            basis=quat_multiply(hand.rotation,row['axes'])
            desired=WorldTransform(vec_add(hand.position,quat_rotate(basis,p)),quat_multiply(basis,q),[1.,1.,1.])
            node=graph['offset']+row['manifestIndex'];parent=_swap_world(graph,tracks,graph['parents'][node],time,cache)
            local_position=_swap_local_position(parent,desired.position);local_rotation=quat_multiply(quat_inverse(parent.rotation),desired.rotation)
            updates[graph['count']+row['manifestIndex']].append((time,local_position,local_rotation))
    animation.entries=[e for e in animation.entries if not (e.bone in channels and (e.is_position or e.is_rotation))]
    for channel,rows in updates.items():
        animation.initial_bone_states[channel].position=list(rows[0][1]);animation.initial_bone_states[channel].rotation=list(rows[0][2])
        for time,p,q in rows[1:]:animation.entries.extend([AnimationEntry(0,4,channel,time,p),AnimationEntry(0,5,channel,time,q)])
    return dict(version=info['version'],bones=len(info['rows']),stage='accurate_grips_before_swap')


def finalize_native_animation(animation,bones,unit,manifest,options,times,arm_reference_data=None):
    """Finalize Source ancestors BEFORE swapping world paths; preserve raw references.

    Applying accepted arm rotations after the swap moves the Source weapon child
    again and invalidates its native-world destination. Runtime pose packaging
    continues to use frozen tested animations; this fixes future animation bakes.
    """
    animation.entries.sort(key=lambda e:e.time)
    data,removed=compact_constant_tracks(animation.to_bytes())
    metrics={}
    if arm_reference_data is not None:
        from .native_arm_reference import apply_arm_reference
        data,arm_metrics=apply_arm_reference(data,arm_reference_data,bones,unit,manifest,
            preserve_clavicles=options.get('preserve_arm_reference_clavicles',False))
        metrics.update(arm_metrics)
    final=AnimationData.parse(data)
    swap_times=sorted(set(times)|{e.time for e in final.entries if e.is_position or e.is_rotation or e.is_scale})
    if not final.is_additive:
        calibration=calibrate_weapon_animation(final,bones,unit,manifest,swap_times)
        if calibration:metrics['weapon_grip_calibration']=calibration
    swap_metrics=apply_attachment_swap(final,bones,unit,manifest,options.get('attachment_swap_config'),swap_times)
    if swap_metrics is not None:
        metrics.update(swap_metrics)
        if swap_metrics['attachment_swap'].get('applied',0):
            final.entries.sort(key=lambda e:e.time)
            data,extra=compact_constant_tracks(final.to_bytes());removed+=extra
            metrics['attachment_swap']['stage']='after-final-arm-reference'
    final.entries.sort(key=lambda e:e.time)
    data,extra=compact_constant_tracks(final.to_bytes());removed+=extra
    metrics['constant_keys_removed']=removed
    return data,metrics


def convert_clip(data, bones, unit, manifest, config, options, arm_reference_data=None):
    first, second = read_blocks(data)
    if (first.header[:12]+first.header[16:],first.flags,first.states,first.hash_floats,first.entries) != (
        second.header[:12]+second.header[16:],second.flags,second.states,second.hash_floats,second.entries):
        raise ValueError('Distinct animation blocks require independent retargeting')
    original = AnimationData.parse(data)
    animation = copy.deepcopy(original)
    if options.get('apply_driver_config', True):
        modify_animation_with_world_compensation(animation, bones, unit, config, allow_additive=True,
            apply_offsets_to_additive=False,
            apply_rotate_multipliers=options.get('rotate_multipliers', False),
            apply_rotation_compensations=options.get('rotation_compensation', False),
            apply_ik_correction=options.get('ik_correction', False))
    # Both skeletons use the same float stream and sampling times. Mixing the
    # original compressed look-ahead records with sorted float keys stalls the
    # native channels in game even when their compressed bytes are unchanged.
    duration = original.animation_length * 1000.
    fps = options.get('fps', 30)
    times = sorted({0., duration, *(i*1000./fps for i in range(1,math.ceil(duration*fps/1000))),
        *(e.time for e in original.entries if e.is_position or e.is_rotation or e.is_scale)})
    animation.animation_length = original.animation_length
    configured=copy.deepcopy(animation)
    translation_reference={}
    if options.get('apply_driver_config',True) and not animation.is_additive:
        for key in manifest.get('motionParentOverrides',{}):
            name=manifest['bones'][int(key)]['driver']
            if name is None:continue
            driver=unit.name_hashes.index(bones.hashes[bones.names.index(name)])
            position=list(unit.transforms[driver].position)
            if name in config.offsets:
                position=vec_add(position,config.offsets[name])
                if unit.parents[driver] is not None:
                    position=[v*config.distance_multipliers.get(name,1.) for v in position]
            translation_reference[driver]=position
    grip_target=options.get('grip_target','configured')
    if grip_target not in ('configured','original'):raise ValueError('grip_target must be configured or original')
    metrics = append_animation(animation, bones, unit, manifest, fps, times,
        (configured if grip_target=='configured' else original) if options.get('align_standard_grips',True) or options.get('align_standard_feet',False) else None,
        options.get('align_standard_feet',False),options.get('align_standard_grips',True),original,
        translation_reference, options.get('stable_grip_pole',False), options.get('grip_soft_distance',0.),
        options.get('foot_y_degrees',{}))
    metrics['grip_target']=grip_target
    metrics['source_translation_reference']='configured-bind-v8' if layers(manifest) else 'legacy'
    count = len(bones.names)
    tracks = _build_tracks(original)
    animation.entries = [e for e in animation.entries
        if (e.is_position or e.is_rotation or e.is_scale) and e.bone >= count]
    animation.entries.extend(copy.deepcopy(e) for e in original.entries
        if not (e.is_position or e.is_rotation or e.is_scale))
    for channel in range(count):
        p,r,s = (track[channel].evaluate(0.) for track in tracks)
        animation.initial_bone_states[channel] = AnimationBoneState(p,r,s,False,False,False)
    for time in times[1:]:
        for channel in range(count):
            for subtype, track in zip((4,5,6),tracks):
                animation.entries.append(AnimationEntry(0,subtype,channel,time,track[channel].evaluate(time)))
    append_motion_animation(animation,configured,bones,manifest,times)
    append_shadow_animation(animation,original,bones,unit,manifest,times,tracks)
    append_source_attachment_animation(animation,configured,bones,unit,manifest,times)
    data,final_metrics=finalize_native_animation(animation,bones,unit,manifest,options,times,arm_reference_data)
    metrics.update(final_metrics)
    roundtrip = AnimationData.parse(data)
    if len(roundtrip.initial_bone_states) != len(bones.names) + len(manifest['bones'])+len(layers(manifest))+len(shadows(manifest)):
        raise ValueError('Animation roundtrip channel count mismatch')
    return data, {'additive': animation.is_additive, **metrics}


def resolve_inline(index, store, file_id, type_id, external_cache):
    """TOC-only indexing omits external payloads; check raw sizes before copying."""
    package = index.locate(file_id, type_id)
    if package not in external_cache:
        header = store.load_toc_header(package)
        types, count = struct.unpack_from('<II', header, 4)
        start = 72 + types * 32
        external_cache[package] = {
            struct.unpack_from('<QQ', header, start + i * 80)
            for i in range(count)
            if any(struct.unpack_from('<II', header, start + i * 80 + 60))}
    if (file_id, type_id) in external_cache[package]:
        raise ValueError(f'Resource {file_id}/{type_id} has external stream/GPU data; cannot copy it as inline')
    return index.resolve(file_id, type_id)


def load_avatar_template(path, original):
    """Accept one standalone mesh only when its original bind graph is identical."""
    path = Path(path)
    template = TocArchive.parse_parts(path.read_bytes(),
        Path(str(path)+'.gpu_resources').read_bytes(), Path(str(path)+'.stream').read_bytes())
    if set(template.entries) != {(original.file_id, UNIT_TYPE_ID)}:
        raise ValueError('Avatar template must contain only the reference Unit')
    entry = template.entries[original.file_id, UNIT_TYPE_ID]
    if struct.unpack_from('<Q', entry.toc_data, 16)[0] or not entry.gpu_data or entry.stream_data:
        raise ValueError('Avatar template must have standalone GPU mesh data and no CompositeRef or stream')
    a, b = UnitData.parse(original.toc_data), UnitData.parse(entry.toc_data)
    if (a.bones_ref, a.state_machine_ref, a.name_hashes, a.parents) != (b.bones_ref, b.state_machine_ref, b.name_hashes, b.parents):
        raise ValueError('Avatar template references or node graph differ from the current game')
    old_at = struct.unpack_from('<I', original.toc_data, 52)[0]
    new_at = struct.unpack_from('<I', entry.toc_data, 52)[0]
    size = 16+136*len(a.transforms)
    if original.toc_data[old_at:old_at+size] != entry.toc_data[new_at:new_at+size]:
        raise ValueError('Avatar template bind data differ from the current game')
    return entry


def build_project(manifest_path, config_path, game_data, output, sample_count=None, threads=None):
    if threads is not None and (isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 16):
        raise ValueError("threads must be an integer between 1 and 16")
    manifest_path, config_path, output = map(Path, (manifest_path, config_path, output))
    manifest = load_manifest(manifest_path)
    from .native_config import resolve_native_config
    config_document=resolve_native_config(config_path,manifest)
    options = config_document.get('native_skeleton', {})
    if options.get('calibrate_weapon_bones') and not manifest.get('weaponGripCalibration'):
        raise ValueError('Prepare the converted model weapon bones before attachment swap; run prepare-native-model first')
    fps = options.get('fps', 30)
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
        raise ValueError('[native_skeleton].fps must be an integer between 1 and 120')
    workers = threads if threads is not None else options.get('workers', 4)
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
        raise ValueError('[native_skeleton].workers must be an integer between 1 and 16')
    allowed = {'fps', 'workers', 'apply_driver_config', 'rotate_multipliers', 'rotation_compensation', 'ik_correction', 'model_scale', 'align_standard_grips', 'align_standard_feet','grip_target','stable_grip_pole','grip_soft_distance','foot_y_degrees','avatar_template','arm_reference_archive','preserve_arm_reference_clavicles','attachment_swap','calibration_preset','runtime_policy','calibrate_weapon_bones','use_model_preset','attachment_mode'}
    if set(options) - allowed:
        raise ValueError(f'Unknown native_skeleton settings: {sorted(set(options)-allowed)}')
    if not isinstance(options.get('stable_grip_pole',False),bool):
        raise ValueError('stable_grip_pole must be true or false')
    soft=options.get('grip_soft_distance',0.)
    if isinstance(soft,bool) or not isinstance(soft,(int,float)) or not math.isfinite(soft) or not 0<=soft<=.05:
        raise ValueError('grip_soft_distance must be metres between 0 and 0.05')
    angles=options.get('foot_y_degrees',{})
    if not isinstance(angles,dict) or any(k not in ('l_foot','r_foot') or isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>90 for k,v in angles.items()):
        raise ValueError('foot_y_degrees accepts l_foot/r_foot angles between -90 and 90')
    model_scale = config_document.get('native_skeleton', {}).get('model_scale', 1.)
    if isinstance(model_scale, bool) or not isinstance(model_scale, (int,float)) or not math.isfinite(model_scale) or not 0 < model_scale <= 10:
        raise ValueError('native_skeleton.model_scale must be in (0,10]')
    if abs(model_scale - manifest.get('modelScale', 1.)) > 1e-6:
        raise ValueError('Model/config scale mismatch; reconvert the model before rebuilding animations')
    if options.get('grip_target','configured') not in ('configured','original'):
        raise ValueError('native_skeleton.grip_target must be configured or original')
    avatar_template = options.get('avatar_template')
    if avatar_template is not None and (not isinstance(avatar_template, str) or not avatar_template.strip()):
        raise ValueError('native_skeleton.avatar_template must be a nonempty path')
    arm_reference_archive = options.get('arm_reference_archive')
    if arm_reference_archive is not None and (not isinstance(arm_reference_archive, str) or not arm_reference_archive.strip()):
        raise ValueError('native_skeleton.arm_reference_archive must be a nonempty path')
    for key in allowed - {'fps', 'workers', 'model_scale','grip_target','grip_soft_distance','foot_y_degrees','avatar_template','arm_reference_archive','calibration_preset','runtime_policy','attachment_mode'}:
        if key in options and not isinstance(options[key], bool):
            raise ValueError(f'native_skeleton.{key} must be true or false')
    # 挂点对调（B22）：[attachment_swap] 表驱动「动画侧节点级互换」；开关在
    # [native_skeleton].attachment_swap。注入 options 供 convert_clip 使用。
    swap_config=attachment_swap_plan(options.get('attachment_swap_config') or config_document.get('attachment_swap',{}),
        options.get('attachment_swap',False))
    options = dict(options)
    if options.get('attachment_mode')=='source-lua-native-hd2-v1' and swap_config:
        raise ValueError('Managed Source/Lua route forbids attachment swap')
    if options.get('attachment_mode') not in (None,'source-lua-native-hd2-v1'):
        raise ValueError('Unsupported native attachment mode')
    options['attachment_swap_config'] = swap_config
    config = ModConfig.load(config_path)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Output must be empty; choose a new project directory')
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, output/'config.toml')
    (output/'source-skeleton.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'status': 'building', 'threads': workers, 'game_tested': False, 'animations': [], 'files': [],
              'attachment_swap_contract': 'v2-after-arm-reference-scaled-parent',
              'source_bones': len(manifest['bones']), 'config_sha256': hashlib.sha256(config_path.read_bytes()).hexdigest()}
    def save_report():
        (output/'build-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save_report()
    index = None
    try:
        progress('index', 0, 1, '读取游戏 bundle 映射')
        store = PackageStore(Path(game_data))
        index = ResourceIndex(store, output/'resource-index.sqlite3', {BONE_TYPE_ID, STATE_MACHINE_TYPE_ID, ANIMATION_TYPE_ID, UNIT_TYPE_ID})
        index.load_or_build(lambda done,total,label: progress('index',done,total, f'读取游戏资源索引 {done}/{total}') if done % 250 == 0 or done == total else None)
        external_cache = {}
        def resolve(file_id, type_id):
            return resolve_inline(index, store, file_id, type_id, external_cache)
        _, unit_entry = resolve(int(manifest['referenceUnit'], 0), UNIT_TYPE_ID)
        unit = UnitData.parse(unit_entry.toc_data)
        output_unit_entry = unit_entry
        if avatar_template is not None:
            template_path = (config_path.parent/avatar_template).resolve()
            output_unit_entry = load_avatar_template(template_path, unit_entry)
            report['avatar_template'] = {'path': avatar_template, 'composite_ref': 0,
                'toc_sha256': hashlib.sha256(output_unit_entry.toc_data).hexdigest(),
                'gpu_sha256': hashlib.sha256(output_unit_entry.gpu_data).hexdigest(),
                'gpu_bytes': len(output_unit_entry.gpu_data), 'original_bind_byte_identical': True}
        _, bones_entry = resolve(unit.bones_ref, BONE_TYPE_ID)
        bones = BonesData.parse(bones_entry.toc_data)
        ensure_hand_references(manifest,unit,bones)
        from .attachment_skeleton import resolve_source_attachment_channels
        resolve_source_attachment_channels(manifest,unit,bones)
        (output/'source-skeleton.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        _, state = resolve(unit.state_machine_ref, STATE_MACHINE_TYPE_ID)
        animation_ids = sorted(set(parse_state_machine_animation_ids(state.toc_data)))
        if not animation_ids:
            raise ValueError('Reference avatar has no animations')
        report['available_animations']=len(animation_ids)
        if sample_count is not None:
            if not 1<=sample_count<=32:raise ValueError('Diagnostic sample count must be 1..32')
            animation_ids=[animation_ids[round(i*(len(animation_ids)-1)/max(1,sample_count-1))] for i in range(sample_count)]
            report['diagnosticSample']=True
        else:report['diagnosticSample']=False
        arm_reference = None
        if arm_reference_archive is not None:
            from .native_arm_reference import AnimationReference
            arm_reference = AnimationReference((config_path.parent/arm_reference_archive).resolve())
            if not set(animation_ids).issubset(arm_reference.entries):
                raise ValueError('Arm reference archive does not cover every current animation')
            with arm_reference.path.open('rb') as stream:
                reference_sha = hashlib.file_digest(stream,'sha256').hexdigest()
            report['arm_reference_archive'] = {'path': arm_reference_archive, 'sha256': reference_sha,
                                              'scope': '38 Source arm rotation channels; additive retained'}
        report['expected_animations'] = len(animation_ids)
        report['driver_bones'] = len(bones.names)
        report['avatar_nodes'] = len(unit.name_hashes)
        report['mapped_source_bones'] = sum(n['driver'] is not None for n in manifest['bones'])
        report['sampling_fps'] = fps
        report['driver_config_applied'] = options.get('apply_driver_config', True)
        report['model_scale'] = model_scale
        report['retarget_version'] = 'native-anatomical-elbow-v13' if layers(manifest) else 'configured-grips-source-origin-dual-attachments-v6'
        if arm_reference is not None:report['retarget_version'] = 'native-reference-arms-v15' if options.get('preserve_arm_reference_clavicles',False) else 'native-reference-arms-v14'
        report['motion_layer_nodes']=len(layers(manifest))
        report['attachment_shadow_nodes']=len(shadows(manifest))
        report['attachment_swap'] = swap_config if swap_config is not None else {'enabled': False}
        report['driver_poses_preserved'] = True
        report['physics_unlinked_nodes'] = sum(n.get('physics', False) for n in manifest['bones'])
        save_report()
        # Bounded chunks keep a full 3,000+ clip set from retaining gigabytes in RAM.
        # Runtime stays under an incomplete name until every referenced clip succeeds.
        staging = output/'runtime.incomplete'
        staging.mkdir()
        archive = TocArchive.load_toc_only(store, '9ba626afa44a3aa3')
        writer = InlinePatchWriter(archive, staging/'9ba626afa44a3aa3.patch_2',
            {UNIT_TYPE_ID:1, BONE_TYPE_ID:1, STATE_MACHINE_TYPE_ID:1, ANIMATION_TYPE_ID:len(animation_ids)},
            standalone=avatar_template is not None)
        def write_chunk(entries):
            for entry in entries: writer.append(entry)
        entries = []
        for original, data in [(output_unit_entry, append_unit(output_unit_entry.toc_data, manifest)),
                               (bones_entry, append_bones(bones_entry.toc_data, manifest))]:
            entry = copy.deepcopy(original); entry.toc_data = data
            if (original.gpu_data or original.stream_data) and original is not output_unit_entry:
                raise ValueError('Unexpected external data in avatar/Bones; refuse to discard it')
            entries.append(entry)
        write_chunk(entries)  # avatar/Bones are separate from animation payloads
        patched_state, mask_count = append_state_machine_masks(state.toc_data, bones, manifest)
        state_entry = copy.deepcopy(state)
        state_entry.toc_data = patched_state
        write_chunk([state_entry])  # current-game masks belong to the animation companion, never the model package
        report['blend_masks_extended'] = mask_count
        mask_owners=source_blend_mask_owners(bones,manifest) if mask_count else []
        report['unmapped_root_masks']=[dict(name=n['name'],sourceName=n.get('sourceName'),
            sourceIndex=i,publishedParent=source_parent(i,n,manifest,len(manifest['driverHashes'])),
            ownerChannel=mask_owners[i],ownerName=bones.names[mask_owners[i]])
            for i,n in enumerate(manifest['bones']) if mask_count and n['parent'] is None and n['driver'] is None]
        report['state_machine'] = str(state.file_id)
        entries = []
        with ProcessPoolExecutor(max_workers=workers) as executor:
            pending = deque()
            iterator = iter(animation_ids)
            def enqueue():
                animation_id = next(iterator, None)
                if animation_id is None:
                    return
                package, original = resolve(animation_id, ANIMATION_TYPE_ID)
                pending.append((animation_id, package, original, executor.submit(convert_clip,
                    original.toc_data, bones, unit, manifest, config, options,
                    arm_reference.read(animation_id) if arm_reference is not None else None)))
            for _ in range(workers * 2):
                enqueue()
            while pending:
                animation_id, package, original, future = pending.popleft()
                try:
                    data, metrics = future.result()
                except Exception as error:
                    raise ValueError(f'Animation {animation_id} ({package}): {error}') from error
                entry = copy.copy(original)
                entry.toc_data = bytearray(data)
                entries.append(entry)
                report['animations'].append({'id': str(animation_id), 'package': package, **metrics})
                number = len(report['animations'])
                progress('animation', number, len(animation_ids), f'转换原生骨架动画 {number}/{len(animation_ids)}')
                if number % 64 == 0:
                    write_chunk(entries)
                    entries = []
                    save_report()
                enqueue()
        if entries:
            write_chunk(entries)
        for path in writer.finish():
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            report['files'].append({'path':'runtime/'+path.name,'bytes':path.stat().st_size,'sha256':digest})
        staging.rename(output/'runtime')
        report['status'] = 'complete'
        report['scope'] = 'HD2 third-person avatar; global animation/Bones replacement, one Source rig at a time'
        save_report()
        return report
    except BaseException as error:
        report['status'] = 'failed'; report['error'] = str(error); save_report()
        raise
    finally:
        if 'writer' in locals(): writer.close()
        if index is not None:
            index.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build HD2 animations for an intact Source bind rig')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--game-data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sample-count',type=int,help='Diagnostic only: select 1..32 clips, never production default')
    from .cli import parse_thread_count
    parser.add_argument('--threads', type=parse_thread_count, help='Parallel animation workers (1..16); overrides config workers')
    args = parser.parse_args(argv)
    try:
        report = build_project(args.manifest, args.config, args.game_data, args.output,args.sample_count,args.threads)
        print(json.dumps({'status': report['status'], 'animations': len(report['animations']), 'output': str(args.output)}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
