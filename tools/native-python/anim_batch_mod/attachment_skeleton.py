"""Unmodified attachment reference nodes, independent of Lua output nodes."""
import copy,struct
from .formats import UnitData,BonesData,AnimationBoneState,AnimationEntry
from .math3d import quat_inverse,quat_multiply,quat_rotate,vec_sub
from .processor import WorldTransform,_build_tracks,_calculate_world_transforms,_compose_additive_local,_decompose_additive_position
from .motion_skeleton import layers

def attachment_swap_plan(raw,enabled=True):
    """Normalize the same hand swap table for animation baking and runtime audit."""
    if not enabled:return None
    raw=raw or {};policy=raw.get('policy','position')
    if policy not in ('position','pose'):raise ValueError('attachment_swap.policy must be position or pose')
    pairs=raw.get('pairs')
    if pairs is None:
        pairs=[dict(native=raw.get(side+'_native','attach_hand_'+side[0]),
            source=raw.get(side+'_source',default)) for side,default in
            (('right','ValveBiped.weapon_bone'),('left','ValveBiped.L_weapon_bone'))]
    normalized=[]
    for pair in pairs:
        native,source=pair.get('native'),pair.get('source')
        if not isinstance(native,str) or not native.strip() or not isinstance(source,str) or not source.strip():
            raise ValueError('attachment_swap source/native must be nonempty names')
        normalized.append(dict(native=native.strip(),source=source.strip()))
    if len({p['native'].lower() for p in normalized})!=len(normalized):
        raise ValueError('Duplicate native hand swap target')
    return dict(policy=policy,pairs=normalized)


def shadows(manifest):return manifest.get('attachmentShadows',[])+manifest.get('sourceAttachmentShadows',[])

def ensure_hand_references(manifest, unit, bones):
    """New GUI exports need the unswapped hand tracks that historic test01 already carries."""
    from .native_skeleton import bone_name_hash
    rows=manifest.setdefault('attachmentShadows',[])
    for name in ('attach_hand_l','attach_hand_r'):
        index=unit.name_hashes.index(bone_name_hash(name))
        existing=[row for row in rows if row['index']==index]
        if len(existing)>1:raise ValueError('Duplicate unswapped hand references: '+name)
        if existing:
            row=existing[0];channel=bones.hashes.index(unit.name_hashes[index])
            if row.get('animationChannel')!=channel or row.get('maskChannel')!=channel:
                raise ValueError('Hand reference must use Bones channel, not Unit index: '+name)
            if row.get('hash')!=bone_name_hash(row['name']) or row['hash']==unit.name_hashes[index]:
                raise ValueError('Hand reference must be an independent named node: '+name)
            continue
        reference=f"__hd2_attach_original__{manifest['boneNamespace']}_{index:03d}"
        channel=bones.hashes.index(unit.name_hashes[index])
        rows.append(dict(index=index,name=reference,hash=bone_name_hash(reference),animationChannel=channel,maskChannel=channel))
    return manifest


def upgrade_reference_animation(converted_data, original_data, bones, unit, manifest):
    """Append missing original hand references to an already validated animation.

    Existing retarget/attachment-swap results, events and all earlier channels
    retain their values. Reuse this for archived projects, without reretargeting.
    """
    from .formats import AnimationData
    converted=AnimationData.parse(converted_data);original=AnimationData.parse(original_data)
    expected=len(bones.names)+len(manifest['bones'])+len(layers(manifest))
    assert len(converted.initial_bone_states)==expected, 'Only a project without shadows can be upgraded'
    assert not manifest.get('sourceAttachmentShadows'), 'Existing shadow projects need no channel upgrade'
    before_states=copy.deepcopy(converted.initial_bone_states)
    before_entries=copy.deepcopy(converted.entries)
    times=sorted({0.,*(e.time for e in original.entries if e.is_position or e.is_rotation or e.is_scale)})
    append_shadow_animation(converted,original,bones,unit,manifest,times,_build_tracks(original))
    converted.entries.sort(key=lambda e:e.time)
    encoded=converted.to_bytes();checked=AnimationData.parse(encoded)
    assert checked.initial_bone_states[:expected]==before_states, 'Existing animation state changed'
    retained=[e for e in checked.entries if not (e.is_position or e.is_rotation or e.is_scale) or e.bone<expected]
    assert retained==before_entries, 'Existing key/event changed'
    # Verify every new channel at every original key time against the original
    # track, including additive scale deltas; never read the swapped hand output.
    a,b=_build_tracks(original),_build_tracks(checked)
    for i,row in enumerate(manifest['attachmentShadows']):
        for time in times:
            for kind,(old,new) in enumerate(zip(a,b)):
                x,y=old[row['animationChannel']].evaluate(time),new[expected+i].evaluate(time)
                error=max(abs(v-w) for v,w in zip(x,y))
                if kind==1:error=min(error,max(abs(v+w) for v,w in zip(x,y)))
                assert error<1e-5, (row['index'],kind,time,error)
    return encoded

