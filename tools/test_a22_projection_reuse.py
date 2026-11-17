"""Differential pure-Lua projection tests for A22. No fabricated game FPS or engine timing.
A22 carries the same private projection reuse as A21 plus non-writing health sampling;
this test isolates projection semantics/storage lifetime only."""
from pathlib import Path
import hashlib, importlib, json, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'
TEST=r'''
local function project_of(module)
  for i=1,100 do
    local name,value=debug.getupvalue(module.single_policy.tick,i)
    if name=='project' then return value end
    if name==nil then break end
  end
  error('project upvalue not found')
end
local baseline,optimized=project_of(B),project_of(A)
local function runtime()
  return {options={singleMainline=true},logger=function()end,frame=1,dt=.01,
    world={},cache={},avatars={},sessions={},liveUnits={}}
end
local rb,ra=runtime(),runtime()
local units,avatars,sessions={},{},{}
for i=1,8 do
  units[i]={id=i}
  avatars[i]={unit=units[i],nodes={root=i},tag='avatar'..i,extra=i}
  sessions[i]={id=i,unit={id=100+i},singleMainline=true,owner=units[i],
    ownerTag='owner'..i,ownerOrder=i,singleOwnerOrder=i,sessions={}}
end
local checks,steps=0,0
local function check(ok,label) assert(ok,label); checks=checks+1 end
local function equal_projection(sb,sa)
  check(#sb.avatars==#sa.avatars,'avatar count')
  check(#sb.sessions==#sa.sessions,'wrapper count')
  for i,v in ipairs(sb.avatars) do
    local w=sa.avatars[i]
    for k,x in pairs(v) do check(w[k]==x,'clone field '..k) end
    for k,x in pairs(w) do check(v[k]==x,'no extra clone fields '..k) end
  end
  for i,v in ipairs(sb.sessions) do
    local w=sa.sessions[i]
    check(v.source==w.source and v.owner==w.owner and v.ownerTag==w.ownerTag
      and v.ownerOrder==w.ownerOrder,'wrapper order and owner fields')
    check(getmetatable(w).__index==w.source,'wrapper original __index')
  end
  for src,v in pairs(sb.wrappers) do check(sa.wrappers[src].source==v.source,'map preserves source identity') end
  for src in pairs(sa.wrappers) do check(sb.wrappers[src]~=nil,'no stale map keys') end
  for _,k in ipairs({'selfUnit','fpLockUnit','fpLockFrames'}) do check(sb[k]==sa[k],'lock '..k) end
  for _,map in pairs(sa.projectionScratch) do check(next(map)==nil,'scratch has no Unit/source references') end
  for _,map in pairs(sa.projectionBuffers[3-sa.projectionSlot]) do check(next(map)==nil,'retired outputs empty') end
end
local priorViews,priorAvatars={},{}
local pool,scratch
local function run(av,ss,explicit)
  steps=steps+1;rb.frame=steps;ra.frame=steps
  rb.avatars=av;ra.avatars=av;rb.sessions=ss;ra.sessions=ss
  local sb=baseline(rb,explicit);local sa=optimized(ra,explicit)
  equal_projection(sb,sa)
  if pool then check(pool==sa.projectionBuffers and scratch==sa.projectionScratch,'fixed pool identity')
  else pool=sa.projectionBuffers;scratch=sa.projectionScratch end
  for src,v in pairs(sa.wrappers) do
    if priorViews[src] then check(priorViews[src]==v,'surviving wrapper identity stable') end
  end
  for _,v in ipairs(sa.avatars) do
    if priorAvatars[v.unit] then check(priorAvatars[v.unit]==v,'surviving clone identity stable') end
  end
  priorViews={};for src,v in pairs(sa.wrappers) do priorViews[src]=v end
  priorAvatars={};for _,v in ipairs(sa.avatars) do priorAvatars[v.unit]=v end
end
run({avatars[1],avatars[2]},{sessions[1],sessions[2]})
for i=1,600 do run({avatars[1],avatars[2]},{sessions[1],sessions[2]}) end
-- Same callback can project twice with a different input. No frame cache.
rb.frame=777;ra.frame=777
local sb=baseline(rb,{avatars[3],avatars[2]});local sa=optimized(ra,{avatars[3],avatars[2]});equal_projection(sb,sa)
sb=baseline(rb,{avatars[1],avatars[4]});sa=optimized(ra,{avatars[1],avatars[4]});equal_projection(sb,sa)
priorViews={};priorAvatars={}
-- Deterministic adversarial reorder/churn, owner mutation, empty and mixed routes.
local seed=314159
local function rand(n) seed=(seed*48271)%2147483647;return seed%n+1 end
for i=1,700 do
  local av,ss={},{}
  for j=1,rand(8)-1 do av[#av+1]=avatars[rand(8)] end
  -- Duplicate-new-avatar semantics are compared, not 'fixed' in the optimization.
  local used={}
  for j=1,rand(8)-1 do local k=rand(8);if not used[k] then used[k]=true;ss[#ss+1]=sessions[k] end end
  local k=rand(8);sessions[k].owner=units[rand(8)];sessions[k].ownerTag='mutated'..i
  sessions[k].singleOwnerOrder=rand(8);sessions[k].singleMainline=i%11~=0
  avatars[k].nodes={root=i};avatars[k].tag='new'..i;avatars[k].extra=i
  if i%13==0 and rb.singleState then
    -- Accepted identity watch is allowed to replace projected arrays.
    local b,a=rb.singleState,ra.singleState
    local ba,aa,bs,as={},{},{},{}
    for j=1,#b.avatars do if j%2==1 then ba[#ba+1]=b.avatars[j];aa[#aa+1]=a.avatars[j] end end
    for j=1,#b.sessions do if j%2==1 then bs[#bs+1]=b.sessions[j];as[#as+1]=a.sessions[j] end end
    b.avatars,a.avatars,b.sessions,a.sessions=ba,aa,bs,as
    priorViews={};priorAvatars={}
  end
  if i%17==0 then
    rb.singleState.selfUnit=units[k];ra.singleState.selfUnit=units[k]
    rb.singleState.fpLockUnit=units[k];ra.singleState.fpLockUnit=units[k]
    rb.singleState.fpLockFrames=5;ra.singleState.fpLockFrames=5
  end
  -- Duplicate avatars create multiple valid clones in baseline: only compare
  -- canonical values there, not an impossible one-clone-per-unit assertion.
  priorAvatars={}
  run(av,ss)
end
-- Equal native wrapper objects must follow unchanged hash-key semantics.
local eq={__eq=function(a,b)return a.native==b.native end}
local x,y=setmetatable({id=91,native=1},eq),setmetatable({id=92,native=1},eq)
priorAvatars={};priorViews={}
run({{unit=x,nodes={},tag='x'},{unit=y,nodes={},tag='y'}},{})
run({},{});check(next(ra.singleState.wrappers)==nil,'no stale removed wrappers')
A.single_policy.clear_projection(ra)
check(ra.singleState.projectionBuffers==nil and ra.singleState.projectionScratch==nil,'pool detached')
return {checks=checks,steps=steps,fixedProjectionTablesAfterWarmup=true,
  sameCallbackReprojection=true,previewArrayReplacement=true,nativeEqWrappers=true}
'''
results=[]
for vm in ['lua51','luajit21']:
    lua=importlib.import_module('lupa.'+vm).LuaRuntime(unpack_returned_tuples=True)
    lua.globals().B=lua.execute((ROOT/'HD2PhysBoneCompat/src/production/single_remote_A_runtime.lua').read_text('utf-8-sig'))
    lua.globals().A=lua.execute((LAB/'A-source/physbone_runtime.lua').read_text('utf-8-sig'))
    row=dict(lua.execute(TEST).items());row['vm']=vm;results.append(row)
(LAB/'projection-differential-test.lua').write_text(TEST,encoding='utf-8')
(LAB/'projection-verification.json').write_text(json.dumps(dict(status='PASS_DIFFERENTIAL_PRIVATE_PROJECTION_TABLE_REUSE',results=results,testScriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='pure projection semantics and storage lifetime; not game timing or whole-runtime leak proof'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(results,indent=2))