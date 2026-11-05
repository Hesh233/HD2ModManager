"""Independent animation layers for native ancestors with distinct blend masks."""
import copy,struct
from .formats import UnitData,AnimationBoneState,AnimationEntry
from .processor import WorldTransform,_build_tracks,_calculate_world_transforms
from .math3d import quat_inverse,quat_multiply,quat_rotate,vec_sub

def layers(manifest):
    return manifest.get('motionLayers',[])

def source_local(node,index,manifest):
    return manifest.get('motionLocalOverrides',{}).get(str(index),node['local'])

def source_parent(index,node,manifest,source_offset):
    layer=manifest.get('motionParentOverrides',{}).get(str(index))
    if layer is not None:return source_offset+len(manifest['bones'])+layer
    return 0 if node['parent'] is None else source_offset+node['parent']

def matrix(pose,world=False):
    x,y,z,w=pose.rotation
    r=[1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,
       2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,
       2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y]
    if world:return r[:3]+[0.]+r[3:6]+[0.]+r[6:]+[0.]+list(pose.position)+[1.]
    return r+list(pose.position)+list(pose.scale)+[0.]

def relative(parent,child):
    q=quat_inverse(parent.rotation)
    return WorldTransform(quat_rotate(q,vec_sub(child.position,parent.position)),quat_multiply(q,child.rotation),[1.,1.,1.])

def apply_unit_layers(data,manifest):
    """Append helper nodes; preserve existing indices and all world bind matrices."""
    rows=layers(manifest)
    if not rows:return data
    u=UnitData.parse(data);count=len(u.transforms);offset=struct.unpack_from('<I',data,52)[0]
    local=copy.deepcopy(u.transforms);parents=list(u.parents);hashes=list(u.name_hashes)
    world=_calculate_world_transforms(local,parents);lookup={h:i for i,h in enumerate(hashes)}
    for row in rows:
        if row['hash'] in lookup:raise ValueError('Motion layer already exists')
        parent=lookup[row['parentHash']];driver=lookup[row['driverHash']]
        target=world[driver]
        lookup[row['hash']]=len(hashes);hashes.append(row['hash']);parents.append(parent)
        local.append(relative(world[parent],target));world.append(target)
    for key,layer in manifest.get('motionParentOverrides',{}).items():
        node=manifest['bones'][int(key)];i=lookup[node['hash']];parent=lookup[rows[layer]['hash']]
        parents[i]=parent;local[i]=relative(world[parent],world[i])
    after=_calculate_world_transforms(local,parents)
    if any(max(abs(a-b) for a,b in zip(before.position,now.position))>1e-5 or abs(sum(a*b for a,b in zip(before.rotation,now.rotation)))<1-1e-5 for before,now in zip(world,after)):
        raise ValueError('Motion reparent changed bind pose')
    block=bytearray(struct.pack('<I',len(local))+data[offset+4:offset+16])
    changed={lookup[manifest['bones'][int(key)]['hash']] for key in manifest.get('motionParentOverrides',{})}
    for i,t in enumerate(local):
        block.extend(data[offset+16+64*i:offset+16+64*(i+1)] if i<count and i not in changed else struct.pack('<16f',*matrix(t)))
    for i,t in enumerate(world):
        block.extend(data[offset+16+64*count+64*i:offset+16+64*count+64*(i+1)] if i<count else struct.pack('<16f',*matrix(t,True)))
    entries=offset+16+128*count
    for i,parent in enumerate(parents):
        if i<count and i not in changed:block.extend(data[entries+4*i:entries+4*(i+1)])
        else:
            flags=struct.unpack_from('<H',data,entries+4*i)[0] if i<count else 1
            block.extend(struct.pack('<HH',flags,65535 if parent is None else parent))
    block.extend(struct.pack(f'<{len(hashes)}I',*hashes))
    output=bytearray(data);output.extend(b'\0'*(-len(output)%16));struct.pack_into('<I',output,52,len(output));output.extend(block)
    return output

def append_motion_animation(result,configured,bones,manifest,times):
    start=len(result.initial_bone_states);tracks=_build_tracks(configured)
    for i,row in enumerate(layers(manifest)):
        channel=bones.names.index(row['driver'])
        p,q,s=(tr[channel].evaluate(0.) for tr in tracks)
        result.initial_bone_states.append(AnimationBoneState(list(p),list(q),list(s),False,False,False))
        for t in times[1:]:
            for subtype,track in zip((4,5,6),tracks):
                result.entries.append(AnimationEntry(0,subtype,start+i,t,track[channel].evaluate(t)))
