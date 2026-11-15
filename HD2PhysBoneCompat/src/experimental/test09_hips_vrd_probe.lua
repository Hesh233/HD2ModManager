-- Exact visible test09 Hips READ-ONLY probe2. Accepted axis1 is the underlying
-- module; no spring/VRD math, setter, flush or animation change is made here.
local HAttach,HUpdate,HDrivers,HInterp,HRelease=M.attach,M.update_tip,M.update_drivers,M.quatinterp,M.release
local HIP_RESOURCE='34a40a5ae7a392ba'
local FRONT={'skirt_a_c','skirt_b_l','skirt_c_l','skirt_d_l','skirt_b_r','skirt_c_r','skirt_d_r'}
local function identity(S,u)
    local ok,value=pcall(function()return S.Unit.name_hash(u)end)
    if ok and type(value)=='string' and value:lower()==HIP_RESOURCE then return HIP_RESOURCE end
    local good,tag=pcall(function()return S.Unit.debug_name(u)end)
    if good and tag=='#ID['..HIP_RESOURCE..']' then return HIP_RESOURCE end
    return nil
end
local function node(S,u,name,count)
    local ok,id=pcall(function()return S.Application.string_to_id32(name)end)
    if not ok or id==nil then return nil end
    local good,has=pcall(function()return S.Unit.has_node(u,id)end)
    if not good or has~=true then return nil end
    local valid,n=pcall(function()return S.Unit.node(u,id)end)
    if valid and type(n)=='number' and n>=1 and n<=count then return n end
    return nil
end
local function safe(s)
    if s.dead~=nil or not M.unit_alive(s.S,s.unit) then return false end
    local ok,n=pcall(function()return s.S.Unit.num_scene_graph_items(s.unit)end)
    return ok and n==s.nodeCount
end
local function q(S,u,n)
    local x,y,z,w=read_quat4(S,u,n)
    if x==nil then return nil end
    return {x,y,z,w}
end
local function lq(S,u,n)
    local ok,p=pcall(function()return S.Unit.local_pose(u,n)end)
    local snap=ok and p~=nil and snapshot_pose(S,p) or nil
    return snap and {stored9_quaternion(snap.r)} or nil
end
local function pos(S,u,n)
    local ok,v=pcall(function()return S.Unit.world_position(u,n)end)
    if not ok or v==nil then return nil end
    local good,x,y,z=pcall(function()return S.Vector3.to_elements(v)end)
    if not good or type(x)~='number' or x~=x or y~=y or z~=z then return nil end
    return {x,y,z}
end
local function rel(p,c)
    if not p or not c then return nil end
    return {qmul(-p[1],-p[2],-p[3],p[4],c[1],c[2],c[3],c[4])}
end
local function frame(r,l)
    if not r or not l then return nil end
    return {qmul(r[1],r[2],r[3],r[4],-l[1],-l[2],-l[3],l[4])}
end
local function angle(a,b)
    if not a or not b then return -1 end
    local dot=a[1]*b[1]+a[2]*b[2]+a[3]*b[3]+a[4]*b[4]
    local na=a[1]^2+a[2]^2+a[3]^2+a[4]^2
    local nb=b[1]^2+b[2]^2+b[3]^2+b[4]^2
    if na<1e-12 or nb<1e-12 or dot~=dot then return -1 end
    return 360/math.pi*math.acos(math.min(1,math.abs(dot)/math.sqrt(na*nb)))
end
local function text(v)
    if not v then return 'unreadable' end
    local parts={};for i=1,#v do parts[i]=string.format('%.6f',v[i]) end
    return table.concat(parts,',')
end
local function body(s)
    local out={}
    for _,name in ipairs({'hips','spine1','spine2'}) do
        local n=s.test09HipProbe.body[name]
        if n then out[name]={world=q(s.S,s.unit,n),p=pos(s.S,s.unit,n)} end
    end
    return out
