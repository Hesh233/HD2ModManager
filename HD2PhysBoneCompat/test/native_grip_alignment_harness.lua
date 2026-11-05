-- Actual serialized topology, independently composed affine worlds, recycled
-- engine temporaries, and an output allowlist enforced by the fake engine.
local function copy(v)if type(v)~='table'then return v end;local r={};for k,x in pairs(v)do r[k]=copy(x)end;return r end
local checks=0
local function check(v,m)checks=checks+1;assert(v,m)end
local function near(a,b,e)for i=1,#a do if math.abs(a[i]-b[i])>(e or 1e-7)then return false end end;return true end
local function compose(a,b)
 local r={}
 for c=0,2 do for j=1,3 do r[c*3+j]=a[j]*b[c*3+1]+a[3+j]*b[c*3+2]+a[6+j]*b[c*3+3]end end
 for j=1,3 do r[9+j]=a[j]*b[10]+a[3+j]*b[11]+a[6+j]*b[12]+a[9+j]end;return r
end
local cfg=profile.nativeGripAlignment
local allowed={};for _,p in ipairs(cfg.pairs)do allowed[p.target.index+1]=true end
local avatar={alive=true,count=#fixture.hashes,locals=copy(fixture.matrices),parents=copy(fixture.parents),names={}}
for i,h in ipairs(fixture.hashes)do avatar.names[h]=i end
local actor={unit=avatar,world=1,label=1}
local function world(u,n)local p=u.parents[n];return p>0 and compose(world(u,p),u.locals[n])or copy(u.locals[n])end
local scratch={};local writes=0;local failAt;local logs={}
local function recycled(v)for k in pairs(scratch)do scratch[k]=nil end;for i,x in ipairs(v)do scratch[i]=x end;return scratch end
local S={Unit={},World={},Matrix4x4={},Quaternion={}}
local U,X=S.Unit,S.Matrix4x4
U.alive=function(u)return u.alive end
U.num_scene_graph_items=function(u)return u.count end
U.has_node=function(u,h)return u.names[h]~=nil end
U.node=function(u,h)return u.names[h]end
U.scene_graph_parent=function(u,n)return u.parents[n]end
U.world_pose=function(u,n)return recycled(world(u,n))end
U.local_pose=function(u,n)return recycled(u.locals[n])end
U.world_rotation=function(u,n)return recycled(quat_from_matrix(world(u,n)))end
X.to_elements=function(m)return unpack(m)end
X.from_elements=function(...)return recycled({...})end
S.Quaternion.to_elements=function(q)return unpack(q)end
U.set_local_pose=function(u,n,m)
 check(u==avatar and allowed[n],'wrote Source/other Avatar/model/aim child')
 writes=writes+1;u.locals[n]=copy(m)
 if writes==failAt then failAt=nil;error('injected post-mutation fault')end
end
S.World.update_unit=function(_,u)check(u==avatar,'updated wrong Avatar')end
-- STRICT_ID_FIXTURE
local base=copy(avatar.locals)
local function reset()
 avatar.locals=copy(base);avatar.parents=copy(fixture.parents);avatar.alive=true;avatar.count=#fixture.hashes
 for i,h in ipairs(fixture.hashes)do avatar.names[h]=i end
 actor.layoutInvalid=nil;writes=0;failAt=nil
end
local function make(p)return module.new(S,p or profile,function(fmt,...)logs[#logs+1]=string.format(fmt,...)end)end
local function snapshot()local s={};for i=1,avatar.count do s[i]=world(avatar,i)end;return s end
local function checkAll(before)
 for i=1,avatar.count do check(near(world(avatar,i),before[i]),'restoration world mismatch '..i)end
end
local function length(m,c)local n=0;for j=1,3 do n=n+m[c*3+j]^2 end;return math.sqrt(n)end
local function aligned(before,localsBefore)
 local affected={};for n in pairs(allowed)do affected[n]=true end
 for i=1,avatar.count do local p=avatar.parents[i];while p>0 do if allowed[p]then affected[i]=true end;p=avatar.parents[p]end end
 for i=1,avatar.count do
  if not allowed[i]then check(near(avatar.locals[i],localsBefore[i]),'protected local changed '..i)end
  if not affected[i]then check(near(world(avatar,i),before[i]),'protected world changed '..i)end
 end
 for _,p in ipairs(cfg.pairs)do
  local dst,src=world(avatar,p.target.index+1),world(avatar,p.source.index+1)
  check(near({dst[10],dst[11],dst[12]},{src[10],src[11],src[12]}),'wrong target position')
  if p.rotationMode=='native-world'then
   for i=1,9 do check(math.abs(dst[i]-before[p.target.index+1][i])<1e-7,'native aiming basis changed')end
  else
   local a,b=quat_from_matrix(dst),quat_from_matrix(src);local d=0
   for i=1,4 do d=d+a[i]*b[i]end;check(1-math.abs(d)<1e-7,'wrong world orientation')
  end
  for c=0,2 do check(math.abs(length(dst,c)-length(before[p.target.index+1],c))<1e-7,'weapon world scale changed')end
 end
end
local instance=make();local before=snapshot();local localsBefore=copy(avatar.locals)
strictIdStats.advanceFrame();check(instance:apply(actor,true,1),'initial alignment failed');aligned(before,localsBefore)
check(writes==#cfg.pairs,'wrong number of writes');instance:after_refresh();instance:restore_all(2);checkAll(before)
-- Native and Source parents translate and rotate independently on every frame.
for frame=2,62 do
 strictIdStats.advanceFrame();instance:restore_all(frame)
 for i,p in ipairs(cfg.pairs)do
  local a=frame*.017*i;local b=-frame*.023*i
  avatar.locals[p.target.parentIndex+1]=compose(base[p.target.parentIndex+1],
   {math.cos(a),math.sin(a),0,-math.sin(a),math.cos(a),0,0,0,1,math.cos(frame*.3)*.12,0,0})
  avatar.locals[p.source.parentIndex+1]=compose(base[p.source.parentIndex+1],
   {1,0,0,0,math.cos(b),math.sin(b),0,-math.sin(b),math.cos(b),0,math.sin(frame*.2)*.035,0})
 end
 before=snapshot();localsBefore=copy(avatar.locals)
 check(instance:apply(actor,true,frame),'continuous alignment failed');aligned(before,localsBefore);instance:after_refresh()
end
instance:restore_all(63);checkAll(before)
-- Distinct rotated, nonuniform native and Source ancestors exercise affine
-- inverse math and preservation of native equipment size.
reset();avatar.locals[72]={0,2,0,-3,0,0,0,0,4,.1,.2,.3}
avatar.locals[48]={1.5,0,0,0,.5,0,0,0,2,.03,.04,.05}
avatar.locals[1]={0,1.2,0,-.8,0,0,0,0,1.1,10,20,30}
before=snapshot();localsBefore=copy(avatar.locals);instance=make()
strictIdStats.advanceFrame();check(instance:apply(actor,true,1),'affine input failed');aligned(before,localsBefore)
instance:after_refresh();check(not instance.disabled,'affine post refresh failed');instance:restore_all(2);checkAll(before)
-- Fresh engine animation wins over the cached restoration record.
reset();instance=make();instance:apply(actor,true,1)
local first=cfg.pairs[1].target.index+1
avatar.locals[first]=copy(base[first]);avatar.locals[first][10]=avatar.locals[first][10]+.091
local fresh=copy(avatar.locals[first]);strictIdStats.advanceFrame();instance:restore_all(2)
check(near(avatar.locals[first],fresh),'fresh animation overwritten')
before=snapshot();localsBefore=copy(avatar.locals)
check(instance:apply(actor,true,2),'new animation alignment failed');aligned(before,localsBefore)
instance:restore_all(3);checkAll(before)
-- No target setter may escape its transaction, including throws after write.
for fail=1,#cfg.pairs do
 reset();before=snapshot();instance=make();failAt=fail;strictIdStats.advanceFrame()
 check(not instance:apply(actor,true,1),'fault accepted');check(instance.disabled,'fault did not disable')
 check(next(instance.pending)==nil,'successful rollback kept pending');checkAll(before)
end
for _,kind in ipairs({'parent','source_name','target_name','count','dead','singular','api'})do
 reset();instance=make();local saved=X.from_elements
 if kind=='parent'then avatar.parents[first]=1
 elseif kind=='source_name'then avatar.names[cfg.pairs[1].source.hash]=nil
 elseif kind=='target_name'then avatar.names[cfg.pairs[1].target.hash]=nil
 elseif kind=='count'then avatar.count=avatar.count-1
 elseif kind=='dead'then avatar.alive=false
 elseif kind=='singular'then avatar.locals[cfg.pairs[1].target.parentIndex+1]={0,0,0,0,0,0,0,0,0,0,0,0}
 else X.from_elements=nil end
 strictIdStats.advanceFrame();check(not instance:apply(actor,true,1),'invalid input accepted '..kind)
 check(writes==0,'invalid input wrote '..kind);X.from_elements=saved
end
-- Later refresh can overwrite a target. Diagnose it, then preserve the newer
-- engine value on release instead of calling it the source of old flicker.
reset();instance=make();instance:apply(actor,true,1)
avatar.locals[first][10]=avatar.locals[first][10]+.1;fresh=copy(avatar.locals[first])
instance:after_refresh();check(instance.disabled,'post-refresh overwrite undetected')
instance:restore_all(2);check(near(avatar.locals[first],fresh),'post-refresh engine value overwritten')
-- Engine changes to a Source input during update must be detected. Roll back
-- only our native outputs; never restore a Source bone to a stale snapshot.
reset();instance=make();local update=S.World.update_unit;local injected=false
S.World.update_unit=function(w,u)
 update(w,u)
 if not injected then injected=true;u.locals[155][10]=u.locals[155][10]+.02 end
end
check(not instance:apply(actor,true,1)and instance.disabled,'Source update conflict undetected')
check(math.abs(avatar.locals[155][10]-base[155][10]-.02)<1e-8,'engine Source update was overwritten')
for n in pairs(allowed)do check(near(avatar.locals[n],base[n]),'Source conflict native rollback failed')end
S.World.update_unit=update
reset();instance=make();instance:apply(actor,true,1);local count=writes;avatar.count=avatar.count-1
instance:restore_all(2);check(writes==count,'restore touched rebuilt actor')
reset();instance=make();strictIdStats.advanceFrame();check(not instance:apply(actor,false,1)and writes==0,'unequipped write')
for _,key in ipairs({'armSync','armGripSync'})do
 local p=copy(profile);p[key]=true;instance=make(p)
 check(instance.disabled and not instance:apply(actor,true,1),'reverse solver allowed '..key)
end
local p=copy(profile);p.attachmentProbe.enabled=true;check(make(p).disabled,'probe conflict allowed')
p=copy(profile);p.nativeGripAlignment.enabled=false;check(make(p)==nil,'default path created alignment')
check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'invalid/expired ID used')
return {checks=checks,logs=logs,continuousFrames=61,sourceAndOtherNodesUnchanged=true,
 affineParents=true,nativeEquipmentScalePreserved=true,postMutationFaultCases=#cfg.pairs,
 nativeWorldBasisPreserved=cfg.pairs[1].rotationMode=='native-world',independentAnimatedRotations=true,
 invalidInputCases=7,lateOverwriteDetected=true,sourceUpdateConflictDetected=true,expiredIdCalls=strictIdStats.expiredArgumentCalls}
