-- Real exported Unit layouts, independent cached linked worlds and recycled API values.
local function copy(x)
    if type(x)~='table' then return x end
    local r={};for k,v in pairs(x) do r[k]=copy(v) end;return r
end
local integratedProfile=copy(profile)
profile.attachments=nil
local deliveredProfile=copy(profile)
local fullProfile=copy(profile);fullProfile.bodySync.enabled=false
profile=copy(fullProfile);profile.leftGrip.enabled=false;profile.sync.enabled=false
local checks=0
local function check(x,message) checks=checks+1;assert(x,message) end
local function near(a,b,e)
    for i=1,12 do if math.abs(a[i]-b[i])>(e or 1e-7) then return false end end;return true
end
local function multiply(a,b)
    local out={}
    for col=0,2 do for row=1,3 do
        local n=0;for k=0,2 do n=n+a[k*3+row]*b[col*3+k+1] end
        out[col*3+row]=n
    end end
    for row=1,3 do
        local n=a[row+9];for k=0,2 do n=n+a[k*3+row]*b[10+k] end
        out[row+9]=n
    end
    return out
end
local function transform(z,x,y,up,scale)
    local c,s=math.cos(z),math.sin(z);scale=scale or 1
    return {scale*c,scale*s,0,-scale*s,scale*c,0,0,0,scale,x or 0,y or 0,up or 0}
end
local function make(spec)
    local u={alive=true,count=#spec.hashes,resource=spec.resource,visible=true,
        parents=copy(spec.parents),locals=copy(spec.matrices),names={},cache={},
        isModel=profile.models[spec.resource]~=nil,externalParents=profile.models[spec.resource]~=nil}
    for i,h in ipairs(spec.hashes) do u.names[h]=i end;return u
end
local A,B,model,gun,grip=make(fixture.avatar),make(fixture.avatar),make(fixture.model),
    make(fixture.weapon),make(fixture.foregrip)
local baseGun=gun
local groups={[1]={A,model,gun,grip},[2]={B}}
local gunParent=model
local gunMount=profile.target.hash
local linkedItems={}
local duplicateGrip=nil
local duplicateGun=nil
local refreshTrace={}
local ti=profile.target.index+1
local nativeRight=profile.nativeRight.index+1
local sri,sli=profile.sourceRight.index+1,profile.sourceLeft.index+1
local oi=profile.originalMount.index+1
local weaponRoot=profile.consumers[gun.resource].root+1
local gripRoot=profile.consumers[grip.resource].root+1
local under=gun.names[hash_name('attach_underbarrel')]
local function calculate(u,linkedRoot,linkedPose)
    local cache={}
    local function node(n)
        if cache[n] then return cache[n] end
        if n==linkedRoot then cache[n]=copy(linkedPose);return cache[n] end
        local p=u.parents[n]
        local m=p~=nil and p>=0 and multiply(node(p+1),u.locals[n]) or copy(u.locals[n])
        cache[n]=m;return m
    end
    for i=1,u.count do node(i) end;u.cache=cache
end
local function refresh(u)
    if u.linkOwner then
        calculate(u,u.linkRoot,u.linkOwner.cache[u.linkIndex])
    elseif u==gun or u==duplicateGun then
        -- The engine supplies the external root link. Serialized FBX ancestors
        -- may be singular; descendants still evaluate from the linked root.
        calculate(u,weaponRoot,gunParent.cache[gunParent.names[gunMount]])
    else calculate(u) end
    if u.isModel then
        for h,i in pairs(u.names) do if A.names[h] then u.cache[i]=copy(A.cache[A.names[h]]) end end
    elseif u==grip or u==duplicateGrip then
        local old=copy(u.cache[gripRoot]);local mount=gun.cache[under]
        if mount then for i=1,u.count do u.cache[i]=numpy_multiply(mount,numpy_relative(old,u.cache[i])) end end
    end
end
local function refresh_all() refresh(A);refresh(B);refresh(model);refresh(gun);refresh(grip);for _,u in ipairs(linkedItems) do refresh(u) end end
local scratch={};local calls=0;local writes=0;local refreshes=0
local failAt,refreshFault,corruptReadback=nil,false,false
local leftAllowed=false
local leftIndices={}
for _,node in ipairs(fullProfile.leftGrip.outputs) do leftIndices[node.index+1]=true end
local bodyAllowed=false
local attachmentAllowed=false
local attachmentIndices={}
for _,row in ipairs(integratedProfile.attachments) do attachmentIndices[row.node.index+1]=true end
local bodyIndices={}
for _,item in ipairs(deliveredProfile.bodySync.outputs) do bodyIndices[item.node.index+1]=true end
local avatarRefreshes,failAvatarRefresh=0,nil
local function recycled(values)
    calls=calls+1
    for k in pairs(scratch) do scratch[k]=nil end
    if values then for i,x in ipairs(values) do scratch[i]=x end end
    return scratch
