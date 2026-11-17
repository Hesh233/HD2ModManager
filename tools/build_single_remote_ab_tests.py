"""Build isolated single-skeleton A/B sources; never modify installed code or models.
The packages must be exported by EACH resource-only candidate Core afterward.
"""
from pathlib import Path
import argparse, hashlib, json, re

ROOT = Path(__file__).resolve().parents[1]
NORMAL = ROOT / 'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
DIAG = ROOT / 'outputs/physics-test01-multiplayer-combat-fps-20261116'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def replace_once(text, old, new):
    assert text.count(old) == 1, (old[:100], text.count(old))
    return text.replace(old, new, 1)

def build(output):
    output = output.resolve()
    assert output.is_relative_to(ROOT) and not output.is_symlink()
    output.mkdir(exist_ok=True)
    assert not (output / 'A-source').exists() and not (output / 'B-source').exists(), 'Use a fresh build output'
    runtime_path = DIAG / 'diagnostic-source/physbone_runtime.lua'
    compat_path = ROOT / 'HD2PhysBoneCompat/src/physbone_compat.lua'
    assert sha(runtime_path) == '8094b9c26a84d43cef7c7b8bc696f332bb25f45ca813dbaa780ca36fd57eeefd'
    assert compat_path.read_bytes() == (DIAG / 'source-physbone_compat.lua').read_bytes(), 'Do not overwrite concurrent compat changes'
    assert sha(ROOT / 'HD2PhysBoneCompat/src/physbone_runtime.lua') == 'a2d576f070fed2b57a7b7a54a899864521d7984cd2652d33422e1241ec32f211'
    runtime = runtime_path.read_text(encoding='utf-8')
    compat = compat_path.read_text(encoding='utf-8')
    policy = (ROOT / 'HD2PhysBoneCompat/src/experimental/single_remote_ab_policy.lua.in').read_text(encoding='utf-8')
    helper = (ROOT / 'HD2PhysBoneCompat/src/experimental/single_remote_ab_compat_helpers.lua.in').read_text(encoding='utf-8')
    (output / 'baseline-diagnostic-runtime.lua').write_bytes(runtime_path.read_bytes())
    (output / 'baseline-r2-compat.lua').write_bytes(compat_path.read_bytes())
    protected = {ROOT / 'HD2PhysBoneCompat/src/physbone_runtime.lua', compat_path,
                 ROOT / '../config.toml', ROOT / 'tools/native-python/anim_batch_mod/config.toml'}
    protected.update(p for p in NORMAL.iterdir() if p.is_file())
    model = NORMAL / 'test-library/[单骨架模型]test01'
    protected.update(p for p in model.rglob('*') if p.is_file())
    # Also preserve the user's active selections/profiles, not just root config.
    for folder in ['profiles', 'library', 'test-library']:
        protected.update(p for p in (NORMAL / folder).rglob('*.json') if p.is_file())
    before = {str(p.resolve()): sha(p) for p in sorted(protected) if p.is_file()}
    (output / 'protected-before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    c = replace_once(compat, 'M.version = "1.3.7"', 'M.version = "1.3.8"')
    c = replace_once(c, 'if session == nil or session.vrdPolicyBlocked == true then return 0 end',
                     'if session == nil or session.vrdPolicyBlocked == true or session.singleRemoteVrdExcluded == true then return 0 end')
    c = replace_once(c, 'if session.drivers ~= nil then\n\t\tfor _, row in ipairs(session.drivers) do',
                     'if session.drivers ~= nil and session.singleRemoteVrdExcluded ~= true then\n\t\tfor _, row in ipairs(session.drivers) do')
    # The exact Source/test1201 solver evaluates VRD inline, unlike update_tip.
    # Honor the same remote gate there. Read the existing helper ONLY as a spring
    # anchor; do not interpolate a VRD rule, synthesize a helper bind, or write it.
    a = ' for _,rec in ipairs(profile.records) do\n  local parent=virtual[rec.parent];local goal='
    b = ''' for _,rec in ipairs(profile.records) do
  if rec.kind==2 and session.singleRemoteVrdExcluded==true then
   local actual=sRead(S,unit,rec.node);calls=calls+4
   if actual==nil then session.dead='source-remote-helper-read';return 0 end
   target[rec.source]=actual
   virtual[rec.source]={p={unpack(actual.p)},q=sQ(sQ(actual.q,sInv(rec.targetBindQ)),rec.virtualBindQ)}
  else
  local parent=virtual[rec.parent];local goal='''
    c = replace_once(c, a, b)
    c = replace_once(c, '  plan[#plan+1]={node=rec.node,q=outputQ,p=outputP,source=rec.source,kind=rec.kind}\n  end\n end',
                     '  plan[#plan+1]={node=rec.node,q=outputQ,p=outputP,source=rec.source,kind=rec.kind}\n  end\n  end -- remote VRD gate; springs keep their original solver\n end')
    a = " for _,row in ipairs(st.saved) do local pose=rebuild_pose(session.S,row.pose);if pose~=nil then session.S.Unit.set_local_pose(session.unit,row.node,pose);n=n+1 end end"
    b = " for _,row in ipairs(st.saved) do if not (session.singleRemoteVrdExcluded==true and session.singleRemoteDriverNodes and session.singleRemoteDriverNodes[row.node]) then local pose=rebuild_pose(session.S,row.pose);if pose~=nil then session.S.Unit.set_local_pose(session.unit,row.node,pose);n=n+1 end end end"
    c = replace_once(c, a, b)
    assert c.endswith('return M\n')
    c = c[:-len('return M\n')] + helper + '\nreturn M\n'
    results = []
    for variant, version, mode in [('A', '2.3.9', 'self-only'), ('B', '2.3.10', 'remote-no-vrd')]:
        r = replace_once(runtime, 'M.VERSION = "2.3.8"', 'M.VERSION = "'+version+'"')
        r = r.replace('hd2physbone_test01_perf.log', 'hd2physbone_test01_'+variant+'_perf.log')
        r = r.replace('TEST01_PERF runtime=2.3.8 compat=1.3.7 diagnostic=test01-mp-perf-r1',
                      'TEST01_PERF runtime='+version+' compat=1.3.8 variant='+variant+' policy='+mode+' baseline=2.3.7-r2 diagnostic=single-remote-ab-r1')
        r = replace_once(r, 'M.single_policy = Single\n', 'M.single_policy = Single\n\n'+policy.replace('@POLICY@', mode).replace('@VARIANT@', variant)+'\n')
        r = replace_once(r, '\tSingle.tick(runtime)\n\tPerf.mark(runtime,"solver-and-writes")',
                        '\tSingle.tick(runtime)\n\tRemoteTest.apply(runtime)\n\tPerf.mark(runtime,"solver-and-writes")')
        r = replace_once(r, '\t\tlocal pending = (session.pendingDt or 0) + dt',
                        '\t\tlocal pending = session.singleRemotePhysicsExcluded == true and 0 or ((session.pendingDt or 0) + dt)')
        r = replace_once(r, '\t\t\tdue = session.singleDue == true',
                        '\t\t\tdue = session.singleDue == true and session.singleRemotePhysicsExcluded ~= true')
        r = replace_once(r, '\t\t\tlocal ok, out = pcall(Compat.update, session, pending)',
                        '''\t\t\tlocal driverBefore = session.driverWrites or 0
\t\t\tif session.singleMainline then session.singleRemoteHadUpdate = true end
\t\t\tlocal ok, out = pcall(Compat.update, session, pending)
\t\t\tlocal driverDelta = math.max(0, (session.driverWrites or 0) - driverBefore)
\t\t\tif session.singleRemoteIsRemote then runtime.remoteFrameDriverWrites = runtime.remoteFrameDriverWrites + driverDelta
\t\t\telseif session.singleRemoteIsSelf then runtime.selfFrameDriverWrites = runtime.selfFrameDriverWrites + driverDelta end''')
        r = replace_once(r, '\t\tfor _, item in ipairs(session.sessions) do\n\t\t\tif (item.staticFrames or 0) > 0 then staticChains = staticChains + 1 end\n\t\tend',
                        '\t\tif session.singleRemotePhysicsExcluded ~= true then\n\t\tfor _, item in ipairs(session.sessions) do\n\t\t\tif (item.staticFrames or 0) > 0 then staticChains = staticChains + 1 end\n\t\tend\n\t\tend')
        # Excluded actors must not trip the global physics failure watchdog.
        r = replace_once(r, '\t\tfor _, item in ipairs(session.sessions) do\n\t\t\tif item.disabled == true then tripped = true end\n\t\tend',
                        '\t\tif session.singleRemotePhysicsExcluded ~= true then\n\t\tfor _, item in ipairs(session.sessions) do\n\t\t\tif item.disabled == true then tripped = true end\n\t\tend\n\t\tend')
        r = replace_once(r, 'if(session.singleOwnerOrder or session.ownerOrder or 99)==1 then row.primary=1 end',
                        'if session.singleRemoteIsSelf==true then row.primary=1 end')
        r = replace_once(r, '  p.written=p.written+(runtime.perfFrameWritten or 0);p.calls=p.calls+(runtime.perfFrameCalls or 0)',
                        '  p.written=p.written+(runtime.perfFrameWritten or 0);p.calls=p.calls+(runtime.perfFrameCalls or 0)\n  p.selfVrd=(p.selfVrd or 0)+(runtime.selfFrameDriverWrites or 0);p.remoteVrd=(p.remoteVrd or 0)+(runtime.remoteFrameDriverWrites or 0)')
        extra = ''' local rs=runtime.remoteTestStats or {}
 line=line:gsub("\\n$",string.format(" policy=%s identity=%s selfUnits=%d selfChains=%d remoteUnits=%d remoteChains=%d physicsExcluded=%d vrdExcluded=%d unknownOwners=%d selfVrdWriteAvg=%.2f remoteVrdWriteAvg=%.2f\\n",tostring(rs.mode or "waiting"),tostring(rs.identity or "waiting"),rs.selfUnits or 0,rs.selfChains or 0,rs.remoteUnits or 0,rs.remoteChains or 0,rs.physicsExcluded or 0,rs.vrdExcluded or 0,rs.unknownOwners or 0,(p.selfVrd or 0)/p.samples,(p.remoteVrd or 0)/p.samples))
 p.selfVrd,p.remoteVrd=0,0
'''
        r = replace_once(r, ' p.bytes=p.bytes+#line;p.handle:write(line);p.handle:flush()', extra+' p.bytes=p.bytes+#line;p.handle:write(line);p.handle:flush()')
        a = '\truntime.singleState, runtime.singleLiveIndex, runtime.singleLiveWanted, runtime.singlePolicyLogged = nil, nil, nil, nil'
        r = replace_once(r, a, a+'\n\truntime.remoteTestSingle, runtime.remoteTestConfirmedSelf, runtime.remoteTestStats = nil, nil, nil')
        folder = output / (variant+'-source'); folder.mkdir()
        (folder / 'physbone_runtime.lua').write_text(r, encoding='utf-8', newline='\n')
        (folder / 'physbone_compat.lua').write_text(c, encoding='utf-8', newline='\n')
        results.append({'variant':variant, 'runtimeVersion':version, 'compatVersion':'1.3.8', 'defaultPolicy':mode,
                        'runtimeSha256':sha(folder/'physbone_runtime.lua'), 'compatSha256':sha(folder/'physbone_compat.lua')})
    report = {'status':'ISOLATED_TEST_SOURCES_ONLY', 'baselineRuntime':'2.3.7-r2', 'baselineCompat':'1.3.7',
              'diagnosticBaselineRuntimeSha256':sha(runtime_path), 'variants':results,
              'modelsAndUserConfigUnchanged':True, 'productionSourcesNotModified':True, 'actualGameFpsNotMeasured':True}
    (output/'source-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output', type=Path, required=True)
    build(ap.parse_args().output)