def transfer_attachments(avatar, manifest, native_names, reference, native_bind):
    """Shared B23/GUI attachment plan; head descendants and controller inputs stay native."""
    from .native_skeleton import bone_name_hash
    from .math3d import quat_rotate
    native_names=dict(native_names)
    for name in ('hellpad_socket',):
        h=bone_name_hash(name)
        if h in avatar.name_hashes:native_names[name]=avatar.name_hashes.index(h)
    by_driver = {n['driver']:i for i,n in enumerate(manifest['bones']) if n['driver']}
    def node(name):
        index=avatar.name_hashes.index(bone_name_hash(name))
        return dict(name=name,index=index,parent=avatar.parents[index],hash=bone_name_hash(name))
    targets = {name:driver for names,driver in (
        (('attach_samplepouch','attach_intelpad','target_designator','attach_knife'),'spine1'),
        (('sling',),'spine2'),
        (('backpack','support_mg','support',*[f'cape{i}' for i in range(1,9)]),'chest'),
        (('attach_weapon',),'r_hand'),(('attach_hand_l',),'l_hand'),
        (('hellpad_socket',),'l_elbow'),(('pistol',),'r_thigh')) for name in names}
    result=[]
    for name,driver in targets.items():
        if name not in native_names or driver not in by_driver:continue
        index=native_names[name]
        ancestor=index
        while ancestor is not None:
            if ancestor==native_names.get('head'):raise ValueError('Head attachment must remain native: '+name)
            ancestor=avatar.parents[ancestor]
        q=quat_multiply(quat_inverse(reference[by_driver[driver]]),native_bind[native_names[driver]].rotation)
        axes=[v for axis in ([1,0,0],[0,1,0],[0,0,1]) for v in quat_rotate(q,axis)]+[0,0,0]
        row=dict(node=node(name),native=node(driver),source=node(manifest['bones'][by_driver[driver]]['name']),axes=axes)
        if name=='attach_hand_l':
            shadow=next(s for s in manifest['attachmentShadows'] if s['index']==index)
            row['reference']=node(shadow['name'])
        result.append(row)
    return sorted(result,key=lambda row:row['node']['index'])


def validate_attachment_transfer_contract(profile,avatar,bones,manifest,swap_config=None):
    """One channel/node/semantic check shared by project packaging and GUI export.

    The runtime consumes unswapped native shadows and converter hand axes. Source
    weapon bones are bake carriers, never the runtime's calibration references.
    """
    from .native_skeleton import bone_name_hash
    if profile.get('axisRegistration')!='converter-reference-rotation':
        raise ValueError('Attachment runtime axes must come from the converter reference')
    def check_node(row):
        index=avatar.name_hashes.index(bone_name_hash(row['name']))
        if index!=row['index'] or avatar.parents[index]!=row['parent']:
            raise ValueError('Attachment contract node identity/parent mismatch: '+row['name'])
        return index
    left=next(row for row in profile['attachments'] if row['node']['name']=='attach_hand_l')
    rows=[]
    for name,driver,output,reference,anchor in (
        ('attach_hand_r','r_hand',profile['target'],profile['originalMount'],profile['sourceRight']),
        ('attach_hand_l','l_hand',left['node'],left['reference'],profile['sourceLeft'])):
        index=check_node(output);ref=check_node(reference);check_node(anchor)
        native=next(n for n in profile['avatar']['nodes'] if n['name']==driver)
        check_node(native)
        if ref==index or avatar.parents[ref]!=native['index'] or avatar.parents[index]!=native['index']:
            raise ValueError('Native hand reference must be independent and under the same native hand: '+name)
        shadow=[row for row in manifest['attachmentShadows'] if row['index']==index]
        if len(shadow)!=1 or shadow[0]['hash']!=avatar.name_hashes[ref]:
            raise ValueError('Unswapped hand reference missing/duplicated: '+name)
        channel=bones.hashes.index(avatar.name_hashes[index]);ref_channel=bones.hashes.index(avatar.name_hashes[ref])
        if shadow[0]['animationChannel']!=channel or shadow[0]['maskChannel']!=channel or ref_channel==channel:
            raise ValueError('Hand swap contract confuses animation channel and Unit index: '+name)
        source=next(n for n in manifest['bones'] if n['driver']==driver)
        if anchor['name']!=source['name']:
            raise ValueError('Runtime calibration must use the converter hand, not an old Source weapon bone: '+name)
        rows.append(dict(native=name,nativeNode=index,nativeChannel=channel,
            nativeReference=reference['name'],referenceNode=ref,referenceChannel=ref_channel,
            runtimeSource=anchor['name'],runtimeSourceNode=anchor['index']))
    if swap_config:
        swap_config=attachment_swap_plan(swap_config)
        if swap_config.get('policy','position')!='position':
            raise ValueError('Position-only native-aim runtime cannot pair with a pose-swap animation build')
        for pair in swap_config.get('pairs',[]):
            if pair['native'] not in ('attach_hand_r','attach_hand_l'):continue
            row=next(row for row in rows if row['native']==pair['native'])
            carrier=[n for n in manifest['bones'] if (n.get('sourceName') or '').lower()==pair['source'].lower()]
            if len(carrier)==1:
                row['sourceBakeCarrier']=carrier[0]['name']
                row['sourceBakeChannel']=bones.hashes.index(bone_name_hash(carrier[0]['name']))
                row['sourceBakeNode']=avatar.name_hashes.index(bone_name_hash(carrier[0]['name']))
    return dict(status='PASS',pairs=rows,policy='position_preserve_native_aim',
        nativeReferencePolicy='original_unswapped_animation_channels',
        runtimeCalibration='converter_hands_not_legacy_weapon_bone_worlds',
        additivePolicy='no_world_path_swap_preserve_original_references')


