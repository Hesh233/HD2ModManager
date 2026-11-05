-- Test contract: opaque factory tokens are distinct from serialized numbers.
-- This models identity provenance, without claiming the game's exact Lua type.
local byName,byToken={},{}
local idFrame=0
local stats={factoryCalls=0,lookupCalls=0,invalidArgumentCalls=0,expiredArgumentCalls=0}
function stats.advanceFrame()idFrame=idFrame+1;byName={}end
local function decode(id)
 stats.lookupCalls=stats.lookupCalls+1
 if byToken[id]==nil then
  stats.invalidArgumentCalls=stats.invalidArgumentCalls+1
  error('engine_name_id_required: numeric hashes and unregistered tokens are invalid')
 end
 if byToken[id].frame~=idFrame then
  stats.expiredArgumentCalls=stats.expiredArgumentCalls+1
  error('expired_id32: token belongs to an earlier frame')
 end
 return byToken[id].hash
end
S.Application=S.Application or {}
S.Application.string_to_id32=function(name)
 assert(type(name)=='string'and #name>0 and not name:match('^hash_'),'real_name_required')
 stats.factoryCalls=stats.factoryCalls+1
 if not byName[name]then local token={};byName[name]=token;byToken[token]={hash=hash_name(name),frame=idFrame}end
 return byName[name]
end
local oldHas,oldNode=S.Unit.has_node,S.Unit.node
-- Decode has_node and node independently: never call the wrapped method with a hash.
S.Unit.has_node=function(u,id)return oldHas(u,decode(id))end
S.Unit.node=function(u,id)
 local h=decode(id)
 if not oldHas(u,h)then return 1 end
 return u.names[h]
end
local strictIdStats=stats
