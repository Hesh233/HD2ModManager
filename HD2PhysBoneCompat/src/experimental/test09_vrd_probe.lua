-- TEST09 VRD/upper-body READ-ONLY probe. Appended to the accepted axis1
-- compat copy. It changes no solver, driver output, setter, gate or flush.
-- One foreground eligible session, 1 sample/2 s, <=20 samples; no file IO.
local test09ProbeAttach, test09ProbeUpdate = M.attach, M.update_tip
local test09ProbeRelease, test09ProbeQuatinterp = M.release, M.quatinterp

local function test09_probe_angle(a,b)
    if type(a) ~= 'table' or type(b) ~= 'table' then return -1 end
    local dot=a[1]*b[1]+a[2]*b[2]+a[3]*b[3]+a[4]*b[4]
    local na=a[1]^2+a[2]^2+a[3]^2+a[4]^2
    local nb=b[1]^2+b[2]^2+b[3]^2+b[4]^2
    if na<1e-12 or nb<1e-12 or dot~=dot then return -1 end
    return 360/math.pi*math.acos(math.min(1,math.abs(dot)/math.sqrt(na*nb)))
end
local function test09_probe_qtext(q)
    if q==nil then return 'unreadable' end
    return string.format('%.5f,%.5f,%.5f,%.5f',q[1],q[2],q[3],q[4])
end
local function test09_probe_q(S,u,n)
    local x,y,z,w=read_quat4(S,u,n)
    if x==nil then return nil end
    return {x,y,z,w}
end
local function test09_probe_local(S,u,n)
    local ok,pose=pcall(function()return S.Unit.local_pose(u,n)end)
    local snap=ok and pose~=nil and snapshot_pose(S,pose) or nil
    if not snap then return nil end
    return {stored9_quaternion(snap.r)}
end
local function test09_probe_relative(parent,child)
    if not parent or not child then return nil end
    return {qmul(-parent[1],-parent[2],-parent[3],parent[4],child[1],child[2],child[3],child[4])}
end
local function test09_probe_position(S,u,n)
    local ok,v=pcall(function()return S.Unit.world_position(u,n)end)
    if not ok or v==nil then return nil end
    local good,x,y,z=pcall(function()return S.Vector3.to_elements(v)end)
    if not good or type(x)~='number' or x~=x or y~=y or z~=z then return nil end
    return {x,y,z}
end
local function test09_probe_safe(session)
    if session.dead~=nil or not M.unit_alive(session.S,session.unit) then return false end
    local ok,n=pcall(function()return session.S.Unit.num_scene_graph_items(session.unit)end)
    return ok and n==session.nodeCount
end
local function test09_probe_node(S,u,name,count)
    local ok,id=pcall(function()return S.Application.string_to_id32(name)end)
    if not ok or id==nil then return nil end
    local exists,has=pcall(function()return S.Unit.has_node(u,id)end)
    if not exists or has~=true then return nil end
    local valid,n=pcall(function()return S.Unit.node(u,id)end)
    if valid and type(n)=='number' and n>=1 and n<=count then return n end
    return nil
end
local function test09_probe_body(session)
    local state=session.test09Probe;local out={}
    for _,name in ipairs({'hips','spine1','spine2'}) do
        local n=state.body[name]
        if n then out[name]={localQ=test09_probe_local(session.S,session.unit,n),worldQ=test09_probe_q(session.S,session.unit,n),p=test09_probe_position(session.S,session.unit,n)} end
    end
    return out
end
local function test09_probe_before(session)
    local state=session.test09Probe
    state.pre={};state.rule={};state.bodyPre=test09_probe_body(session)
    for _,row in ipairs(session.drivers) do
        local S,u=session.S,session.unit
        local parent=test09_probe_q(S,u,row.parentNode)
        local world=test09_probe_q(S,u,row.node)
        local localQ=test09_probe_local(S,u,row.node)
        state.pre[row.name]={localQ=localQ,relativeQ=test09_probe_relative(parent,world),last=row.lastWritten and {row.lastWritten[1],row.lastWritten[2],row.lastWritten[3],row.lastWritten[4]} or nil}
        row.test09ProbeSink=state.rule
    end
end
function M.quatinterp(control,procedure)
    local x,y,z,w=test09ProbeQuatinterp(control,procedure)
    local sink=type(procedure)=='table' and procedure.test09ProbeSink or nil
    if sink~=nil then
        local total,count,best=0,0,0
        for _,rule in ipairs(procedure.rules) do
            local dot=math.abs(control[1]*rule.trigger[1]+control[2]*rule.trigger[2]+control[3]*rule.trigger[3]+control[4]*rule.trigger[4])
            local weight=math.max(0,1-2*math.acos(math.min(1,dot))*rule.invTolerance)
            if weight>0 then total=total+weight;count=count+1;best=math.max(best,weight) end
        end
        sink[procedure.name]={delta={control[1],control[2],control[3],control[4]},target=x and {x,y,z,w} or nil,support=total,matches=count,best=best}
    end
    if x==nil then return nil end
    return x,y,z,w