def transfer_profile(original_raw, original_bones_raw, manifest, model_units, weapon_targets, soft_distance=.008):
    """Compile the existing B23 rig and configuration from this model's converter reference."""
    import math
    from . import native_skeleton as native
    from .formats import BonesData
    from .motion_skeleton import source_local
    from .math3d import quat_inverse_rotate
    from .processor import _cross
    original=UnitData.parse(original_raw);bones=BonesData.parse(original_bones_raw)
    ensure_hand_references(manifest,original,bones)
    native_names={n:original.name_hashes.index(h) for n,h in zip(bones.names,bones.hashes)}
    expanded_raw=native.append_unit(original_raw,manifest)
    revised,bone_raw,rig=runtime_outputs(expanded_raw,native.append_bones(original_bones_raw,manifest),manifest,native_names)
    avatar=UnitData.parse(revised);by_driver={n['driver']:i for i,n in enumerate(manifest['bones']) if n['driver']}
    source_bind=[native.local_pose(source_local(n,i,manifest)) for i,n in enumerate(manifest['bones'])]
    bind=_calculate_world_transforms(original.transforms,original.parents)
    reference,reference_local=native._reference_rotations(manifest['bones'],source_bind,
        [native.row_pose(n['world']) for n in manifest['bones']],bind,native_names,manifest)
    def affine(q,p=(0,0,0)):
        return [v for axis in ([1,0,0],[0,1,0],[0,0,1]) for v in quat_rotate(q,axis)]+list(p)
    def node(name):
        h=native.bone_name_hash(name);i=avatar.name_hashes.index(h)
        return dict(name=name,index=i,parent=avatar.parents[i],hash=h)
    def source(driver):return node(manifest['bones'][by_driver[driver]]['name'])
    rig_rows={r['driver']:r for r in rig['rows']}
    def ref(driver):return node(rig_rows[driver]['referenceName']) if driver in rig_rows else source(driver)
    def axes(driver):return affine(quat_multiply(quat_inverse(reference[by_driver[driver]]),bind[native_names[driver]].rotation))
    nr,nl,sr,sl=node('r_hand'),node('l_hand'),source('r_hand'),source('l_hand')
    target=node('attach_hand_r');shadow=next(r for r in manifest['attachmentShadows'] if r['index']==target['index'])
    original_mount=node(shadow['name'])
    watched=[target,nr,nl,sr,sl,original_mount,node('attach_hand_l'),node('weapon_aim'),
        source('r_shoulder'),source('r_elbow'),source('l_shoulder'),source('l_elbow'),source('spine1')]
    models={};sync=[]
    for driver in ('hips','spine1','spine2','chest','neck','head','l_clavicle','l_shoulder','l_elbow','l_hand',
                   'r_clavicle','r_shoulder','r_elbow','r_hand'):
        row=dict(name=driver,native=node(driver),source=source(driver),axes=axes(driver))
        if driver in rig_rows:row['reference']=ref(driver)
        sync.append(row)
    for resource,unit in model_units.items():
        signature=[]
        for driver in ('spine1','r_shoulder','r_elbow','r_hand','l_hand'):
            av=source(driver);i=unit.name_hashes.index(av['hash'])
            signature.append(dict(name=av['name'],hash=av['hash'],index=i,parent=unit.parents[i],avatarIndex=av['index']))
        models[resource]=dict(kind='model',resource=resource,count=len(unit.parents),nodes=signature,
            observeNodes=[dict(name=r['source']['name'],index=unit.name_hashes.index(r['source']['hash']),
                avatarIndex=r['source']['index'],driver=r['name']) for r in sync])
    assert models,'No body model layouts; refusing a global Avatar-only writer'
    # Same stable elbow reference as the converter and B13/B14 calibration.
    expanded=UnitData.parse(expanded_raw);local=list(expanded.transforms);offset=len(original.parents)
    for i,(p,q) in enumerate(zip(source_bind,reference_local)):
        local[offset+i]=WorldTransform(list(p.position),q,[1,1,1])
    world=_calculate_world_transforms(local,expanded.parents)
    a,b,c=[offset+by_driver['l_'+n] for n in ('shoulder','elbow','hand')]
    normal=_cross(vec_sub(world[b].position,world[a].position),vec_sub(world[c].position,world[b].position))
    length=math.sqrt(sum(v*v for v in normal));assert length>1e-8,'Degenerate Source elbow reference'
    hinge=quat_inverse_rotate(world[a].rotation,[v/length for v in normal])
    na,nb,nc=[bind[native_names['l_'+n]] for n in ('shoulder','elbow','hand')]
    forearm=quat_inverse_rotate(reference[by_driver['l_elbow']],_cross(vec_sub(nb.position,na.position),vec_sub(nc.position,nb.position)))
    body=[]
    for driver in ('spine2','chest'):
        out=source(driver);pose=avatar.transforms[out['index']]
        q=quat_multiply(quat_inverse(bind[native_names[driver]].rotation),reference[by_driver[driver]])
        parent=manifest['bones'][by_driver[driver]]['parent']
        body.append(dict(node=out,native=node(driver),reference=ref(driver),
            positionParent=node(manifest['bones'][parent]['name']),localPose=affine(q,pose.position)))
    attachments=transfer_attachments(avatar,manifest,native_names,reference,bind)
    left_outputs=[source('l_'+n) for n in ('shoulder','elbow','hand')]
    corrected={r['node']['index'] for r in attachments}|{r['index'] for r in left_outputs}|{target['index']}
    cfg=dict(version=1,variant=manifest['boneNamespace']+'-B23-1.0.7',axisRegistration='converter-reference-rotation',
        avatar=dict(kind='avatar',resource=f"{int(manifest['referenceUnit'],0):016x}",count=len(avatar.parents),nodes=watched),
        models=models,consumers={},target=target,nativeRight=nr,nativeLeft=nl,sourceRight=sr,sourceLeft=sl,
        originalMount=original_mount,rightAxes=axes('r_hand'),leftAxes=axes('l_hand'),attachments=attachments,
        protected=[dict(n,world=n['name']!='weapon_aim') for n in watched if n['index'] not in corrected],
        bodySync=dict(enabled=True,outputs=body,mode='native_parent_unanimated_output'),
        leftGrip=dict(enabled=True,nodes=[ref('l_'+n) for n in ('clavicle','shoulder','elbow','hand')],outputs=left_outputs,
            weaponTargets=weapon_targets,contactMetres=.002,contactDegrees=.1,linkMetres=.002,linkDegrees=.1,
            hingeAxis=hinge,forearmHingeAxis=forearm,softDistance=soft_distance,
            reachPolicy='anim_batch_mod.processor._apply_two_bone_ik',requireNativeContact=False),
        sync=dict(enabled=True,seconds=.2,maxSamples=1800,pairs=sync,aim=node('weapon_aim')),
        minNodes=3,maxNodes=1024,maxRecords=50000,scanSeconds=.5,logSeconds=.2,consumerRadius=3.,
        maxWristMountDistance=.5,matchTolerance=.001,localTolerance=.00002,worldTolerance=.002)
    return cfg,revised,bone_raw,rig

