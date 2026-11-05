-- Full affine external-parent model; setters mutate real model offsets, and
-- refreshes compose them. Includes a mutate-then-throw setter and shared refresh.
local function copy(t)if type(t)~='table'then return t end;local r={};for k,v in pairs(t)do r[k]=copy(v)end;return r end
local function identity()return {1,0,0,0,1,0,0,0,1,0,0,0}end
local function compose(a,b)
 local r={};for c=0,2 do for y=1,3 do local v=0;for k=0,2 do v=v+a[k*3+y]*b[c*3+k+1]end;r[c*3+y]=v end end
 for y=1,3 do local v=a[9+y];for k=0,2 do v=v+a[k*3+y]*b[10+k]end;r[9+y]=v end
 return r
end
local checks=0;local function check(v,s)checks=checks+1;assert(v,s)end
local cases={}
local function run(kind)
 local logs,writes,updates={},0,0
 local avatar={alive=true,count=255,names={},worlds={}}
 local parts,items,owners={},{},{}
 local a={unit=avatar,label=1,world=1,active=true,stable={body=20,head=20}}
 local parent={0,2,0,-3,0,0,0,0,4,10,20,30}
 local lp=identity()
 if kind=='scaled_rotated' then lp={0,1.2,0,-.8,0,0,0,0,1.1,.1,.2,.3}end
 for _,resource in ipairs({'d154442f2e33fdee','e0b67b19ba91057b'})do
  local u={alive=true,count=205,resource=resource,visible=true,names={},locals={},worlds={}}
  for _,r in ipairs(profile.sceneRoundtrip.layouts[resource])do
   u.names[r.name]=r.index+1;avatar.names[r.name]=r.avatarIndex+1
   u.locals[r.index+1]=copy(lp);u.worlds[r.index+1]=compose(parent,lp)
   avatar.worlds[r.avatarIndex+1]=compose(parent,lp)
  end
  parts[#parts+1]=u;items[#items+1]={unit=u,world=1,count=205,resource=resource,slot='body'};owners[u]=avatar
 end
 local shared={};local function temporary(m)for i=1,12 do shared[i]=m[i]end;return shared end
 local S={Unit={},World={},Application={string_to_id32=function(n)return n end},
  Matrix4x4={to_elements=function(v)return unpack(v)end,from_elements=function(...)return temporary({...})end},
  Vector3={to_elements=function(v)return unpack(v)end}}
 local U=S.Unit
 U.local_pose=function(u,n)return temporary(u.locals[n])end
 U.world_pose=function(u,n)return temporary(u.worlds[n])end
 U.local_scale=function(u,n)local m=u.locals[n];local s={};for i=1,3 do local k=(i-1)*3;s[i]=math.sqrt(m[k+1]^2+m[k+2]^2+m[k+3]^2)end;return s end
 U.num_scene_graph_items=function(u)return u.count end
 U.has_node=function(u,n)return u.names[n]~=nil end
 U.node=function(u,n)return u.names[n]end
 U.scene_graph_parent=function(u,n)return u.parent end
 U.set_local_pose=function(u,n,m)
  check(u~=avatar and u.alive and u.count==205,'unsafe or Avatar write')
  writes=writes+1;u.locals[n]=copy(m)
  if kind=='throw_after_mutation'and writes==2 then u.locals[n][10]=u.locals[n][10]+.2;error('injected_setter_failure')end
  if kind=='readback_mismatch'and writes==1 then u.locals[n][1]=u.locals[n][1]*.5 end
  if kind=='destroy_during_write'and writes==1 then u.alive=false end
  if kind=='resource_during_write'and writes==1 then u.resource='ffffffffffffffff' end
  if kind=='avatar_side_effect'and writes==1 then local i=next(avatar.worlds);avatar.worlds[i][10]=avatar.worlds[i][10]+.2 end
 end
 S.World.update_unit=function(_,u)
  check(u.alive and u.count==205,'unsafe refresh');updates=updates+1
  for n,m in pairs(u.locals)do u.worlds[n]=compose(parent,m)end
  if kind=='shared_refresh'and updates==2 then
   local n=next(parts[1].worlds);parts[1].worlds[n][10]=parts[1].worlds[n][10]+.2
  end
 end
 if kind=='parent_changed' then parts[1].parent=1 end
 if kind=='hidden' then parts[1].visible=false end
 if kind=='unowned' then owners[parts[1]]=nil;owners[parts[2]]=nil end
 if kind=='ambiguous' then owners={}end
 if kind=='missing_api' then S.Matrix4x4.from_elements=nil end
 if kind=='wrong_index' then local key=next(parts[1].names);parts[1].names[key]=1 end
 local function logger(fmt,...)logs[#logs+1]=string.format(fmt,...)end
 local q=roundtrip.new(S,profile,logger)
 local function tick(frame,time)q:tick(frame,time,{[avatar]=a},items,owners,function(u)return u.alive end,function(u)return u.visible end,function(u)return u.resource end,10)end
 tick(1,0)
 local text=table.concat(logs,'\n');local count=writes
 if kind=='normal'or kind=='scaled_rotated'then
  check(writes==16 and text:find('status=PASS',1,true),'successful roundtrip absent')
  for _,u in ipairs(parts)do for _,m in pairs(u.locals)do for i=1,12 do check(m[i]==lp[i],'local matrix changed')end end end
  tick(2,1);check(writes==count,'rate limit failed')
  tick(3,3);check(writes==count+16,'next trial missing')
 elseif kind=='unowned'or kind=='ambiguous'then check(writes==0 and #logs==0,'unowned probe ran')
 elseif kind=='avatar_side_effect'then
  check(q.disabled and text:find('status=FAIL',1,true)and text:find('rollback=incomplete',1,true),'Avatar side effect incorrectly reported restored')
  tick(2,3);check(writes==count,'failed probe retried')
 elseif kind=='destroy_during_write'or kind=='resource_during_write'then
  check(q.disabled and text:find('rollback=incomplete',1,true),'invalid instance rollback not reported')
  check(writes==1,'write continued on changed instance')
 elseif kind=='throw_after_mutation'or kind=='readback_mismatch'or kind=='shared_refresh'then
  check(q.disabled and text:find('status=FAIL',1,true)and text:find('rollback=verified',1,true),'failure rollback unverified')
  for _,u in ipairs(parts)do for _,m in pairs(u.locals)do for i=1,12 do check(m[i]==lp[i],'rollback left modified local')end end end
  tick(2,3);check(writes==count,'failed probe retried')
 else check(q.disabled and writes==0 and text:find('event=rejected',1,true),'bad precondition wrote model')end
 cases[kind]={writes=writes,updates=updates,disabled=q.disabled,logs=logs}
end
for _,kind in ipairs({'normal','scaled_rotated','throw_after_mutation','readback_mismatch','shared_refresh',
 'destroy_during_write','resource_during_write','avatar_side_effect','parent_changed','hidden','unowned','ambiguous','missing_api','wrong_index'})do run(kind)end
return {checks=checks,cases=cases,externalLocalOffsetsIncluded=true,recycledTemporaries=true}
