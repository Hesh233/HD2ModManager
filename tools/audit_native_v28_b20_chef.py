"""Validate each B20 binary with the actual Chef parser and sandbox fixture."""
from pathlib import Path
from package_native_v12 import ROOT, load, save_json

W = ROOT / 'outputs/native-v28-b20-20261105'
reports = {}
for variant in ('R', 'A', 'H', 'T'):
    source = (ROOT / 'tools/audit_native_v15_chef.py').read_text(encoding='utf-8')
    replacements = {
        'native-v15-20261104': 'native-v28-b20-20261105',
        "W/'physics-export-delivery/lua版/hd2physbone.lua'": f"W/'hd2physbone-B20-{variant}.lua'",
        "W/'project/ab-profiles/B6.json'": f"W/'B20-{variant}.json'",
        "type(a.hooks.update)=='function' and a.hooks.render==nil": "type(a.hooks.render)=='function' and a.hooks.update==nil",
        'assert(count==5 and p.armSync==true and p.armGripSync==true': 'assert(count==11 and p.armSync==false and p.armGripSync==false',
        'a.hooks.update()': 'a.hooks.render()',
        'updateFrames=state.frame': 'renderFrames=state.frame',
        "W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'": f"W/'runtime/{variant}/9ba626afa44a3aa3.patch_0'",
        "('native_attachments.lua','physbone_runtime.lua')": "('native_attachments.lua','physbone_runtime.lua','native_scene_observer.lua','native_scene_roundtrip.lua','native_attachment_probe.lua','native_grip_alignment.lua')",
        "W/'chef-compatibility-audit.json'": f"W/'chef-compatibility-{variant}.json'",
        'print(json.dumps(report,indent=2))': f"print('Chef B20-{variant}: PASS')",
    }
    for old, new in replacements.items():
        assert old in source, old
        source = source.replace(old, new)
    marker = "assert(state.options.logPath==api.log_directory..'/hd2physbone.log')"
    extra = '''assert(not p.sceneRoundtrip.enabled and not p.attachmentProbe.enabled and not p.sceneObservation.enabled)
assert(p.nativeGripAlignment.enabled and p.nativeGripAlignment.exclusive)
assert(p.diagnosticMode==expected_profile.diagnosticMode and p.diagnosticMode=='apply')
assert(p.nativeGripAlignment.consumerObservation.enabled)
for _,pair in ipairs(p.nativeGripAlignment.pairs)do assert(pair.rotationMode=='native-world')end
local function same(a,b)
 if type(a)~='table' then return a==b end
 if type(b)~='table' then return false end
 for k,v in pairs(a)do if not same(v,b[k])then return false end end
 for k in pairs(b)do if a[k]==nil then return false end end
 return true
end
assert(same(p.nativeGripAlignment,expected_profile.nativeGripAlignment))
'''
    assert marker in source
    source = source.replace(marker, extra + marker)
    exec(compile(source, str(Path(__file__)), 'exec'), dict(__file__=__file__, __name__='__main__'))
    reports[variant] = load(W / f'chef-compatibility-{variant}.json')
assert all(r['status'] == 'PASS' for r in reports.values())
assert all(r['embeddedSourceSha256'] == reports['R']['embeddedSourceSha256'] for r in reports.values())
save_json(W / 'chef-compatibility-audit.json', dict(status='PASS', variants=reports,
    embeddedSourceSha256=reports['R']['embeddedSourceSha256'], gameTested=False))