end
local function before(s)
    local st=s.test09HipProbe;st.pre={};st.rules={};st.bodyPre=body(s)
    local hips=st.bodyPre.hips and st.bodyPre.hips.world
    for _,r in ipairs(st.frontDrivers) do
        local w=q(s.S,s.unit,r.node)
        st.pre[r.name]={localQ=lq(s.S,s.unit,r.node),world=w,hipRel=rel(hips,w),last=r.lastWritten and {r.lastWritten[1],r.lastWritten[2],r.lastWritten[3],r.lastWritten[4]} or nil}
        r.test09HipProbeSink=st.rules
    end
    for _,item in ipairs(st.frontSprings) do
        local expected=nil
        if item.lastWritten and item.lastWritten[1] then expected={M.compose_bind_rotation(item.lastWritten[1],item.basePoses[1])} end
        st.pre[item.chain[1].name]={localQ=lq(s.S,s.unit,item.nodes[1]),world=q(s.S,s.unit,item.nodes[1]),last=expected}
    end
end
function M.quatinterp(control,procedure)
    local x,y,z,w=HInterp(control,procedure)
    local sink=type(procedure)=='table' and procedure.test09HipProbeSink or nil
    if sink then
        local matches,total=0,0
        for _,rule in ipairs(procedure.rules) do
            local dot=math.abs(control[1]*rule.trigger[1]+control[2]*rule.trigger[2]+control[3]*rule.trigger[3]+control[4]*rule.trigger[4])
            local weight=math.max(0,1-2*math.acos(math.min(1,dot))*rule.invTolerance)
            if weight>0 then matches=matches+1;total=total+weight end
        end
        sink[procedure.name]={delta={control[1],control[2],control[3],control[4]},target=x and {x,y,z,w} or nil,matches=matches,support=total}
    end
    if x==nil then return nil end
    return x,y,z,w
