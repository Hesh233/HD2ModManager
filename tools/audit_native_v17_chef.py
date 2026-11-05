"""Run the deployed Chef parser and sandbox on B8's final embedded Lua."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'tools/audit_native_v15_chef.py').read_text(encoding='utf-8')
replacements={
 'native-v15-20261104':'native-v17-20261104',
 "W/'physics-export-delivery/lua版/hd2physbone.lua'":"W/'hd2physbone-B8.lua'",
 "W/'project/ab-profiles/B6.json'":"W/'B8.json'",
 "type(a.hooks.update)=='function' and a.hooks.render==nil":"type(a.hooks.render)=='function' and a.hooks.update==nil",
 'assert(count==5 and':'assert(count==11 and',
 'a.hooks.update()':'a.hooks.render()',
 'updateFrames=state.frame':'renderFrames=state.frame',
 "W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'":"W/'runtime/B8/9ba626afa44a3aa3.patch_0'",
}
for old,new in replacements.items():
 assert old in source,old
 source=source.replace(old,new)
marker="assert(state.options.logPath==api.log_directory..'/hd2physbone.log')"
extra="""assert(p.modelArmLocalSync==true)
for resource,rows in pairs(expected_profile.modelArmLocalLayouts)do
 assert(#p.modelArmLocalLayouts[resource]==8)
 for i,row in ipairs(rows)do
  local actual=p.modelArmLocalLayouts[resource][i]
  for key,value in pairs(row)do assert(actual[key]==value,'direct local metadata mismatch')end
 end
end
"""
assert marker in source
source=source.replace(marker,extra+marker)
exec(compile(source,str(Path(__file__)),'exec'),dict(__file__=__file__,__name__='__main__'))