def append_unit_shadows(data,manifest):
    rows=shadows(manifest)
    if not rows:return data
    u=UnitData.parse(data);count=len(u.transforms);offset=struct.unpack_from('<I',data,52)[0]
    local=offset+16;world=local+64*count;parents=world+64*count
    remap={r['index']:count+i for i,r in enumerate(manifest.get('attachmentShadows',[]))}
    block=bytearray(struct.pack('<I',count+len(rows))+data[offset+4:offset+16])
    for base in (local,world):
        block.extend(data[base:base+64*count])
        for r in rows:
            if 'sourceParent' in r:
                values=r['localMatrix'] if base==local else r['worldMatrix']
                block.extend(struct.pack('<16f',*values))
            else:block.extend(data[base+64*r['index']:base+64*(r['index']+1)])
    block.extend(data[parents:parents+4*count])
    for r in rows:
        parent=u.parents[r['index']]
        parent=r['sourceParent'] if 'sourceParent' in r else remap.get(parent,parent)
        block.extend(struct.pack('<HH',1,parent if parent is not None else 65535))
    block.extend(struct.pack(f'<{count}I',*u.name_hashes))
    block.extend(struct.pack(f'<{len(rows)}I',*(r['hash'] for r in rows)))
    result=bytearray(data);result.extend(b'\0'*(-len(result)%16));struct.pack_into('<I',result,52,len(result));result.extend(block)
    return result

def append_shadow_animation(result,original,bones,unit,manifest,times,tracks):
    rows=manifest.get('attachmentShadows',[]);start=len(bones.names)+len(manifest['bones'])+len(layers(manifest))
    for i,row in enumerate(rows):
        ui=row['index'];channel=row['animationChannel']
        def values(t):
            if channel is not None:return [track[channel].evaluate(t) for track in tracks]
            if original.is_additive:return [[0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.]]
            bind=unit.transforms[ui];return [bind.position,bind.rotation,bind.scale]
        p,r,s=values(0.)
        result.initial_bone_states.append(AnimationBoneState(list(p),list(r),list(s),False,False,False))
        for time in times[1:]:
            for subtype,value in zip((4,5,6),values(time)):
                result.entries.append(AnimationEntry(0,subtype,start+i,time,list(value)))


def source_attachment_pose(world,row):
    anchor=world[row['driverAnchorIndex']];target=world[row['index']]
    inverse=quat_inverse(anchor.rotation);axis=row['axisCorrection']
    return WorldTransform(quat_rotate(axis,quat_rotate(inverse,vec_sub(target.position,anchor.position))),
        quat_multiply(axis,quat_multiply(inverse,target.rotation)),[1.,1.,1.])


