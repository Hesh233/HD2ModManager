-- Standalone observer test: all mutations throw, matrices use recycled engine
-- temporaries, and world includes the model's local offset plus non-unit scale.
local function copy(v)if type(v)~='table'then return v end;local r={};for k,x in pairs(v)do r[k]=copy(x)end;return r end
local function mat(sx,sy,sz,x,y,z)return {sx,0,0,0,sy,0,0,0,sz,x,y,z}end
local checks=0;local function check(v,s)checks=checks+1;assert(v,s)end
local resource='d154442f2e33fdee';local rows=profile.sceneObservation.layouts[resource]
local model={alive=true,count=205,names={},visible=true,resource=resource}
local avatar={alive=true,count=255,names={}}
for _,row in ipairs(rows)do
 model.names[row.name]=row.index+1;model.names[row.parentName]=row.parentIndex+1
 avatar.names[row.name]=row.avatarIndex+1;avatar.names[row.parentName]=row.avatarParentIndex+1
end
local locals,worlds,parents={},{},{}
local al,aw,ap={},{},{}
for i=1,205 do locals[i]=mat(1,1,1,0,0,0);worlds[i]=mat(2,3,4,10,20,30);parents[i]=0 end
for i=1,255 do al[i]=mat(1,1,1,.1,0,0);aw[i]=mat(2,3,4,10,20,30);ap[i]=0 end
local shared={};local function temporary(v)for i=1,12 do shared[i]=v[i]end;return shared end
local S={Unit={},Application={string_to_id32=function(x)return x end},Matrix4x4={to_elements=function(v)return unpack(v)end},Vector3={to_elements=function(v)return unpack(v)end}}
local U=S.Unit
U.set_local_pose=function()error('observer attempted write')end
U.local_pose=function(u,n)return temporary((u==model and locals or al)[n])end
U.world_pose=function(u,n)return temporary((u==model and worlds or aw)[n])end
U.scene_graph_parent=function(u,n)return (u==model and parents or ap)[n]end
U.local_scale=function(u,n)local v=(u==model and locals or al)[n];return {v[1],v[5],v[9]}end
U.num_scene_graph_items=function(u)return u.count end
U.has_node=function(u,name)return u.names[name]~=nil end
U.node=function(u,name)return u.names[name]end
local item={unit=model,resource=resource,count=205,slot='body',world=1}
local a={unit=avatar,label=1,active=true,world=1}
local avatars={[avatar]=a};local armor={item};local owners={[model]=avatar}
local function alive(u)return u.alive end
local function visible(u)return u.visible end
local function res(u)return u.resource end
local logs={};local function logger(fmt,...)logs[#logs+1]=string.format(fmt,...)end
local function probe(p)return observer.new(S,p or profile,logger)end
local function capture(o,f,t,phase)o:capture(f,t,phase,avatars,armor,owners,alive,visible,res)end
local o=probe()
-- Same-name external attachment with a scaled local offset: parent world is
-- diag(2,3,4), translation(10,20,30); local is diag(1.2,.8,1), translation(.1,.2,.3).
for _,r in ipairs(rows)do
 locals[r.index+1]=mat(1.2,.8,1,.1,.2,.3)
 worlds[r.index+1]=mat(2.4,2.4,4,10.2,20.6,31.2)
end
capture(o,1,0,'pre_apply');capture(o,1,0,'post_refresh')
check(#logs==20,'two complete 8-node phases expected')
local externalLog=table.concat(logs,'\n')
local count=#logs;capture(o,2,1,'pre_apply');capture(o,2,1,'post_refresh');check(#logs==count,'rate limit failed')
for _,r in ipairs(rows)do parents[r.index+1]=-1 end
capture(o,3,3,'pre_apply');capture(o,3,3,'post_refresh')
for _,r in ipairs(rows)do parents[r.index+1]=nil end
capture(o,4,6,'pre_apply');capture(o,4,6,'post_refresh')
-- Internal parent snapshot uses its real runtime index, independently of file topology.
for _,r in ipairs(rows)do parents[r.index+1]=1 end
capture(o,5,9,'pre_apply');capture(o,5,9,'post_refresh')
local variants=table.concat(logs,'\n')
local function failure(change,undo,expected)
 change();local start=#logs;local q=probe();capture(q,1,0,'pre_apply');capture(q,1,0,'post_refresh')
 local text=table.concat(logs,'\n',start+1);check(text:find(expected,1,true)~=nil,'missing rejection '..expected);undo()
end
local oldWorld=U.world_pose
failure(function()U.world_pose=nil end,function()U.world_pose=oldWorld end,'matrix_api_missing')
local name=rows[1].name;local index=model.names[name]
failure(function()model.names[name]=index+1 end,function()model.names[name]=index end,'node_identity:')
failure(function()model.visible=false end,function()model.visible=true end,'model_changed_or_hidden')
failure(function()model.alive=false end,function()model.alive=true end,'unit_unavailable')
failure(function()model.count=204 end,function()model.count=205 end,'node_count_changed')
failure(function()model.resource='ffffffffffffffff' end,function()model.resource=resource end,'model_changed_or_hidden')
local oldValue=locals[index][1]
failure(function()locals[index][1]=0/0 end,function()locals[index][1]=oldValue end,'matrix_nonfinite')
local oldParent=U.scene_graph_parent;U.scene_graph_parent=nil
local start=#logs;local missing=probe();capture(missing,1,0,'pre_apply');capture(missing,1,0,'post_refresh')
check(#logs-start==20 and logs[start+2]:find('api_missing',1,true),'missing parent API should preserve raw matrices')
U.scene_graph_parent=oldParent
local oldScale=U.local_scale;U.local_scale=nil
start=#logs;local noScale=probe();capture(noScale,1,0,'pre_apply');capture(noScale,1,0,'post_refresh')
check(logs[start+2]:find('"localScale":"unavailable"',1,true),'scale API fallback lost');U.local_scale=oldScale
start=#logs;owners[model]=nil;local unowned=probe();capture(unowned,1,0,'pre_apply');capture(unowned,1,0,'post_refresh')
check(#logs==start,'unowned model observed');owners[model]=avatar
local disabled=copy(profile);disabled.sceneObservation.enabled=false;check(probe(disabled)==nil,'disabled observer active')
local capped=copy(profile);capped.sceneObservation.maxSamples=1
local one=probe(capped);capture(one,1,0,'pre_apply');capture(one,1,0,'post_refresh');start=#logs
capture(one,2,3,'pre_apply');capture(one,2,3,'post_refresh');check(#logs==start and logs[start]:find('complete',1,true),'sample cap failed')
return {checks=checks,externalLog=externalLog,variantsLog=variants,readOnly=true,recycledTemporaries=true,scaleIncluded=true}
