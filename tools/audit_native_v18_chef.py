"""Use deployed Chef parser/sandbox on the complete B9 module."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'tools/audit_native_v15_chef.py').read_text(encoding='utf-8')
replacements={
 'native-v15-20261104':'native-v18-20261104',
 "W/'physics-export-delivery/lua版/hd2physbone.lua'":"W/'hd2physbone-B9.lua'",
 "W/'project/ab-profiles/B6.json'":"W/'B9.json'",
 "type(a.hooks.update)=='function' and a.hooks.render==nil":"type(a.hooks.render)=='function' and a.hooks.update==nil",
 'assert(count==5 and':'assert(count==11 and',
 'a.hooks.update()':'a.hooks.render()',
 'updateFrames=state.frame':'renderFrames=state.frame',
 "W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'":"W/'runtime/B9/9ba626afa44a3aa3.patch_0'",
 "('native_attachments.lua','physbone_runtime.lua')":"('native_attachments.lua','physbone_runtime.lua','native_scene_observer.lua')",
}
for old,new in replacements.items():
 assert old in source,old
 source=source.replace(old,new)
marker="assert(state.options.logPath==api.log_directory..'/hd2physbone.log')"
extra="""assert(not p.modelArmLocalSync and p.sceneObservation.enabled==true)
assert(p.sceneObservation.maxSamples==90 and p.sceneObservation.intervalSeconds==3)
for resource,rows in pairs(expected_profile.sceneObservation.layouts)do
 assert(#p.sceneObservation.layouts[resource]==8)
 for i,row in ipairs(rows)do
  local actual=p.sceneObservation.layouts[resource][i]
  for key,value in pairs(row)do assert(actual[key]==value,'observation metadata mismatch')end
 end
end
"""
assert marker in source;source=source.replace(marker,extra+marker)
exec(compile(source,str(Path(__file__)),'exec'),dict(__file__=__file__,__name__='__main__'))
