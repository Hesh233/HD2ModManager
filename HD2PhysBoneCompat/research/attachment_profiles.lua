-- Offline prototype. No engine calls and not loaded by the production runtime.
-- Indices in profiles/snapshots are zero-based Unit TransformInfo indices.
local M = {}
local function mul(a,b)
    local x,y,z,w=unpack(a);local X,Y,Z,W=unpack(b)
    return {w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z}
end
local function inverse(q)
    local n=0;for i=1,4 do n=n+q[i]*q[i] end
    assert(n>1e-12,'invalid quaternion')
    return {-q[1]/n,-q[2]/n,-q[3]/n,q[4]/n}
end
local function rotate(q,v)
    local p=mul(mul(q,{v[1],v[2],v[3],0}),inverse(q));return {p[1],p[2],p[3]}
end
local function compose(a,b)
    local scaled={};for i=1,3 do scaled[i]=a.scale[i]*b.position[i] end
    local p=rotate(a.rotation,scaled);local s={}
    for i=1,3 do p[i]=p[i]+a.position[i];s[i]=a.scale[i]*b.scale[i] end
    return {position=p,rotation=mul(a.rotation,b.rotation),scale=s}
end
local function relative(a,b)
    local p={};for i=1,3 do p[i]=b.position[i]-a.position[i] end
    p=rotate(inverse(a.rotation),p);local s={}
    for i=1,3 do assert(math.abs(a.scale[i])>1e-12,'zero scale');p[i]=p[i]/a.scale[i];s[i]=b.scale[i]/a.scale[i] end
    return {position=p,rotation=mul(inverse(a.rotation),b.rotation),scale=s}
end

-- A future integration must obtain this evidence from actual equipment ownership.
-- A mock evidence record passing here does not validate any game-side API.
function M.select(profile,snapshot,evidence,slot)
    if not evidence or evidence.verified~=true or evidence.method~='equipment-owner'
        or evidence.avatar~=snapshot.avatar or evidence.generation~=snapshot.generation
        or evidence.frame~=snapshot.frame or evidence.rigIdentity~=profile.boneNamespace or evidence.slot~=slot
        or snapshot.phase~='post-animation-pre-attachments' then return 'native' end
    for _,id in ipairs(profile.targets[slot] or {}) do
        if id==evidence.armorResource then return 'vpk' end
    end
    return 'native'
end

-- Returns a complete pair of poses for every selected node. The caller would
-- need a verified game adapter to translate world poses to locals and write them.
-- Each invocation requires a fresh original animation snapshot; no cached bind.
function M.evaluate(profile,snapshot,evidence)
    evidence=evidence or {}
    local selected={body=M.select(profile,snapshot,evidence.body,'body'),head=M.select(profile,snapshot,evidence.head,'head')}
    local rows={}
    for _,entry in ipairs(profile.vpk) do
        local original=assert(snapshot.original[entry.index],'missing original node')
        local target=original
        if selected[entry.ownerSlot]=='vpk' and entry.policy=='source-anchor-relative-animation' then
            local driver=assert(snapshot.original[entry.driverAnchorIndex],'missing driver anchor')
            local source=assert(snapshot.source[entry.sourceAnchorIndex],'missing source anchor')
            local offset=relative(driver,original)
            for i=1,3 do offset.position[i]=offset.position[i]*entry.translationScale end
            local correction={position={0,0,0},rotation=entry.axisCorrection,scale={1,1,1}}
            target=compose(compose(source,correction),offset)
        end
        rows[#rows+1]={index=entry.index,standardHash=entry.standardHash,
            virtualName=entry.virtualName,original=original,target=target}
    end
    return rows,selected
end
return M