def append_source_attachment_animation(result,configured,bones,unit,manifest,times):
    """Bake offsets from the same configured driver pose as Source retargeting.

    A Source reference is parented to its Source anchor. Lua selects the baked
    output; it never subtracts a live native hand from a baked weapon pose.
    """
    rows=manifest.get('sourceAttachmentShadows',[])
    if not rows:return
    start=len(result.initial_bone_states);tracks=_build_tracks(configured)
    if manifest.get('attachmentReferenceMode')=='blended-configured-chain':
        # Keep each native local track and mask separate. Lua evaluates the
        # relative offset only after the engine has blended the full chain.
        for i,row in enumerate(rows):
            channel=row['animationChannel']
            def sample(t):
                if channel is not None:return [tr[channel].evaluate(t) for tr in tracks]
                if configured.is_additive:return [[0.,0.,0.],[0.,0.,0.,1.],[0.,0.,0.]]
                bind=unit.transforms[row['index']];return [bind.position,bind.rotation,bind.scale]
            p,q,s=sample(0.)
            result.initial_bone_states.append(AnimationBoneState(list(p),list(q),list(s),False,False,False))
            for time in times[1:]:
                for subtype,value in zip((4,5,6),sample(time)):
                    result.entries.append(AnimationEntry(0,subtype,start+i,time,list(value)))
        return
    mapping=[unit.name_hashes.index(h) for h in bones.hashes]
    bind_world=_calculate_world_transforms(unit.transforms,unit.parents)
    bases=[source_attachment_pose(bind_world,row) for row in rows]
    previous=[None]*len(rows)
    for ti,time in enumerate(times):
        local=list(unit.transforms)
        for ai,ui in enumerate(mapping):
            p=WorldTransform(*(track[ai].evaluate(time) for track in tracks))
            local[ui]=_compose_additive_local(unit.transforms[ui],p) if configured.is_additive else p
        world=_calculate_world_transforms(local,unit.parents)
        for i,row in enumerate(rows):
            pose=source_attachment_pose(world,row);p,q=pose.position,pose.rotation
            if configured.is_additive:
                p=_decompose_additive_position(bases[i],p)
                q=quat_multiply(quat_inverse(bases[i].rotation),q)
            if previous[i] is not None and sum(a*b for a,b in zip(previous[i],q))<0:q=[-v for v in q]
            previous[i]=q
            if ti==0:result.initial_bone_states.append(AnimationBoneState(p,q,[0.,0.,0.] if configured.is_additive else [1.,1.,1.],False,False,False))
            else:
                result.entries.extend([AnimationEntry(0,4,start+i,time,p),AnimationEntry(0,5,start+i,time,q)])


def runtime_outputs(avatar_raw, bone_raw, manifest, by_native_name):
    """Reuse the existing animation channels as references; expose unanimated outputs.

    Torso outputs inherit real native controller nodes. Left outputs inherit their
    private animated references, so an IK delta survives the next animation pass.
    Skin names, all old indices, bind worlds and native channels remain intact.
    """
    from . import native_skeleton as native
    from .formats import BonesData
    from .motion_skeleton import relative as relative_pose, matrix as pose_matrix
    unit = UnitData.parse(avatar_raw)
    bones = BonesData.parse(bone_raw)
    count = len(unit.parents)
    world = _calculate_world_transforms(unit.transforms, unit.parents)
    local = copy.deepcopy(unit.transforms)
    parents, hashes = list(unit.parents), list(unit.name_hashes)
    names, channel_hashes = list(bones.names), list(bones.hashes)
    source = {n['driver']: n for n in manifest['bones'] if n['driver']}
    rows, remap = [], {}
    for driver in ('spine2', 'chest', 'l_shoulder', 'l_elbow', 'l_hand'):
        name = source[driver]['name']; old_hash = native.bone_name_hash(name)
        index = hashes.index(old_hash); output = len(hashes)
        private = '__hd2_b23_reference__' + name
        private_hash = native.bone_name_hash(private)
        assert private_hash not in hashes
        channel = channel_hashes.index(old_hash)
        names[channel] = private; channel_hashes[channel] = private_hash
        hashes[index] = private_hash
        parent = by_native_name[driver] if driver in ('spine2', 'chest') else index
        local.append(relative_pose(world[parent], world[index]))
        parents.append(parent); hashes.append(old_hash)
        remap[index] = output
        rows.append(dict(driver=driver, name=name, referenceName=private,
            referenceIndex=index, outputIndex=output, parentIndex=parent, channel=channel))
    changed = []
    # Keep the three animated arm references connected. Their fingers/helpers,
    # and the clavicle/neck subtrees, inherit the corresponding corrected output.
    for i in range(107, 107 + len(manifest['bones'])):
        if i not in remap and parents[i] in remap:
            parents[i] = remap[parents[i]]; changed.append(i)
    offset = struct.unpack_from('<I', avatar_raw, 52)[0]
    entries = offset + 16 + 128 * count
    block = bytearray(struct.pack('<I', len(local)) + avatar_raw[offset+4:offset+16])
    for i, pose in enumerate(local):
        block.extend(avatar_raw[offset+16+64*i:offset+16+64*(i+1)] if i<count
            else struct.pack('<16f', *pose_matrix(pose)))
    block.extend(avatar_raw[offset+16+64*count:entries])
    for row in rows:
        i=row['referenceIndex']
        block.extend(avatar_raw[offset+16+64*count+64*i:offset+16+64*count+64*(i+1)])
    for i, parent in enumerate(parents):
        if i<count and i not in changed:
            block.extend(avatar_raw[entries+4*i:entries+4*(i+1)])
        else:
            flags=struct.unpack_from('<H',avatar_raw,entries+4*i)[0] if i<count else 1
            block.extend(struct.pack('<HH',flags,65535 if parent is None else parent))
    block.extend(struct.pack(f'<{len(hashes)}I',*hashes))
    revised=bytearray(avatar_raw);revised.extend(bytes(-len(revised)%16))
    struct.pack_into('<I',revised,52,len(revised));revised.extend(block)
    parsed=UnitData.parse(revised)
    after=_calculate_world_transforms(parsed.transforms,parsed.parents)
    for i, before in enumerate(world):
        assert max(abs(a-b) for a,b in zip(before.position,after[i].position))<1e-5
        assert abs(sum(a*b for a,b in zip(before.rotation,after[i].rotation)))>1-1e-6
    for row in rows:
        assert max(abs(a-b) for a,b in zip(after[row['outputIndex']].position,world[row['referenceIndex']].position))<1e-5
    n,lods=struct.unpack_from('<II',bone_raw)
    assert n==len(names)
    revised_bones=bytearray(bone_raw[:8+4*lods])+struct.pack(f'<{n}I',*channel_hashes)
    revised_bones+=bone_raw[8+4*lods+4*n:8+8*lods+4*n]
    revised_bones+=b''.join(s.encode('utf-8')+b'\0' for s in names)
    assert len(BonesData.parse(revised_bones).names)==n
    assert not set(r['outputIndex'] for r in rows) & {parsed.name_hashes.index(h) for h in channel_hashes}
    return bytes(revised),bytes(revised_bones),dict(rows=rows,reparentedChildren=changed,
        originalNodeCount=count,nodeCount=len(local),animationChannelCount=n,
        animationChannelsAdded=0,animationBytesChanged=False,modelBytesChanged=False,
        originalNativeHierarchyPreserved=True,bindWorldsPreserved=True)


