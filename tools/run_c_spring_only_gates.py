"""C spring-only DIAGNOSTIC gates: packaging integrity + projection differential.

C intentionally removes ship VRD and driver writes, so the frozen A production
ship/VRD gate suite (which asserts ship evaluateDrivers==true and VRD enabled) is
NOT applied to C — that would assert behavior C deliberately removes. C's physics
contract is proven instead by probe_c_spring_only_candidate.py (789 checks: VRD/driver
zero writes, regular springs preserved, certificates intact, A22-inherited health/
projection/lifecycle safety). These gates cover the variant-agnostic packaging gates:
  * actual-ZIP installer/duplicate/uninstall across 2 VMs x 3 loaders (6 combos);
  * byte-exact catalog encoding + actual Chef size negative/boundary controls;
  * private projection differential A22(baseline) vs C (projection logic unchanged).
Routing adaptations mirror the A22 round (current normal Core 575e97b5/19281/42 wraps
SkeletonRuntime + PhysicsRoutes; compat already embedded; runtime-only resource change;
variant recovered from router skeletonRuntime upvalue). Frozen originals untouched.
No game FPS measured or claimed."""
from pathlib import Path
import hashlib, json, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import replace_once
LAB=ROOT/'outputs/physics-C-spring-only-diagnostic-20261117'
A22=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'
MANIFEST="ROOT/'outputs/physics-C-spring-only-diagnostic-20261117/candidate-manifest.json'"
ACOMPAT='3530bd37c701e1dea98affe1dfc30ff0716233813c011765249b57a6f821279b'
CSTATUS='C-SPRING-ONLY-DIAGNOSTIC-PENDING-REAL-GAME-PHYSICS-FPS-DELTA-NOT-FOR-ACCEPTANCE'

# 1) Installer / duplicate / uninstall (6 combos), routing-adapted, math guard kept.
s=(ROOT/'tools/verify_single_consumers_ship_fix.py').read_text('utf-8-sig')
s=replace_once(s,"PROD/'single_remote_release_manifest.json'", MANIFEST)
s=s.replace("'loader-size-candidate-pending-physics-and-FPS'", "'"+CSTATUS+"'")
s=replace_once(s,"base=(LAB/('before/HD2PhysBoneCompat/src/production/single_remote_compat.lua'if a.loader_size_fix else'before-source/single_remote_compat.lua')).read_text('utf-8-sig')", "base=(PROD/'single_remote_compat.lua').read_text('utf-8-sig')")
s=replace_once(s,"('physbone_runtime.lua','PhysBoneRuntime')","('physbone_runtime.lua','SkeletonRuntime')")
s=replace_once(s,"assert audit['methodsBefore']==audit['methodsAfter']==19802 and audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']",
    "assert audit['methodsBefore']==audit['methodsAfter'] and audit['resourcesBefore']==audit['resourcesAfter'] and set(audit['changedResources'])<={'HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua'} and 'HD2ModCore.PhysBone.physbone_runtime.lua' in audit['changedResources']")
