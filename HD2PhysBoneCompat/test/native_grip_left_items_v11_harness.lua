-- V11: real exported layouts, non-identity linked locals and stale muzzle roots.
do (function()
local v11={}
local savedCalculate=calculate
calculate=function(u,linkedRoot,linkedPose)
 if u.linkLocalOffset and linkedRoot then linkedPose=numpy_multiply(linkedPose,u.locals[linkedRoot])end
 return savedCalculate(u,linkedRoot,linkedPose)
end
local function held_scene(rid,modelOwner)
 repaired_start('cf8934ff6567a42d');gun.visible=false
 local nl=integratedProfile.nativeLeft.index+1;local root=A.cache[integratedProfile.leftGrip.nodes[1].index+1]
 local goal=copy(A.cache[nl]);goal[10]=root[10];goal[11]=root[11];goal[12]=root[12]+.10
 A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],goal);refresh_all()
 local item=make(weapon_assets[rid]);item.linkOwner=modelOwner and model or A
 item.linkIndex=item.linkOwner.names[hash_name('attach_hand_l')];item.linkRoot=test_component_specs[rid].heldRoots[1]+1
 local c,s=math.cos(.4),math.sin(.4)
 item.locals[item.linkRoot]={1.2*c,1.2*s,0,-.8*s,.8*c,0,0,0,1.1,.10,-.08,.04};item.linkLocalOffset=true
 linkedItems={item};groups[1]={A,model,gun,item};pad_main();refresh_all()
 return item,nl
end
for k,rid in ipairs({'7372947782b91123','1ec5f54265a91c83','1b1fcc0e025c1f7d','d5cb9b5401b261f9'})do
 local item,nl=held_scene(rid,k%2==0);local input=copy(item.locals);local mount=copy(A.cache[A.names[hash_name('attach_hand_l')]])
 local native=copy(A.cache[nl]);check(not near(item.cache[item.linkRoot],mount,.012),'TEST V11 nonidentity fixture accidentally zero offset')
 step(runtime,'render',10700,1070)
 check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST V11 nonidentity left-linked local not recovered')
 check(near(A.cache[A.names[hash_name('attach_hand_l')]],mount,4e-5),'TEST V11 native left mount moved')
 local actual=contact_point(A.cache[integratedProfile.sourceLeft.index+1],integratedProfile.testRepairs.contacts.left.source)
 local wanted=contact_point(native,integratedProfile.testRepairs.contacts.left.native)
 for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST V11 recovered left contact missed')end
 all_same(item.locals,input,'TEST V11 child local offset was erased')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+4;refresh_all();local writesBefore=runtime.stats.leftWrites
 step(runtime,'render',10701,1070.1);check(runtime.stats.leftWrites==writesBefore,'TEST V11 released offset item still followed');runtime:stop()
end
v11.affineLinkedLocalsAndModelParent=true
-- Keep the already-accepted non-reload left beacon policy, even for an internal anchor read.
do
 local item=held_scene('16f397ca5f51f271',false);item.locals[item.linkRoot]=copy(weapon_assets[item.resource].matrices[item.linkRoot])
 item.linkLocalOffset=false;item.legacyParentRead=true;refresh_all()
 step(runtime,'render',10705,1070.5)
 check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST V11 changed accepted non-reload left beacon policy');runtime:stop()
end
v11.acceptedNonReloadPolicyUnchanged=true
-- A near, aligned but internally-parented magazine must not drive the hand.
do
 local item=held_scene('7372947782b91123',false);item.linkOwner=nil;item.linkLocalOffset=false
 refresh_all();item.cache[item.linkRoot]=copy(A.cache[A.names[hash_name('attach_hand_l')]])
 step(runtime,'render',10710,1071)
 check(not runtime.disabled and runtime.stats.leftWrites==0,'TEST V11 internal-parent lookalike was claimed');runtime:stop()
end
v11.internalParentLookalikeRejected=true
-- Two equally valid left-held items are deliberately not disambiguated by distance.
do
 local item=held_scene('7372947782b91123',false);local other=make(weapon_assets['1ec5f54265a91c83'])
 other.linkOwner=A;other.linkIndex=item.linkIndex;other.linkRoot=test_component_specs[other.resource].heldRoots[1]+1
 other.locals[other.linkRoot]=copy(item.locals[item.linkRoot]);other.linkLocalOffset=true
 linkedItems[#linkedItems+1]=other;groups[1][#groups[1]+1]=other;refresh_all();local mount=copy(A.cache[item.linkIndex])
 step(runtime,'render',10720,1072)
 check(not runtime.disabled and runtime.stats.leftWrites==0,'TEST V11 ambiguous left items were driven')
 check(near(A.cache[item.linkIndex],mount,4e-5),'TEST V11 ambiguous native mount moved');runtime:stop()
end
v11.ambiguityNoWrites=true
-- Named skeleton AND game_mesh caches may be stale while the verified external root is nearby.
do
 local part=reload_start('94bd931b5fb4ee95','16051937941bb709');local input=copy(part.locals)
 for _,name in ipairs({'skeleton','game_mesh'})do local n=part.names[hash_name(name)];part.cache[n][10]=part.cache[n][10]+4 end
 step(runtime,'render',10730,1073)
 check(not runtime.disabled and near(part.cache[part.linkRoot],gun.cache[part.linkIndex],4e-5),'TEST V11 Reprimand external-root refresh missing')
 local sk=part.names[hash_name('skeleton')];local expected=numpy_multiply(part.cache[part.parents[sk]+1],part.locals[sk])
 check(near(part.cache[sk],expected,4e-5),'TEST V11 Reprimand stale skeleton not refreshed')
 all_same(part.locals,input,'TEST V11 Reprimand local changed');runtime:stop()
end
v11.reprimandExternalRootRefresh=true
local candidates,graphs=false,false
for _,line in ipairs(logs)do
 candidates=candidates or line:find('"event":"test_left_item_link_candidates"',1,true)~=nil
 graphs=graphs or line:find('"event":"test_equipment_graph"',1,true)~=nil
end
check(candidates and graphs,'TEST V11 bounded link/graph telemetry missing')
v11.boundedReadOnlyTelemetry=true
calculate=savedCalculate
result15.leftItemsV11=v11
end)()end
