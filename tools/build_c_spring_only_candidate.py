"""Build isolated C spring-only DIAGNOSTIC candidate (A22 base + runtime-only policy).

C removes driver-bone writes AND VRD skirt chains, exactly like upstream mainline
(which has neither), while keeping regular springs (hair/bust/etc.). It exists ONLY
to isolate the driver+VRD performance cost against A on identical models/scenes.
It is NOT a daily-driver replacement and NOT for production acceptance: skirt
physics is intentionally absent, so a visual difference vs A is EXPECTED.

Runtime-only change; compat bytes are identical to A22/production (3530bd37).
Never edit production, never deploy, never overwrite accepted A19/B20/A21/A22.
"""
from pathlib import Path
import hashlib, json, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import replace_once, protected_files
A22 = ROOT / 'outputs/physics-A22-health-sampling-candidate-20261117'
OUT = ROOT / 'outputs/physics-C-spring-only-diagnostic-20261117'
PROD = ROOT / 'HD2PhysBoneCompat/src/production'

# A22 candidate runtime is the C base (08f3924d). Compat is byte-identical (3530bd37).
A22_RUNTIME_SHA = '08f3924d613403f944cee8c4311472819d2630da936ff74dce9e0b04fd2884f4'
A22_COMPAT_SHA = '3530bd37c701e1dea98affe1dfc30ff0716233813c011765249b57a6f821279b'

SPRING_ONLY_FN = '''-- C DIAGNOSTIC ONLY: spring-only policy. Removes driver-bone writes AND VRD
-- skirt chains (like upstream mainline, which has neither); regular springs
-- (hair/bust/etc.) are kept. NOT a daily-driver replacement: skirt physics is
-- intentionally absent, so a visual difference vs A is EXPECTED. Used solely to
-- isolate the driver+VRD performance cost against A on identical models/scenes.
-- VRD classifier: a chain is a VRD skirt chain iff its anchor (chain[1].parentName)
-- is a NON-WRIST driver bone name. Wrist drivers (weapon grip) are NOT VRD and
-- their anchored chains stay regular springs. item.disabled is honored by the
-- spring loop and release; evaluateDrivers=false gates all driver writes.
-- item.singleSpringOnlyExcluded marks the disable as INTENTIONAL and permanent so
-- the runtime solver-failure guard (which trips on any unexpected item.disabled)
-- ignores these VRD chains while still catching every other disabled item.
local function spring_only_policy(session)
	session.evaluateDrivers = false
	session.singleRemoteVrdExcluded = true
	local vrd = {}
	local rig = session.rig
	if rig and rig.drivers and rig.drivers.bones then
		for _, b in ipairs(rig.drivers.bones) do
			if not Compat.is_wrist_driver(b) then vrd[b.name] = true end
		end
	end
	for _, item in ipairs(session.consumerFullSessions or session.sessions or {}) do
		local cn = item.chain and item.chain[1]
		local anchor = cn and cn.parentName
		if anchor and vrd[anchor] then item.disabled = true; item.singleSpringOnlyExcluded = true end
	end
end
'''