def _local_under(parent,child):
    from .math3d import quat_inverse_rotate
    p=quat_inverse_rotate(parent.rotation,vec_sub(child.position,parent.position))
    return WorldTransform([v/scale for v,scale in zip(p,parent.scale)],
        quat_multiply(quat_inverse(parent.rotation),child.rotation),[a/b for a,b in zip(child.scale,parent.scale)])


def calibrate_weapon_manifest(manifest,model_unit):
    """Re-place only the two original Source weapon bones at converter/native grips.

    All other bind worlds (including weapon children) remain fixed. Old weapon
    world positions are diagnostic only and never a calibration target.
    """
    from . import native_skeleton as native
    from .motion_skeleton import source_local,matrix
    from .math3d import quat_inverse_rotate
    drivers={n['driver'] for n in manifest['bones'] if n['driver']}
    hashes=manifest['driverHashes']
    names={name:hashes.index(native.bone_name_hash(name)) for name in drivers|{'root','boss','attach_hand_r','attach_hand_l'}}
    # Body Unit node order differs from Avatar. Never slice a model's first 107
    # nodes as if they were the Avatar; use the exported original driver bind.
    bind=[native.row_pose(row['values']) for row in manifest['driverWorld']]
    source_bind=[native.local_pose(source_local(n,i,manifest)) for i,n in enumerate(manifest['bones'])]
    refs,_=native._reference_rotations(manifest['bones'],source_bind,[native.row_pose(n['world']) for n in manifest['bones']],bind,names,manifest)
    by_driver={n['driver']:i for i,n in enumerate(manifest['bones']) if n['driver']}
    old_world=[native.row_pose(n['world']) for n in manifest['bones']];desired={};rows=[]
    for hand,source_name,mount in [('r_hand','ValveBiped.weapon_bone','attach_hand_r'),('l_hand','ValveBiped.L_weapon_bone','attach_hand_l')]:
        matches=[i for i,n in enumerate(manifest['bones']) if (n.get('sourceName') or '').lower()==source_name.lower()]
        if not matches:continue
        if len(matches)!=1:raise ValueError('Ambiguous original weapon bone: '+source_name)
        i=matches[0];h=by_driver[hand];axes=quat_multiply(quat_inverse(refs[h]),bind[names[hand]].rotation)
        original=_local_under(bind[names[hand]],bind[names[mount]])
        q=quat_multiply(old_world[h].rotation,axes)
        wanted=WorldTransform([a+b for a,b in zip(old_world[h].position,quat_rotate(q,original.position))],
            quat_multiply(q,original.rotation),list(old_world[i].scale))
        desired[i]=wanted
        rows.append(dict(sourceName=source_name,manifestIndex=i,originalSourceIndex=manifest['bones'][i]['sourceIndex'],handIndex=h,native=mount,
            nativeIndex=names[mount],axes=axes,originalWorld=list(old_world[i].position),targetWorld=list(wanted.position)))
    if not rows:raise ValueError('No original Source weapon bones to calibrate')
    changed=set(desired)
    for i,node in enumerate(manifest['bones']):
        if i not in desired and node['parent'] in desired:changed.add(i)
    for i in changed:
        node=manifest['bones'][i];parent=node['parent']
        parent_world=bind[0] if parent is None else desired.get(parent,old_world[parent])
        world=desired.get(i,old_world[i]);local=_local_under(parent_world,world)
        node['local']=dict(position=local.position,rotation=matrix(local)[:9],scale=local.scale)
        node['world']=matrix(world,True)
        if str(i) in manifest.get('motionLocalOverrides',{}):manifest['motionLocalOverrides'][str(i)]=node['local']
    manifest['weaponGripCalibration']=dict(version='converter-native-grip-v1',rows=rows,changedSourceIndices=sorted(changed),
        targetPolicy='converter_hand_axes_times_original_native_mount',otherBindWorldsPreserved=True)
    return manifest['weaponGripCalibration']


