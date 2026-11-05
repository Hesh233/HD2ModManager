-- Affine, real-layout fixture. Every engine matrix read reuses one scratch
-- buffer; setters must copy. Independent world composition checks all nodes.
local function copy(v)if type(v)~='table'then return v end;local r={};for k,x in pairs(v)do r[k]=copy(x)end;return r end
local checks=0
local function check(v,m)checks=checks+1;assert(v,m)end
local function near(a,b,e)for i=1,#a do if math.abs(a[i]-b[i])>(e or 1e-8)then return false end end;return true end
local function compose(a,b)
 local r={}
 for col=0,2 do for row=1,3 do r[col*3+row]=a[row]*b[col*3+1]+a[3+row]*b[col*3+2]+a[6+row]*b[col*3+3]end end
 for row=1,3 do r[9+row]=a[row]*b[10]+a[3+row]*b[11]+a[6+row]*b[12]+a[9+row]end;return r
end
local logs={};local scratch={};local writes=0;local failAt=nil
local avatar={alive=true,count=#fixture.hashes,locals=copy(fixture.matrices),hashes=fixture.hashes,parents=copy(fixture.parents),names={}}
for i,h in ipairs(avatar.hashes)do avatar.names[h]=i end
local actor={unit=avatar,world=1,label=1}
local function world(u,n)
 if u.owner then return compose(world(u.owner,u.anchor),u.locals[n])end
 local m=copy(u.locals[n]);local parent=u.parents[n];if parent>0 then return compose(world(u,parent),m)end;return m
end
local function reused(m)for i=1,12 do scratch[i]=m[i]end;return scratch end
local S={Unit={},Matrix4x4={},World={}}
local U=S.Unit;local X=S.Matrix4x4
U.alive=function(u)return u.alive end
U.num_scene_graph_items=function(u)return u.count end
U.has_node=function(u,h)return u.names and u.names[h]~=nil end
U.node=function(u,h)return u.names[h]end
U.scene_graph_parent=function(u,n)return u.parents[n]end
U.local_pose=function(u,n)return reused(u.locals[n])end
U.world_pose=function(u,n)return reused(world(u,n))end
X.to_elements=function(m)return unpack(m)end
X.from_elements=function(...)return reused({...})end
U.set_local_pose=function(u,n,m)
 check(u==avatar,'probe wrote an external unit');writes=writes+1;u.locals[n]=copy(m)
 if failAt==writes then failAt=nil;error('injected mutation failure')end
end
S.World.update_unit=function(_,u)check(u==avatar,'probe refreshed external unit')end
local function make(p)return probe.new(S,p or profile,function(fmt,...)logs[#logs+1]=string.format(fmt,...)end)end
local base=copy(avatar.locals)
local function restoreFixture()avatar.locals=copy(base);avatar.alive=true;avatar.count=#fixture.hashes;avatar.parents=copy(fixture.parents);writes=0;failAt=nil end
local function allWorld()local r={};for i=1,avatar.count do r[i]=world(avatar,i)end;return r end
local selected={};for _,r in ipairs(profile.attachmentProbe.nodes)do selected[r.index+1]=true end
local function checkShift(before,up)
 for i=1,avatar.count do
  local expected=copy(before[i]);if up and selected[i]then expected[12]=expected[12]+.6 end
  check(near(world(avatar,i),expected,1e-7),'wrong affected world node '..i)
 end
end
local p=make();local before=allWorld()
check(not p:apply(actor,true,0,1,{}),'baseline writes')
check(writes==0,'baseline wrote')
check(p:apply(actor,true,4.1,2,{}),'UP did not apply');checkShift(before,true)
local roots=0;for _,r in ipairs(profile.attachmentProbe.nodes)do if not selected[r.parentIndex+1]then roots=roots+1 end end
check(writes==roots,'nested candidate was written twice')
p:restore_all();checkShift(before,false)
check(p:apply(actor,true,4.2,3,{}),'repeat did not apply');checkShift(before,true)
p:restore_all();checkShift(before,false)
check(not p:apply(actor,true,8.1,4,{}),'baseline cycle wrote')
-- New animation values replace the probe rather than accumulating it.
p:apply(actor,true,12.1,5,{})
local first=profile.attachmentProbe.nodes[1].index+1
avatar.locals[first]=copy(base[first]);avatar.locals[first][10]=avatar.locals[first][10]+.031
local fresh=copy(avatar.locals[first]);p:restore_all()
check(near(avatar.locals[first],fresh),'fresh animation overwritten')
before=allWorld();p:apply(actor,true,12.2,6,{});checkShift(before,true)
p:restore_all();checkShift(before,false)
check(not p:apply(actor,false,12.3,7,{}),'unselected body wrote')
check(not p:apply(actor,true,12.4,8,{}),'switch-back failed to reset baseline')
-- Nonuniform rotated/scaled ancestor: world delta still exactly vertical.
restoreFixture();avatar.locals[1]={0,2,0,-3,0,0,0,0,4,10,20,30}
before=allWorld();p=make();p:apply(actor,true,0,1,{});p:apply(actor,true,4.1,2,{})
check(not p.disabled,'affine ancestor rejected');checkShift(before,true)
for i=1,avatar.count do for k=1,9 do check(avatar.locals[i][k]==(i==1 and ({0,2,0,-3,0,0,0,0,4})[k]or base[i][k]),'linear component changed')end end
p:restore_all();checkShift(before,false)
-- The observation is read-only even when a linked weapon follows the probe.
restoreFixture();p=make();p:apply(actor,true,0,1,{})
local ident={1,0,0,0,1,0,0,0,1,0,0,0}
local gun={alive=true,count=3,owner=avatar,anchor=profile.attachmentProbe.nodes[1].index+1,locals={ident,ident,ident}}
local consumer={unit=gun,world=1,count=3,resource='fixture_weapon',kind='weapon',markers={1}}
p:apply(actor,true,4.1,2,{consumer});p:after_refresh();p:restore_all()
local consumerSeen=false
for _,line in ipairs(logs)do if line:find('event=consumer',1,true)and line:find('dz=0.600000',1,true)and line:find('owner=unverified',1,true)then consumerSeen=true end end
check(consumerSeen,'linked consumer response missing')
-- A setter throwing AFTER mutation must roll back all touched nodes.
restoreFixture();before=allWorld();p=make();p:apply(actor,true,0,1,{});failAt=math.min(2,roots)
check(not p:apply(actor,true,4.1,2,{}),'fault accepted');check(p.disabled,'fault did not disable');checkShift(before,false)
check(next(p.pending)==nil,'verified rollback retained pending')
-- Invalid topology, missing API, dead/rebuilt object never gets a guessed write.
for _,kind in ipairs({'parent','api','dead','count','hash'})do
 restoreFixture();p=make();p:apply(actor,true,0,1,{})
 local savedParent=avatar.parents[first];local savedHash=avatar.names[profile.attachmentProbe.nodes[1].hash];local saved=X.from_elements
 if kind=='parent'then avatar.parents[first]=1 elseif kind=='api'then X.from_elements=nil
 elseif kind=='dead'then avatar.alive=false elseif kind=='count'then avatar.count=avatar.count-1
 else avatar.names[profile.attachmentProbe.nodes[1].hash]=nil end
 check(not p:apply(actor,true,4.1,2,{}),'invalid case applied '..kind);check(writes==0,'invalid case wrote '..kind)
 avatar.parents[first]=savedParent;avatar.names[profile.attachmentProbe.nodes[1].hash]=savedHash;X.from_elements=saved
end
restoreFixture();p=make();p:apply(actor,true,0,1,{});p:apply(actor,true,4.1,2,{})
local count=writes;avatar.count=avatar.count-1;p:restore_all();check(writes==count,'restore wrote rebuilt object')
local disabled=copy(profile);disabled.attachmentProbe.enabled=false;check(make(disabled)==nil,'disabled probe instantiated')
return {checks=checks,logs=logs,roots=roots,caseCount=12,affinePreserved=true,recycledMatrices=true,consumerObservationReadOnly=true}