end
local S={Application={},Unit={},World={},Matrix4x4={},IdString64={},Mesh={}}
local U,X=S.Unit,S.Matrix4x4
S.Application.worlds=function()
    recycled();local worlds={};for w in pairs(groups) do worlds[#worlds+1]=w end
    table.sort(worlds);return worlds
end
S.World.units=function(w) recycled();return groups[w] or {} end
S.World.units_by_resource=function(w,path)
    recycled();check(path=='content/fac_helldivers/cha_avatar/avatar_helldiver','wrong avatar query')
    local result={}
    for _,u in ipairs(groups[w] or {}) do if u.resource==fixture.avatar.resource then result[#result+1]=u end end
    return result
end
U.alive=function(u) recycled();return u.alive end
U.num_scene_graph_items=function(u) recycled();return u.count end
U.resource_name=function(u) recycled();return u.resource end
S.IdString64.to_hex=function(id) recycled();return id end
U.has_node=function(u,h) recycled();return u.names[h]~=nil end
U.node=function(u,h) recycled();return u.names[h] end
U.scene_graph_parent=function(u,n)
    recycled()
    -- B21 live captures: linked model nodes return nil, independently of the
    -- serialized hierarchy used to construct their cached poses.
    if u.externalParents or u.externalParentNode==n then return nil end
    local p=u.parents[n];return p~=nil and p+1 or 0
end
U.local_pose=function(u,n) check(u.alive and n<=u.count,'invalid local read');return recycled(u.locals[n]) end
U.world_pose=function(u,n)
    check(u.alive and n<=u.count,'invalid world read')
    local value=copy(u.cache[n])
    if corruptReadback and u==A and n==ti and writes>0 then value[10]=value[10]+.02;corruptReadback=false end
    return recycled(value)
end
X.to_elements=function(m) return unpack(m) end
X.from_elements=function(...) return recycled({...}) end
U.num_meshes=function(u) recycled();return (u==A or u==B) and 0 or 1 end
U.mesh=function(u,_) recycled();return u end
S.Mesh.visibility=function(u) recycled();return u.visible end
U.set_local_pose=function(u,n,m)
    check(u==A and (n==ti or (leftAllowed and leftIndices[n]) or (bodyAllowed and bodyIndices[n]) or (attachmentAllowed and attachmentIndices[n])),
        'wrote outside right mount and explicitly enabled left Source arm')
    local value=copy(m);recycled();u.locals[n]=value;writes=writes+1
    if failAt==writes then failAt=nil;error('injected_after_set') end
end
S.World.update_unit=function(w,u)
    recycled();local present=false
    for _,entry in ipairs(groups[w] or {}) do if entry==u then present=true;break end end
    check(present,'refreshed unit outside its world');refreshes=refreshes+1
    refreshTrace[#refreshTrace+1]=u;refresh(u)
    if u==A and refreshFault then refreshFault=false;error('injected_refresh_failure') end
    if u==A then
        avatarRefreshes=avatarRefreshes+1
        if failAvatarRefresh==avatarRefreshes then failAvatarRefresh=nil;error('injected_left_refresh_failure') end
    end
end
-- STRICT_ID_FIXTURE
local baseA,baseB=copy(A.locals),copy(B.locals)
local logs={}
local function make_runtime(p)
    return module.new(S,p or profile,function(line) logs[#logs+1]=line end,arm_math)
end
local function reset()
    gun=baseGun;weaponRoot=profile.consumers[gun.resource] and profile.consumers[gun.resource].root+1
        or profile.consumers[fixture.weapon.resource].root+1
    under=gun.names[hash_name('attach_underbarrel')]
    A.locals=copy(baseA);B.locals=copy(baseB);A.alive=true;B.alive=true;model.alive=true
    gun.alive=true;grip.alive=true;model.visible=true;A.count=#fixture.avatar.hashes
    A.parents=copy(fixture.avatar.parents);A.resource=fixture.avatar.resource;model.resource=fixture.model.resource
    model.parents=copy(fixture.model.parents);model.externalParents=true
    A.externalParentNode=nil;model.externalParentNode=nil
    A.externalParents=false;B.externalParents=false;gun.externalParents=false;grip.externalParents=false
    gun.resource=fixture.weapon.resource;grip.resource=fixture.foregrip.resource
    gun.visible=true;grip.visible=true;duplicateGrip=nil;duplicateGun=nil
    leftAllowed=false;bodyAllowed=false;attachmentAllowed=false
    avatarRefreshes=0;failAvatarRefresh=nil
    gunParent=model;gunMount=profile.target.hash;linkedItems={};refreshTrace={}
    A.names={};for i,h in ipairs(fixture.avatar.hashes) do A.names[h]=i end
    model.names={};for i,h in ipairs(fixture.model.hashes) do model.names[h]=i end
    groups={[1]={A,model,gun,grip},[2]={B}}
    failAt=nil;refreshFault=false;corruptReadback=false;writes=0;refreshes=0
    refresh_all();strictIdStats.advanceFrame()
end

local function separation(a,b)
    local n=0;for i=10,12 do n=n+(a[i]-b[i])^2 end;return math.sqrt(n)
end
local function step(runtime,phase,frame,now)
    strictIdStats.advanceFrame();runtime:tick(phase,frame,now or frame/60)
end
local function exact_protected(before)
    for i=1,A.count do if i~=ti then check(near(A.locals[i],before[i]),'unrelated local changed '..i) end end
    for i=1,B.count do check(near(B.locals[i],baseB[i]),'other avatar changed') end
end
local function expected(source,original,native)
    return numpy_target(source,original,native,profile.rightAxes)
end
reset()
local runtime=make_runtime()
local source,original,native=copy(A.cache[sri]),copy(A.locals[oi]),copy(A.cache[ti])
local before=copy(A.locals)
step(runtime,'render',1)
check(not runtime.disabled and runtime.stats.writes==1,'initial apply failed')
check(near(A.cache[ti],expected(source,original,native)),'initial numpy world mismatch')
for i=1,9 do check(math.abs(A.cache[ti][i]-native[i])<1e-7,'native aiming basis changed') end
check(near(gun.cache[weaponRoot],A.cache[ti]),'gun cache did not follow mount')
check(near(grip.cache[gripRoot],gun.cache[under]),'foregrip cache did not follow underbarrel')
check(refreshTrace[1]==A and refreshTrace[2]==model and refreshTrace[3]==gun and refreshTrace[4]==grip,
    'legacy avatar/model/gun/component refresh order changed')
exact_protected(before)
local held=copy(A.locals[ti]);local heldWrites=writes
step(runtime,'update',2)
check(writes==heldWrites and near(A.locals[ti],held),'update cleared the render write')
check(#runtime.pending==1,'render write was not held until the next render')

-- Continuous motion includes independently animated native wrists, Source wrists,
-- and a changing original local reference. The output's swapped position is irrelevant.
for frame=2,92 do
    A.locals=copy(baseA)
    A.locals[nativeRight]=multiply(baseA[nativeRight],transform(frame*.027,.03,0,.008))
    A.locals[sri]=multiply(baseA[sri],transform(-frame*.018,.015*math.sin(frame*.2),0,0))
    A.locals[oi]=multiply(baseA[oi],transform(frame*.012,.007*math.sin(frame*.3),.004,0))
    A.locals[ti]=multiply(baseA[ti],transform(.2,.27,-.16,.06))
    refresh_all()
    before=copy(A.locals);source=copy(A.cache[sri]);original=copy(A.locals[oi]);native=copy(A.cache[ti])
    step(runtime,'render',frame)
    check(not runtime.disabled,'continuous transfer disabled')
    check(near(A.cache[ti],expected(source,original,native),1e-6),'moving numpy world mismatch')
    exact_protected(before)
    held=copy(A.locals[ti]);heldWrites=writes
    step(runtime,'update',frame+1)
    check(writes==heldWrites and near(A.locals[ti],held),'update cleared moving render write')
end
local dynamicWrites=runtime.stats.writes
runtime:stop('motion_done')

-- Preserve support for internal model parents as well as the live linked layout.
reset();model.externalParents=false;runtime=make_runtime()
step(runtime,'render',1)
check(not runtime.disabled and runtime.stats.writes==1,'serialized model parents rejected')
runtime:stop()
reset();model.externalParents=false
model.externalParentNode=profile.models[model.resource].nodes[1].index+1
runtime=make_runtime();step(runtime,'render',1)
check(not runtime.disabled and runtime.stats.writes==1,'mixed linked/internal model parents rejected')
runtime:stop()

-- Repeated render callbacks without a fresh animation must never accumulate offsets.
reset();runtime=make_runtime();before=copy(A.locals)
source=copy(A.cache[sri]);original=copy(A.locals[oi]);native=copy(A.cache[ti])
local target=expected(source,original,native)
for i=1,25 do step(runtime,'render',i);check(near(A.cache[ti],target),'repeat callback accumulated') end
runtime:stop();for i=1,A.count do check(near(A.locals[i],before[i]),'repeat shutdown restoration') end
local logCount=#logs;runtime:stop();step(runtime,'render',30)
check(#logs==logCount and #runtime.pending==0,'stop not idempotent')

-- Preserve a fresh engine local, even when it arrives before our restoring callback.
reset();runtime=make_runtime();step(runtime,'render',1)
local fresh=multiply(baseA[ti],transform(.12,.019,0,0));A.locals[ti]=copy(fresh);refresh_all()
local count=writes;step(runtime,'update',2)
check(writes==count and near(A.locals[ti],fresh),'fresh native animation overwritten')
step(runtime,'render',2)
check(runtime.stats.freshPreserved==1,'fresh preservation was not recorded')
check(near(runtime.pending[1].before,fresh),'next render did not preserve fresh engine input')
runtime:stop()
check(near(A.locals[ti],fresh),'fresh engine input not restored on shutdown')

-- Source scaling must not scale the weapon or the wrist-to-mount offset.
reset();A.locals[sri]=multiply(baseA[sri],transform(.4,0,0,0,1.08));refresh_all()
runtime=make_runtime();native=copy(A.cache[ti]);source=copy(A.cache[sri]);original=copy(A.locals[oi])
step(runtime,'render',1)
check(not runtime.disabled and near(A.cache[ti],expected(source,original,native)),'source scale transfer')
runtime:stop()

-- Removing the visible matching part releases the old override immediately.
reset();runtime=make_runtime();step(runtime,'render',1);model.visible=false
step(runtime,'render',2)
check(near(A.locals[ti],baseA[ti]) and runtime.stats.writes==1,'hidden model kept writing')
model.visible=true;step(runtime,'render',3);check(runtime.stats.writes==2,'visible model did not resume')
groups[1]={A,gun,grip};step(runtime,'render',4)
check(near(A.locals[ti],baseA[ti]) and #runtime.pending==0,'removed model kept override')
runtime:stop()

-- The real mission has more than 2048 Units; UI worlds may precede it.
reset();groups[1]={}
local prop={alive=false}
for i=1,6000 do groups[1][i]=prop end
for _,u in ipairs({A,model,gun,grip}) do groups[1][#groups[1]+1]=u end
runtime=make_runtime();step(runtime,'render',1)
check(runtime.stats.writes==1 and runtime.stats.consumerRefreshes==2,'late mission actors/components were skipped')
runtime:stop();check(near(A.locals[ti],baseA[ti]),'late mission actor failed to restore')
reset();groups={};for w=1,16 do groups[w]={} end;groups[17]={A,model,gun,grip}
runtime=make_runtime();step(runtime,'render',1)
check(runtime.stats.writes==1 and runtime.actors[1].world==17,'world after index 16 was skipped')
runtime:stop()

-- B20 selected the whole exported body set, including split parts/LODs.
local testedBodyLayouts=0
for resourceId,spec in pairs(fixture.bodyModels) do
    reset();local part=make(spec);groups[1]={A,part,gun,grip};gunParent=part
    refresh(part);refresh(gun);refresh(grip)
    runtime=make_runtime();step(runtime,'render',1)
    check(runtime.stats.writes==1,'body layout did not select Avatar: '..resourceId)
    check(near(gun.cache[weaponRoot],A.cache[ti]),'body-linked gun cache not refreshed: '..resourceId)
    runtime:stop();testedBodyLayouts=testedBodyLayouts+1
end

-- Equipment refresh uses runtime markers, including other weapon resources.
reset();gun.resource='0000000000000002';grip.resource='0000000000000003'
gun.externalParents=true;grip.externalParents=true
runtime=make_runtime();step(runtime,'render',1)
check(runtime.stats.writes==1 and runtime.stats.consumerRefreshes==2,'generic linked equipment not refreshed')
check(near(gun.cache[weaponRoot],A.cache[ti]) and near(grip.cache[gripRoot],gun.cache[under]),
    'generic equipment did not consume changed mount')
runtime:stop()

local avatarQuery=S.World.units_by_resource
reset();S.World.units_by_resource=nil;runtime=make_runtime();step(runtime,'render',1)
check(runtime.stats.writes==1,'full scan fallback without avatar query failed');runtime:stop()
S.World.units_by_resource=avatarQuery

-- Every independent gating failure starts without a pose write.
local rejected={}
for _,kind in ipairs({'native107','wrong_avatar_resource','wrong_model_resource','source_name','shadow_name',
                      'wrong_parent','avatar_external_parent','wrong_model_parent','model_parent_zero',
                      'model_parent_negative','model_source_name','model_pose_mismatch',
                      'invisible','unknown_visibility','dead','other_world','ambiguous'}) do
    reset()
    local modelNode=profile.models[fixture.model.resource].nodes[1]
    if kind=='native107' then A.count=107
    elseif kind=='wrong_avatar_resource' then A.resource='0000000000000001'
    elseif kind=='wrong_model_resource' then model.resource='0000000000000001'
    elseif kind=='source_name' then A.names[profile.sourceRight.hash]=nil
    elseif kind=='shadow_name' then A.names[profile.originalMount.hash]=nil
    elseif kind=='wrong_parent' then A.parents[ti]=0
    elseif kind=='avatar_external_parent' then A.externalParentNode=ti
    elseif kind=='wrong_model_parent' then model.externalParents=false;model.parents[modelNode.index+1]=0
    elseif kind=='model_parent_zero' then model.externalParents=false;model.parents[modelNode.index+1]=-1
    elseif kind=='model_parent_negative' then model.externalParents=false;model.parents[modelNode.index+1]=-2
    elseif kind=='model_source_name' then model.names[modelNode.hash]=nil
    elseif kind=='model_pose_mismatch' then model.cache[modelNode.index+1][10]=model.cache[modelNode.index+1][10]+.01
    elseif kind=='invisible' then model.visible=false
    elseif kind=='unknown_visibility' then model.visible=nil
    elseif kind=='dead' then A.alive=false
    elseif kind=='other_world' then groups[1]={A,gun,grip};groups[2]={model,B};B.alive=false
    else groups[1]={A,B,model,gun,grip};groups[2]={} end
    runtime=make_runtime();step(runtime,'render',1)
    check(writes==0,'gating failure wrote: '..kind);runtime:stop();rejected[#rejected+1]=kind
end

-- Same object handle but rebuilt graph: do not restore through a stale target identity.
reset();runtime=make_runtime();step(runtime,'render',1)
A.names[profile.target.hash]=nil
count=writes;step(runtime,'render',2)
check(writes==count and #runtime.pending==0,'restored rebuilt graph');runtime:stop()

-- Consumer destruction is optional telemetry; an otherwise valid right-hand test survives.
reset();runtime=make_runtime();step(runtime,'render',1);gun.alive=false;grip.alive=false
step(runtime,'render',2)
check(not runtime.disabled and runtime.stats.writes==2,'destroyed consumer disabled transfer')
runtime:stop()

-- Faults after actual mutation and after refresh must restore the original target local.
local rollback={}
for _,kind in ipairs({'after_set','after_refresh','bad_readback'}) do
    reset();runtime=make_runtime()
    if kind=='after_set' then failAt=1 elseif kind=='after_refresh' then refreshFault=true
    else corruptReadback=true end
    step(runtime,'render',1)
    check(runtime.disabled,'failed transaction stayed enabled: '..kind)
    check(near(A.locals[ti],baseA[ti]) and #runtime.pending==0,'rollback failed: '..kind)
    exact_protected(baseA);runtime:stop();rollback[#rollback+1]=kind
end

for _,kind in ipairs({'singular_native','sheared_source','mirrored_source','nan'}) do
    reset()
    if kind=='singular_native' then for i=1,9 do A.locals[nativeRight][i]=0 end
    elseif kind=='sheared_source' then A.locals[sri][4]=A.locals[sri][4]+.8
    elseif kind=='mirrored_source' then for i=1,3 do A.locals[sri][i]=-A.locals[sri][i] end
    else A.locals[oi][10]=0/0 end
    refresh_all();runtime=make_runtime();step(runtime,'render',1)
    check(runtime.disabled and writes==0,'invalid matrix reached setter: '..kind)
    runtime:stop();rejected[#rejected+1]=kind
end
-- Extend the accepted right-hand harness with left-only writes and real graph consumers.
local leftNodes=fullProfile.leftGrip.nodes
local lp,lri,lmi,lhi=leftNodes[1].index+1,leftNodes[2].index+1,leftNodes[3].index+1,leftNodes[4].index+1
local outputs=fullProfile.leftGrip.outputs
local lr,lm,lh=outputs[1].index+1,outputs[2].index+1,outputs[3].index+1
local nl=fullProfile.nativeLeft.index+1
local ik=gun.names[hash_name('IK_left')]
local function weapon_left_offset()
    -- 1.0.5 rule: the held weapon's own IK_left rides rigidly with the mount.
    return numpy_relative(gun.cache[weaponRoot],gun.cache[ik])
end
local function prepare_left(reach,worldScale)
    reset();leftAllowed=true
    if worldScale then A.locals[1]=multiply(A.locals[1],transform(0,0,0,0,worldScale));refresh_all() end
    local target=expected(A.cache[sri],A.locals[oi],A.cache[ti])
    local offset=weapon_left_offset()
    local front=numpy_multiply(target,offset)
    local root=copy(A.cache[lr])
    root[10]=front[10]+(reach or .2);root[11]=front[11]+.1;root[12]=front[12]+.04
    A.locals[lri]=numpy_relative(A.cache[lp],root)
    A.locals[lmi]=multiply(A.locals[lmi],transform(.5))
    local contact=numpy_multiply(A.cache[ti],offset)
    A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],contact)
    refresh_all()
    return copy(A.locals),separation(A.cache[lr],A.cache[lm]),separation(A.cache[lm],A.cache[lh])
end
local function check_left_protected(snapshot,first,second)
    for i=1,A.count do
        if i~=ti and not leftIndices[i] then check(near(A.locals[i],snapshot[i]),'LR changed unrelated local '..i) end
    end
    for i=1,B.count do check(near(B.locals[i],baseB[i]),'LR changed other Avatar') end
    for _,n in ipairs({lri,lmi,lhi}) do
        for j=10,12 do check(A.locals[n][j]==snapshot[n][j],'left arm bone offset changed') end
    end
    check(math.abs(separation(A.cache[lr],A.cache[lm])-first)<1e-6,'left upper arm stretched')
    check(math.abs(separation(A.cache[lm],A.cache[lh])-second)<1e-6,'left forearm stretched')
end
local leftCases=0
for _,scale in ipairs({1,1.08}) do
    local snapshot,first,second=prepare_left(nil,scale)
    runtime=make_runtime(fullProfile);step(runtime,'render',1)
    check(not runtime.disabled and runtime.stats.leftWrites==1,'left arm did not apply')
    check(separation(A.cache[lh],gun.cache[ik])<1e-5,'left wrist missed held weapon IK_left')
    local equivalent=numpy_multiply(A.cache[lh],fullProfile.leftAxes)
    for col=0,2 do for j=1,3 do equivalent[col*3+j]=equivalent[col*3+j]/scale end end
    local target=copy(gun.cache[ik])
    for col=0,2 do for j=1,3 do target[col*3+j]=target[col*3+j]/scale end end
    check(near(equivalent,target,1e-5),'left wrist axes did not match held weapon IK_left')
    check_left_protected(snapshot,first,second)
    check(near(gun.cache[weaponRoot],A.cache[ti]),'left solve changed right weapon attachment')
    local modelHand=model.names[fullProfile.sourceLeft.hash]
    check(near(model.cache[modelHand],A.cache[lh]),'left model cache did not follow solved arm')
    local locals=copy(A.locals);local count=writes
    step(runtime,'update',2)
    check(writes==count,'sync observer or update mutated the pose')
    for i=1,A.count do check(near(A.locals[i],locals[i]),'update changed LR result') end
    for frame=2,7 do
        step(runtime,'render',frame)
        check(separation(A.cache[lh],gun.cache[ik])<1e-5,'repeated LR callback drifted')
        check_left_protected(snapshot,first,second)
    end
    runtime:stop()
    for i=1,A.count do check(near(A.locals[i],snapshot[i]),'LR shutdown did not restore '..i) end
    leftCases=leftCases+1
end

local snapshot,first,second=prepare_left(.65)
runtime=make_runtime(fullProfile);step(runtime,'render',1)
check(runtime.stats.leftWrites==1 and separation(A.cache[lh],gun.cache[ik])>.1,'unreachable target was stretched/rejected')
check_left_protected(snapshot,first,second);runtime:stop();leftCases=leftCases+1

snapshot,first,second=prepare_left(2.0)
A.locals[nl][10]=A.locals[nl][10]+.1;refresh_all();snapshot=copy(A.locals)
runtime=make_runtime(fullProfile);step(runtime,'render',1)
check(not runtime.disabled and runtime.stats.leftWrites==1,'non-contact distant target stopped the left solve')
check(separation(A.cache[lh],gun.cache[ik])>1,'distant target stretched the hand onto grip')
check(separation(A.cache[lr],A.cache[lh])>first+second-.00001,'unreachable non-contact arm did not extend')
check_left_protected(snapshot,first,second);runtime:stop();leftCases=leftCases+1

-- Weapon identity remains required; the foregrip no longer participates in the left gate.
for _,kind in ipairs({'hidden_weapon','missing_weapon','non_allowlist_weapon',
                      'ambiguous_weapon','grip_present_irrelevant','missing_left_parent'}) do
    snapshot,first,second=prepare_left()
    if kind=='hidden_weapon' then gun.visible=false
    elseif kind=='missing_weapon' then groups[1]={A,model,grip}
    elseif kind=='non_allowlist_weapon' then gun.resource='0000000000000002'
    elseif kind=='missing_left_parent' then A.names[fullProfile.leftGrip.nodes[1].hash]=nil
    elseif kind=='grip_present_irrelevant' then grip.visible=false
    else duplicateGun=make(fixture.weapon);groups[1][#groups[1]+1]=duplicateGun;refresh(duplicateGun) end
    local leftBefore=copy(A.locals)
    runtime=make_runtime(fullProfile);step(runtime,'render',1)
    local expectLeft=kind=='grip_present_irrelevant'
    if expectLeft then
        check(not runtime.disabled and runtime.stats.writes==1 and runtime.stats.leftWrites==1,
            'hidden foregrip still gated the left arm')
        check(separation(A.cache[lh],gun.cache[ik])<1e-5,'left wrist missed weapon IK without grip')
    else
        check(not runtime.disabled and runtime.stats.writes==1 and runtime.stats.leftWrites==0,'left gate failed: '..kind)
        for _,n in ipairs({lr,lm,lh}) do check(near(A.locals[n],leftBefore[n]),'gated left pose changed: '..kind) end
    end
    runtime:stop();leftCases=leftCases+1
end

-- Dynamic discovery: an allowlisted weapon without a static signature still drives the left IK.
snapshot,first,second=prepare_left()
gun.resource='84354339522c932d' -- AR-2: allowlisted in the survey, absent from cfg.consumers
runtime=make_runtime(fullProfile);step(runtime,'render',1)
check(not runtime.disabled and runtime.stats.leftWrites==1,'dynamic allowlisted weapon was skipped')
check(separation(A.cache[lh],gun.cache[ik])<1e-5,'dynamic weapon left wrist missed IK_left')
check_left_protected(snapshot,first,second);runtime:stop();leftCases=leftCases+1

-- Every supported resource uses its real node hashes, parents and local poses.
-- The held-root relation is simulated; this does not certify live ownership.
local weaponCoverage={};local leftOnlyCoverage={};local airburstFixture
for _,weapon in ipairs(fixture.weapons) do
    reset();leftAllowed=true
    gun=make(weapon);weaponRoot=gun.names[hash_name(weapon.rootName)]
    under=gun.names[hash_name('attach_underbarrel')]
    groups[1]={A,model,gun};refresh_all()
    local snapshot=copy(A.locals)
    local first,second=separation(A.cache[lr],A.cache[lm]),separation(A.cache[lm],A.cache[lh])
    runtime=make_runtime(fullProfile);step(runtime,'render',1)
    check(not runtime.disabled and runtime.stats.writes==1 and runtime.stats.leftWrites==1,
        'actual weapon layout skipped: '..weapon.resource)
    check_left_protected(snapshot,first,second)
    weaponCoverage[#weaponCoverage+1]=weapon.resource
    if not gun.names[hash_name('IK_right')] then leftOnlyCoverage[#leftOnlyCoverage+1]=weapon.resource end
    if weapon.resource=='26e40437ea275296' then airburstFixture=weapon end
    runtime:stop()
end
check(airburstFixture~=nil,'RL-77 real layout missing')

-- Live 1.0.5 disabled the entire addon after a finite reference excursion.
-- Skip before all setters; normal frames (including after an active frame) recover.
reset();leftAllowed=true;bodyAllowed=true
gun=make(airburstFixture);weaponRoot=gun.names[hash_name(airburstFixture.rootName)]
under=gun.names[hash_name('attach_underbarrel')];groups[1]={A,model,gun}
A.locals[oi][10]=.6;refresh_all();snapshot=copy(A.locals)
runtime=make_runtime(deliveredProfile);step(runtime,'render',1)
check(not runtime.disabled and writes==0 and runtime.stats.mountSkipped==1 and #runtime.pending==0,
    'transient RL-77 mount excursion reached a setter or disabled future frames')
for i=1,A.count do check(near(A.locals[i],snapshot[i]),'skipped excursion changed a node') end
A.locals[oi]=copy(baseA[oi]);refresh_all();step(runtime,'render',2)
check(runtime.stats.writes==1 and runtime.stats.leftWrites==1 and runtime.stats.bodyNodeWrites==2,
    'RL-77 did not recover when the animated mount returned')
A.locals[oi][10]=.6;refresh_all();step(runtime,'render',3)
check(not runtime.disabled and runtime.stats.mountSkipped==2 and #runtime.pending==0,
    'active-frame restore or later excursion disabled the runtime')
A.locals[oi]=copy(baseA[oi]);refresh_all();step(runtime,'render',4)
check(runtime.stats.writes==2 and runtime.stats.leftWrites==2 and runtime.stats.bodyNodeWrites==4,
    'second mount recovery did not resume all outputs')
runtime:stop()

-- Partial left writes share B23's rollback, including failure after the second Avatar refresh.
for _,fault in ipairs({2,3,4,5}) do
    snapshot,first,second=prepare_left()
    runtime=make_runtime(fullProfile)
    if fault==5 then failAvatarRefresh=2 else failAt=fault end
    step(runtime,'render',1)
    check(runtime.disabled and #runtime.pending==0,'partial left failure was not rolled back')
    for i=1,A.count do check(near(A.locals[i],snapshot[i]),'partial left rollback failed '..i) end
    runtime:stop();leftCases=leftCases+1
end

snapshot,first,second=prepare_left()
runtime=make_runtime(fullProfile);step(runtime,'render',1)
local freshRoot=multiply(snapshot[lr],transform(.13))
A.locals[lr]=copy(freshRoot);model.visible=false;refresh_all()
step(runtime,'render',2)
check(near(A.locals[lr],freshRoot),'fresh left shoulder animation overwritten')
check(near(A.locals[lm],snapshot[lm]) and near(A.locals[lh],snapshot[lh]),'owned left child overrides not restored')
check(runtime.stats.leftFreshPreserved>0 and #runtime.pending==0,'left freshness not tracked')
runtime:stop();leftCases=leftCases+1

snapshot,first,second=prepare_left()
runtime=make_runtime(fullProfile)
for frame=1,60 do
    A.locals=copy(snapshot)
    A.locals[nativeRight]=multiply(snapshot[nativeRight],transform(.3*math.sin(frame*.09)))
    A.locals[lmi]=multiply(snapshot[lmi],transform(.12*math.sin(frame*.13)))
    refresh_all()
    local contact=numpy_multiply(A.cache[ti],weapon_left_offset())
    A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],contact)
    local released=frame>=25 and frame<=30
    if released then A.locals[nl][10]=A.locals[nl][10]+.1 end
    refresh_all()
    local input=copy(A.locals);local rootBefore=copy(A.cache[lr]);local previous=runtime.stats.leftWrites
    local goal=numpy_multiply(expected(A.cache[sri],A.locals[oi],A.cache[ti]),weapon_left_offset())
    local converterEnd=processor_endpoint(A.cache[lri],A.cache[lmi],A.cache[lhi],goal)
    step(runtime,'update',frame,frame/60);step(runtime,'render',frame,frame/60)
    check(not runtime.disabled,'animated LR solve disabled')
    check_left_protected(input,first,second)
    check(separation(A.cache[lr],rootBefore)<1e-6,'animated shoulder position changed')
    check(runtime.stats.leftWrites==previous+1,'moving/non-contact hand was skipped')
    for j=1,3 do check(math.abs(A.cache[lh][j+9]-converterEnd[j])<1e-5,'left endpoint differs from anim_batch_mod IK') end
end
runtime:stop();leftCases=leftCases+1

-- Separate native aim motion from stale model consumption without any body writes.
reset();local syncProfile=copy(fullProfile);syncProfile.leftGrip.enabled=false;syncProfile.sync.seconds=.05
runtime=make_runtime(syncProfile);step(runtime,'render',1000,100)
step(runtime,'update',1001,100.1);step(runtime,'render',1001,100.1)
local chestPair
for _,pair in ipairs(fullProfile.sync.pairs) do if pair.name=='chest' then chestPair=pair end end
local nativeChest,sourceChest=chestPair.native.index+1,chestPair.source.index+1
local bodyBefore=copy(A.locals[sourceChest])
A.locals[nativeChest]=multiply(A.locals[nativeChest],transform(.3));refresh(A)
model.cache[model.names[chestPair.source.hash]][10]=model.cache[model.names[chestPair.source.hash]][10]+.025
local count=writes
step(runtime,'update',1002,100.2)
check(writes==count and near(A.locals[sourceChest],bodyBefore),'sync update changed body/pose')
step(runtime,'render',1002,100.2)
check(near(A.locals[sourceChest],bodyBefore) and runtime.stats.syncErrors==0,'sync probe changed Source chest')
A.names[chestPair.native.hash]=nil
local previous=runtime.stats.writes
step(runtime,'update',1003,100.3);step(runtime,'render',1003,100.3)
check(not runtime.disabled and runtime.stats.writes==previous+1 and runtime.stats.syncErrors>0,
    'optional synchronization probe disabled proven right path')
runtime:stop()

-- A late engine animation pass writes only the serialized Bones channels.
-- The named outputs must survive it even when every input is re-evaluated.
snapshot,first,second=prepare_left()
runtime=make_runtime(fullProfile);step(runtime,'render',2000,200)
local outputLocals={};for _,n in ipairs({lr,lm,lh}) do outputLocals[n]=copy(A.locals[n]) end
local solved=copy(A.cache[lh])
for _,index in ipairs(fixture.animationIndices) do
    check(not leftIndices[index+1] and not bodyIndices[index+1],'output has an animation channel')
    A.locals[index+1]=copy(snapshot[index+1])
end
refresh_all()
for n,value in pairs(outputLocals) do check(near(A.locals[n],value),'late animation erased output') end
check(near(A.cache[lh],solved),'late animation discarded the corrected wrist')
check(near(model.cache[model.names[fullProfile.sourceLeft.hash]],solved),'linked model lost left output')
runtime:stop();leftCases=leftCases+1

-- Real native parent changes must reach the Source torso before another Lua
-- callback, while private animation references remain available for diagnostics.
reset();leftAllowed=true;bodyAllowed=true
runtime=make_runtime(deliveredProfile);step(runtime,'render',2100,210)
check(not runtime.disabled and runtime.stats.bodyNodeWrites==2,'native parent outputs not initialized')
for frame=1,20 do
    for _,item in ipairs(deliveredProfile.bodySync.outputs) do
        local n=item.native.index+1
        A.locals[n]=multiply(baseA[n],transform(.5*math.sin(frame*.23)))
    end
    refresh_all()
    for _,item in ipairs(deliveredProfile.bodySync.outputs) do
        local pair
        for _,candidate in ipairs(deliveredProfile.sync.pairs) do
            if candidate.source.index==item.node.index then pair=candidate end
        end
        local equivalent=numpy_multiply(A.cache[item.node.index+1],pair.axes)
        for j=1,9 do check(math.abs(equivalent[j]-A.cache[item.native.index+1][j])<1e-5,
            'native controller rotation did not propagate before Lua') end
        local mi=model.names[item.node.hash]
        check(near(model.cache[mi],A.cache[item.node.index+1]),'model missed native-parent body output')
    end
    step(runtime,'update',2100+frame,210+frame*.1)
    step(runtime,'render',2100+frame,210+frame*.1)
    check(not runtime.disabled,'combined torso/left/right update failed')
    for _,item in ipairs(deliveredProfile.bodySync.outputs) do
        local expectedPosition=multiply(A.cache[item.positionParent.index+1],A.locals[item.reference.index+1])
        check(separation(expectedPosition,A.cache[item.node.index+1])<1e-6,'native torso parent stretched Source offsets')
    end
end
runtime:stop()
for _,fault in ipairs({1,2,3,4,5,6}) do
    reset();leftAllowed=true;bodyAllowed=true;local before=copy(A.locals)
    runtime=make_runtime(deliveredProfile);failAt=fault;step(runtime,'render',2200+fault,220+fault)
    check(runtime.disabled,'body/left injected fault not exercised')
    check(#runtime.pending==0,'body transaction left a pending rollback')
    for i=1,A.count do check(near(A.locals[i],before[i]),'body/left rollback changed '..i) end
    runtime:stop()
end

-- Integrated paths omitted by the original every-gun-at-hand-r fixture.
local integratedCases=0
local function integrated_weapon(resource,mount)
    reset();leftAllowed=true;bodyAllowed=true;attachmentAllowed=true
    for _,spec in ipairs(fixture.weapons) do if spec.resource==resource then gun=make(spec) end end
    check(gun.resource==resource,'integrated weapon fixture missing')
    weaponRoot=gun.names[hash_name('skeleton')]
    gunMount=hash_name(mount);under=gun.names[hash_name('attach_underbarrel')]
    groups[1]={A,model,gun};refresh_all()
    return make_runtime(integratedProfile)
end
for _,resource in ipairs({'73d84eaae8c75342','8d3d52a3b2f19402','9eb160830321bfd6','9f80d67a12a7e40f'}) do
    for _,mount in ipairs({'attach_hand_r','attach_weapon'}) do
        runtime=integrated_weapon(resource,mount)
        local before=copy(A.locals);local gunBefore=copy(gun.locals)
        local worldBefore=copy(A.cache)
        step(runtime,'render',3000+integratedCases,300+integratedCases)
        check(not runtime.disabled,'integrated attachment transaction disabled: '..resource..' '..mount)
        local policy=integratedProfile.leftGrip.weaponTargets[resource].leftPolicy
        local expectedLeft=policy~='aim_only' or mount=='attach_hand_r'
        check((runtime.stats.leftWrites>0)==expectedLeft,'sidearm hold policy wrong: '..resource..' '..mount)
        check(runtime.stats.attachmentWrites==#integratedProfile.attachments,'missing non-head attachment writes')
        for _,row in ipairs(integratedProfile.attachments) do
            local reference=worldBefore[(row.reference or row.node).index+1]
            local offset=numpy_relative(worldBefore[row.native.index+1],reference)
            local target=numpy_target(A.cache[row.source.index+1],offset,worldBefore[row.node.index+1],row.axes)
            check(near(A.cache[row.node.index+1],target,2e-5),'attachment target or final left-arm phase wrong: '..row.node.name)
        end
        for i=1,107 do
            if i~=ti and not attachmentIndices[i] then check(near(A.locals[i],before[i]),'native controller/head changed') end
        end
        for i=1,gun.count do check(near(gun.locals[i],gunBefore[i]),'weapon part animation changed') end
        if expectedLeft then
            local marker=gun.cache[gun.names[hash_name('IK_left')]]
            local endpoint=processor_endpoint(A.cache[lri],A.cache[lmi],A.cache[lhi],marker)
            for i=1,3 do check(math.abs(A.cache[lh][i+9]-endpoint[i])<1e-5,'live weapon marker endpoint mismatch') end
        end
        runtime:stop()
        for i=1,A.count do check(near(A.locals[i],before[i]),'integrated restore changed '..i) end
        integratedCases=integratedCases+1
    end
end
-- Real package, GR-8 shell, and P-4 barrel layouts have no IK/muzzle/bullet_01.
-- They must be refreshed after the mount or gun they consume, without setters.
for _,spec in ipairs(fixture.carried) do
    local shell=spec.resource=='db50297b40133d12'
    local barrel=spec.resource=='4851d75853622a47'
    runtime=integrated_weapon(shell and '9f80d67a12a7e40f' or '8d3d52a3b2f19402',shell and 'attach_hand_r' or 'attach_weapon')
    gun.visible=shell or barrel
    local item=make(spec);item.linkOwner=model
    local right=spec.resource=='7686544f539bb9b7' or spec.resource=='16f397ca5f51f271'
    item.linkIndex=model.names[hash_name(right and 'attach_hand_r' or 'attach_hand_l')]
    if barrel then item.linkOwner=gun;item.linkIndex=gun.names[hash_name('attach_muzzle')] end
    item.linkRoot=item.names[hash_name('skeleton')] or item.names[hash_name('game_mesh')]
    linkedItems={item};groups[1][#groups[1]+1]=item;refresh_all()
    local before=copy(A.locals);local itemBefore=copy(item.locals)
    step(runtime,'render',3100+integratedCases,310+integratedCases)
    check(not runtime.disabled and (runtime.stats.leftWrites>0)==shell,'single-hand/reload left policy failed')
    check(near(item.cache[item.linkRoot],item.linkOwner.cache[item.linkIndex]),'unmarked item cache separated from its parent mount')
    local found=false
    for _,entry in ipairs(refreshTrace) do found=found or entry==item end
    check(found,'unmarked item omitted from refresh')
    for i=1,item.count do check(near(item.locals[i],itemBefore[i]),'carried item local modified') end
    if shell then
        item.linkOwner=gun;item.linkIndex=gun.names[hash_name('attach_ammo')]
        refresh_all();step(runtime,'render',3150,315)
        check(not runtime.disabled,'shell relink disabled the runtime')
        check(near(item.cache[item.linkRoot],gun.cache[item.linkIndex]),'loaded shell separated from gun ammo socket')
    end
    runtime:stop()
    for i=1,A.count do check(near(A.locals[i],before[i]),'carry restore failed') end
    integratedCases=integratedCases+1
end
runtime=integrated_weapon('9eb160830321bfd6','attach_hand_r')
step(runtime,'render',3170,317)
local attachment=integratedProfile.attachments[1].node.index+1
local freshAttachment=copy(A.locals[attachment]);freshAttachment[10]=freshAttachment[10]+.09
A.locals[attachment]=copy(freshAttachment);model.visible=false;refresh_all()
step(runtime,'render',3171,317.1)
check(near(A.locals[attachment],freshAttachment),'fresh engine attachment animation overwritten')
check(runtime.stats.attachmentFreshPreserved>0,'fresh attachment ownership not released')
runtime:stop();integratedCases=integratedCases+1
-- Faults in nested attachment writes must unwind both parents and children.
for _,fault in ipairs({3,8,15,20,21}) do
    runtime=integrated_weapon('9eb160830321bfd6','attach_hand_r')
    local before=copy(A.locals);failAt=fault;step(runtime,'render',3200+fault,320+fault)
    check(runtime.disabled and #runtime.pending==0,'attachment failure did not roll back')
    for i=1,A.count do check(near(A.locals[i],before[i]),'attachment rollback failed '..i) end
    runtime:stop();integratedCases=integratedCases+1
end

check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'cached/wrong ID token')
return {integratedCases=integratedCases,las44SkeletonLinkVerified=true,sidearmPoliciesVerified=true,
    nonHeadAttachmentsAndCarryVerified=true,unmarkedPartsRefreshed=true,checks=checks,dynamicWrites=dynamicWrites,engineCalls=calls,strictIdCalls=strictIdStats.factoryCalls,
    actualWeaponLayouts=weaponCoverage,leftOnlyWeaponLayouts=leftOnlyCoverage,
    airburstMountExcursionRecovers=true,mountExcursionSkippedBeforeSetters=true,
    rejected=rejected,rollback=rollback,logs=logs,rightBaselineOnlyMountWritten=true,
    independentlyComputedNumpyTargets=true,unrelatedSourceAndOtherActorsPreserved=true,
    independentLinkedConsumerCaches=true,noRepeatedCallbackDrift=true,freshAnimationPreserved=true,
    hiddenOrRemovedModelRestores=true,deadConsumersDoNotDisable=true,
    externalModelParentsAccepted=true,serializedModelParentsAccepted=true,mixedModelParentsAccepted=true,
    avatarParentValidationPreserved=true,nativeAimingBasisPreserved=true,renderWriteHeldThroughUpdate=true,
    allWorldsAndUnitsDiscovered=true,bodyLayoutsTested=testedBodyLayouts,
    orderedModelAndEquipmentRefresh=true,genericEquipmentRefresh=true,
    leftCases=leftCases,leftWeaponSelfIkPoseVerified=true,leftBoneLengthsPreserved=true,
    leftContactObservationOnly=true,leftWeaponIdentityGated=true,leftPartialRollbackAndFreshAnimation=true,
    leftUnreachableExtensionMatchesConverter=true,optionalProbesPreserveRightPath=true,
    upperBodyObservationOnly=false,nativeTorsoParentsPropagateBeforeLua=true,
    leftOutputSurvivesAnimationPass=true,bodyRollback=true,pairedSyncPhases=true}
