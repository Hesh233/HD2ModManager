-- B23 opt-in experiment, separate from the production physics/attachment addons.
-- The converter supplies the wrist AXIS registration, not a palm-surface fit.
-- Position = rigid(Source wrist) * sourceToNativeAxes * animated original mount local.
-- B19/B20 write path: preserve native aim, refresh model -> gun -> components.
-- test07 policy optionally aligns sidearm IK_right and selects linked underbarrel IK_left.
-- Engine matrices and IdString values are temporary: retain numeric copies only.
local M = {VERSION = '1.0.13'}
local unpack = unpack or table.unpack

local function finite(x)
    return type(x) == 'number' and x == x and math.abs(x) < 1e10
end
local function copy(a)
    local b = {}; for i, v in ipairs(a) do b[i] = v end; return b
end
local function difference(a, b)
    local d = 0
    for i = 1, 12 do d = math.max(d, math.abs(a[i] - b[i])) end
    return d
end
local function distance(a, b)
    local d = 0
    for i = 10, 12 do d = d + (a[i] - b[i]) ^ 2 end
    return math.sqrt(d)
end
local function compose(a, b)
    local r = {}
    for c = 0, 2 do
        for j = 1, 3 do
            r[c * 3 + j] = a[j]*b[c*3+1] + a[j+3]*b[c*3+2] + a[j+6]*b[c*3+3]
        end
    end
    for j = 1, 3 do r[9+j] = a[j]*b[10] + a[j+3]*b[11] + a[j+6]*b[12] + a[9+j] end
    return r
end
local function inverse_vector(m, v)
    local a,b,c,d,e,f,g,h,i = m[1],m[4],m[7],m[2],m[5],m[8],m[3],m[6],m[9]
    local det = a*(e*i-f*h) - b*(d*i-f*g) + c*(d*h-e*g)
    assert(finite(det) and math.abs(det) > 1e-8, 'singular_parent')
    return {((e*i-f*h)*v[1] + (c*h-b*i)*v[2] + (b*f-c*e)*v[3])/det,
            ((f*g-d*i)*v[1] + (a*i-c*g)*v[2] + (c*d-a*f)*v[3])/det,
            ((d*h-e*g)*v[1] + (b*g-a*h)*v[2] + (a*e-b*d)*v[3])/det}
end
local function relative(a, b)
    local r = {}
    for c = 0, 2 do
        local v = inverse_vector(a, {b[3*c+1], b[3*c+2], b[3*c+3]})
        for j = 1, 3 do r[3*c+j] = v[j] end
    end
    local v = inverse_vector(a, {b[10]-a[10], b[11]-a[11], b[12]-a[12]})
    for j = 1, 3 do r[9+j] = v[j] end
    return r
end
local function rigid(m)
    local r, scales = copy(m), {}
    for c = 0, 2 do
        local n = 0; for j = 1, 3 do n = n + m[3*c+j]^2 end
        n = math.sqrt(n); assert(finite(n) and n > 1e-6, 'invalid_axis_scale')
        scales[c+1] = n
        for j = 1, 3 do r[3*c+j] = m[3*c+j]/n end
    end
    for a = 0, 1 do for b = a+1, 2 do
        local dot = 0; for j = 1, 3 do dot = dot + r[3*a+j]*r[3*b+j] end
        assert(math.abs(dot) < 0.002, 'sheared_wrist_or_mount')
    end end
    local det = r[1]*(r[5]*r[9]-r[6]*r[8]) - r[4]*(r[2]*r[9]-r[3]*r[8])
        + r[7]*(r[2]*r[6]-r[3]*r[5])
    assert(det > 0.998 and det < 1.002, 'mirrored_wrist_or_mount')
    return r, scales
end
local function angle(a, b)
    local x, y = rigid(a), rigid(b)
    local trace = 0; for i = 1, 9 do trace = trace + x[i]*y[i] end
    return math.deg(math.acos(math.max(-1, math.min(1, (trace-1)/2))))