s=replace_once(s,"m.FORMAL_PHYSICS_VARIANT==v","(m.FORMAL_PHYSICS_VARIANT or lua.eval('function(r)local f=r.install;for i=1,300 do local n,u=debug.getupvalue(f,i);if n==\"skeletonRuntime\" then return u.FORMAL_PHYSICS_VARIANT end;if n==nil then break end end end')(m))==v")
s=replace_once(s,"st.options.sceneContext==ctx","(st.options or st.skeleton.options).sceneContext==ctx")
s=replace_once(s,"resourcesChanged=2","resourcesChanged=len(audit['changedResources'])")
s=s.replace('PASS_ACTUAL_LOADER_SIZE_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS','PASS_ACTUAL_C_DIAGNOSTIC_ZIP_NOT_GAME_PHYSICS_OR_FPS')
(LAB/'c-installer-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['c-installers','--evidence-root',str(LAB),'--loader-size-fix']
exec(compile(s,str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'exec'),{'__file__':str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'__name__':'c_installers'})

# 2) Encoding exactness, old oversized negative controls, exact inclusive 4MiB boundary.
s=(ROOT/'tools/test_single_consumer_loader_size.py').read_text('utf-8-sig')
s=replace_once(s,"OUT/'A-export/physics-runtime.zip'","OUT/'C-export/physics-runtime.zip'")
(LAB/'size-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['c-size','--evidence-root',str(LAB)]
exec(compile(s,str(ROOT/'tools/test_single_consumer_loader_size.py'),'exec'),{'__file__':str(ROOT/'tools/test_single_consumer_loader_size.py'),'__name__':'c_sizes'})

# 3) Private projection differential: A22 baseline (B) vs C (A). C does not touch the
#    projection logic, so projections must be identical step-for-step in both VMs.
s=(ROOT/'tools/test_a22_projection_reuse.py').read_text('utf-8-sig')
s=replace_once(s,"LAB=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'","LAB=ROOT/'outputs/physics-C-spring-only-diagnostic-20261117'")
s=replace_once(s,"lua.globals().B=lua.execute((ROOT/'HD2PhysBoneCompat/src/production/single_remote_A_runtime.lua').read_text('utf-8-sig'))",
    "lua.globals().B=lua.execute((ROOT/'outputs/physics-A22-health-sampling-candidate-20261117/A-source/physbone_runtime.lua').read_text('utf-8-sig'))")
s=replace_once(s,"lua.globals().A=lua.execute((LAB/'A-source/physbone_runtime.lua').read_text('utf-8-sig'))",
    "lua.globals().A=lua.execute((LAB/'C-source/physbone_runtime.lua').read_text('utf-8-sig'))")
(LAB/'projection-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['c-projection']
exec(compile(s,str(ROOT/'tools/test_a22_projection_reuse.py'),'exec'),{'__file__':str(ROOT/'tools/test_a22_projection_reuse.py'),'__name__':'c_projection'})

(LAB/'gate-policy-receipt.json').write_text(json.dumps(dict(
    status='C_DIAGNOSTIC_GATES_PACKAGING_AND_PROJECTION_PASS',
    normalCoreSha256='575e97b57b2fbb6130b9bf4b5a08c7af16422ca55f08758ea2c718634e5aeb47',
    coreMethods=19281,coreResources=42,compatAlreadyEmbedded=True,
    appliedGates=['actual-ZIP installer/duplicate/uninstall 2 VM x 3 loaders (6 combos)',
        'byte-exact catalog encoding + actual Chef size negative/inclusive-4MiB boundary',
        'private projection differential A22 baseline vs C (2 VMs)'],
    notAppliedGates='Frozen A production ship/VRD gate suite (asserts ship evaluateDrivers==true and VRD enabled) is intentionally NOT applied: C deliberately removes ship VRD and driver writes. C physics contract is proven by probe_c_spring_only_candidate.py (789 checks).',
    physicsContractProbe='probe-c-candidate (789 checks) + probe-actual-zip (789 checks): VRD-exclusive node writes==0, driver solver calls==0, driver bone writes==0, regular-spring writes identical to A22, evaluateDrivers==false, all VRD chains disabled, no regular chain disabled, certificates intact, remote-mission exclusion matches A22, A22-inherited health-sampling/projection/lifecycle safety pass',
    installerAdaptation='SkeletonRuntime extraction label; dynamic current-Core audit baseline; runtime-only resource change accepted; variant C recovered from router skeletonRuntime upvalue; active.skeleton.options.sceneContext',
    frozenOriginalsEdited=False,gameFpsMeasured=False,diagnosticOnly=True),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('C diagnostic gates complete: installers + size + projection PASS; A ship/VRD gates intentionally not applied (C contract proven by 789-check probe)')