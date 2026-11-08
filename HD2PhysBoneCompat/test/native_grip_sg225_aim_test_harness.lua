-- Actual SG225-family magazines lack bullet_01 and were never classified.
local sgResult={}
local function sg_start(rid,magId,muzzleId)
 repaired_start(rid)
 gun=make(weapon_assets[rid]);gunParent=model;gunMount=hash_name('attach_hand_r')
 weaponRoot=gun.names[hash_name('root')] or gun.names[hash_name('boss')]
 under=gun.names[hash_name('attach_underbarrel')]
 linkedItems={};groups[1]={A,model,gun};pad_main();refresh_all()
 local function component(id,mount)
  local u=make(weapon_assets[id]);u.linkOwner=gun;u.linkIndex=gun.names[hash_name(mount)]
  local skeleton=u.names[hash_name('skeleton')]
  -- The common serialized entity root parents both rig and game_mesh.
  u.linkRoot=skeleton and (u.parents[skeleton]+1) or (u.parents[u.names[hash_name('game_mesh')]]+1)
  linkedItems[#linkedItems+1]=u;groups[1][#groups[1]+1]=u;return u
 end
 local mag=component(magId,'attach_mag');local muzzle=component(muzzleId,'attach_muzzle')
 refresh_all();native_contact(.30);refresh_all()
 return mag,muzzle
end
for _,row in ipairs({
 {'46183b50961d1328','68b8d040421e8a49','d8cf7fe059b4bf1e'},
 {'6228d0242bde56b6','3ddb9d36da22555d','8cd335a5f711bb59'},
 {'c12a34f375bd5a87','3ddb9d36da22555d','cdf733b0106a23c3'}})do
 local mag,muzzle=sg_start(row[1],row[2],row[3]);local inputs={}
 for _,u in ipairs({mag,muzzle})do inputs[u]=copy(u.locals)end
 step(runtime,'render',9400,940)
 check(not runtime.disabled,'TEST SG225 family disabled')
 local found={};for _,item in ipairs(runtime.consumers)do found[item.spec.resource]=true end
 check(found[mag.resource],'TEST SG225 magazine signature not discovered')
 check(found[muzzle.resource],'TEST SG225 muzzle signature not discovered')
 for _,u in ipairs({mag,muzzle})do
  check(near(u.cache[u.linkRoot],gun.cache[u.linkIndex],3e-5),'TEST SG225 component detached')
  all_same(u.locals,inputs[u],'TEST SG225 component animation mutated')
 end
 mag.linkOwner=model;mag.linkIndex=model.names[hash_name('attach_hand_l')]
 refresh_all();step(runtime,'render',9401,940.02)
 check(near(mag.cache[mag.linkRoot],model.cache[mag.linkIndex],3e-5),'TEST SG225 magazine reload relink lost')
 all_same(mag.locals,inputs[mag],'TEST SG225 reload animation mutated');runtime:stop()
end
sgResult.actualFamiliesMagazineMuzzleAndReload=true
-- A stale skeleton cache must not prevent a verified nearby mesh refresh.
local mag,muzzle=sg_start('46183b50961d1328','68b8d040421e8a49','d8cf7fe059b4bf1e')
local si=muzzle.names[hash_name('skeleton')]
muzzle.cache[si]=copy(muzzle.cache[si]);muzzle.cache[si][10]=muzzle.cache[si][10]+10
step(runtime,'render',9410,941)
check(not runtime.disabled,'TEST SG225 stale-root scene disabled')
local expected=multiply(gun.cache[muzzle.linkIndex],muzzle.locals[si])
check(near(muzzle.cache[si],expected,3e-5),'TEST SG225 muzzle root cache stayed detached')
runtime:stop();sgResult.staleRootNearMeshRefresh=true
-- Read-only camera/root traces; never write a camera or alter accepted aim axes.
repaired_start('cf8934ff6567a42d');aim_native();native_contact(.30)
local oldDebug=S.World.debug_camera_pose;local camera=transform(.2)
S.World.debug_camera_pose=function(w)check(w==1,'TEST wrong main camera world');return copy(camera)end
local input=copy(A.locals);local gunInput=copy(gun.locals)
step(runtime,'render',9420,942)
all_same(gun.locals,gunInput,'TEST aim diagnostics mutated gun')
local seen=false
for _,line in ipairs(logs)do
 if line:find('"event":"test_aim_sync_probe"',1,true) and line:find('"cameraWorld"',1,true) and line:find('"nativeLeftRoot"',1,true)then seen=true end
end
check(seen,'TEST aim camera/roots trace missing');runtime:stop();all_same(A.locals,input,'TEST aim diagnostics restore')
S.World.debug_camera_pose=oldDebug;sgResult.cameraRootTraceReadOnly=true
result15.sg225AndAimDiagnostics=sgResult