end
local function quote(s)
    return '"' .. tostring(s):gsub('[%z\1-\31\\"]', function(c)
        if c == '\\' then return '\\\\' elseif c == '"' then return '\\"' end
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
local function json(v)
    if v == nil then return 'null' end
    if type(v) == 'boolean' then return tostring(v) end
    if type(v) == 'number' then assert(finite(v), 'nonfinite_log'); return string.format('%.12g', v) end
    if type(v) == 'string' then return quote(v) end
    assert(type(v) == 'table', 'invalid_log_value')
    local out = {}
    if #v > 0 then
        for i = 1, #v do out[i] = json(v[i]) end
        return '[' .. table.concat(out, ',') .. ']'
    end
    local keys = {}; for k in pairs(v) do keys[#keys+1] = k end; table.sort(keys)
    for _, k in ipairs(keys) do out[#out+1] = quote(k) .. ':' .. json(v[k]) end
    return '{' .. table.concat(out, ',') .. '}'
end

function M.new(S, cfg, logger, ArmMath, sceneContext)
    local U, X, W, A = S.Unit, S.Matrix4x4, S.World, S.Application
    assert(U and X and W and A and S.IdString64, 'engine_api_missing')
    for _, name in ipairs({'alive','resource_name','num_scene_graph_items','has_node','node',
                           'scene_graph_parent','local_pose','world_pose','set_local_pose'}) do
        assert(type(U[name]) == 'function', 'unit_api_missing:' .. name)
    end
    assert(type(W.units)=='function' and type(W.update_unit)=='function'
        and type(A.worlds)=='function' and type(A.string_to_id32)=='function'
        and type(X.to_elements)=='function' and type(X.from_elements)=='function'
        and type(S.IdString64.to_hex)=='function', 'pose_api_missing')
    assert(cfg.target.name == 'attach_hand_r' and cfg.target.index == 84, 'write_allowlist')
    assert(cfg.originalMount.index ~= cfg.target.index and cfg.originalMount.parent == cfg.target.parent,
        'independent_original_reference_required')
    assert(cfg.sourceRight.name:match('_r_hand$'), 'source_wrist_required')
    assert(cfg.axisRegistration == 'converter-reference-rotation', 'axis_registration_required')
    rigid(cfg.rightAxes); rigid(cfg.leftAxes)
    local leftEnabled=cfg.leftGrip and cfg.leftGrip.enabled==true
    for _, row in ipairs(cfg.attachments or {}) do
        assert(row.node.index~=cfg.target.index and row.native.name~='head', 'attachment_allowlist')
        assert(row.node.name~='weapon_aim' and row.node.name~='aim_weapon'
            and row.node.name~='boss_aim' and row.node.name~='climb_ref'
            and row.node.name~='attach_cam_1', 'controller_input_protected')
        rigid(row.axes)
    end
    if leftEnabled then
        assert(ArmMath and type(ArmMath.solve_arm)=='function' and type(ArmMath.quaternion)=='function',
            'existing_arm_math_required')
        local nodes=cfg.leftGrip.nodes
        assert(#nodes==4,'left_arm_allowlist')
        local outputs=cfg.leftGrip.outputs
        if outputs then
            assert(#outputs==3 and outputs[3].index==cfg.sourceLeft.index,'left_output_allowlist')
            for i=1,3 do assert(outputs[i].parent==nodes[i+1].index,'left_output_reference_parent') end
        else assert(nodes[4].index==cfg.sourceLeft.index,'left_arm_allowlist') end
        for i=2,4 do assert(nodes[i].parent==nodes[i-1].index,'left_arm_direct_chain') end
        assert(nodes[2].name:match('_l_shoulder$')
            and nodes[3].name:match('_l_elbow$'),'left_source_chain_required')
        local targets=cfg.leftGrip.weaponTargets
        assert(type(targets)=='table','left_weapon_targets_required')
        local count=0
        for id,row in pairs(targets) do
            count=count+1
            assert(type(id)=='string' and #id==16
                and (row.rootName=='boss' or row.rootName=='skeleton'),
                'left_target_identity:'..tostring(id))
            for _,key in ipairs({'rootToIKLeft','rootToIKRight'}) do
                local m=row[key]
                if key=='rootToIKLeft' or m~=nil then
                    assert(type(m)=='table' and #m==12,'left_target_matrix:'..key..':'..tostring(id))
                    for j=1,12 do assert(finite(m[j]),'left_target_finite:'..key..':'..tostring(id)) end
                    rigid(m)
                end
            end
        end
        assert(count>0,'left_weapon_targets_empty')
    end
    local performance=cfg.performance or {}
    local fixes=cfg.gripFixes or {}
    local rightEnabled=cfg.rightGrip and cfg.rightGrip.enabled==true and cfg.rightAttachmentEnabled~=false
    if fixes.nativeSidearmAim then
        assert(cfg.rightGrip and #cfg.rightGrip.nodes==4 and #cfg.rightGrip.outputs==3,'right_output_contract_required')
        local c=cfg.rightGrip
        assert(c.outputs[3].index==cfg.sourceRight.index,'right_wrist_output_required')
        for i=1,3 do assert(c.outputs[i].parent==c.nodes[i+1].index,'right_output_reference_parent') end
        for i=2,4 do assert(c.nodes[i].parent==c.nodes[i-1].index,'right_reference_direct_chain') end
        assert(c.nodes[2].name:match('_r_shoulder$') and c.nodes[3].name:match('_r_elbow$'),'right_reference_identity')
        assert(ArmMath and type(ArmMath.solve_arm)=='function','right_arm_math_required')
    end
    if cfg.leftGrip and cfg.leftGrip.intent and cfg.leftGrip.intent.enabled then
        local intent=cfg.leftGrip.intent
        local function thresholds(enter,leave)
            assert(finite(enter) and finite(leave) and enter>0 and enter<=leave and leave<=.5,'invalid_intent_thresholds')
        end
        thresholds(intent.primaryEnterMetres,intent.primaryLeaveMetres)
        thresholds(intent.sidearmEnterMetres,intent.sidearmLeaveMetres)
        for id,row in pairs(intent.weaponThresholds or {}) do
            assert(cfg.leftGrip.weaponTargets[id],'unknown_intent_weapon')
            thresholds(row.enterMetres,row.leaveMetres)
        end
    end
    if cfg.previewGuard and cfg.previewGuard.enabled then
        local n=cfg.previewGuard.minimumWorldUnits
        assert(finite(n) and n%1==0 and n>0 and n<=10000,'invalid_preview_guard')
    end
    local self = {validation={},nodeValidation={},negativeResources={},leftIntent={},rightIntent={},pending={}, actors={}, observerActors={}, models={}, consumers={}, sequence=0, identities={},
        monitored={},syncFrame=nil,lastSync=nil,
        lastScan=nil, lastLog=nil, lastStatus=nil, disabled=false, stopped=false, records=0,
        stats={writes=0, readbacks=0, restores=0, freshPreserved=0, skipped=0,mountSkipped=0,
            modelRefreshes=0, consumerRefreshes=0, refreshErrors=0,
            leftWrites=0,leftNodeWrites=0,leftRestores=0,leftFreshPreserved=0,leftSkipped=0,
            syncSamples=0,syncErrors=0,bodyNodeWrites=0,bodyRestores=0,bodyFreshPreserved=0,
            attachmentWrites=0,attachmentRestores=0,attachmentFreshPreserved=0,
            membershipEntries=0,identityChecks=0,sidearmCorrections=0,underbarrelTargets=0,sceneBypasses=0,rightWrites=0,rightNodeWrites=0,rightRestores=0,rightFreshPreserved=0,firstPersonBypasses=0,unknownViewBypasses=0,fpPresentationRefreshes=0,fpPresentationErrors=0}}
    local function emit(row, urgent)
        if self.records >= cfg.maxRecords and not urgent then return end
        row.variant = cfg.variant
        self.records = self.records + 1; logger(json(row))
    end
    local function resource(u)
        local id = S.IdString64.to_hex(U.resource_name(u))
        assert(type(id)=='string' and id:match('^%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x%x$'), 'resource_id')
        return id:lower()
    end
    local function matrix(u, n, world)
        local r = {X.to_elements((world and U.world_pose or U.local_pose)(u, n+1))}
        assert(#r == 12, 'matrix_size')
        for _, v in ipairs(r) do assert(finite(v), 'matrix_nonfinite') end
        return r
    end
    -- Never retain opaque engine IdStrings; only verification results are cached.
    local function name_id(name) return A.string_to_id32(name) end
    local function verify_node(u,node,parents)
        local cache=self.nodeValidation[u]
        if performance.cacheNodeChecks and cache and cache[node] and (not parents or cache[node]==2) then return end
        local id=name_id(node.name)
        assert(U.has_node(u,id)==true and U.node(u,id)==node.index+1,'node_identity:'..node.name)
        if parents then assert(U.scene_graph_parent(u,node.index+1)==node.parent+1,'node_parent:'..node.name) end
        if performance.cacheNodeChecks then
            cache=cache or {};self.nodeValidation[u]=cache;cache[node]=parents and 2 or 1
        end
    end
    local function identity(item)
        local u, spec = item.unit, item.spec
        assert(U.alive(u)==true,'unit_dead')
        if performance.transactionIdentity and self.validation[u]==spec then return end
        self.stats.identityChecks=self.stats.identityChecks+1
        local count=U.num_scene_graph_items(u)
        assert(count==spec.count,'node_count:'..spec.kind..':actual='..tostring(count)..':expected='..spec.count)
        assert(resource(u)==spec.resource, 'resource_changed')
        if performance.cacheIdentity and self.validation[u]==spec then return end
        for _, node in ipairs(spec.nodes) do
            local id = name_id(node.name)
            assert(U.has_node(u,id)==true and U.node(u,id)==node.index+1, 'node_identity:'..node.name)
            if node.parent ~= nil and (spec.kind=='avatar' or spec.kind=='model') then
                local parent = U.scene_graph_parent(u,node.index+1)
                -- B21 live captures show nil parents for externally linked model bones.
                -- Their five world poses must still match one Avatar before any write.
                local externalModelParent = spec.kind=='model' and parent==nil
                assert(externalModelParent or parent==node.parent+1, 'node_parent:'..node.name)
            end
        end
        if performance.cacheIdentity or performance.transactionIdentity then self.validation[u]=spec end
    end
    local function visible(u)
        if not (U.num_meshes and U.mesh and S.Mesh and S.Mesh.visibility) then return nil end
        local count=U.num_meshes(u)
        if not finite(count) or count<1 or count>128 then return nil end
        local unknown=false
        for i=1,count do
            local value=S.Mesh.visibility(U.mesh(u,i))
            if value==true then return true elseif value~=false then unknown=true end
        end
        if unknown then return nil end
        return false
    end
    -- B19/B20 enumerated every world and every Unit. Prefix limits miss live
    -- mission actors while still admitting the much smaller preview worlds.
    local function members(full)
        local tracked
        if performance.sparseMembership and full==false then
            tracked={}
            for _,list in ipairs({self.actors,self.observerActors,self.models,self.consumers}) do
                for _,item in ipairs(list) do tracked[item.unit]=true end
            end
            for _,record in ipairs(self.pending) do tracked[record.actor.unit]=true end
        end
        local result, worlds = {}, A.worlds() or {}
        for wi, world in ipairs(worlds) do
            local ok, units = pcall(W.units, world)
            if ok then
                local set = {}; result[world] = {units=units or {}, set=set, label=wi}
                for _, u in ipairs(units or {}) do
                    if not tracked or tracked[u] then set[u]=true;self.stats.membershipEntries=self.stats.membershipEntries+1 end
                end
            end
        end
        return result
    end
    local function present(item, membership)
        return membership[item.world] and membership[item.world].set[item.unit] == true and U.alive(item.unit)==true
    end
    local function refresh_models(world, membership, actor)
        for _, item in ipairs(self.models) do
            if item.world==world and present(item,membership) and (not performance.scopedRefresh
                or not actor or self.modelOwners[item.unit]==actor.unit) then
                local ok,why=pcall(function()
                    identity(item)
                    if visible(item.unit)~=false then
                        W.update_unit(world,item.unit)
                        self.stats.modelRefreshes=self.stats.modelRefreshes+1
                    end
                end)
                if not ok then
                    self.stats.refreshErrors=self.stats.refreshErrors+1
                    if self.stats.refreshErrors<=8 then
                        emit({event='refresh_unavailable',kind='model',resource=item.spec.resource,reason=tostring(why)})
                    end
                end
            end
        end
    end
    local function refresh_consumers(world, membership, actor)
        local right,left
        if performance.scopedRefresh and actor then
            right=matrix(actor.unit,cfg.target.index,true);left=matrix(actor.unit,cfg.sourceLeft.index,true)
        end
        for _, item in ipairs(self.consumers) do
            if item.world==world and present(item,membership) then
                -- B19/B20 refreshes every recognized existing equipment graph
                -- in the affected world, with gun roots before components.
                local ok,why=pcall(function()
                    identity(item)
                    if visible(item.unit)~=false then
                        if performance.scopedRefresh and actor then
                            local root=matrix(item.unit,item.spec.root,true)
                            if math.min(distance(root,right),distance(root,left))>(performance.refreshRadius or 1.5) then return end
                        end
                        if item.spec.kind=='linked_item' then
                            local near=false
                            for _, actor in ipairs(self.actors) do
                                if actor.world==world and present(actor,membership) then
                                    near=near or distance(matrix(item.unit,item.spec.root,true),
                                        matrix(actor.unit,cfg.target.index,true))<=cfg.consumerRadius
                                end
                            end
                            if not near then return end
                        end
                        W.update_unit(world,item.unit)
                        self.stats.consumerRefreshes=self.stats.consumerRefreshes+1
                    end
                end)
                if not ok then
                    self.stats.refreshErrors=self.stats.refreshErrors+1
                    if self.stats.refreshErrors<=8 then
                        emit({event='refresh_unavailable',kind=item.spec.kind,resource=item.spec.resource,reason=tostring(why)})
                    end
                end
            end
        end
    end
    local function restore(record, membership, force)
        local item = record.actor
        if not present(item,membership) then return 'gone' end
        local valid = pcall(identity,item)
        if not valid then return 'layout_changed' end
        local changed=false
        local function restore_node(index,before,written,left)
            local current=matrix(item.unit,index,false)
            if not force and difference(current,written)>cfg.localTolerance then
                local key=left=='right' and 'rightFreshPreserved' or left=='attachment' and 'attachmentFreshPreserved' or left=='body' and 'bodyFreshPreserved' or left and 'leftFreshPreserved' or 'freshPreserved'
                self.stats[key]=self.stats[key]+1
                return
            end
            U.set_local_pose(item.unit,index+1,X.from_elements(unpack(before)))
            assert(difference(matrix(item.unit,index,false),before)<=cfg.localTolerance,'restore_readback')
            local key=left=='right' and 'rightRestores' or left=='attachment' and 'attachmentRestores' or left=='body' and 'bodyRestores' or left and 'leftRestores' or 'restores';self.stats[key]=self.stats[key]+1
            changed=true
        end
        if record.written then restore_node(cfg.target.index,record.before,record.written,false) end
        for _,row in ipairs(record.right or {}) do
            if row.touched then restore_node(row.index,row.before,row.written,'right') end
        end
        for _,row in ipairs(record.left or {}) do
            if row.touched then restore_node(row.index,row.before,row.written,true) end
        end
        for _,row in ipairs(record.body or {}) do
            if row.touched then restore_node(row.index,row.before,row.written,'body') end
        end
        for _,row in ipairs(record.attachments or {}) do
            if row.touched then restore_node(row.index,row.before,row.written,'attachment') end
        end
        if changed then
            W.update_unit(item.world,item.unit)
            refresh_models(item.world,membership,item)
            refresh_consumers(item.world,membership,item)
        end
        return changed and 'restored' or 'fresh_animation_preserved'
    end
    function self:release(membership)
        local pending = self.pending; self.pending = {}
        for _, record in ipairs(pending) do
            local ok, result = pcall(restore,record,membership,false)
            if not ok then
                self.pending[#self.pending+1]=record; self.disabled=true
                emit({event='restore_failed',avatar=record.actor.id,reason=tostring(result)},true)
            elseif record.diagnostic or result=='layout_changed' then
                emit({event='release',avatar=record.actor.id,result=result,phase=self.phase},true)
            end
        end
    end
    -- Reuse B19/B20 marker-based equipment discovery. These dynamic signatures
    -- authorize graph refresh/observation only, never setters or new links.
    local function equipment_spec(u, id, count)
        if performance.strictConsumers and not (cfg.allowedConsumers and cfg.allowedConsumers[id]) then return nil end
        if count<3 or count>192 then return nil end
        local function node(name)
            local hash=name_id(name)
            if U.has_node(u,hash)~=true then return nil end
            local n=U.node(u,hash)
            assert(finite(n) and n%1==0 and n>=1 and n<=count,'consumer_node_index:'..name)
            return {name=name,index=n-1}
        end
        local left,right=node('IK_left'),node('IK_right')
        local supported=cfg.leftGrip and cfg.leftGrip.weaponTargets[id]
        if supported and left then
            local root=node(supported.rootName)
            if not root then return nil end
            local nodes={root,left};if right then nodes[#nodes+1]=right end
            for _, name in ipairs(supported.linkNodes or {}) do
                local extra=node(name)
                if extra and extra.index~=root.index then nodes[#nodes+1]=extra end
            end
            return {kind='weapon',resource=id,count=count,nodes=nodes,root=root.index,order=0}
        end
        if left and right then
            local root=node('boss') or node('skeleton') or right
            return {kind='weapon',resource=id,count=count,nodes={left,right,root},root=root.index,order=0}
        end
        local skeleton,mesh=node('skeleton'),node('game_mesh')
        if not mesh then return nil end
        if not skeleton then
            -- G-16 and other rigid hand items have game_mesh/pivot but no
            -- skeleton or IK markers. They still consume the right hand link.
            local pivot=node('pivot')
            if not pivot then return nil end
            return {kind='linked_item',resource=id,count=count,nodes={mesh,pivot},root=pivot.index,order=2}
        end
        for _,row in ipairs({{'IK_left','weapon_grip'},{'muzzle','weapon_muzzle'},
                             {'attach_offset','weapon_optic'},{'bullet_01','weapon_magazine'},
                             {'laser','weapon_underbarrel'}}) do
            local marker=node(row[1])
            if marker then
                return {kind=row[2],resource=id,count=count,nodes={skeleton,mesh,marker},
                    root=skeleton.index,order=1}
            end
        end
        -- Shells, revolver parts and carried objects need a cache refresh too;
        -- IK/muzzle/bullet_01 is not a complete equipment signature. No setters
        -- are authorized on these Units, and refresh is limited to nearby items.
        local root=node('boss') or node('root') or skeleton
        return {kind='linked_item',resource=id,count=count,nodes={skeleton,mesh,root},
            root=root.index,order=2}
    end
    local function scan(membership, now)
        self.actors={}; self.observerActors={}; self.models={}; self.consumers={}
        local identities,seen,worlds,rejected,negative = {},{},{},{},{}
        for world, group in pairs(membership) do
            local summary={world=group.label,units=#group.units,actors=0,models=0,consumers=0}
            worlds[#worlds+1]=summary
            local function consider(u)
                if seen[u] or not group.set[u] then return end
                seen[u]=true
                local ok,why=pcall(function()
                    if U.alive(u)~=true then return end
                    local count=U.num_scene_graph_items(u)
                    if count<cfg.minNodes or count>cfg.maxNodes then return end
                    local id=resource(u)
                    local spec = id==cfg.avatar.resource and cfg.avatar or cfg.models[id] or cfg.consumers[id]
                    if not spec then
                        local cacheMiss=performance.negativeResourceCache and performance.strictConsumers
                            and not (cfg.allowedConsumers and cfg.allowedConsumers[id])
                        if cacheMiss and (negative[id] or self.negativeResources[id])==count then negative[id]=count;return end
                        spec=equipment_spec(u,id,count)
                        if not spec and cacheMiss then negative[id]=count end
                    end
                    if not spec then return end
                    local item={unit=u,world=world,worldLabel=group.label,spec=spec}
                    -- A true 107-node native Avatar is an observer ONLY. Never
                    -- weaken the writer's full dedicated-rig identity contract.
                    if id==cfg.avatar.resource and count==107 and cfg.sidearmDiagnostics and cfg.sidearmDiagnostics.enabled then
                        item.spec={kind='native_observer',resource=id,count=107,
                            nodes={cfg.nativeRight,cfg.nativeLeft,cfg.target}}
                        identity(item);item.id='native_observer_'..group.label
                        self.observerActors[#self.observerActors+1]=item
                        summary.nativeObservers=(summary.nativeObservers or 0)+1
                        return
                    end
                    identity(item)
                    local previous=self.identities[u]
                    if previous and previous.world==world and previous.resource==id then item.id=previous.id
                    else self.sequence=self.sequence+1;item.id=self.sequence end
                    identities[u]={id=item.id,world=world,resource=id}
                    if spec.kind=='avatar' then self.actors[#self.actors+1]=item;summary.actors=summary.actors+1
                    elseif spec.kind=='model' then self.models[#self.models+1]=item;summary.models=summary.models+1
                    else self.consumers[#self.consumers+1]=item;summary.consumers=summary.consumers+1 end
                end)
                if not ok then
                    local reason=tostring(why);rejected[reason]=(rejected[reason] or 0)+1
                end
            end
            if type(W.units_by_resource)=='function' then
                local ok,avatars=pcall(W.units_by_resource,world,'content/fac_helldivers/cha_avatar/avatar_helldiver')
                if ok then for _,u in ipairs(avatars or {}) do consider(u) end
                else rejected.avatar_query=(rejected.avatar_query or 0)+1 end
            end
            for _,u in ipairs(group.units) do consider(u) end
        end
        -- Gun graph first, then its separate foregrip graph.
        table.sort(self.consumers,function(a,b) return a.spec.order<b.spec.order end)
        self.identities=identities;self.negativeResources=negative;self.lastScan=now
        table.sort(worlds,function(a,b) return a.world<b.world end)
        if next(rejected) or not self.lastScanLog or now<self.lastScanLog or now-self.lastScanLog>=(performance.scanLogSeconds or 0) then
            self.lastScanLog=now
            emit({event='scan',time=now,worlds=worlds,actors=#self.actors,models=#self.models,
                consumers=#self.consumers,rejected=rejected,scope='all_worlds_all_units'})
        end
    end
    local function matching_actors(membership)
        local selected,blocked,actorPoses={},{},{}
        local function actor_pose(actor,index)
            if not performance.snapshotPoseCache then return matrix(actor.unit,index,true) end
            local poses=actorPoses[actor.unit] or {};actorPoses[actor.unit]=poses
            if not poses[index] then poses[index]=matrix(actor.unit,index,true) end
            return poses[index]
        end
        self.modelOwners={}
        local reasons={hidden=0,poseMismatch=0,ambiguous=0,unavailable=0}
        for _, model in ipairs(self.models) do
            local ok, matches=pcall(function()
                if not present(model,membership) then return {} end
                identity(model);if not visible(model.unit) then reasons.hidden=reasons.hidden+1;return {} end
                local poses={}
                for i,row in ipairs(model.spec.nodes) do poses[i]=matrix(model.unit,row.index,true) end
                local found={}
                for _, actor in ipairs(self.actors) do
                    if actor.world==model.world and present(actor,membership) then
                        local good=pcall(function()
                            identity(actor)
                            for i,row in ipairs(model.spec.nodes) do
                                assert(difference(poses[i],actor_pose(actor,row.avatarIndex))<=cfg.matchTolerance,
                                    'model_avatar_pose_mismatch')
                            end
                        end)
                        if good then found[#found+1]=actor else reasons.poseMismatch=reasons.poseMismatch+1 end
                    end
                end
                return found
            end)
            -- Geometric agreement gates this experiment, not a claim of API ownership.
            if ok and #matches==1 then selected[matches[1]]=model;self.modelOwners[model.unit]=matches[1].unit
            elseif ok and #matches>1 then
                reasons.ambiguous=reasons.ambiguous+1
                for _,actor in ipairs(matches) do blocked[actor]=true end
            elseif not ok then reasons.unavailable=reasons.unavailable+1 end
        end
        for actor in pairs(blocked) do selected[actor]=nil end
        return selected,reasons
    end
    -- Observe both the live native skeleton and the added Source hierarchy.
    -- The observer itself does not write poses; output nodes may inherit native parents.
    local function begin_sync(frame,now)
        local sync=cfg.sync
        if not sync or not sync.enabled or not next(self.monitored) then return end
        if self.stats.syncSamples>=sync.maxSamples or self.syncFrame==frame then return end
        if self.lastSync and now>=self.lastSync and now-self.lastSync<sync.seconds then return end
        self.lastSync=now;self.syncFrame=frame;self.stats.syncSamples=self.stats.syncSamples+1
    end
    local function capture_sync(phase,selected,membership,frame,now)
        if self.syncFrame~=frame then return end
        for actor,model in pairs(selected) do
            local ok,why=pcall(function()
                if not present(actor,membership) or not present(model,membership) then return end
                identity(actor);identity(model)
                if not visible(model.unit) then return end
                local nodes={};local maximum,position=0,0
                for _,pair in ipairs(cfg.sync.pairs) do
                    verify_node(actor.unit,pair.native,false);verify_node(actor.unit,pair.source,false)
                    local native=matrix(actor.unit,pair.native.index,true)
                    local source=matrix(actor.unit,pair.source.index,true)
                    local equivalent=compose(rigid(source),pair.axes)
                    local node
                    for _,n in ipairs(model.spec.observeNodes or {}) do if n.driver==pair.name then node=n end end
                    assert(node,'sync_model_node_missing:'..pair.name)
                    local hash=A.string_to_id32(node.name)
                    assert(U.has_node(model.unit,hash)==true and U.node(model.unit,hash)==node.index+1,
                        'sync_model_identity:'..node.name)
                    local consumed=matrix(model.unit,node.index,true)
                    local error=difference(source,consumed)
                    maximum=math.max(maximum,error);position=math.max(position,distance(source,consumed))
                    nodes[pair.name]={nativeWorld=native,sourceWorld=source,modelWorld=consumed,
                        nativeLocal=matrix(actor.unit,pair.native.index,false),
                        sourceLocal=matrix(actor.unit,pair.source.index,false),
                        nativeParent=U.scene_graph_parent(actor.unit,pair.native.index+1) or 'nil',
                        sourceParent=U.scene_graph_parent(actor.unit,pair.source.index+1) or 'nil',
                        nativeSourceAngle=angle(native,equivalent),modelMatrixError=error}
                    if pair.reference then
                        verify_node(actor.unit,pair.reference,false)
                        nodes[pair.name].animationReferenceWorld=matrix(actor.unit,pair.reference.index,true)
                        nodes[pair.name].animationReferenceLocal=matrix(actor.unit,pair.reference.index,false)
                    end
                end
                local owned=0
                for _,record in ipairs(self.pending) do if record.actor.unit==actor.unit then
                    for _,row in ipairs(record.left or {}) do
                        if row.touched and difference(matrix(actor.unit,row.index,false),row.written)<=cfg.localTolerance then
                            owned=owned+1
                        end
                    end
                end end
                emit({event='sync',sample=self.stats.syncSamples,phase=phase,frame=frame,time=now,
                    avatar=actor.id,world=actor.worldLabel,modelResource=model.spec.resource,nodes=nodes,
                    aimWorld=matrix(actor.unit,cfg.sync.aim.index,true),
                    rightMountWorld=matrix(actor.unit,cfg.target.index,true),leftLocalsOwned=owned,
                    modelMaxMatrixError=maximum,modelMaxPositionError=position,
                    ownership='last_unique_geometric_match_revalidated',cameraSample=false,
                    upperBodyWrites=cfg.bodySync and cfg.bodySync.enabled or false})
            end)
            if not ok then
                self.stats.syncErrors=self.stats.syncErrors+1
                if self.stats.syncErrors<=8 then emit({event='sync_unavailable',phase=phase,frame=frame,
                    avatar=actor.id,reason=tostring(why)}) end
            end
        end
    end
    local function consumer_node(item,name)
        for _,node in ipairs(item.spec.nodes) do if node.name==name then return node.index end end
        error('consumer_marker_missing:'..name)
    end
    local function weapon_static(resource,key)
        local targets=cfg.leftGrip and cfg.leftGrip.weaponTargets
        local row=targets and targets[resource]
        if resource then return row and row[key] end
        if key=='rootToIKRight' then return cfg.weaponRight end
        return cfg.weaponForegripLeft
    end
    local function solve_source_arm(actor,c,armAxes,gripPose)
        local function pose(m)
            return {p={m[10],m[11],m[12]},q=ArmMath.quaternion(rigid(m))}
        end
        local worlds,locals={},{ }
        for i,node in ipairs(c.nodes) do
            worlds[i]=matrix(actor.unit,node.index,true)
            locals[i]=matrix(actor.unit,node.index,false)
        end
        local _,parentScales=rigid(worlds[1]);local parentScale=parentScales[1]
        for i=2,3 do assert(math.abs(parentScales[i]-parentScale)<0.001,'left_parent_nonuniform_scale') end
        for i=2,4 do
            local _,scales=rigid(locals[i])
            for j=1,3 do assert(math.abs(scales[j]-1)<0.001,'left_joint_scaled') end
        end
        local root,mid,hand,parent=pose(worlds[2]),pose(worlds[3]),pose(worlds[4]),pose(worlds[1])
        local axes={p={0,0,0},q=ArmMath.quaternion(armAxes)}
        local inverseAxes=ArmMath.relative(axes,{p={0,0,0},q={0,0,0,1}})
        local desiredHand=ArmMath.compose(pose(gripPose),inverseAxes)
        desiredHand.referencePosition=hand.p
        local chain={upperCalibration={0,0,0,1},forearmCalibration={0,0,0,1},handCalibration={0,0,0,1},
            upperOffset={locals[3][10],locals[3][11],locals[3][12]},
            forearmOffset={locals[4][10],locals[4][11],locals[4][12]},armFrame='reference',
            hingeAxis=c.hingeAxis,forearmHingeAxis=c.forearmHingeAxis}
        -- Match processor._apply_two_bone_ik's reachable interval and soft extension.
        -- Native contact is telemetry only: an unreachable target still extends the arm.
        local first,second=distance(worlds[2],worlds[3]),distance(worlds[3],worlds[4])
        local actualDistance=distance(worlds[2],gripPose)
        local minimum,maximum=math.abs(first-second)+1e-7,first+second-1e-7
        local reach=math.max(minimum,math.min(maximum,actualDistance))
        local soft=math.min(c.softDistance or 0,(maximum-minimum)*0.25)
        if soft>0 and actualDistance>maximum-soft then
            reach=maximum-soft*math.exp(-(actualDistance-(maximum-soft))/soft)
        end
        for j=1,3 do
            local direction=actualDistance>1e-8 and (gripPose[j+9]-root.p[j])/actualDistance
                or (mid.p[j]-root.p[j])/first
            desiredHand.p[j]=root.p[j]+direction*reach
        end
        local targets=ArmMath.solve_arm(root,root,mid,desiredHand,parent,chain,{},1/60,parentScale,desiredHand.q)
        local residual=math.abs(actualDistance-reach)
        local rows={};local expected=worlds[1]
        for i=1,3 do
            local before=locals[i+1];local written=copy(before)
            for col=0,2 do
                local axis={0,0,0};axis[col+1]=1
                local rotated=ArmMath.rotate(targets[i].q,axis)
                for j=1,3 do written[col*3+j]=rotated[j] end
            end
            -- The existing solver changes rotations; retain the animated bone offsets.
            for j=1,3 do assert(math.abs(targets[i].p[j]-before[j+9])<cfg.localTolerance,'left_bone_offset_changed') end
            expected=compose(expected,written)
            local output=c.outputs and c.outputs[i]
            if output then
                -- The animation still owns the private input chain. Only its
                -- unanimated named outputs receive IK deltas, held through skinning.
                rows[i]={index=output.index,before=matrix(actor.unit,output.index,false),
                    written=relative(worlds[i+1],expected),touched=false}
            else rows[i]={index=c.nodes[i+1].index,before=before,written=written,touched=false} end
        end
        return {rows=rows,target=gripPose,expected=expected,before=worlds[4],reachResidual=residual}
    end
    local function plan_left(actor,target,nativeBefore,nativeLeft,membership,attachmentSnapshots)
        local c=cfg.leftGrip
        for _,node in ipairs(c.nodes) do verify_node(actor.unit,node,true) end
        for _,node in ipairs(c.outputs or {}) do verify_node(actor.unit,node,true) end
        local weapons={}
        local mounts={{name='attach_hand_r',pose=target}}
        for _, row in ipairs(cfg.attachments or {}) do
            if row.node.name=='attach_weapon' then
                mounts[#mounts+1]={name=row.node.name,pose=matrix(actor.unit,row.node.index,true)}
            end
        end
        for _,item in ipairs(self.consumers) do
            local supported=c.weaponTargets[item.spec.resource]
            if item.world==actor.world and supported and present(item,membership) then
                local ok,linked=pcall(function()
                    identity(item);if visible(item.unit)==false then return nil end
                    local names=supported.linkNodes or {supported.rootName}
                    for _,name in ipairs(names) do
                        local hash=name_id(name)
                        if U.has_node(item.unit,hash) then
                            local pose=matrix(item.unit,U.node(item.unit,hash)-1,true)
                            for _,mount in ipairs(mounts) do
                                if distance(pose,mount.pose)<=c.linkMetres and angle(pose,mount.pose)<=c.linkDegrees then
                                    -- Sidearms use the hand-r link while aiming; the
                                    -- hip carry link must not force their free hand.
                                    -- GP-20 Ultimatum explicitly uses both links.
                                    if supported.leftPolicy~='aim_only' or mount.name=='attach_hand_r' then
                                        return {mount=mount.name,node=name}
                                    end
                                end
                            end
                        end
                    end
                end)
                if ok and linked then
                    weapons[#weapons+1]={item=item,link=linked}
                end
            end
        end
        if #weapons~=1 then self.leftIntent[actor.unit]=nil;return nil,'no_unique_supported_held_weapon' end
        local weapon=weapons[1].item
        -- test07: the attached foregrip/underbarrel weapon wins over the gun marker.
        -- Proximity of IK_left is NOT ownership. Require its existing link root to
        -- coincide in position AND rotation with this gun's animated mount.
        local gripPose=matrix(weapon.unit,consumer_node(weapon,'IK_left'),true)
        local gripItem=weapon;local gripKind='weapon_self'
        if fixes.underbarrel then
            local hash=name_id('attach_underbarrel')
            if U.has_node(weapon.unit,hash)==true then
                local mount=matrix(weapon.unit,U.node(weapon.unit,hash)-1,true)
                local attached={}
                for _,item in ipairs(self.consumers) do
                    if item.unit~=weapon.unit and item.world==actor.world and present(item,membership) then
                        local ok,result=pcall(function()
                            identity(item);if visible(item.unit)==false then return end
                            local marker=name_id('IK_left')
                            if U.has_node(item.unit,marker)~=true then return end
                            local linked=false
                            local roots={item.spec.root};local seen={[item.spec.root]=true}
                            -- An underbarrel firearm can have a moving boss below
                            -- its external skeleton/root link, unlike a rigid grip.
                            for _,name in ipairs({'skeleton','root','boss'}) do
                                local id=name_id(name)
                                if U.has_node(item.unit,id)==true then
                                    local n=U.node(item.unit,id)-1
                                    if not seen[n] then roots[#roots+1]=n;seen[n]=true end
                                end
                            end
                            for _,n in ipairs(roots) do
                                local root=matrix(item.unit,n,true)
                                if distance(root,mount)<=c.linkMetres and angle(root,mount)<=c.linkDegrees then linked=true;break end
                            end
                            if not linked then return end
                            return matrix(item.unit,U.node(item.unit,marker)-1,true)
                        end)
                        if ok and result then attached[#attached+1]={item=item,pose=result} end
                    end
                end
                if #attached>1 then self.leftIntent[actor.unit]=nil;return nil,'ambiguous_underbarrel_link' end
                if #attached==1 then
                    gripItem=attached[1].item;gripPose=attached[1].pose;gripKind='underbarrel'
                    self.stats.underbarrelTargets=self.stats.underbarrelTargets+1
                end
            end
        end
        local intent=c.intent
        if intent and intent.enabled then
            -- A TESTED pose-intent proxy, not a claim of reading engine ADS/reload flags.
            -- Reconstruct the unswapped native gun path, using this frame's animated
            -- marker relative to the actual matched link node (not static weapon bind).
            local link=weapons[1].link
            local linkPose=matrix(weapon.unit,U.node(weapon.unit,name_id(link.node))-1,true)
            local nativeMount
            if link.mount=='attach_hand_r' then nativeMount=matrix(actor.unit,cfg.originalMount.index,true)
            else
                for _,row in ipairs(attachmentSnapshots or {}) do
                    if row.spec.node.name==link.mount then nativeMount=row.basis end
                end
            end
            if not nativeMount then return nil,'native_intent_mount_unavailable' end
            local nativeGrip=compose(nativeMount,relative(linkPose,gripPose))
            local separation=distance(nativeLeft,nativeGrip)
            local sidearm=c.weaponTargets[weapon.spec.resource].leftPolicy=='aim_only'
            local enter=sidearm and intent.sidearmEnterMetres or intent.primaryEnterMetres
            local leave=sidearm and intent.sidearmLeaveMetres or intent.primaryLeaveMetres
            local calibrated=intent.weaponThresholds and intent.weaponThresholds[weapon.spec.resource]
            if calibrated then enter,leave=calibrated.enterMetres,calibrated.leaveMetres end
            local previous=self.leftIntent[actor.unit]
            local held=previous and previous.resource==weapon.spec.resource and previous.held
            local permitted=separation<=(held and leave or enter)
            self.leftIntent[actor.unit]={resource=weapon.spec.resource,held=permitted,distance=separation,
                threshold=held and leave or enter,policy=sidearm and 'aim_pose_proxy' or 'native_hand_action_proxy'}
            if not permitted then return nil,sidearm and 'native_pose_not_two_hand_aim' or 'native_left_free_reload_or_other_action' end
        end
        local oldGrip=compose(nativeBefore,weapon_static(weapon.spec.resource,'rootToIKLeft'))
        local contact=distance(nativeLeft,oldGrip)
        local inContact=contact<=c.contactMetres and angle(nativeLeft,oldGrip)<=c.contactDegrees
        local result=solve_source_arm(actor,c,cfg.leftAxes,gripPose)
        result.nativeContactDistance=contact;result.nativeInContact=inContact;result.weapon=weapon.id
        result.weaponResource=weapon.spec.resource;result.link=weapons[1].link
        result.gripResource=gripItem.spec.resource;result.gripKind=gripKind
        return result
    end
    local function plan_attachments(actor)
        local rows={};local poses={}
        local function world(index)
            if not performance.snapshotPoseCache then return matrix(actor.unit,index,true) end
            if not poses[index] then poses[index]=matrix(actor.unit,index,true) end
            return poses[index]
        end
        for _,spec in ipairs(cfg.attachments or {}) do
            verify_node(actor.unit,spec.node,true);verify_node(actor.unit,spec.native,true)
            verify_node(actor.unit,spec.source,true)
            if spec.reference then verify_node(actor.unit,spec.reference,true) end
            if spec.sourceMount then verify_node(actor.unit,spec.sourceMount,true) end
            local before=world(spec.node.index)
            local reference=spec.reference and world(spec.reference.index) or before
            -- Snapshot every offset before any attachment write. Nested cape
            -- nodes must not receive the parent's translation a second time.
            local offset
            if spec.sourceMount then
                -- New exports bake ALL VPK mounts from the original batch-configured
                -- driver chain. Evaluate the Source mount, never the old VPK bind.
                offset=relative(rigid(world(spec.source.index)),world(spec.sourceMount.index))
            else
                offset=relative(rigid(world(spec.native.index)),reference)
            end
            rows[#rows+1]={spec=spec,index=spec.node.index,before=matrix(actor.unit,spec.node.index,false),
                basis=before,offset=offset,touched=false}
        end
        return rows
    end
    local function apply_attachments(actor,rows,leftPhase)
        local worlds,changed,sources,parents={},{},{},{}
        local function source_pose(index)
            if not performance.snapshotPoseCache then return rigid(matrix(actor.unit,index,true)) end
            if not sources[index] then sources[index]=rigid(matrix(actor.unit,index,true)) end
            return sources[index]
        end
        local function parent_pose(index)
            if worlds[index] then return worlds[index] end
            if not performance.snapshotPoseCache then return matrix(actor.unit,index,true) end
            if not parents[index] then parents[index]=matrix(actor.unit,index,true) end
            return parents[index]
        end
        for _,row in ipairs(rows) do
            if (row.spec.native.name=='l_hand' or row.spec.native.name=='l_elbow')==leftPhase then
                local source=source_pose(row.spec.source.index)
                local destination=compose(row.spec.sourceMount and source or compose(source,row.spec.axes),row.offset)
                local desired=copy(row.basis)
                for i=10,12 do desired[i]=destination[i] end
                row.written=relative(parent_pose(row.spec.node.parent),desired)
                worlds[row.index]=desired;changed[#changed+1]=row
                row.touched=true
                U.set_local_pose(actor.unit,row.index+1,X.from_elements(unpack(row.written)))
                assert(difference(matrix(actor.unit,row.index,false),row.written)<=cfg.localTolerance,'attachment_local_readback')
                self.stats.attachmentWrites=self.stats.attachmentWrites+1
            end
        end
        if #changed>0 then
            W.update_unit(actor.world,actor.unit)
            for _,row in ipairs(changed) do
                assert(difference(matrix(actor.unit,row.index,true),worlds[row.index])<=cfg.worldTolerance,'attachment_world_readback')
            end
        end
    end
    local function observe_consumers(actor, sourceLeft, nativeLeft, target, membership, frame)
        for _, item in ipairs(self.consumers) do
            if item.world==actor.world and present(item,membership) then
                pcall(function()
                    identity(item)
                    local root=matrix(item.unit,item.spec.root,true)
                    if distance(root,target)>cfg.consumerRadius then return end
                    local poses={}
                    for _,node in ipairs(item.spec.nodes) do poses[node.name]=matrix(item.unit,node.index,true) end
                    local row={event='consumer',frame=frame,phase='render',avatar=actor.id,
                        world=actor.worldLabel,instance=item.id,kind=item.spec.kind,
                        resource=item.spec.resource,owner='unverified',poses=poses}
                    if item.spec.kind=='weapon' and cfg.leftGrip and cfg.leftGrip.enabled
                        and cfg.leftGrip.weaponTargets[item.spec.resource] then
                        row.mountDistance=distance(root,target);row.mountAngleDegrees=angle(root,target)
                        local right=weapon_static(item.spec.resource,'rootToIKRight')
                        row.rightMarkerAvailable=poses.IK_right~=nil
                        if poses.IK_right and right then
                            row.predictedRightMarkerError=distance(poses.IK_right,compose(target,right))
                        end
                        row.predictedLeftMarkerError=distance(poses.IK_left,
                            compose(target,weapon_static(item.spec.resource,'rootToIKLeft')))
                    elseif item.spec.kind=='foregrip' then
                        row.sourceLeftDistance=distance(sourceLeft,poses.IK_left)
                        row.sourceLeftAngleDegrees=angle(sourceLeft,poses.IK_left)
                        row.nativeLeftDistance=distance(nativeLeft,poses.IK_left)
                        row.nativeLeftAngleDegrees=angle(nativeLeft,poses.IK_left)
                        row.predictedForegripError=distance(poses.IK_left,compose(target,cfg.weaponForegripLeft))
                    end
                    emit(row)
                end)
            end
        end
    end
    -- Bounded read-only graph telemetry; no links, no animation-node setters.
    local function probe_sidearm(actor,membership,phase,frame,now,path)
        local c=cfg.sidearmDiagnostics
        if not c or not c.enabled or not present(actor,membership) then return end
        self.probeState=self.probeState or {};self.probeCount=self.probeCount or {}
        local state=self.probeState[actor.unit] or {};self.probeState[actor.unit]=state
        if state.frame~=frame then
            local count=self.probeCount[path] or 0
            if count>=(c.maxSamplesPerPath or 180) then return end
            if state.last and now>=state.last and now-state.last<(c.intervalSeconds or 1) and state.path==path then return end
            state.frame=frame;state.last=now;state.path=path;self.probeCount[path]=count+1
        end
        local ok,why=pcall(function()
            identity(actor)
            local count=U.num_scene_graph_items(actor.unit)
            local function actor_pose(node)
                if not node or node.index>=count then return nil end
                verify_node(actor.unit,node,false);return matrix(actor.unit,node.index,true)
            end
            local hands={nativeRight=actor_pose(cfg.nativeRight),nativeLeft=actor_pose(cfg.nativeLeft),
                currentMount=actor_pose(cfg.target),sourceRight=actor_pose(cfg.sourceRight),
                sourceRightReference=actor_pose(cfg.rightGrip and cfg.rightGrip.nodes[4]),
                originalMount=actor_pose(cfg.originalMount)}
            local parts={}
            for _,item in ipairs(self.consumers) do
                local id=item.spec.resource
                if item.world==actor.world and present(item,membership)
                    and (id=='8d3d52a3b2f19402' or id=='b96cc3b704a76464' or id=='4851d75853622a47') then
                    identity(item)
                    local root=matrix(item.unit,item.spec.root,true)
                    if distance(root,hands.currentMount)<cfg.consumerRadius then
                        local nodes={};local ncount=U.num_scene_graph_items(item.unit)
                        for _,name in ipairs({'skeleton','root','IK_right','IK_left','game_mesh','g_body',
                            'cylinder_swivel','cylinder','attach_mag','eject_rod','attach_ammo','attach_muzzle'}) do
                            local h=name_id(name)
                            if U.has_node(item.unit,h)==true then
                                local n=U.node(item.unit,h);assert(n>=1 and n<=ncount,'probe_index')
                                local parent=U.scene_graph_parent(item.unit,n)
                                nodes[name]={index=n-1,runtimeIndex=n,runtimeParent=parent,
                                    parentState=parent==nil and 'external_or_root' or 'engine_reported',
                                    world=matrix(item.unit,n-1,true),localPose=matrix(item.unit,n-1,false)}
                            end
                        end
                        parts[#parts+1]={resource=id,instance=item.id,count=ncount,kind=item.spec.kind,
                            owner='unverified',nodes=nodes}
                    end
                end
            end
            if #parts>0 then emit({event='sidearm_probe',frame=frame,time=now,phase=phase,path=path,
                avatar=actor.id,hands=hands,parts=parts,indexBase=0,runtimeIndexBase=1,
                readOnly=true,skinMatricesObserved=false,animationLocalsWritten=false}) end
        end)
        if not ok then emit({event='sidearm_probe_unavailable',frame=frame,phase=phase,reason=tostring(why)}) end
    end
    local function sidearm_target(actor,native,equivalent,membership)
        if cfg.rightAttachmentEnabled==false or not fixes.sidearmRightIK then return nil end
        local candidates={}
        for _,item in ipairs(self.consumers) do
            local isSidearm=fixes.sidearms and fixes.sidearms[item.spec.resource]
            local supported=cfg.leftGrip.weaponTargets[item.spec.resource]
            if supported and (isSidearm or fixes.nativeSidearmAim) and item.world==actor.world and present(item,membership) then
                local ok,result=pcall(function()
                    identity(item);if visible(item.unit)==false then return end
                    local spec=supported
                    for _,name in ipairs(spec.linkNodes or {spec.rootName}) do
                        local id=name_id(name)
                        if U.has_node(item.unit,id)==true then
                            local link=matrix(item.unit,U.node(item.unit,id)-1,true)
                            if distance(link,native)<=cfg.leftGrip.linkMetres and angle(link,native)<=cfg.leftGrip.linkDegrees then
                                -- A primary sharing a stale hand link blocks the
                                -- sidearm follower; never disturb proven primary grips.
                                if not isSidearm then return {blocker=true} end
                                local marker=name_id('IK_right')
                                if U.has_node(item.unit,marker)~=true then return end
                                local ik=matrix(item.unit,U.node(item.unit,marker)-1,true)
                                local projected=compose(native,relative(link,ik))
                                local desired=copy(native);local aim=false;local separation
                                local follow=fixes.nativeSidearmAim and rightEnabled
                                if fixes.nativeSidearmAim and rightEnabled then
                                    local left=name_id('IK_left')
                                    if U.has_node(item.unit,left)==true then
                                        local nativeLeft=matrix(actor.unit,cfg.nativeLeft.index,true)
                                        local nativeGrip=matrix(item.unit,U.node(item.unit,left)-1,true)
                                        separation=distance(nativeLeft,nativeGrip)
                                        local intent=cfg.leftGrip.intent
                                        local aimOnly=spec.leftPolicy=='aim_only'
                                        local enter=aimOnly and ((intent and intent.sidearmEnterMetres) or .035) or ((intent and intent.primaryEnterMetres) or .10)
                                        local leave=aimOnly and ((intent and intent.sidearmLeaveMetres) or .055) or ((intent and intent.primaryLeaveMetres) or .14)
                                        local previous=self.rightIntent[actor.unit]
                                        local held=previous and previous.resource==item.spec.resource and previous.held
                                        aim=separation<=(held and leave or enter)
                                    end
                                end
                                if not follow then
                                    for i=10,12 do desired[i]=native[i]+equivalent[i]-projected[i] end
                                end
                                return {desired=desired,resource=item.spec.resource,
                                    hand=follow and projected or copy(equivalent),nativeAim=aim,nativeFollow=follow,
                                    nativeContactDistance=separation,
                                    policy=follow and 'preserve_native_held_path_sync_source_right_arm' or 'live_right_ik_to_registered_hand'}
                            end
                        end
                    end
                end)
                if ok and result then candidates[#candidates+1]=result end
            end
        end
        if #candidates==1 and not candidates[1].blocker then
            local row=candidates[1];self.rightIntent[actor.unit]={resource=row.resource,held=row.nativeAim}
            return row
        end
        self.rightIntent[actor.unit]=nil
        return nil
    end
    local function apply(actor, model, membership, frame, now, diagnostic)
        local record
        local ok, why=pcall(function()
            identity(actor);identity(model)
            probe_sidearm(actor,membership,'before_write',frame,now,'lua')
            assert(visible(model.unit),'model_hidden_before_write')
            local u=actor.unit
            local original=matrix(u,cfg.originalMount.index,false)
            -- A rigid Source wrist preserves this displacement's length. Check
            -- the animated reference before any body/mount/left setter: an
            -- out-of-range transition must not disable every later weapon.
            local offset=compose(cfg.rightAxes,original)
            local mountDistance=math.sqrt(offset[10]^2+offset[11]^2+offset[12]^2)
            if cfg.rightAttachmentEnabled~=false and mountDistance>cfg.maxWristMountDistance then
                self.stats.mountSkipped=self.stats.mountSkipped+1
                if diagnostic or self.stats.mountSkipped==1 then
                    emit({event='mount_skipped',avatar=actor.id,frame=frame,time=now,
                        reason='mount_offset_out_of_range',distance=mountDistance,
                        limit=cfg.maxWristMountDistance,retry='next_render',originalLocal=original})
                end
                return
            end
            record={actor=actor,diagnostic=diagnostic,protected={},body={},attachments=plan_attachments(actor)}
            self.pending[#self.pending+1]=record
            if cfg.bodySync and cfg.bodySync.enabled then
                for _,item in ipairs(cfg.bodySync.outputs) do
                    verify_node(u,item.node,true);verify_node(u,item.native,true)
                    verify_node(u,item.reference,true);verify_node(u,item.positionParent,true)
                    assert(item.node.parent==item.native.index,'body_native_parent_required')
                    -- Keep the Source torso's animated offsets; direct native
                    -- pivots otherwise separate its coincident upper-spine joints.
                    local positioned=compose(matrix(u,item.positionParent.index,true),matrix(u,item.reference.index,false))
                    local parentLocal=relative(matrix(u,item.native.index,true),positioned)
                    local outputPose=copy(item.localPose)
                    for j=10,12 do outputPose[j]=parentLocal[j] end
                    local row={index=item.node.index,before=matrix(u,item.node.index,false),
                        written=outputPose,touched=true}
                    record.body[#record.body+1]=row
                    U.set_local_pose(u,row.index+1,X.from_elements(unpack(row.written)))
                    assert(difference(matrix(u,row.index,false),row.written)<=cfg.localTolerance,'body_local_readback')
                    self.stats.bodyNodeWrites=self.stats.bodyNodeWrites+1
                    W.update_unit(actor.world,u)
                    assert(distance(matrix(u,row.index,true),positioned)<=cfg.worldTolerance,'body_position_readback')
                end
                if not performance.batchRefresh then refresh_models(actor.world,membership,actor) end
                if diagnostic then emit({event='body_applied',avatar=actor.id,frame=frame,
                    mode=cfg.bodySync.mode,outputs=#record.body,nativeLocalsWritten=false,
                    positionPolicy='source_chain_animated_offsets'}) end
            end
            local native=matrix(u,cfg.target.index,true)
            local nativeLeftBefore=leftEnabled and matrix(u,cfg.nativeLeft.index,true) or nil
            local source=matrix(u,cfg.sourceRight.index,true)
            local sourceLeft=compose(rigid(matrix(u,cfg.sourceLeft.index,true)),cfg.leftAxes)
            local equivalent=compose(rigid(source),cfg.rightAxes)
            -- Capture the live right-IK offset before modifying any hand mount.
            local sidearm=sidearm_target(actor,native,equivalent,membership)
            for _,node in ipairs(cfg.protected) do
                record.protected[#record.protected+1]={node=node,localPose=matrix(u,node.index,false),
                    worldPose=node.world and matrix(u,node.index,true) or nil}
            end
            if sidearm and sidearm.nativeFollow then
                for _,node in ipairs(cfg.rightGrip.nodes) do verify_node(u,node,true) end
                for _,node in ipairs(cfg.rightGrip.outputs) do verify_node(u,node,true) end
                local solved=solve_source_arm(actor,cfg.rightGrip,cfg.rightAxes,sidearm.hand)
                record.right=solved.rows
                for _,row in ipairs(record.right) do
                    row.touched=true;U.set_local_pose(u,row.index+1,X.from_elements(unpack(row.written)))
                    assert(difference(matrix(u,row.index,false),row.written)<=cfg.localTolerance,'right_local_readback')
                    self.stats.rightNodeWrites=self.stats.rightNodeWrites+1
                end
                W.update_unit(actor.world,u)
                assert(difference(matrix(u,cfg.sourceRight.index,true),solved.expected)<=cfg.worldTolerance,'right_world_readback')
                self.stats.rightWrites=self.stats.rightWrites+1
                source=matrix(u,cfg.sourceRight.index,true);equivalent=compose(rigid(source),cfg.rightAxes)
                if diagnostic then emit({event='right_applied',frame=frame,avatar=actor.id,resource=sidearm.resource,
                    target=sidearm.hand,sourceBefore=solved.before,sourceAfter=source,
                    reachResidual=solved.reachResidual,nativeLocalsWritten=false,
                    outputMode='unanimated_reference_children',nativeAimMountPreserved=true}) end
            end
            local reference=compose(equivalent,original)
            if cfg.sourceRightMount then
                verify_node(u,cfg.sourceRightMount,true)
                reference=matrix(u,cfg.sourceRightMount.index,true)
            end
            -- B20's effective position-only setter: keep the live native aim
            -- basis and scale. The destination still uses B23's wrist reference.
            local desired=copy(native);local _,nativeScale=rigid(native)
            for j=10,12 do desired[j]=reference[j] end
            if sidearm then
                desired=sidearm.desired;self.stats.sidearmCorrections=self.stats.sidearmCorrections+1
                if diagnostic then emit({event='sidearm_aligned',resource=sidearm.resource,avatar=actor.id,
                    handTarget=sidearm.hand,desiredWorld=desired,policy=sidearm.policy,nativeAimProxy=sidearm.nativeAim,nativeFollow=sidearm.nativeFollow,nativeContactDistance=sidearm.nativeContactDistance,partLocalsWritten=false}) end
            end
            if cfg.rightAttachmentEnabled==false then desired=copy(native) end
            assert(cfg.rightAttachmentEnabled==false or distance(desired,source)<=cfg.maxWristMountDistance,'mount_offset_out_of_range')
            local parent=matrix(u,cfg.target.parent,true)
            local written=relative(parent,desired)
            for _,v in ipairs(written) do assert(finite(v),'invalid_output') end
            record.before=matrix(u,cfg.target.index,false)
            if cfg.rightAttachmentEnabled~=false then record.written=written end
            record.sourceWorld=source;record.desired=desired
            apply_attachments(actor,record.attachments,false)
            if cfg.rightAttachmentEnabled~=false then
                U.set_local_pose(u,cfg.target.index+1,X.from_elements(unpack(written)))
                self.stats.writes=self.stats.writes+1
            end
            W.update_unit(actor.world,u)
            local modelRefreshes,consumerRefreshes=self.stats.modelRefreshes,self.stats.consumerRefreshes
            refresh_models(actor.world,membership,actor)
            refresh_consumers(actor.world,membership,actor)
            probe_sidearm(actor,membership,'after_mount_refresh',frame,now,'lua')
            local leftResult,leftReason
            if leftEnabled then
                local planned,result,reason=pcall(plan_left,actor,desired,native,nativeLeftBefore,membership,record.attachments)
                if planned then leftResult,leftReason=result,reason else leftReason=tostring(result) end
                if leftResult then
                    record.left=leftResult.rows
                    for _,row in ipairs(record.left) do
                        row.touched=true
                        U.set_local_pose(u,row.index+1,X.from_elements(unpack(row.written)))
                        self.stats.leftNodeWrites=self.stats.leftNodeWrites+1
                    end
                    W.update_unit(actor.world,u)
                    if not performance.batchRefresh or #record.attachments==0 then
                        refresh_models(actor.world,membership,actor);refresh_consumers(actor.world,membership,actor)
                    end
                    for _,row in ipairs(record.left) do
                        assert(difference(matrix(u,row.index,false),row.written)<=cfg.localTolerance,'left_local_readback')
                    end
                    local actualLeft=matrix(u,cfg.sourceLeft.index,true)
                    assert(difference(actualLeft,leftResult.expected)<=cfg.worldTolerance,'left_world_readback')
                    self.stats.leftWrites=self.stats.leftWrites+1
                    sourceLeft=compose(rigid(actualLeft),cfg.leftAxes)
                    if diagnostic then emit({event='left_applied',frame=frame,time=now,avatar=actor.id,
                        weapon=leftResult.weapon,weaponResource=leftResult.weaponResource,owner='unverified',
                        link=leftResult.link,
                        mode='existing_two_bone_solver',nativeContactDistance=leftResult.nativeContactDistance,
                        intent=self.leftIntent[actor.unit],gripResource=leftResult.gripResource,gripKind=leftResult.gripKind,
                        outputMode=cfg.leftGrip.outputs and 'unanimated_reference_children' or 'animated_source_nodes',
                        nativeInContact=leftResult.nativeInContact,requireNativeContact=false,
                        reachPolicy=cfg.leftGrip.reachPolicy,softDistance=cfg.leftGrip.softDistance,
                        beforeDistance=distance(leftResult.before,leftResult.target),
                        afterDistance=distance(actualLeft,leftResult.target),
                        afterAngleDegrees=angle(sourceLeft,leftResult.target),reachResidual=leftResult.reachResidual,
                        target=leftResult.target,sourceBefore=leftResult.before,sourceAfter=actualLeft}) end
                else
                    self.stats.leftSkipped=self.stats.leftSkipped+1
                    if diagnostic then emit({event='left_skipped',frame=frame,time=now,avatar=actor.id,reason=leftReason,intent=self.leftIntent[actor.unit]}) end
                end
            end
            -- A package or reload shell follows the final left wrist, whether
            -- that wrist is animated freely or solved to a two-handed weapon.
            apply_attachments(actor,record.attachments,true)
            if #record.attachments>0 then
                refresh_models(actor.world,membership,actor);refresh_consumers(actor.world,membership,actor)
                if diagnostic then emit({event='attachments_applied',frame=frame,avatar=actor.id,
                    count=#record.attachments,headDescendants=false,policy='position_preserve_native_basis',
                    singleHand='right_and_left_mounts_independent'}) end
            end
            local actual=matrix(u,cfg.target.index,true)
            assert(difference(matrix(u,cfg.target.index,false),written)<=cfg.localTolerance,'local_readback')
            assert(difference(actual,desired)<=cfg.worldTolerance,'world_readback')
            for _,row in ipairs(record.protected) do
                assert(difference(matrix(u,row.node.index,false),row.localPose)<=cfg.localTolerance,
                    'protected_local_changed:'..row.node.name)
                if row.worldPose then
                    assert(difference(matrix(u,row.node.index,true),row.worldPose)<=cfg.worldTolerance,
                        'protected_world_changed:'..row.node.name)
                end
            end
            self.stats.readbacks=self.stats.readbacks+1
            probe_sidearm(actor,membership,'final_output',frame,now,'lua')
            if diagnostic then
                local nativeLeft=matrix(u,cfg.nativeLeft.index,true)
                local rightMarker=leftResult and weapon_static(leftResult.weaponResource,'rootToIKRight')
                    or (not leftEnabled and cfg.weaponRight or nil)
                emit({event='applied',frame=frame,time=now,phase='render',avatar=actor.id,world=actor.worldLabel,
                    target=cfg.target.name,source=cfg.sourceRight.name,reference=cfg.originalMount.name,
                    axisRegistration=cfg.axisRegistration,originalLocal=original,rotationMode='native-world',
                    worldUnits=#membership[actor.world].units,modelResource=model.spec.resource,
                    modelRefreshes=self.stats.modelRefreshes-modelRefreshes,
                    consumerRefreshes=self.stats.consumerRefreshes-consumerRefreshes,
                    nativeRight=matrix(u,cfg.nativeRight.index,true),sourceRight=source,
                    equivalentRight=equivalent,beforeWorld=native,desiredWorld=desired,actualWorld=actual,
                    localReadbackError=difference(matrix(u,cfg.target.index,false),written),
                    worldReadbackError=difference(actual,desired),weaponWorldScale=nativeScale,
                    weaponResource=leftResult and leftResult.weaponResource,
                    rightWristToMarker=rightMarker and relative(equivalent,compose(desired,rightMarker)),
                    sourceLeft=sourceLeft,nativeLeft=nativeLeft,leftWrite=leftResult~=nil,
                    predictedLeftDistance=leftResult and distance(sourceLeft,leftResult.target),
                    palmSurfaceCalibrated=false})
                if not cfg.diagnostics or cfg.diagnostics.consumers~=false then
                    observe_consumers(actor,sourceLeft,nativeLeft,actual,membership,frame)
                end
            end
        end)
        if not ok then
            self.disabled=true
            if record then
                local restored,result=pcall(restore,record,membership,true)
                if restored then
                    for i=#self.pending,1,-1 do if self.pending[i]==record then table.remove(self.pending,i) end end
                end
                emit({event='rollback',avatar=actor.id,verified=restored and result=='restored',reason=tostring(result)},true)
            end
            emit({event='disabled',avatar=actor.id,reason=tostring(why)},true)
        end
    end
    -- FP presentation still needs dependency/skin graph refreshes. These are
    -- existing links only: NO attachment, bone-pose, visibility or relink setters.
    local function fp_presentation(frame,now,detail)
        local due=not self.lastFpScan or now<self.lastFpScan or now-self.lastFpScan>=cfg.scanSeconds
        local membership=members(due)
        local main
        if sceneContext and type(sceneContext.world)=='function' then
            local ok,w=pcall(sceneContext.world);if ok then main=w end
        end
        if not main or not membership[main] then return end
        if cfg.missionGuard and cfg.missionGuard.enabled then
            local ok,mission=false,false
            if sceneContext and type(sceneContext.inMission)=='function' then ok,mission=pcall(sceneContext.inMission) end
            if not ok or mission~=true then return end
        end
        -- Keep the known gameplay World, plus any actual FP camera World. No
        -- preview/ship World or arbitrary mesh discovery becomes a write owner.
        local scoped={[main]=membership[main]}
        if sceneContext and type(sceneContext.fpWorld)=='function' then
            local ok,w=pcall(sceneContext.fpWorld)
            if ok and w and membership[w] then scoped[w]=membership[w] end
        end
        if due then scan(scoped,now);self.lastFpScan=now end
        local diagnostic=not self.lastFpLog or now<self.lastFpLog or now-self.lastFpLog>=1
        local actorRows,modelRows={},{ }
        local function refresh(item,kind)
            if not present(item,scoped) then return false end
            local ok,why=pcall(function()
                identity(item);W.update_unit(item.world,item.unit)
                self.stats.fpPresentationRefreshes=self.stats.fpPresentationRefreshes+1
            end)
            if not ok then
                self.stats.fpPresentationErrors=self.stats.fpPresentationErrors+1
                if diagnostic then emit({event='fp_presentation_unavailable',frame=frame,kind=kind,
                    resource=item.spec.resource,reason=tostring(why)}) end
            end
            return ok
        end
        -- Avatar -> known body Units -> already classified equipment graphs.
        -- Refresh even temporarily hidden body meshes: visibility can be restored
        -- later by the native FP renderer, and stale palettes must not survive it.
        for _,a in ipairs(self.actors) do
            if refresh(a,'avatar') and diagnostic then
                local ok,row=pcall(function()
                    return {instance=a.id,resource=a.spec.resource,world=a.worldLabel,
                        root=matrix(a.unit,0,true),nativeRight=matrix(a.unit,cfg.nativeRight.index,true),
                        sourceRight=matrix(a.unit,cfg.sourceRight.index,true),
                        sourceReference=cfg.rightGrip and matrix(a.unit,cfg.rightGrip.nodes[4].index,true)}
                end)
                if ok then actorRows[#actorRows+1]=row
                else emit({event='fp_presentation_snapshot_unavailable',kind='avatar',frame=frame,instance=a.id,reason=tostring(row)}) end
            end
        end
        for _,item in ipairs(self.models) do
            local before={}
            if diagnostic and present(item,scoped) then
                pcall(function()
                    for _,row in ipairs(item.spec.observeNodes or {}) do
                        if row.driver=='l_hand' or row.driver=='r_hand' then before[row.driver]=matrix(item.unit,row.index,true) end
                    end
                end)
            end
            if refresh(item,'model') and diagnostic then
                local ok,row=pcall(function()
                    local after,parents={},{ }
                    for _,node in ipairs(item.spec.observeNodes or {}) do
                        if node.driver=='l_hand' or node.driver=='r_hand' then
                            after[node.driver]=matrix(item.unit,node.index,true)
                            local parent=U.scene_graph_parent(item.unit,node.index+1)
                            parents[node.driver]=parent==nil and 'nil_external_or_unavailable' or parent
                        end
                    end
                    local visibility=visible(item.unit)
                    return {instance=item.id,resource=item.spec.resource,count=item.spec.count,world=item.worldLabel,
                        root=matrix(item.unit,0,true),visible=visibility==nil and 'unknown' or visibility,
                        before=before,after=after,parents=parents,
                        owner='unverified_existing_link',poseWritten=false,skinPaletteObserved=false}
                end)
                if ok then modelRows[#modelRows+1]=row
                else emit({event='fp_presentation_snapshot_unavailable',kind='model',frame=frame,instance=item.id,reason=tostring(row)}) end
            end
        end
        -- Only nearby classified equipment; do not refresh every battlefield
        -- consumer when no attachment solve is running. Existing links stay intact.
        for _,item in ipairs(self.consumers) do
            local ok,near=pcall(function()
                if not present(item,scoped) then return false end
                local root=matrix(item.unit,item.spec.root,true)
                for _,a in ipairs(self.actors) do
                    if a.world==item.world and present(a,scoped) then
                        if math.min(distance(root,matrix(a.unit,cfg.nativeRight.index,true)),
                            distance(root,matrix(a.unit,cfg.nativeLeft.index,true))) <= (performance.refreshRadius or 1.5) then return true end
                    end
                end
                return false
            end)
            if ok and near then refresh(item,'consumer') end
        end
        if diagnostic then
            self.lastFpLog=now
            emit({event='fp_presentation',frame=frame,time=now,view=detail,actors=actorRows,models=modelRows,
                refreshed=self.stats.fpPresentationRefreshes,attachmentsWritten=false,bonesWritten=false,
                visibilityWritten=false,linksChanged=false,skinMatricesObserved=false})
        end
    end
    local function view_bypass(frame,now)
        if not sceneContext or type(sceneContext.firstPerson)~='function' then return false end
        local ok,first,detail=pcall(sceneContext.firstPerson)
        if ok and first==false then
            if self.viewBlocked then self.viewBlocked=false;self.lastScan=nil;self.lastFpScan=nil end
            return false
        end
        -- One cleanup transaction on entry; subsequent FP frames have no setters.
        if #self.pending>0 then self:release(members(false)) end
        self.leftIntent={};self.rightIntent={};self.lastScan=nil
        local counter=ok and first==true and 'firstPersonBypasses' or 'unknownViewBypasses'
        self.stats[counter]=self.stats[counter]+1
        local status=ok and first==true and 'first_person_bypass' or 'unknown_view_bypass'
        if self.lastStatus~=status then
            emit({event='view_bypass',status=status,phase=self.phase,frame=frame,
                restored=#self.pending==0,detail=ok and detail or tostring(first),
                writes=false,scope='all_attachment_arm_and_body_outputs'},true)
            self.lastStatus=status
        end
        self.viewBlocked=true
        if ok and first==true and self.phase=='render' then fp_presentation(frame,now,detail) end
        return true
    end
    function self:tick(phase, frame, now)
        if self.stopped then return end
        self.phase=phase
        self.validation={};self.nodeValidation={}
        assert(phase=='update' or phase=='render','unknown_phase')
        if view_bypass(frame,now) then return end
        -- Match the working B19/B20 lifetime: hold the write through update,
        -- restore immediately before the next render transaction or shutdown.
        if phase=='update' then
            if cfg.missionGuard and cfg.missionGuard.enabled then return end
            begin_sync(frame,now)
            if self.syncFrame==frame then capture_sync('update',self.monitored,members(),frame,now) end
            return
        end
        if cfg.missionGuard and cfg.missionGuard.enabled and #self.pending==0 then
            local ok,mission=false,false
            if sceneContext and type(sceneContext.inMission)=='function' then ok,mission=pcall(sceneContext.inMission) end
            if not ok or mission~=true then
                self.stats.sceneBypasses=self.stats.sceneBypasses+1;self.leftIntent={};self.rightIntent={};self.monitored={};self.lastScan=nil
                if self.lastStatus~='non_mission_bypass' then
                    emit({event='scene_bypass',reason='ship_loading_or_unverified_mission',writes=false},true)
                    self.lastStatus='non_mission_bypass'
                end
                return
            end
        end
        local rescanned=not self.lastScan or now<self.lastScan or now-self.lastScan>=cfg.scanSeconds
        local membership=members(rescanned)
        begin_sync(frame,now)
        capture_sync('render_input',self.monitored,membership,frame,now)
        for actor in pairs(self.monitored) do probe_sidearm(actor,membership,'next_input',frame,now,'lua') end
        self:release(membership)
        if self.disabled then return end
        self.validation={};self.nodeValidation={}
        if cfg.missionGuard and cfg.missionGuard.enabled then
            local allowed=false
            if sceneContext and type(sceneContext.inMission)=='function' and type(sceneContext.world)=='function' then
                local ok,mission=pcall(sceneContext.inMission)
                local wok,world=pcall(sceneContext.world)
                allowed=ok and wok and mission==true and world~=nil
                if allowed then
                    for w in pairs(membership) do if w~=world then membership[w]=nil end end
                end
            end
            if not allowed then
                self.stats.sceneBypasses=self.stats.sceneBypasses+1
                self.leftIntent={};self.rightIntent={};self.monitored={};self.lastScan=nil
                if self.lastStatus~='non_mission_bypass' then
                    emit({event='scene_bypass',reason='ship_loading_or_unverified_mission',writes=false},true)
                    self.lastStatus='non_mission_bypass'
                end
                return
            end
        end
        if rescanned then scan(membership,now) end
        local diagnostic=not self.lastLog or now<self.lastLog or now-self.lastLog>=cfg.logSeconds
        local selected,reasons=matching_actors(membership);local active=0
        for _,actor in ipairs(self.observerActors) do probe_sidearm(actor,membership,'native_only',frame,now,'native') end
        for _,actor in ipairs(self.actors) do
            if not selected[actor] then probe_sidearm(actor,membership,'native_only',frame,now,'native') end
        end
        if cfg.previewGuard and cfg.previewGuard.enabled then
            for actor in pairs(selected) do
                -- The captured preview has 33 Units. Do not hardcode world 11.
                -- Small-world isolation is conservative and explicitly experimental.
                if #membership[actor.world].units<cfg.previewGuard.minimumWorldUnits then
                    selected[actor]=nil;self.leftIntent[actor.unit]=nil
                    if diagnostic then emit({event='small_world_bypass',avatar=actor.id,world=actor.worldLabel,
                        units=#membership[actor.world].units,reason='preview_isolation_heuristic',writes=false}) end
                end
            end
        end
        for actor,model in pairs(selected) do
            if not self.disabled then apply(actor,model,membership,frame,now,diagnostic);active=active+1 end
        end
        self.monitored=selected
        capture_sync('render_output',selected,membership,frame,now)
        if self.disabled then self:release(membership) end
        local status=active>0 and 'active' or 'waiting_for_unique_visible_test01'
        if status~=self.lastStatus then
            emit({event='status',status=status,frame=frame,actors=#self.actors,models=#self.models,
                consumers=#self.consumers},true)
            self.lastStatus=status
        end
        if active==0 then
            self.stats.skipped=self.stats.skipped+1
            if rescanned then emit({event='waiting',frame=frame,actors=#self.actors,models=#self.models,
                consumers=#self.consumers,reasons=reasons}) end
        end
        if diagnostic then self.lastLog=now end
    end
    function self:stop(reason)
        if self.stopped then return end
        self.phase='shutdown';self:release(members());self.stopped=true
        emit({event='complete',reason=reason or 'shutdown',stats=self.stats,pendingRestores=#self.pending,
            disabled=self.disabled},true)
    end
    emit({event='loaded',version=M.VERSION,writePhase='render',restorePhase='before_render_and_shutdown',
        target='attach_hand_r',originalReference=cfg.originalMount.name,axisRegistration=cfg.axisRegistration,
        writePolicy='position_only_preserve_native_aim',discovery='B19_B20_all_worlds_all_units',
        refreshOrder='avatar_model_weapon_components',
        firstPersonGuard=sceneContext and type(sceneContext.firstPerson)=='function' or false,
        experimentalPoseIntent=cfg.leftGrip and cfg.leftGrip.intent and cfg.leftGrip.intent.enabled or false,
        scopedRefresh=performance.scopedRefresh or false,
        previewIsolation=cfg.previewGuard and cfg.previewGuard.enabled or false,
        leftMode=leftEnabled and 'source_arm_to_weapon_self_ik_left' or 'foregrip_observation_only',
        mountOutOfRangePolicy='skip_frame_retry_without_setters',
        leftOutputMode=cfg.leftGrip and cfg.leftGrip.outputs and 'unanimated_reference_children' or 'animated_source_nodes',
        bodyMode=cfg.bodySync and cfg.bodySync.enabled and cfg.bodySync.mode or 'observation_only',
        rigExpectedNodes=cfg.avatar.count,
        attachmentCount=#(cfg.attachments or {}),headDescendants=false,
        syncMode=cfg.sync and cfg.sync.enabled and 'update_render_input_render_output' or 'off',
        physics='separate_addon',palmSurfaceCalibrated=false},true)
    return self
end

return M
