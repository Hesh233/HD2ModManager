local Routes=dofile("HD2PhysBoneCompat/src/physbone_routes.lua")
local Local=dofile("HD2PhysBoneCompat/src/physbone_compat.lua")
local Direct=dofile("HD2PhysBoneCompat/src/direct/physbone_compat.lua")
local SkeletonRuntime=dofile("HD2PhysBoneCompat/src/physbone_runtime.lua")
local DirectRuntime=dofile("HD2PhysBoneCompat/src/direct/physbone_runtime.lua")
local checks=0
local function check(name,condition) checks=checks+1; assert(condition,name) end
check("untagged legacy remains local",Routes.classify({bones={{name="source_extra_1"}}})==Routes.SKELETON)
check("explicit direct route",Routes.classify({bones={{name="source_extra_1"}}},Routes.DIRECT)==Routes.DIRECT)
check("unknown marker remains local",Routes.classify({bones={}},"direct-v2")==Routes.SKELETON)
check("native names cannot be forced direct",Routes.classify({bones={{name="hd2n_aabbccddeeff_phys_1_skirt"}}},Routes.DIRECT)==Routes.SKELETON)
check("single v3 cannot be forced direct",Routes.classify({bones={},drivers={version=3}},Routes.DIRECT)==Routes.SKELETON)
local rigs={old={bones={{name="source_extra_1"}}},direct={bones={{name="source_extra_1"}}},single={bones={{name="source_extra_1"}},drivers={version=3}},native={bones={{name="hd2n_aabbccddeeff_phys_1_skirt"}}}}
local markers={direct=Routes.DIRECT,single=Routes.SKELETON,native=Routes.SKELETON}
Local.load_rig=function(paths) for _,path in ipairs(paths) do if rigs[path] then return rigs[path],path end end end
Local._read_container_bytes=function(path)return markers[path]end
Local.parse_container=function(b)return {data=b}end
Local.find_record=function(c,name) check("only route record queried",name=="hd2_physics_route.txt");return c end
Direct.load_rig=function(paths)return {upstreamParser=true,bones=rigs[paths[1]].bones},paths[1] end
local priorCalls=0
local prior=function()priorCalls=priorCalls+1;return "prior"end
rawset(_G,"render",prior)
local api=Routes.new(Local,SkeletonRuntime,Direct,DirectRuntime)
local state=api.install({}, {log=false,vrdSkeletonOnly=true})
check("both independent states installed",state.skeleton~=state.direct and state.installed)
check("single-policy package version",api.VERSION=="2.3.7")
check("upstream version",api.DIRECT_VERSION=="2.1.45")
check("idempotent composite installation",api.install({}, {})==state)
check("independent install keys",rawget(_G,"__hd2physbone_runtime")==state.skeleton and rawget(_G,"__hd2physbone_direct_runtime")==state.direct)
local localView=state.skeleton.options.compat
local directView=state.direct.options.compat
for _,name in ipairs({"old","single","native"}) do
 check("local owns "..name,localView.load_rig({name})==rigs[name])
 check("direct rejects "..name,directView.load_rig({name})==nil)
end
check("local rejects direct",localView.load_rig({"direct"})==nil)
local rig,path=directView.load_rig({"single","direct","native"})
check("direct uses upstream parser",rig.upstreamParser==true and path=="direct")
check("math libraries are isolated",localView.gains_of==Local.gains_of and directView.gains_of==Direct.gains_of and localView.gains_of~=directView.gains_of)
check("set options supported",api.setOptions({heartbeatFrames=700}))
check("route views cannot be replaced",state.skeleton.options.compat==localView and state.direct.options.compat==directView)
check("options reach both states",state.skeleton.options.heartbeatFrames==700 and state.direct.options.heartbeatFrames==700)
check("uninstall succeeds",api.uninstall())
check("LIFO restores original render",rawget(_G,"render")==prior)
check("all markers removed",rawget(_G,"__hd2physbone_runtime")==nil and rawget(_G,"__hd2physbone_direct_runtime")==nil and rawget(_G,"__hd2physbone_routes")==nil)
check("second uninstall is harmless",not api.uninstall())
local carriers={{rig=rigs.old,path="old"},{rig=rigs.direct,path="direct"},{rig=rigs.single,path="single"},{rig=rigs.native,path="native"}}
local mixed=api.install({}, {log=false,carriers=carriers})
check("injected carriers are partitioned",#mixed.skeleton.options.carriers==3 and #mixed.direct.options.carriers==1)
check("injected direct is not owned locally",mixed.direct.options.carriers[1].rig==rigs.direct)
check("input carriers are untouched",#carriers==4)
api.uninstall()
local legacy={installed=true}
rawset(_G,"__hd2physbone_runtime",legacy)
local ok=pcall(api.install,{}, {log=false})
check("foreign unfiltered runtime is not reused",not ok and rawget(_G,"__hd2physbone_runtime")==legacy)
check("foreign runtime does not install direct beside it",rawget(_G,"__hd2physbone_direct_runtime")==nil and rawget(_G,"render")==prior)
rawset(_G,"__hd2physbone_runtime",nil)
print("PASS physics route isolation: "..checks.." checks")