def build_runtime(base):
    # 1) Define the policy at module scope, before RemotePhysics (in scope for both
    #    RemotePhysics.bind and the later tryAttach attach site).
    text = replace_once(base,
        'RemotePhysics={REVISION="ship-vrd-mission-ads-v2",DEFAULT="self-only"}\n',
        SPRING_ONLY_FN + 'RemotePhysics={REVISION="ship-vrd-mission-ads-v2",DEFAULT="self-only"}\n')
    # 2) Re-apply at the end of RemotePhysics.bind's active body. bind early-returns
    #    when epoch/owner are unchanged, so this runs ONLY on a scene/owner transition
    #    (when single_remote_policy_transition may have cleared item.disabled via
    #    remote_reset_numeric), NOT every frame. Re-disables VRD + forces drivers off.
    text = replace_once(text,
        ' session.singleFormalEpoch,session.singleFormalOwner=epoch,session.owner\n'
        ' if session.singleRemotePhysicsExcluded then session.pendingDt,session.singleDue=0,false end\n'
        'end\n',
        ' session.singleFormalEpoch,session.singleFormalOwner=epoch,session.owner\n'
        ' if session.singleRemotePhysicsExcluded then session.pendingDt,session.singleDue=0,false end\n'
        ' spring_only_policy(session)\n'
        'end\n')
    # 3) Apply once at attach, after ownerTag and BEFORE ConsumerRuntime.bind, so the
    #    full session.sessions list is disabled before any consumer selection. Consumer
    #    apply/unapply shares the same item tables, so disabled persists across rebinds.
    text = replace_once(text,
        '\t\t\tsession.ownerTag = entry.owner ~= nil and entry.owner.tag or nil\n'
        '\t\t\tConsumerRuntime.bind(runtime, session)\n',
        '\t\t\tsession.ownerTag = entry.owner ~= nil and entry.owner.tag or nil\n'
        '\t\t\tspring_only_policy(session)\n'
        '\t\t\tConsumerRuntime.bind(runtime, session)\n')
    # The frozen application exporter requires strict numeric semver (^\d+\.\d+\.\d+$),
    # so C keeps the A22 base version 2.3.22 and is distinguished by FORMAL_PHYSICS_VARIANT
    # = "C" (the same variant-letter convention as A/B). The runtime SHA differs from A22.
    text = replace_once(text, 'M.FORMAL_PHYSICS_VARIANT="A"', 'M.FORMAL_PHYSICS_VARIANT="C"')
    # 4) Adapt the runtime solver-failure guard: it trips on ANY item.disabled==true
    #    (a sign of unexpected stale/handback state in A). C's VRD disables are
    #    intentional and permanent, so ignore items flagged singleSpringOnlyExcluded
    #    while STILL tripping on every other disabled item (safety property preserved).
    text = replace_once(text,
        '\t\t\tif item.disabled == true then tripped = true end',
        '\t\t\tif item.disabled == true and item.singleSpringOnlyExcluded ~= true then tripped = true end')
    # Exactly one policy definition and two call sites; no other structural change.
    assert text.count('local function spring_only_policy(session)') == 1
    assert text.count('spring_only_policy(session)') == 3  # 1 def + 2 calls
    assert text.count('item.singleSpringOnlyExcluded = true') == 1
    assert text.count('item.singleSpringOnlyExcluded ~= true') == 1
    return text


