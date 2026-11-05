"""B10 deployed Chef reader and sandbox compatibility."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'tools/audit_native_v15_chef.py').read_text(encoding='utf-8')
replacements={
 'native-v15-20261104':'native-v19-20261104',
 "W/'physics-export-delivery/lua版/hd2physbone.lua'":"W/'hd2physbone-B10.lua'",
 "W/'project/ab-profiles/B6.json'":"W/'B10.json'",
 "type(a.hooks.update)=='function' and a.hooks.render==nil":"type(a.hooks.render)=='function' and a.hooks.update==nil",
 'assert(count==5 and':'assert(count==11 and',
 'a.hooks.update()':'a.hooks.render()',
 'updateFrames=state.frame':'renderFrames=state.frame',
 "W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'":"W/'runtime/B10/9ba626afa44a3aa3.patch_0'",
 "('native_attachments.lua','physbone_runtime.lua')":"('native_attachments.lua','physbone_runtime.lua','native_scene_observer.lua','native_scene_roundtrip.lua')",
}
for old,new in replacements.items():assert old in source;source=source.replace(old,new)
marker="assert(state.options.logPath==api.log_directory..'/hd2physbone.log')"
extra="""assert(not p.modelArmLocalSync and p.sceneObservation.enabled and p.sceneRoundtrip.enabled)
assert(p.sceneRoundtrip.mode=='same_model_local')
for resource,rows in pairs(expected_profile.sceneRoundtrip.layouts)do
 assert(#p.sceneRoundtrip.layouts[resource]==8)
 for i,row in ipairs(rows)do for key,value in pairs(row)do assert(p.sceneRoundtrip.layouts[resource][i][key]==value)end end
end
"""
assert marker in source;source=source.replace(marker,extra+marker)
exec(compile(source,str(Path(__file__)),'exec'),dict(__file__=__file__,__name__='__main__'))
