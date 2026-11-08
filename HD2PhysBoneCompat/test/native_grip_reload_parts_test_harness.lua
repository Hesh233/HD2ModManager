-- HMG belt box and laser rigid power modules, including no-skeleton Units.
local reloadResult={}
local function reload_start(weaponId,partId)
 repaired_start(weaponId)
 gun=make(weapon_assets[weaponId]);gunParent=model;gunMount=hash_name('attach_hand_r')
 weaponRoot=gun.names[hash_name('root')] or gun.names[hash_name('boss')]
 under=gun.names[hash_name('attach_underbarrel')]
 linkedItems={};groups[1]={A,model,gun};pad_main();refresh_all()
 local part=make(weapon_assets[partId]);part.linkOwner=gun;part.linkIndex=gun.names[hash_name('attach_mag')]
 local skeleton=part.names[hash_name('skeleton')];local mesh=part.names[hash_name('game_mesh')]
 part.linkRoot=part.parents[skeleton or mesh]+1
 linkedItems[1]=part;groups[1][#groups[1]+1]=part;refresh_all();native_contact(.30);refresh_all()
 return part
end
for _,row in ipairs({
 {'2152d5147b0ac418','b7cd35e0edc15cd7'},
 {'8645f167b3c813a2','e3541de70b7ec1c0'},
 {'27ee1ed8f6fb6356','50cd7e9f909fe5a1'},
 {'c85f576d5e086147','6600b5e755a21f1f'},
 {'295beb26dc4f8ff1','80e8335ab4042fcf'},
 {'7e3145a5baa4b948','d44c25420aa3e2ff'}})do
 local part=reload_start(row[1],row[2]);local input=copy(part.locals)
 step(runtime,'render',9500,950)
 check(not runtime.disabled,'TEST reload family disabled')
 local found=false;for _,item in ipairs(runtime.consumers)do if item.spec.resource==part.resource then found=true end end
 check(found,'TEST laser reload module not discovered '..part.resource)
 check(near(part.cache[part.linkRoot],gun.cache[part.linkIndex],3e-5),'TEST reload component detached '..part.resource)
 all_same(part.locals,input,'TEST reload component locals mutated')
 part.linkOwner=model;part.linkIndex=model.names[hash_name('attach_hand_l')];refresh_all()
 step(runtime,'render',9501,950.02)
 check(near(part.cache[part.linkRoot],model.cache[part.linkIndex],3e-5),'TEST reload native handoff lost')
 all_same(part.locals,input,'TEST reload handoff locals mutated');runtime:stop()
end
reloadResult.actualHmgAndLaserFamilies=true
local part=reload_start('2152d5147b0ac418','b7cd35e0edc15cd7')
local spec=integratedProfile.consumers[part.resource];local rootIndex=spec.root+1
local skeleton=part.names[hash_name('skeleton')];local mesh=part.names[hash_name('game_mesh')]
check(rootIndex~=skeleton,'TEST HMG fixture root/skeleton not distinct')
part.cache[rootIndex]=copy(part.cache[rootIndex]);part.cache[rootIndex][10]=part.cache[rootIndex][10]+10
part.cache[mesh]=copy(part.cache[mesh]);part.cache[mesh][10]=part.cache[mesh][10]+10
step(runtime,'render',9510,951)
local expected=multiply(gun.cache[part.linkIndex],multiply(part.locals[skeleton],part.locals[rootIndex]))
check(not runtime.disabled and near(part.cache[rootIndex],expected,3e-5),'TEST HMG multi-anchor cache recovery missing')
runtime:stop();reloadResult.multiAnchorCacheRecovery=true
-- Final diagnostics must distinguish the pre-compensation residual from the
-- current corrected weapon path. Existing safe compensation stays bounded.
repaired_start('cf8934ff6567a42d');aim_native();native_contact(.30)
step(runtime,'render',9520,952)
local seen=false;for _,line in ipairs(logs)do if line:find('"event":"test_final_contacts"',1,true) and line:find('"beforeCompensationResidual"',1,true) and line:find('"finalResidual"',1,true)then seen=true end end
check(seen,'TEST final contact diagnostic absent');runtime:stop()
reloadResult.finalCompensationDiagnostics=true
result15.reloadPartsV4=reloadResult
