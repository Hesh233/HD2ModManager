do (function()
local itemsResult={}
-- Left native-held items: retain native mount/FX while only Source hand follows.
for _,rid in ipairs({'16f397ca5f51f271','1ec5f54265a91c83','7372947782b91123','6e165f05a49233f6','1b1fcc0e025c1f7d'})do
 repaired_start('cf8934ff6567a42d');gun.visible=false
 local nl=integratedProfile.nativeLeft.index+1;local root=A.cache[integratedProfile.leftGrip.nodes[2].index+1];local goal=copy(A.cache[nl])
 goal[10]=root[10]+.20;goal[11]=root[11];goal[12]=root[12]+.10
 A.locals[nl]=numpy_relative(A.cache[A.parents[nl]+1],goal);refresh_all()
 local item=make(weapon_assets[rid]);item.linkOwner=A;item.linkIndex=A.names[hash_name('attach_hand_l')];item.linkRoot=test_component_specs[rid].heldRoots[1]+1
 linkedItems={item};groups[1]={A,model,gun,item};pad_main();refresh_all();local mount=copy(A.cache[item.linkIndex]);local input=copy(item.locals)
 local native=copy(A.cache[nl]);step(runtime,'render',10600,1060)
 check(not runtime.disabled and runtime.stats.leftWrites==1,'TEST V10 left native-held follower missing')
 check(near(A.cache[item.linkIndex],mount,4e-5),'TEST V10 left item native mount moved')
 local actual=contact_point(A.cache[integratedProfile.sourceLeft.index+1],integratedProfile.testRepairs.contacts.left.source)
 local wanted=contact_point(native,integratedProfile.testRepairs.contacts.left.native)
 for j=1,3 do check(math.abs(actual[j]-wanted[j])<4e-5,'TEST V10 left held contact missed')end
 all_same(item.locals,input,'TEST V10 left item local animation modified')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+4;refresh_all();local count=runtime.stats.leftWrites
 step(runtime,'render',10601,1060.1);check(runtime.stats.leftWrites==count,'TEST V10 released left item still followed');runtime:stop()
end
itemsResult.leftBeaconAndReloadContacts=true
-- Every audited throwable/mined hand item must not become a persistent projectile owner.
for _,rid in ipairs(test_v10_throwable_ids)do
 repaired_start('cf8934ff6567a42d');aim_native();native_contact(.30);gun.visible=false
 local spec=test_component_specs[rid];local item=make(weapon_assets[rid]);item.linkOwner=A;item.linkIndex=ti;item.linkRoot=spec.heldRoots[1]+1
 linkedItems={item};groups[1]={A,model,gun,item};pad_main();refresh_all();local input=copy(item.locals)
 step(runtime,'render',10610,1061);check(not runtime.disabled and runtime.stats.rightWrites==1,'TEST V10 throwable right follower missing '..rid)
 all_same(item.locals,input,'TEST V10 throwable pose mutated')
 item.linkOwner=nil;item.locals[1][10]=item.locals[1][10]+4;refresh_all();local released=copy(item.locals);local count=runtime.stats.rightWrites
 step(runtime,'render',10611,1061.1);check(runtime.stats.rightWrites==count,'TEST V10 projectile still followed '..rid)
 all_same(item.locals,released,'TEST V10 released projectile changed');runtime:stop()
end
itemsResult.allAuditedThrowablesHeldReleased=true
-- Actual missing rigid component layouts and linked Stoker subweapon.
for _,row in ipairs({{'43b2d7766120203b','819ec78bcaf69c49'},{'d54b9505c0f72873','612f7f6193fb1b2b'},{'6cfcc7f8801a0266','076692fd83a83c5c'},{'25aa2fd4643cf4ee','48fd06b465e8b681'},{'8a307bd1811a5fe9','d5cb9b5401b261f9'},{'94bd931b5fb4ee95','16051937941bb709'}})do
 local part=reload_start(row[1],row[2]);local input=copy(part.locals)
 step(runtime,'render',10620,1062);local seen=false;for _,it in ipairs(runtime.consumers)do if it.unit==part then seen=true end end
 check(not runtime.disabled and seen,'TEST V10 exact component missing '..row[2])
 check(near(part.cache[part.linkRoot],gun.cache[part.linkIndex],4e-5),'TEST V10 component detached '..row[2]);all_same(part.locals,input,'TEST V10 component local changed');runtime:stop()
end
local sub=reload_start('8a307bd1811a5fe9','72fe4b13f726c344');sub.linkIndex=gun.names[hash_name('attach_underbarrel')]
local muzzle=make(weapon_assets['7b153e02ad22d12c']);muzzle.linkOwner=sub;muzzle.linkIndex=sub.names[hash_name('attach_muzzle')];muzzle.linkRoot=muzzle.parents[muzzle.names[hash_name('skeleton')]]+1
linkedItems[#linkedItems+1]=muzzle;groups[1][#groups[1]+1]=muzzle;refresh_all();step(runtime,'render',10621,1062.1)
check(not runtime.disabled and near(muzzle.cache[muzzle.linkRoot],sub.cache[muzzle.linkIndex],4e-5),'TEST V10 nested Stoker muzzle detached');runtime:stop()
itemsResult.actualRigidAndNestedComponents=true
-- Hip/leg pistols and accessories must update even with hands far above them.
for _,row in ipairs({{'3575aabc5f1f9326','c891acf9e8dbda97'},{'52e4334e6a128caf','5f4b129d947d79d7'}})do
 local part=reload_start(row[1],row[2]);gunMount=hash_name('pistol')
 for _,cfg in ipairs({integratedProfile.rightGrip,integratedProfile.leftGrip})do A.locals[cfg.nodes[1].index+1][10]=A.locals[cfg.nodes[1].index+1][10]+4 end
 refresh_all();refreshTrace={};local input=copy(part.locals)
 step(runtime,'render',10630,1063);check(not runtime.disabled,'TEST V10 holster disabled')
 local foundGun,foundPart=false,false;for _,u in ipairs(refreshTrace)do foundGun=foundGun or u==gun;foundPart=foundPart or u==part end
 check(foundGun and foundPart,'TEST V10 holstered gun/component refresh missing')
 check(near(part.cache[part.linkRoot],gun.cache[part.linkIndex],4e-5),'TEST V10 holstered ammo detached');all_same(part.locals,input,'TEST V10 holstered ammo local changed');runtime:stop()
end
itemsResult.pistolHolsterGraph=true
result15.leftItemsV10=itemsResult

end)() end
