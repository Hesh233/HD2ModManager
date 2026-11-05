"""Exercise the shipped Chef parser, sandbox and profile for all B12 variants."""
from pathlib import Path
from package_native_v12 import ROOT,load,save_json
W=ROOT/'outputs/native-v20-b12-20261104'
reports={}
for variant in ('A','B','ALL'):
    source=(ROOT/'tools/audit_native_v15_chef.py').read_text(encoding='utf-8')
    replacements={
        'native-v15-20261104':'native-v20-b12-20261104',
        "W/'physics-export-delivery/lua版/hd2physbone.lua'":f"W/'hd2physbone-B12-{variant}.lua'",
        "W/'project/ab-profiles/B6.json'":f"W/'B12-{variant}.json'",
        "type(a.hooks.update)=='function' and a.hooks.render==nil":"type(a.hooks.render)=='function' and a.hooks.update==nil",
        'assert(count==5 and':'assert(count==11 and',
        'a.hooks.update()':'a.hooks.render()',
        'updateFrames=state.frame':'renderFrames=state.frame',
        "W/'physics-export-delivery/patch版/9ba626afa44a3aa3.patch_0'":f"W/'runtime/{variant}/9ba626afa44a3aa3.patch_0'",
        "('native_attachments.lua','physbone_runtime.lua')":"('native_attachments.lua','physbone_runtime.lua','native_scene_observer.lua','native_scene_roundtrip.lua','native_attachment_probe.lua')",
        "W/'chef-compatibility-audit.json'":f"W/'chef-compatibility-{variant}.json'",
        'print(json.dumps(report,indent=2))':f"print('Chef B12-{variant}: PASS')",
    }
    for old,new in replacements.items():assert old in source;source=source.replace(old,new)
    marker="assert(state.options.logPath==api.log_directory..'/hd2physbone.log')"
    extra="""assert(not p.sceneRoundtrip.enabled and p.attachmentProbe.enabled)
assert(p.attachmentProbe.variant==expected_profile.attachmentProbe.variant)
assert(p.attachmentProbe.worldDelta[3]==0.6 and p.attachmentProbe.phaseSeconds==4)
assert(#p.attachmentProbe.nodes==#expected_profile.attachmentProbe.nodes)
for i,row in ipairs(expected_profile.attachmentProbe.nodes)do
 for key,value in pairs(row)do assert(p.attachmentProbe.nodes[i][key]==value)end
end
"""
    assert marker in source;source=source.replace(marker,extra+marker)
    exec(compile(source,str(Path(__file__)),'exec'),dict(__file__=__file__,__name__='__main__'))
    reports[variant]=load(W/f'chef-compatibility-{variant}.json')
assert all(r['status']=='PASS'for r in reports.values())
assert all(r['embeddedSourceSha256']==reports['A']['embeddedSourceSha256']for r in reports.values())
save_json(W/'chef-compatibility-audit.json',dict(status='PASS',variants=reports,embeddedSourceSha256=reports['A']['embeddedSourceSha256'],gameTested=False))