def _rewrite_model_weapon_binds(raw,manifest):
    from . import native_skeleton as native
    from .motion_skeleton import matrix
    unit=UnitData.parse(raw);count=len(unit.parents);local=copy.deepcopy(unit.transforms)
    for i in manifest['weaponGripCalibration']['changedSourceIndices']:
        node=manifest['bones'][i];index=unit.name_hashes.index(node['hash']);local[index]=native.local_pose(node['local'])
    world=_calculate_world_transforms(local,unit.parents)
    at=struct.unpack_from('<I',raw,52)[0];block=bytearray(raw[at:at+16+136*count])
    changed={unit.name_hashes.index(manifest['bones'][i]['hash']) for i in manifest['weaponGripCalibration']['changedSourceIndices']}
    for index in changed:
        block[16+64*index:16+64*(index+1)]=struct.pack('<16f',*matrix(local[index]))
        pos=16+64*count+64*index;block[pos:pos+64]=struct.pack('<16f',*matrix(world[index],True))
    revised=bytearray(raw);revised.extend(bytes(-len(revised)%16));struct.pack_into('<I',revised,52,len(revised));revised.extend(block)
    checked=UnitData.parse(revised);after=_calculate_world_transforms(checked.transforms,checked.parents)
    before=_calculate_world_transforms(unit.transforms,unit.parents)
    weapon_nodes={unit.name_hashes.index(manifest['bones'][row['manifestIndex']]['hash']) for row in manifest['weaponGripCalibration']['rows']}
    for i,(a,b) in enumerate(zip(before,after)):
        if i not in weapon_nodes:
            assert max(abs(x-y) for x,y in zip(a.position,b.position))<1e-4,'non-weapon bind position changed'
            assert abs(sum(x*y for x,y in zip(a.rotation,b.rotation)))>1-1e-5,'non-weapon bind rotation changed'
    prefix=bytearray(revised[:len(raw)]);prefix[52:56]=raw[52:56]
    assert prefix==raw,'model mesh/UV/weights bytes changed outside transform pointer'
    for row in manifest['weaponGripCalibration']['rows']:
        index=checked.name_hashes.index(manifest['bones'][row['manifestIndex']]['hash'])
        assert max(abs(a-b) for a,b in zip(after[index].position,row['targetWorld']))<1e-4,'weapon bind readback mismatch'
    return bytes(revised)