def main():
    assert not OUT.exists(), 'Evidence is write-once; use a new stage'
    OUT.mkdir()
    frozen = protected_files()
    (OUT/'protected-before.json').write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    base = (A22/'A-source/physbone_runtime.lua').read_text('utf-8-sig')
    assert hashlib.sha256((A22/'A-source/physbone_runtime.lua').read_bytes()).hexdigest() == A22_RUNTIME_SHA
    assert hashlib.sha256((A22/'A-source/physbone_compat.lua').read_bytes()).hexdigest() == A22_COMPAT_SHA
    a22manifest = json.loads((A22/'candidate-manifest.json').read_text('utf-8-sig'))
    source = OUT/'C-source'; source.mkdir()
    runtime_text = build_runtime(base)
    (source/'physbone_runtime.lua').write_text(runtime_text, encoding='utf-8', newline='\n')
    (source/'physbone_compat.lua').write_bytes((A22/'A-source/physbone_compat.lua').read_bytes())
    assert hashlib.sha256((source/'physbone_compat.lua').read_bytes()).hexdigest() == A22_COMPAT_SHA
    runtime_sha = hashlib.sha256((source/'physbone_runtime.lua').read_bytes()).hexdigest()
    candidate = json.loads(json.dumps(a22manifest))
    accepted = a22manifest['sources'][0]
    candidate['sources'] = [dict(accepted, variant='C', runtimeVersion='2.3.22',
        runtimePath=str(source/'physbone_runtime.lua'), runtimeSha256=runtime_sha)]
    candidate['compatPath'] = str(source/'physbone_compat.lua')
    candidate['realGameAcceptanceStatus'] = 'C-SPRING-ONLY-DIAGNOSTIC-PENDING-REAL-GAME-PHYSICS-FPS-DELTA-NOT-FOR-ACCEPTANCE'
    candidate['candidateOnly'] = True
    candidate['diagnosticOnly'] = True
    candidate['automaticallyInstalledOrDeployed'] = False
    candidate['acceptedFeedback'] = {'baselineOnly': a22manifest['acceptedFeedback'],
        'newUserWords': '先找出最新的物理实现，按照优化方向迭代A包。之后打一个和主线一样只实现弹簧骨骼的c包，用于排除driver骨测试性能差距',
        'scope': 'User authorized a spring-only C diagnostic to isolate driver-bone performance cost; C removes BOTH driver writes AND VRD skirt chains (去driver也去VRD裙摆), keeping regular springs. NOT C acceptance; NOT a production replacement; skirt physics intentionally absent.'}
    candidate['managerEmbeddedDefaultNotChanged'] = True
    candidate['candidateChanges'] = ['runtime-only-spring-only-policy: evaluateDrivers=false (no driver-bone writes)',
        'runtime-only-spring-only-policy: VRD skirt chains item.disabled=true + item.singleSpringOnlyExcluded=true (no VRD spring writes)',
        'runtime-only-spring-only-policy: singleRemoteVrdExcluded=true (update_drivers returns 0; skip driver restore)',
        'policy applied at attach (full list, before consumer bind) and re-applied on RemotePhysics.bind scene/owner transition',
        'runtime solver-failure guard adapted: trips on item.disabled unless item.singleSpringOnlyExcluded (C intentional VRD disable); still trips on every other disabled item',
        'FORMAL_PHYSICS_VARIANT=C; VERSION=2.3.22 (numeric semver kept; variant letter C distinguishes from A22, same convention as A/B)']
    candidate['vrdClassifier'] = ('A chain is a VRD skirt chain iff chain[1].parentName is a NON-WRIST driver bone name '
        '(Compat.is_wrist_driver excludes weapon-grip wrists). Verified across all four real models: '
        'test01 6 VRD (skirt BL1/BR1/FL1/FR1/SL1/SR1) + 6 regular (hair/bust); '
        'Cow 0 VRD + 26 regular (2 non-wrist drivers anchor NO chains); '
        'test13 5 VRD (numeric 12<-2,13<-3,14<-4,15<-5,20<-10) + 9 regular; '
        'test15 8 VRD (q36<-qz12 etc.) + 17 regular + 4 wrist-anchored (x1/x2/y4/y5 KEPT as regular springs). '
        'front_skirt_anchor_policy returns nil for test01 and is NOT a reliable classifier; the driver-bone-name classifier is.')
    candidate['diagnosticSafety'] = ('C is DIAGNOSTIC ONLY. It inherits A22 health-sampling safety gaps (<=900-frame rebuild detection '
        'for stable non-writing sessions; residual transition-callback ordering gap; no pre-write identity guard). '
        'C additionally removes VRD skirt physics, so skirt/bone motion that A renders is intentionally absent in C — '
        'a visual difference is EXPECTED and is NOT a bug. C must NOT be accepted as a production replacement or daily driver. '
        'All disable mechanisms (item.disabled honored by spring loop+release; evaluateDrivers=false gates driver writes and '
        'drivers-mode consumer update; singleRemoteVrdExcluded=true skips driver restore; disabled persists through consumer '
        'apply/unapply which shares item tables; validate() checks bind layout not disabled so certificates stay intact) were '
        'individually verified in A. The runtime solver-failure guard trips on any unexpected item.disabled; C flags its '
        'intentional permanent VRD disables with item.singleSpringOnlyExcluded so the guard ignores ONLY those while still '
        'tripping on every other disabled item (the safety property for non-VRD items is preserved). Offline equivalence is NOT '
        'a crash-safety proof; real-device churn validation required.')
    candidate['comparisonContract'] = ('A vs C must be compared on the SAME current normal Core (which embeds Direct), same models, '
        'same scene/position/view/quality, stable 30-60s windows. C keeps singleRemotePhysicsExcluded exactly as A computes it '
        '(remote mission exclusion unchanged), so the ONLY difference between A and C is driver-bone writes + VRD skirt chains. '
        'The alive/FPS delta C-vs-A isolates the driver+VRD cost. Direct discovery overhead is identical in A and C and cancels out.')
    candidate['unchanged'] = ['compat solver and full certificate/catalog bytes (3530bd37)',
        'A22 dispatch/projection/empty-rejection/health-sampling', 'regular spring chains (hair/bust/wrist-anchored)',
        'singleRemotePhysicsExcluded remote-mission exclusion (same as A)', 'local stride1',
        'writing-session per-frame health and pre-write alive', 'per-frame pointer membership pruning',
        'normal Core and config', 'accepted A19/B20 and A21/A22 candidates',
        'models/binds/profiles/animations', 'game deployment']
    candidate['templateSha256']['cSpringOnlyBuilder'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    candidate['baseA22RuntimeSha256'] = A22_RUNTIME_SHA
    (OUT/'candidate-manifest.json').write_text(json.dumps(candidate, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (OUT/'builder-snapshot.py').write_bytes(Path(__file__).read_bytes())
    (OUT/'runtime.diff').write_text('\n'.join(__import__('difflib').unified_diff(
        base.splitlines(), runtime_text.splitlines(),
        fromfile='A22-2.3.22-variantA', tofile='C-2.3.22-variantC', lineterm=''))+'\n', encoding='utf-8', newline='\n')
    assert protected_files() == frozen
    print('C spring-only diagnostic source ready; base=A22 08f3924d; compat byte-identical 3530bd37;')
    print('runtime SHA', runtime_sha, '; production untouched; diagnostic-only + visual-difference disclosed')


if __name__ == '__main__':
    main()