end
local function after(s)
    local st=s.test09HipProbe;local log=s.logger;local b=body(s)
    local hips=b.hips and b.hips.world;local hp=b.hips and b.hips.p;local lean=-1
    if hp and b.spine2 and b.spine2.p then
        local p=b.spine2.p;lean=180/math.pi*math.atan2(math.sqrt((p[1]-hp[1])^2+(p[2]-hp[2])^2),p[3]-hp[3])
    end
    local changed={}
    for _,name in ipairs({'hips','spine1','spine2'}) do changed[#changed+1]=string.format('%.5f',angle(b[name] and b[name].world,st.bodyPre[name] and st.bodyPre[name].world)) end
    log('[physbone][test09-hipsprobe] sample=%d resource=%s phase=after_physics frontSprings=7 driverWrites=%d bodyDeltaDeg=%s leanUp=%.3f hipsW=%s hipsP=%s',
        st.samples,HIP_RESOURCE,st.driverWrites or 0,table.concat(changed,','),lean,text(hips),text(hp))
    local helper={}
    for _,r in ipairs(st.frontDrivers) do
        local w=q(s.S,s.unit,r.node);local p=pos(s.S,s.unit,r.node);local localQ=lq(s.S,s.unit,r.node)
        local relative=rel(hips,w);local pre=st.pre[r.name];local rule=st.rules[r.name]
        helper[r.name]={q=w,p=p}
        log('[physbone][test09-hipdriver] sample=%d bone=%s matches=%d support=%.5f ctrlD=%s ruleDeg=%.3f smoothDeg=%.3f afterVsWriteDeg=%.5f beforeVsLastDeg=%.5f preBindDeg=%.5f localQ=%s hipRelQ=%s worldQ=%s worldP=%s',
            st.samples,r.name,rule and rule.matches or -1,rule and rule.support or -1,text(rule and rule.delta),
            angle(rule and rule.target,{0,0,0,1}),angle(r.smoothedQ,r.base.bindQ),angle(localQ,r.lastWritten),angle(pre.localQ,pre.last),
            angle(frame(pre.hipRel,pre.localQ),{0,0,0,1}),text(localQ),text(relative),text(w),text(p))
    end
    for _,item in ipairs(st.frontSprings) do
        local name=item.chain[1].name;local h=helper[item.chain[1].parentName]
        local world=q(s.S,s.unit,item.nodes[1]);local localQ=lq(s.S,s.unit,item.nodes[1]);local p=pos(s.S,s.unit,item.nodes[1]);local relative=rel(h and h.q,world)
        local expected=nil
        if item.lastRotations and item.lastRotations[1] then expected={M.compose_bind_rotation(item.lastRotations[1],item.basePoses[1])} end
        local cached=nil
        if item.lastWritten and item.lastWritten[1] then cached={M.compose_bind_rotation(item.lastWritten[1],item.basePoses[1])} end
        local offset=nil
        if h and h.p and h.q and p then offset={qrot(-h.q[1],-h.q[2],-h.q[3],h.q[4],p[1]-h.p[1],p[2]-h.p[2],p[3]-h.p[3])} end
        local rotation=item.lastRotations and item.lastRotations[1]
        local dir=item.tip.dirs and item.tip.dirs[1]
        log('[physbone][test09-hipspring] sample=%d bone=%s parent=%s swingDeg=%.3f afterVsWriteDeg=%.5f afterVsSolveDeg=%.5f beforeVsLastDeg=%.5f preBindDeg=%.5f localQ=%s helperRelQ=%s hipRelQ=%s worldQ=%s helperOffset=%s solverDirW=%s',
            st.samples,name,item.chain[1].parentName,rotation and rotation[4]*180/math.pi or -1,angle(localQ,cached),angle(localQ,expected),angle(st.pre[name].localQ,st.pre[name].last),
            angle(frame(relative,localQ),{0,0,0,1}),text(localQ),text(relative),text(rel(hips,world)),text(world),text(offset),text(dir))
    end
end
function M.attach(S,u,rig,options)
    local s=HAttach(S,u,rig,options)
    if not s or s.dead~=nil or s.nodeCount~=154 or identity(S,u)==nil or M.test09_axis_profile(rig)==nil then return s end
    local drivers,springs={},{}
    for _,r in ipairs(s.drivers or {}) do
        if r.name=='skirt_front_helper1' or r.name=='skirt_front_helper2' then drivers[#drivers+1]=r end
    end
    for _,name in ipairs(FRONT) do
        for _,item in ipairs(s.sessions or {}) do
            if item.chain[1].name==name and #item.chain==1 and item.tip~=nil then springs[#springs+1]=item end
        end
    end
    if #drivers~=2 or #springs~=7 then return s end
    local nodes={}
    for _,name in ipairs({'hips','spine1','spine2'}) do nodes[name]=node(S,u,name,s.nodeCount);if not nodes[name] then return s end end
    s.test09HipProbe={body=nodes,frontDrivers=drivers,frontSprings=springs,elapsed=0,samples=0}
    s.logger('[physbone][test09-hipsprobe] selected resource=%s weightedFrontHelpers=2 frontSprings=7 intervalSeconds=2 maxSamples=16',HIP_RESOURCE)
    return s
end
function M.update_drivers(s,dt)
    local n=HDrivers(s,dt)
    if s.test09HipProbeCapture then s.test09HipProbe.driverWrites=n end
    return n
end
function M.update_tip(s,dt,budget)
    local st=s and s.test09HipProbe;local capture=false
    if st and not st.disabled and st.samples<16 and type(dt)=='number' and dt==dt and dt>0 then
        if M.test09HipProbeOwner==nil and (s.ownerOrder or 1)==1 then M.test09HipProbeOwner=s end
        if M.test09HipProbeOwner==s then
            st.elapsed=st.elapsed+math.min(dt,.25)
            if st.elapsed>=2 then
                st.elapsed=0
                if safe(s) then st.samples=st.samples+1;local ok=pcall(before,s);capture=ok;s.test09HipProbeCapture=ok;if not ok then st.disabled=true end
                else st.disabled=true;M.test09HipProbeOwner=nil end
            end
        end
    end
    local n=HUpdate(s,dt,budget)
    if capture then
        if safe(s) then
            local ok,err=pcall(after,s)
            if not ok then st.disabled=true;s.logger('[physbone][test09-hipsprobe] read_error=%s',tostring(err)) end
        else st.disabled=true;M.test09HipProbeOwner=nil end
    end
    if st then
        for _,r in ipairs(st.frontDrivers) do r.test09HipProbeSink=nil end
        s.test09HipProbeCapture=nil
    end
    return n
end
function M.release(s)
    if M.test09HipProbeOwner==s then M.test09HipProbeOwner=nil end
    return HRelease(s)
end