end
local function test09_probe_after(session)
    local state=session.test09Probe;local log=session.logger
    local body=test09_probe_body(session);local h,s2=body.hips,body.spine2
    local lean,direction=-1,'unreadable'
    if h and s2 and h.p and s2.p then
        local dx,dy,dz=s2.p[1]-h.p[1],s2.p[2]-h.p[2],s2.p[3]-h.p[3]
        lean=180/math.pi*math.atan2(math.sqrt(dx*dx+dy*dy),dz)
        direction=string.format('%.4f,%.4f,%.4f',dx,dy,dz)
    end
    local changes={};local locals={}
    for _,name in ipairs({'hips','spine1','spine2'}) do
        local now,pre=body[name],state.bodyPre[name]
        changes[#changes+1]=string.format('%.5f',test09_probe_angle(now and now.worldQ,pre and pre.worldQ))
        locals[#locals+1]=name..'L='..test09_probe_qtext(now and now.localQ)
    end
    log('[physbone][test09-vrdprobe] sample=%d tag=%s phase=after_physics driverFrameWrites=%d leanUp=%.3f segment=%s bodyPhysicsDeltaDeg=%s %s',
        state.samples,tostring(session.unitTag or '?'),session.test09ProbeDriverWrites or 0,lean,direction,table.concat(changes,','),table.concat(locals,' '))
    for _,row in ipairs(session.drivers) do
        local pre,rule=state.pre[row.name],state.rule[row.name]
        local localQ=test09_probe_local(session.S,session.unit,row.node)
        local relative=test09_probe_relative(test09_probe_q(session.S,session.unit,row.parentNode),test09_probe_q(session.S,session.unit,row.node))
        local bpre=nil
        -- inferred pre-rotation is relative * local^-1, NOT local^-1*relative.
        if pre and pre.relativeQ and pre.localQ then bpre={qmul(pre.relativeQ[1],pre.relativeQ[2],pre.relativeQ[3],pre.relativeQ[4],-pre.localQ[1],-pre.localQ[2],-pre.localQ[3],pre.localQ[4])} end
        log('[physbone][test09-vrdrow] sample=%d bone=%s ctrl=%s matches=%d support=%.4f delta=%s ruleDeg=%.3f smoothDeg=%.3f localVsWriteDeg=%.4f worldVsLocalDeg=%.4f preVsLastWriteDeg=%.4f inferredPreDeg=%.4f helperLocal=%s',
            state.samples,row.name,row.test09ProbeControlName or '?',rule and rule.matches or -1,rule and rule.support or -1,
            test09_probe_qtext(rule and rule.delta),test09_probe_angle(rule and rule.target,{0,0,0,1}),
            test09_probe_angle(row.smoothedQ,row.base.bindQ),test09_probe_angle(localQ,row.lastWritten),test09_probe_angle(relative,localQ),
            test09_probe_angle(pre and pre.localQ,pre and pre.last),test09_probe_angle(bpre,{0,0,0,1}),test09_probe_qtext(localQ))
    end
end
function M.attach(S,u,rig,options)
    local session=test09ProbeAttach(S,u,rig,options)
    if session and session.dead==nil and type(session.drivers)=='table' and #session.drivers==6 and M.test09_axis_profile(rig)~=nil then
        local body={}
        for _,row in ipairs(session.drivers) do
            for _,bone in ipairs(rig.drivers.bones) do if bone.name==row.name then row.test09ProbeControlName=bone.controlName end end
        end
        for _,name in ipairs({'hips','spine1','spine2'}) do body[name]=test09_probe_node(S,u,name,session.nodeCount) end
        session.test09Probe={body=body,elapsed=0,samples=0}
    end
    return session
end
local test09ProbeDrivers=M.update_drivers
function M.update_drivers(session,dt)
    local n=test09ProbeDrivers(session,dt)
    if session.test09Probe and session.test09ProbeCapture then session.test09ProbeDriverWrites=n end
    return n
end
function M.update_tip(session,dt,budget)
    local state=session and session.test09Probe
    local sample=false
    if state and not state.disabled and state.samples<20 and type(dt)=='number' and dt==dt and dt>0 then
        if M.test09ProbeOwner==nil and (session.ownerOrder or 1)==1 then M.test09ProbeOwner=session end
        if M.test09ProbeOwner==session then
            state.elapsed=state.elapsed+math.min(dt,.25)
            if state.elapsed>=2 then
                state.elapsed=0
                if test09_probe_safe(session) then
                    state.samples=state.samples+1
                    local ok=pcall(test09_probe_before,session)
                    sample=ok;session.test09ProbeCapture=ok
                    if not ok then state.disabled=true end
                else state.disabled=true;M.test09ProbeOwner=nil end
            end
        end
    end
    local n=test09ProbeUpdate(session,dt,budget)
    if sample then
        if test09_probe_safe(session) then
            local ok,err=pcall(test09_probe_after,session)
            if not ok then state.disabled=true;session.logger('[physbone][test09-vrdprobe] read_error=%s',tostring(err)) end
        else state.disabled=true;M.test09ProbeOwner=nil end
    end
    if state then
        for _,row in ipairs(session.drivers or {}) do row.test09ProbeSink=nil end
        session.test09ProbeCapture=nil
    end
    return n
end
function M.release(session)
    if M.test09ProbeOwner==session then M.test09ProbeOwner=nil end
    return test09ProbeRelease(session)
end
