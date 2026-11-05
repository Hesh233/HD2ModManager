-- Bounded, read-only motion capture. Nearby equipment is an unverified
-- candidate, never an equipment owner or an input that authorizes a pose write.
local M={VERSION='1.0.0'}
local function finite(x)return type(x)=='number'and x==x and math.abs(x)<1e12 end
local function quote(s)return '"'..tostring(s):gsub('[%z\1-\31\\"]',function(c)
 if c=='\\'then return '\\\\'elseif c=='"'then return '\\"'end;return string.format('\\u%04x',string.byte(c))end)..'"'end
local function json(v)
 if v==nil then return 'null'end
 if type(v)=='boolean'then return tostring(v)end
 if type(v)=='number'then assert(finite(v),'json_nonfinite');return string.format('%.17g',v)end
 if type(v)=='string'then return quote(v)end
 local out={};if #v>0 then for i=1,#v do out[i]=json(v[i])end;return '['..table.concat(out,',')..']'end
 local keys={};for k in pairs(v)do keys[#keys+1]=k end;table.sort(keys)
 for _,k in ipairs(keys)do out[#out+1]=quote(k)..':'..json(v[k])end;return '{'..table.concat(out,',')..'}'
end
function M.new(S,profile,logger)
 local cfg=profile.gripObservation
 if not cfg or cfg.enabled~=true then return nil end
 local U,X=S.Unit,S.Matrix4x4
 local self={samples=0,lastTime=nil,pending=nil,sequence=0,records=0,candidateIds=setmetatable({},{__mode='k'})}
 local function emit(e)if self.records>=20000 then return end;self.records=self.records+1;pcall(logger,'[grip_probe] %s',json(e))end
 local function matrix(unit,index,world)
  local fn=U.local_pose;if world then fn=U.world_pose end
  assert(type(fn)=='function'and X and type(X.to_elements)=='function','matrix_api_missing')
  local a={X.to_elements(fn(unit,index))};assert(#a==12,'matrix_size')
  for _,n in ipairs(a)do assert(finite(n),'matrix_nonfinite')end;return a
 end
 local function named(unit,name,count,expected)
  local h=S.Application.string_to_id32(name)
  if U.has_node(unit,h)~=true then return nil end
  local i=U.node(unit,h)
  assert(type(i)=='number'and i%1==0 and i>=1 and i<=count,'node_range')
  assert(not expected or i==expected,'node_identity');return i
 end
 local function snapshot(unit,index,count)
  local p='unavailable'
  if type(U.scene_graph_parent)=='function'then
   local ok,n=pcall(U.scene_graph_parent,unit,index)
   if ok then p=n==nil and 'nil'or n;if type(p)~='number'and type(p)~='string'then p=tostring(p)end end
  end
  local row={index=index,parent=p,localMatrix=matrix(unit,index,false),worldMatrix=matrix(unit,index,true)}
  if type(p)=='number'and p%1==0 and p>=1 and p<=count and p~=index then row.parentWorld=matrix(unit,p,true)end
  return row
 end
 local function distance(a,b)local d=0;for i=10,12 do d=d+(a[i]-b[i])^2 end;return math.sqrt(d)end
 function self:capture(frame,time,phase,avatars,armor,owners,consumers,alive,visible,resource)
  if phase=='pre_apply'then
   self.pending=nil
   if self.samples>=240 or self.records>=20000 or (self.lastTime and time-self.lastTime<1)then return end
   local selected={}
   for _,item in ipairs(armor)do local owner=owners[item.unit];if owner and avatars[owner]then selected[owner]=avatars[owner]end end
   local list={};for _,a in pairs(selected)do list[#list+1]=a end
   table.sort(list,function(a,b)return a.label>b.label end)
   while #list>4 do table.remove(list)end
   if #list==0 then return end
   self.samples=self.samples+1;self.lastTime=time;self.pending={frame=frame,actors=list}
  elseif phase~='post_refresh'or not self.pending or self.pending.frame~=frame then return end
  emit({event='begin',revision=profile.revision,sample=self.samples,frame=frame,time=time,phase=phase,readOnly=true,indexBase=1})
  local count,errors=0,0
  for _,a in ipairs(self.pending.actors)do
   local ok,result=pcall(function()
    assert(alive(a.unit)and U.num_scene_graph_items(a.unit)==profile.expectedAvatarNodes,'avatar_changed')
    local data={event='actor',sample=self.samples,frame=frame,time=time,phase=phase,avatar=a.label,
     active=a.active==true,bodyStable=a.stable.body,headStable=a.stable.head,nodes={},models={},candidates={}}
    for _,row in ipairs(cfg.avatarNodes)do
     local i=assert(named(a.unit,row.name,profile.expectedAvatarNodes,row.index+1),'avatar_name_missing:'..row.name)
     data.nodes[row.role]=snapshot(a.unit,i,profile.expectedAvatarNodes)
    end
    for _,item in ipairs(armor)do
     local spec=cfg.handModels[item.resource]
     if spec and owners[item.unit]==a.unit then
      assert(alive(item.unit)and U.num_scene_graph_items(item.unit)==item.count and resource(item.unit)==item.resource and visible(item.unit)~=false,'model_changed')
      local out={resource=item.resource,side=spec.side,nodes={}}
      for _,row in ipairs(spec.nodes)do
       local i=assert(named(item.unit,row.name,item.count,row.index+1),'model_name_missing')
       out.nodes[row.role]=snapshot(item.unit,i,item.count)
      end
      data.models[#data.models+1]=out
     end
    end
    -- Bounded proximity selection ONLY reduces telemetry volume. It does not
    -- infer owner, even when a recovered external-parent matrix coincides.
    local candidates={}
    local hand=data.nodes.native_right_hand.worldMatrix
    for _,item in ipairs(consumers)do
     if (item.kind=='weapon'or item.kind=='weapon_grip'or item.kind=='sample_pouch')and item.world==a.world then
      local safe,candidate=pcall(function()
       assert(alive(item.unit)and U.num_scene_graph_items(item.unit)==item.count and resource(item.unit)==item.resource and visible(item.unit)~=false,'candidate_changed')
       local anchor=nil
       for _,name in ipairs({'IK_right','IK_left','boss','skeleton','StingrayEntityRoot'})do
        anchor=named(item.unit,name,item.count);if anchor then break end
       end
       if not anchor then return nil end
       local d=distance(matrix(item.unit,anchor,true),hand)
       if d>3 then return nil end
       return {item=item,distance=d}
      end)
      if safe and candidate then candidates[#candidates+1]=candidate end
     end
    end
    table.sort(candidates,function(a,b)return a.distance<b.distance end)
    local kinds={};local candidateErrors=0
    for _,c in ipairs(candidates)do
     local item=c.item;local quota=item.kind=='weapon'and 3 or (item.kind=='weapon_grip'and 2 or 1)
     if (kinds[item.kind]or 0)<quota then
      kinds[item.kind]=(kinds[item.kind]or 0)+1
      local safe,entry=pcall(function()
       local tag=self.candidateIds[item.unit]
       if not tag or tag.resource~=item.resource or tag.count~=item.count or tag.world~=item.world then
        self.sequence=self.sequence+1;tag={id=self.sequence,resource=item.resource,count=item.count,world=item.world};self.candidateIds[item.unit]=tag
       end
       local entry={id=tag.id,resource=item.resource,kind=item.kind,count=item.count,nearHandDistance=c.distance,owner='unverified',nodes={}}
       for _,name in ipairs({'StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','root','boss','IK_left','IK_right','muzzle','pivot'})do
        local i=named(item.unit,name,item.count)
        if i then entry.nodes[name]=snapshot(item.unit,i,item.count)end
       end
       assert(alive(item.unit)and U.num_scene_graph_items(item.unit)==item.count and resource(item.unit)==item.resource,'candidate_changed_during_capture')
       return entry
      end)
      if safe then data.candidates[#data.candidates+1]=entry else candidateErrors=candidateErrors+1 end
     end
    end
    data.candidateErrors=candidateErrors
    assert(alive(a.unit)and U.num_scene_graph_items(a.unit)==profile.expectedAvatarNodes,'avatar_changed_during_capture')
    return data
   end)
   if ok then emit(result);count=count+1
   else emit({event='unavailable',sample=self.samples,frame=frame,phase=phase,avatar=a.label,reason=tostring(result):sub(1,240)});errors=errors+1 end
  end
  emit({event='end',sample=self.samples,frame=frame,phase=phase,actors=count,errors=errors})
  if phase=='post_refresh'then self.pending=nil end
 end
 return self
end
return M