def prepare_native_model(manifest_path,model_directory,config_path):
    import json,hashlib,os
    from pathlib import Path
    from .archive import TocArchive,InlinePatchWriter
    from .constants import UNIT_TYPE_ID
    from .native_config import resolve_native_config
    manifest_path=Path(manifest_path);folder=Path(model_directory);manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    cfg=resolve_native_config(config_path,manifest)
    if not cfg['native_skeleton'].get('calibrate_weapon_bones',False):return dict(status='skipped',reason='explicit calibration disabled')
    if manifest.get('weaponGripCalibration'):
        return dict(status='complete',alreadyCalibrated=True,calibration=manifest['weaponGripCalibration'])
    paths=[p for p in sorted(folder.glob('*.patch_*')) if p.suffix.rsplit('_',1)[-1].isdigit()]
    archives=[];sample=None
    for path in paths:
        side=lambda suffix:Path(str(path)+suffix).read_bytes() if Path(str(path)+suffix).exists() else b''
        archive=TocArchive.parse_parts(path.read_bytes(),side('.gpu_resources'),side('.stream'));archives.append((path,archive))
        for e in archive.entries.values():
            if e.type_id==UNIT_TYPE_ID and sample is None:sample=UnitData.parse(e.toc_data)
    if sample is None:raise ValueError('No converted model Units')
    calibration=calibrate_weapon_manifest(manifest,sample);files=[]
    for path,archive in archives:
        external={key:(bytes(e.gpu_data),bytes(e.stream_data)) for key,e in archive.entries.items()}
        for e in archive.entries.values():
            if e.type_id==UNIT_TYPE_ID:e.toc_data=bytearray(_rewrite_model_weapon_binds(e.toc_data,manifest))
        counts={}
        for e in archive.entries.values():counts[e.type_id]=counts.get(e.type_id,0)+1
        temp=Path(str(path)+'.calibrated');writer=InlinePatchWriter(archive,temp,counts,standalone=True)
        try:
            for e in archive.entries.values():writer.append(e)
            rebuilt=writer.finish()
        finally:writer.close()
        for source,suffix in zip(rebuilt,['','.gpu_resources','.stream']):
            os.replace(source,Path(str(path)+suffix))
        completed=TocArchive.parse_parts(path.read_bytes(),Path(str(path)+'.gpu_resources').read_bytes(),Path(str(path)+'.stream').read_bytes())
        assert all((bytes(completed.entries[key].gpu_data),bytes(completed.entries[key].stream_data))==value for key,value in external.items()),'external mesh payload changed'
        files.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(status='complete',pipelineVersion='1.0.9',calibration=calibration,files=files,
        meshNormalsUvWeightsUnchanged=True,sourceVpkUnmodified=True)
    (folder/'weapon-grip-calibration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def model_main(argv=None):
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--model-directory',required=True);p.add_argument('--config',required=True)
    a=p.parse_args(argv);print(json.dumps(prepare_native_model(a.manifest,a.model_directory,a.config)));return 0


def build_transfer_package(manifest_path, model_directory, game_data, output, config_path=None):
    """Build a model-specific profile and its required Avatar/Bones companion for the GUI."""
    import json,hashlib,tomllib
    from pathlib import Path
    from . import native_skeleton as native
    from .archive import PackageStore,ResourceIndex,TocArchive,InlinePatchWriter
    from .constants import UNIT_TYPE_ID,BONE_TYPE_ID
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise FileExistsError('Choose an empty attachment output directory')
    output.mkdir(parents=True,exist_ok=True)
    manifest=native.load_manifest(Path(manifest_path));model_directory=Path(model_directory)
    from .native_config import resolve_native_config,apply_runtime_policy
    config=resolve_native_config(config_path,manifest) if config_path else {}
    sections=json.loads((model_directory/'sections.json').read_text(encoding='utf-8-sig'))
    body_ids={int(row['fileId'],16) for row in sections['units'] if row['slot']!='Helmet'}
    model_units={}
    for path in sorted(model_directory.glob('*.patch_*')):
        if path.suffix.rsplit('_',1)[-1].isdigit():
            def side(suffix):
                p=Path(str(path)+suffix)
                return p.read_bytes() if p.exists() else b''
            archive=TocArchive.parse_parts(path.read_bytes(),side('.gpu_resources'),side('.stream'))
            for (file_id,type_id),entry in archive.entries.items():
                if type_id==UNIT_TYPE_ID and file_id in body_ids:
                    model_units[f'{file_id:016x}']=UnitData.parse(entry.toc_data)
    store=PackageStore(Path(game_data));index=ResourceIndex(store,output/'resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID})
    try:
        index.load_or_build();cache={}
        _,unit_entry=native.resolve_inline(index,store,int(manifest['referenceUnit'],0),UNIT_TYPE_ID,cache)
        unit=UnitData.parse(unit_entry.toc_data)
        _,bone_entry=native.resolve_inline(index,store,unit.bones_ref,BONE_TYPE_ID,cache)
        template=config.get('native_skeleton',{}).get('avatar_template')
        if template:unit_entry=native.load_avatar_template((Path(config_path).parent/template).resolve(),unit_entry)
        targets=json.loads((Path(__file__).parent/'weapon_grip_targets.json').read_text(encoding='utf8'))['targets']
        profile,avatar,bones,rig=transfer_profile(unit_entry.toc_data,bone_entry.toc_data,manifest,model_units,targets,
            config.get('native_skeleton',{}).get('grip_soft_distance',.008))
        if config.get('native_skeleton',{}).get('runtime_policy'):
            apply_runtime_policy(profile,config['native_skeleton']['runtime_policy'])
            profile['variant']=manifest['boneNamespace']+'-B23-1.0.8-calibrated-v1'
        contract=validate_attachment_transfer_contract(profile,UnitData.parse(avatar),BonesData.parse(bones),manifest,
            config.get('attachment_swap') if config.get('native_skeleton',{}).get('attachment_swap') else None)
        (output/'source-skeleton.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        def lua(v):
            if v is None:return 'nil'
            if isinstance(v,bool):return 'true' if v else 'false'
            if isinstance(v,(float,int)):return repr(v)
            if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
            if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
            return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'
        (output/'attachment-profile.lua').write_text('return '+lua(profile)+'\n',encoding='utf8')
        (output/'attachment-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf8')
        folder=output/'native-parenting';folder.mkdir()
        writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),folder/'9ba626afa44a3aa3.patch_5',
            {UNIT_TYPE_ID:1,BONE_TYPE_ID:1},standalone=True)
        for source,data in ((unit_entry,avatar),(bone_entry,bones)):
            entry=copy.deepcopy(source);entry.toc_data=bytearray(data);writer.append(entry)
        files=writer.finish()
        report=dict(status='complete',gameTested=False,sourceBones=len(manifest['bones']),
            modelScale=manifest.get('modelScale'),modelResources=sorted(model_units),
            avatarNodes=profile['avatar']['count'],weaponTargets=len(targets),attachments=len(profile['attachments'])+1,
            headDescendants=False,rig=rig,attachmentContract=contract,files=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
        (output/'attachment-build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        return report
    finally:index.close()


def main(argv=None):
    import argparse,json
    p=argparse.ArgumentParser(description='Compile model-specific B23 attachment runtime configuration')
    for name in ('manifest','model-directory','game-data','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--config')
    a=p.parse_args(argv)
    print(json.dumps(build_transfer_package(a.manifest,a.model_directory,a.game_data,a.output,a.config),ensure_ascii=False))
    return 0

