"""Use the established real Chef sandbox audit for the B7 render-only export."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/'tools/audit_native_v15_chef.py').read_text(encoding='utf-8')
replacements={
    'native-v15-20261104':'native-v16-20261104',
    "W/'physics-export-delivery/lua版/hd2physbone.lua'":"W/'hd2physbone-B7.lua'",
    "W/'project/ab-profiles/B6.json'":"W/'B7.json'",
    "type(a.hooks.update)=='function' and a.hooks.render==nil":"type(a.hooks.render)=='function' and a.hooks.update==nil",
    'assert(count==5 and':'assert(count==11 and',
    'a.hooks.update()':'a.hooks.render()',
    'updateFrames=state.frame':'renderFrames=state.frame',
    "W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'":"W/'runtime/B7/9ba626afa44a3aa3.patch_0'",
}
for old,new in replacements.items():
    assert old in source,old
    source=source.replace(old,new)
exec(compile(source,str(Path(__file__)), 'exec'),dict(__file__=__file__,__name__='__main__'))
