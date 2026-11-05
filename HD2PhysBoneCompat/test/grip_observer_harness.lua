-- Read-only bounded capture with recycled matrix temporaries and rebuilt
-- consumer wrappers. No engine writes or refreshes are allowed by this fixture.
local function copy(x)if type(x)~='table'then return x end;local r={};for k,v in pairs(x)do r[k]=copy(v)end;return r end
local checks=0;local function check(v,s)checks=checks+1;assert(v,s)end
local avatar={alive=true,count=255,names={},x=0,resource='avatar'}
for _,r in ipairs(profile.gripObservation.avatarNodes)do avatar.names[r.name]=r.index+1 end
local a={unit=avatar,label=1,world=1,active=true,stable={body=20,head=20}}
local armor,owners={},{}
for resource,spec in pairs(profile.gripObservation.handModels)do
 local u={alive=true,count=205,names={},x=0,resource=resource,visible=true}
 for _,r in ipairs(spec.nodes)do u.names[r.name]=r.index+1 end
 armor[#armor+1]={unit=u,count=205,resource=resource,world=1,slot='body'};owners[u]=avatar
end
local consumers={}
for _,kind in ipairs({'weapon','weapon_grip','sample_pouch'})do for k=1,7 do
 local u={alive=true,count=12,resource=kind..k,names={},x=.1*k,visible=true}
 for i,name in ipairs({'StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','root','boss','IK_left','IK_right','muzzle','pivot'})do u.names[name]=i end
 if k==7 then u.x=50 end
 consumers[#consumers+1]={unit=u,count=12,resource=u.resource,world=1,kind=kind}
end end
local shared={};local function matrix(u,n)
 local values={2,0,0,0,3,0,0,0,4,u.x+(u.offsetIndex==n and u.offset or 0),0,0}
 for i=1,12 do shared[i]=values[i]end;return shared
end
local S={Unit={},Application={string_to_id32=function(n)return n end},Matrix4x4={to_elements=function(m)return unpack(m)end}}
S.Unit.local_pose=matrix;S.Unit.world_pose=matrix
S.Unit.scene_graph_parent=function()return nil end
S.Unit.num_scene_graph_items=function(u)return u.count end
S.Unit.has_node=function(u,n)return u.names[n]~=nil end
S.Unit.node=function(u,n)return u.names[n]end
S.Unit.set_local_pose=function()error('read-only observer wrote')end
S.World={update_unit=function()error('read-only observer refreshed')end}
local logs={};local function logger(fmt,...)logs[#logs+1]=string.format(fmt,...)end
local q=observer.new(S,profile,logger)
local function capture(f,t,phase)
 q:capture(f,t,phase,{[avatar]=a},armor,owners,consumers,function(u)return u.alive end,function(u)return u.visible end,function(u)return u.resource end)
end
capture(1,0,'pre_apply')
for _,r in ipairs(profile.gripObservation.avatarNodes)do if r.role=='native_right_grip'then avatar.offsetIndex=r.index+1;avatar.offset=.2 end end
capture(1,0,'post_refresh');check(#logs==6,'expected paired actor phase')
local firstLog=table.concat(logs,'\n');local count=#logs
capture(2,.5,'pre_apply');capture(2,.5,'post_refresh');check(#logs==count,'rate limit failed')
-- The main adapter rebuilds consumer rows on every scan; IDs must follow Units.
local fresh={};for i,item in ipairs(consumers)do fresh[i]={unit=item.unit,count=item.count,resource=item.resource,world=item.world,kind=item.kind}end;consumers=fresh
capture(3,1,'pre_apply');capture(3,1,'post_refresh')
local stableLog=table.concat(logs,'\n')
count=#logs;local old=S.Unit.world_pose;S.Unit.world_pose=nil
capture(4,2,'pre_apply');capture(4,2,'post_refresh');S.Unit.world_pose=old
check(table.concat(logs,'\n',count+1):find('matrix_api_missing',1,true),'missing API not rejected')
count=#logs;armor[1].unit.visible=false
capture(5,3,'pre_apply');capture(5,3,'post_refresh');armor[1].unit.visible=true
check(table.concat(logs,'\n',count+1):find('model_changed',1,true),'hidden model not rejected')
count=#logs;local saved=owners;owners={}
capture(6,4,'pre_apply');capture(6,4,'post_refresh');owners=saved;check(#logs==count,'unowned actor captured')
q.samples=240;capture(7,5,'pre_apply');capture(7,5,'post_refresh');check(#logs==count,'sample cap failed')
local off=copy(profile);off.gripObservation.enabled=false;check(observer.new(S,off,logger)==nil,'disabled observer active')
return {checks=checks,firstLog=firstLog,stableLog=stableLog,readOnly=true,recycledTemporaries=true}
