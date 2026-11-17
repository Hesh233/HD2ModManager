"""A22 actual-ZIP regressions; narrow A-only adaptation of the frozen 49-gate runner.

The current accepted manager Core (575e97b5, 19281 methods, 42 resources) wraps the
skeleton runtime in PhysicsRoutes.new(PhysBoneCompat, SkeletonRuntime, DirectCompat,
DirectRuntime) and already embeds compat 1.3.13. Two faithful, documented adaptations
are applied to ISOLATED SNAPSHOTS only (frozen originals untouched):
  * the runtime fixture recovers FORMAL_PHYSICS_VARIANT from the router's skeletonRuntime
    upvalue when the addon module is a router (same variant constant, not a weaker check);
  * the installer/audit gates pin the CURRENT normal Core baseline dynamically and accept
    a runtime-only resource change (compat already embedded), keeping the real gate:
    identity unchanged, zero IL method/constant/reference edits.
No game FPS is measured or claimed."""
from pathlib import Path
import hashlib, json, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import replace_once
LAB=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'
MANIFEST="ROOT/'outputs/physics-A22-health-sampling-candidate-20261117/candidate-manifest.json'"
ACOMPAT='3530bd37c701e1dea98affe1dfc30ff0716233813c011765249b57a6f821279b'

# 1) Isolated routing-adapted runtime fixture snapshot (parents[2] still resolves to ROOT).
fx=(ROOT/'HD2PhysBoneCompat/test/single-consumer-runtime-test.py').read_text('utf-8-sig')
fx=replace_once(fx,'state,_,R=H.install(e,opts,C)', '''state,_,R=H.install(e,opts,C)
FORMAL_VARIANT=R.FORMAL_PHYSICS_VARIANT
if FORMAL_VARIANT is None:
    FORMAL_VARIANT=lua.eval('function(r)local f=r.install;for i=1,300 do local n,v=debug.getupvalue(f,i);if n=="skeletonRuntime" then return v.FORMAL_PHYSICS_VARIANT end;if n==nil then break end end;return nil end')(R)
assert FORMAL_VARIANT in ('A','B'),'skeleton variant not recoverable from router' ''')
fx=replace_once(fx,"R.FORMAL_PHYSICS_VARIANT=='A'","FORMAL_VARIANT=='A'")
fx=replace_once(fx,'variant=R.FORMAL_PHYSICS_VARIANT','variant=FORMAL_VARIANT')
routed=LAB/'single-consumer-runtime-test-routed.py'
assert not routed.exists(), 'write-once fixture snapshot'
routed.write_text(fx,encoding='utf-8',newline='\n')

# 2) A-only gate runner snapshot.
s=(ROOT/'tools/run_single_consumers_ship_fix_gates.py').read_text('utf-8-sig')
s=replace_once(s,"ROOT/'HD2PhysBoneCompat/src/production/single_remote_release_manifest.json'", MANIFEST)
s=replace_once(s,"assert inputs['ACompat']==inputs['BCompat'];records=[]", "assert inputs['ACompat']=='"+ACOMPAT+"';records=[]")
s=replace_once(s,"for v in ['A','B']:","for v in ['A']:")
s=replace_once(s,'expected=49 if a.loader_size_fix else 47','expected=33 if a.loader_size_fix else 32')
s=replace_once(s,"'HD2PhysBoneCompat/test/single-consumer-runtime-test.py'", repr(str(routed)))
(LAB/'a-only-gate-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['a22-gates','--evidence-root',str(LAB),'--loader-size-fix']
exec(compile(s,str(ROOT/'tools/run_single_consumers_ship_fix_gates.py'),'exec'),{'__file__':str(ROOT/'tools/run_single_consumers_ship_fix_gates.py'),'__name__':'a22_gates'})

# 3) Aggregated addon installer/duplicate/uninstall checks, routing-adapted, math guard kept.
s=(ROOT/'tools/verify_single_consumers_ship_fix.py').read_text('utf-8-sig')
s=replace_once(s,"PROD/'single_remote_release_manifest.json'", MANIFEST)
s=s.replace("'loader-size-candidate-pending-physics-and-FPS'", "'A22-ISOLATED-TEST-CANDIDATE-PENDING-PHYSICS-FPS-AND-CHURN-SAFETY'")
s=replace_once(s,"base=(LAB/('before/HD2PhysBoneCompat/src/production/single_remote_compat.lua'if a.loader_size_fix else'before-source/single_remote_compat.lua')).read_text('utf-8-sig')", "base=(PROD/'single_remote_compat.lua').read_text('utf-8-sig')")
s=replace_once(s,"('physbone_runtime.lua','PhysBoneRuntime')","('physbone_runtime.lua','SkeletonRuntime')")
s=replace_once(s,"assert audit['methodsBefore']==audit['methodsAfter']==19802 and audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']",
    "assert audit['methodsBefore']==audit['methodsAfter'] and audit['resourcesBefore']==audit['resourcesAfter'] and set(audit['changedResources'])<={'HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua'} and 'HD2ModCore.PhysBone.physbone_runtime.lua' in audit['changedResources']")
s=replace_once(s,"m.FORMAL_PHYSICS_VARIANT==v","(m.FORMAL_PHYSICS_VARIANT or lua.eval('function(r)local f=r.install;for i=1,300 do local n,u=debug.getupvalue(f,i);if n==\"skeletonRuntime\" then return u.FORMAL_PHYSICS_VARIANT end;if n==nil then break end end end')(m))==v")
s=replace_once(s,"st.options.sceneContext==ctx","(st.options or st.skeleton.options).sceneContext==ctx")
s=replace_once(s,"resourcesChanged=2","resourcesChanged=len(audit['changedResources'])")
s=s.replace('PASS_ACTUAL_LOADER_SIZE_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS','PASS_ACTUAL_A22_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS')
(LAB/'a-only-installer-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['a22-installers','--evidence-root',str(LAB),'--loader-size-fix']
exec(compile(s,str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'exec'),{'__file__':str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'__name__':'a22_installers'})

# 4) Encoding exactness, old oversized negative controls, exact inclusive 4MiB boundary.
s=(ROOT/'tools/test_single_consumer_loader_size.py').read_text('utf-8-sig')
(LAB/'size-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['a22-size','--evidence-root',str(LAB)]
exec(compile(s,str(ROOT/'tools/test_single_consumer_loader_size.py'),'exec'),{'__file__':str(ROOT/'tools/test_single_consumer_loader_size.py'),'__name__':'a22_sizes'})

(LAB/'routing-adaptation-receipt.json').write_text(json.dumps(dict(
    status='A22_GATES_ROUTING_ADAPTATION_DOCUMENTED',
    normalCoreSha256='575e97b57b2fbb6130b9bf4b5a08c7af16422ca55f08758ea2c718634e5aeb47',
    coreMethods=19281,coreResources=42,compatAlreadyEmbedded=True,
    runtimeFixtureAdaptation='Recover FORMAL_PHYSICS_VARIANT from router skeletonRuntime upvalue; identical variant constant; all other assertions unchanged',
    installerAdaptation='SkeletonRuntime extraction label; dynamic current-Core audit baseline; runtime-only resource change accepted; variant recovery; active.skeleton.options.sceneContext',
    frozenOriginalsEdited=False,gameFpsMeasured=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')