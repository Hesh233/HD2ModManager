"""Finalize ONLY the isolated C spring-only DIAGNOSTIC delivery and human-readable
evidence; no installation, no acceptance, no production replacement.
C = A22 runtime + runtime-only spring_only_policy: evaluateDrivers=false (no driver
solver path / driver-bone writes), VRD skirt chains item.disabled=true flagged
item.singleSpringOnlyExcluded=true (no VRD spring writes), singleRemoteVrdExcluded=true
(skip driver restore). Regular springs, remote-mission exclusion, A22 dispatch/
projection/empty-rejection/health-sampling all unchanged. compat byte-identical.
C removes BOTH driver writes AND VRD skirt chains (user: 去driver也去VRD裙摆), like
upstream mainline which has neither, so A-vs-C isolates the driver+VRD cost.
Three口径: (1) same old-Core sandbox A22-vs-C isolates driver+VRD; (2) C actual ZIP
runs in current normal Core (embeds Direct) so its alive/instruction delta vs the
same-sandbox C candidate carries Direct discovery overhead independent of C;
(3) cross-round A22-actual-vs-C-actual on the SAME current Core is the cleanest
isolation (Direct identical, cancels). Driver BONE writes are 0 in the test01
fixture (static control bones), so the driver cost isolated here is solver-call
overhead + VRD spring-write removal; all disclosures written into report/receipts."""
from pathlib import Path
import hashlib,json,shutil,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-C-spring-only-diagnostic-20261117'
A22LAB=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'
NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
from analyze_a19_hotpath_candidates import protected_files
from finalize_single_loader_accepted import check_config

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def new_json(p,v):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# phase structure keys that MUST match A22-vs-C (peakAngle intentionally excluded:
# removing VRD skirt chains lowers the all-session peak angle, an expected visual delta).
CK=['label','frames','sessions','lastAttempted','lastChainTotal','staticChains']
# per-unit keys that MUST be identical C-candidate vs C-actual (same C source).
UEQ=['unitId','localOwner','consumerMode','excluded','solverCalls','successfulWrites','writeTraceSha256','healthFrames','pendingDt','vrdChains','vrdDisabled','regularChains','regularDisabled','evaluateDriversOff','vrdNodeWrites','driverExclusiveNodeWrites','regularNodeWrites','driverSolverCalls','driverBoneWrites']
# per-unit keys that MUST match A22-vs-C (C keeps regular springs + remote exclusion).
AC=['localOwner','consumerMode','excluded','solverCalls','regularNodeWrites']

def main():
    frozen=read(LAB/'protected-before.json');assert protected_files()==frozen
    manifest=read(LAB/'candidate-manifest.json');entry=manifest['sources'][0]
    assert 'formalRelease' not in manifest and manifest['candidateOnly'] and manifest['diagnosticOnly'] and not manifest['automaticallyInstalledOrDeployed']
    assert manifest['realGameAcceptanceStatus']=='C-SPRING-ONLY-DIAGNOSTIC-PENDING-REAL-GAME-PHYSICS-FPS-DELTA-NOT-FOR-ACCEPTANCE'
    assert entry['variant']=='C' and entry['runtimeVersion']=='2.3.22' and entry['compatVersion']=='1.3.13'
    assert sha(LAB/'builder-snapshot.py')==manifest['templateSha256']['cSpringOnlyBuilder']
    assert sha(LAB/'C-source/physbone_runtime.lua')==entry['runtimeSha256']
    assert sha(LAB/'C-source/physbone_compat.lua')==entry['compatSha256']
    assert manifest['baseA22RuntimeSha256']=='08f3924d613403f944cee8c4311472819d2630da936ff74dce9e0b04fd2884f4'
    base=read(LAB/'probe-a22-baseline/result.json');cand=read(LAB/'probe-c-candidate/result.json');actual=read(LAB/'probe-actual-zip/result.json')
    assert base['mode']=='a22' and cand['mode']=='c' and actual['mode']=='actual'
    assert base['runtimeSha256']==manifest['baseA22RuntimeSha256']
    assert cand['runtimeSha256']==actual['runtimeSha256']==entry['runtimeSha256']
    assert len(base['phases'])==len(cand['phases'])==len(actual['phases'])==5
    assert len(base['checks'])==193 and len(cand['checks'])==len(actual['checks'])==789
    assert base['protectedFiles']==cand['protectedFiles']==actual['protectedFiles']==len(frozen)
    assert base['fixtureSourceSha256']==cand['fixtureSourceSha256']==actual['fixtureSourceSha256']
    assert cand['probeScriptSha256']==actual['probeScriptSha256']
    assert [p['label'] for p in base['phases']]==[p['label'] for p in cand['phases']]==[p['label'] for p in actual['phases']]
    decomposition=[];direct=[];instr=[]
    for b,c,a in zip(base['phases'],cand['phases'],actual['phases']):
        # ---- 口径一: A22 vs C in the SAME old-Core sandbox (no Direct) ----
        for k in CK:assert b[k]==c[k],(b['label'],k)
        assert b['apiCalls']['Unit.alive']==c['apiCalls']['Unit.alive'],(b['label'],'alive A22!=C oldCore')
        assert [u['unitId'] for u in b['units']]==[u['unitId'] for u in c['units']]==[u['unitId'] for u in a['units']],(b['label'],'unit order')
        bu={u['unitId']:u for u in b['units']};cu={u['unitId']:u for u in c['units']};au={u['unitId']:u for u in a['units']}
        for uid in bu:
            B,Cu,A=bu[uid],cu[uid],au[uid]
            for k in AC:assert B[k]==Cu[k],(b['label'],uid,'A22!=C',k)
            # C: every VRD chain disabled, no regular chain disabled, drivers off, zero VRD/driver writes+calls
            assert Cu['vrdDisabled']==Cu['vrdChains'] and Cu['regularDisabled']==0 and Cu['evaluateDriversOff'],(b['label'],uid,'C disable policy')
            assert Cu['vrdNodeWrites']==0 and Cu['driverExclusiveNodeWrites']==0 and Cu['driverSolverCalls']==0 and Cu['driverBoneWrites']==0,(b['label'],uid,'C nonzero vrd/drv')
            assert Cu['successfulWrites']==Cu['regularNodeWrites'],(b['label'],uid,'C succ!=reg')
            assert B['successfulWrites']==B['regularNodeWrites']+B['vrdNodeWrites']+B['driverExclusiveNodeWrites'],(b['label'],uid,'A22 succ decomposition')
            assert Cu['successfulWrites']==B['successfulWrites']-B['vrdNodeWrites'],(b['label'],uid,'C succ != A22 succ - A22 vrd')
            assert B['regularNodeWrites']==Cu['regularNodeWrites']==A['regularNodeWrites'],(b['label'],uid,'regW A22==C==actual')
            # ---- 口径二: C candidate vs C actual per-unit identity (same C source) ----
            for k in UEQ:assert Cu[k]==A[k],(b['label'],uid,'C cand!=act',k)
        assert c['peakAngle']<=b['peakAngle'],(b['label'],'C peak > A22 (VRD removed should lower peak)')
        assert c['peakAngle']==a['peakAngle'],(b['label'],'C cand peak != actual')
        for k in ['totalRegularNodeWrites','totalVrdNodeWrites','totalDriverSolverCalls','totalDriverBoneWrites']:assert c[k]==a[k],(b['label'],k,'C cand total != actual')
        assert c['totalVrdNodeWrites']==0 and c['totalDriverSolverCalls']==0 and c['totalDriverBoneWrites']==0,(b['label'],'C totals nonzero')
        assert b['totalVrdNodeWrites']>0 and b['totalDriverSolverCalls']>0,(b['label'],'A22 has no VRD/driver to remove')
        assert b['totalDriverBoneWrites']==0 and c['totalDriverBoneWrites']==0,(b['label'],'driver bone writes nonzero (fixture caveat)')
        assert b['totalRegularNodeWrites']==c['totalRegularNodeWrites']==a['totalRegularNodeWrites'],(b['label'],'total regW differ')
        # Direct discovery overhead: actual (current Core) alive > candidate (old Core); independent of C
        assert a['apiCalls']['Unit.alive']>c['apiCalls']['Unit.alive'],(b['label'],'actual alive not > candidate')
        decomposition.append(dict(phase=b['label'],callbacks=b['frames'],
            aliveA22=b['apiCalls']['Unit.alive'],aliveC=c['apiCalls']['Unit.alive'],
            regularWritesA22=b['totalRegularNodeWrites'],regularWritesC=c['totalRegularNodeWrites'],
            vrdWritesA22=b['totalVrdNodeWrites'],vrdWritesC=c['totalVrdNodeWrites'],
            driverSolverCallsA22=b['totalDriverSolverCalls'],driverSolverCallsC=c['totalDriverSolverCalls'],
            driverBoneWritesA22=b['totalDriverBoneWrites'],driverBoneWritesC=c['totalDriverBoneWrites'],
            successfulWritesA22=sum(u['successfulWrites'] for u in b['units']),successfulWritesC=sum(u['successfulWrites'] for u in c['units']),
            peakAngleA22=b['peakAngle'],peakAngleC=c['peakAngle'],
            vrdChains=sum(u['vrdChains'] for u in c['units']),vrdDisabled=sum(u['vrdDisabled'] for u in c['units']),
            regularChains=sum(u['regularChains'] for u in c['units']),regularDisabled=sum(u['regularDisabled'] for u in c['units'])))
        direct.append(dict(phase=b['label'],aliveCandidate=c['apiCalls']['Unit.alive'],aliveActual=a['apiCalls']['Unit.alive'],directAliveOverhead=a['apiCalls']['Unit.alive']-c['apiCalls']['Unit.alive'],
            fixtureInstructionSamplesCandidate=c['instructionSamples'],fixtureInstructionSamplesActual=a['instructionSamples'],
            runtimeLineRangeSamplesCandidate=c['runtimeInstructionSamples'],runtimeLineRangeSamplesActual=a['runtimeInstructionSamples']))
        instr.append(dict(phase=b['label'],fixtureInstructionSamplesA22=b['instructionSamples'],fixtureInstructionSamplesC=c['instructionSamples'],fixtureInstructionSamplesActual=a['instructionSamples'],
            runtimeLineRangeSamplesA22=b['runtimeInstructionSamples'],runtimeLineRangeSamplesC=c['runtimeInstructionSamples'],runtimeLineRangeSamplesActual=a['runtimeInstructionSamples']))
    # ---- 口径三: cross-round A22-actual vs C-actual on the SAME current normal Core ----
    # Direct discovery overhead is identical in A22 and C and cancels; the ONLY difference
    # is driver+VRD. A22 actual probe lacks the node-write decomposition fields (added in
    # probe_c), so cross-reference alive/structure/health/exclusion + successfulWrites delta.
    a22actual=read(A22LAB/'probe-actual-zip-final/result.json')
    assert a22actual['runtimeSha256']==manifest['baseA22RuntimeSha256']
    assert a22actual['actualCandidateZipSha256']=='b54e413d4e639208b1b52be35d104c9398af96a9bf58fc315443432a1b18a11a'
    assert len(a22actual['phases'])==5
    samecore=[]
    for pa,pc in zip(a22actual['phases'],actual['phases']):
        for k in CK:assert pa[k]==pc[k],('A22act!=Cact',pa['label'],k)
        assert pa['apiCalls']['Unit.alive']==pc['apiCalls']['Unit.alive'],('A22act alive != Cact (Direct must cancel)',pa['label'])
        ua={u['unitId']:u for u in pa['units']};uc={u['unitId']:u for u in pc['units']}
        assert set(ua)==set(uc)
        for uid in ua:
            for k in ['localOwner','consumerMode','excluded','healthFrames','pendingDt']:assert ua[uid][k]==uc[uid][k],('A22act!=Cact',pa['label'],uid,k)
        aw=sum(u['successfulWrites'] for u in pa['units']);cw=sum(u['successfulWrites'] for u in pc['units'])
        assert cw<aw,('C actual successfulWrites not < A22',pa['label'])
        # the removed writes equal the VRD spring writes A22 performs in the same-sandbox baseline
        b=next(x for x in base['phases'] if x['label']==pa['label'])
        assert aw-cw==b['totalVrdNodeWrites'],('removed writes != A22 VRD writes',pa['label'],aw-cw,b['totalVrdNodeWrites'])
        assert pc['peakAngle']<pa['peakAngle'],('C peak not < A22 peak',pa['label'])
        samecore.append(dict(phase=pa['label'],aliveA22Actual=pa['apiCalls']['Unit.alive'],aliveCActual=pc['apiCalls']['Unit.alive'],
            successfulWritesA22Actual=aw,successfulWritesCActual=cw,vrdSpringWritesRemoved=aw-cw,
            peakAngleA22Actual=pa['peakAngle'],peakAngleCActual=pc['peakAngle'],
            healthFramesAndExclusionIdentical=True,directDiscoveryOverheadCancels=True))
    # Actual ZIP receipt: parsed source == executed source proves NO real post-parse substitution.
    source_receipt=read(LAB/'probe-actual-zip/sandbox-source-sha.json')
    assert source_receipt['parsedSourceSha256']==source_receipt['executedSourceSha256']
    assert source_receipt['sourceSubstitutionAfterParser'] is False and source_receipt['notCandidatePackageValidation'] is False
    export=read(LAB/'release-candidate/export-verification.json');zip_path=LAB/'release-candidate/C-export/physics-runtime.zip'
    assert sha(zip_path)==export['zipSha256']==actual['chefZipSha256']
    assert export['variant']=='C' and export['runtimeVersion']=='2.3.22' and export['compatVersion']=='1.3.13' and export['diagnosticOnly']
    assert export['runtimeSha256']==entry['runtimeSha256'] and export['compatSha256']==entry['compatSha256']
    assert export['luaResourceBytes']<4194304 and export['chefHeadroomBytes']==4194304-export['luaResourceBytes']
    assert export['compatByteIdentical'] and export['frozenNormalCoreCodeChanged'] is False and export['productionSourceChanged'] is False and export['rootConfigPreserved']
    assert export['normalCoreSha256']=='575e97b57b2fbb6130b9bf4b5a08c7af16422ca55f08758ea2c718634e5aeb47'
    assert export['coreChangedResources']==['HD2ModCore.PhysBone.physbone_runtime.lua']
    assert export['compatAlreadyEmbeddedInNormalCore'] and export['addonRuntimeWrapper']=='SkeletonRuntime'
    assert export['baseA22RuntimeSha256']==manifest['baseA22RuntimeSha256']
    assert sha(LAB/'release-candidate/C-extracted/physbone_runtime.lua')==entry['runtimeSha256']
    assert sha(LAB/'release-candidate/C-extracted/physbone_compat.lua')==entry['compatSha256']
    audit=read(LAB/'release-candidate/C-core-audit.json')
    assert audit['beforeSha256'].lower()==sha(NORMAL/'HD2ModCore.dll') and audit['identityUnchanged']
    assert not audit['changedMethods'] and not audit['changedConstants'] and not audit['changedReferences']
    assert audit['methodsBefore']==audit['methodsAfter']==19281 and audit['resourcesBefore']==audit['resourcesAfter']==42
    assert audit['changedResources']==['HD2ModCore.PhysBone.physbone_runtime.lua']
    installers=read(LAB/'release-candidate/C-formal-verification.json')
    assert installers['variant']=='C' and len(installers['installers'])==6 and all(x['installDuplicateInstallUninstall'] for x in installers['installers'])
    assert installers['resourcesChanged']==1 and installers['methodsChanged']==0 and installers['originalMathAndProfilesBodyUnchanged']
    assert installers['zipSha256']==export['zipSha256'] and installers['newGameFpsMeasurement'] is False
    sizes=read(LAB/'release-candidate/catalog-and-chef-size-tests.json');assert sizes['status'].startswith('PASS_') and sizes['checks']==246765
    assert sizes['catalogSha256']==manifest['consumerCatalogSha256']
    projection=read(LAB/'projection-verification.json');assert len(projection['results'])==2 and all(r['steps']==1303 and r['checks']==69436 for r in projection['results'])
    gates=read(LAB/'gate-policy-receipt.json')
    assert gates['status']=='C_DIAGNOSTIC_GATES_PACKAGING_AND_PROJECTION_PASS' and gates['diagnosticOnly'] and gates['frozenOriginalsEdited'] is False and gates['gameFpsMeasured'] is False
    assert gates['normalCoreSha256']==export['normalCoreSha256'] and len(gates['appliedGates'])==3 and 'NOT applied' in gates['notAppliedGates']
    config=check_config();assert config==read(LAB/'baseline-consumer-and-config-revalidation.json')['configuration']
    assert config[0]['configSha256']=='ff64a88d7a0c786f600a3382db7cfec66a71b0c30e62b755eb2abd9ca413ced6'
    reval=read(LAB/'baseline-consumer-and-config-revalidation.json')['acceptedEvidenceRevalidated']
    # ---- delivery (only after ALL assertions pass) ----
    deliver=LAB/'delivery';assert not deliver.exists();deliver.mkdir()
    dest=deliver/'物理运行时-单骨架-C-仅弹簧骨骼诊断-2.3.22-诊断候选.zip';shutil.copyfile(zip_path,dest)
    assert sha(dest)==sha(zip_path)
    snapshots=LAB/'final-tool-snapshots';snapshots.mkdir()
    for name in ['build_c_spring_only_candidate.py','probe_c_spring_only_candidate.py','export_c_spring_only_candidate.py','run_c_spring_only_gates.py','test_a22_projection_reuse.py','finalize_c_spring_only_candidate.py']:
        shutil.copyfile(ROOT/'tools'/name,snapshots/name)
    package={'path':str(dest),'variant':'C','runtimeVersion':'2.3.22','compatVersion':'1.3.13','bytes':dest.stat().st_size,'sha256':sha(dest),'sourceSha256':entry['runtimeSha256'],'diagnosticOnly':True}
    driver_caveat='Driver BONE writes are 0 in the test01 fixture for BOTH A22 and C (the fake engine leaves driver control bones static/unresolved, so quatinterp produces no valid delta). The driver cost isolated here is therefore the driver SOLVER-CALL overhead (update_drivers invocations: A22 ship 7200 -> C 0) PLUS the VRD spring-write removal (A22 ship 13311 -> C 0). A model/scene with actively-driven control bones is needed to measure driver bone-write cost separately. This is disclosed, not hidden.'
    verification={'status':'PASS_ISOLATED_C_SPRING_ONLY_DIAGNOSTIC_DELIVERABLE_OFFLINE_GATES_PENDING_REAL_GAME_A22_VS_C_FPS_DELTA_NOT_FOR_ACCEPTANCE',
        'package':package,'diagnosticOnly':True,'luaResourceBytes':export['luaResourceBytes'],'chefLimitBytes':4194304,'chefHeadroomBytes':export['chefHeadroomBytes'],
        'candidateZipScannedWithoutRealSourceSubstitution':True,'parsedEqualsExecutedSourceSha256':source_receipt['executedSourceSha256'],
        'installerVmLoaderCases':6,'projectionDifferentialStepsPerVm':1303,'projectionDifferentialAssertionsPerVm':69436,
        'cSpringOnlyContractChecks':789,'a22BaselineChecks':193,'byteExactEncodingChecks':sizes['checks'],
        'springOnlyDecomposition':decomposition,'directOverheadDecomposition':direct,'sameCoreA22VsCActual':samecore,'instructionSamples':instr,
        'configuration':config,'consumerEvidence':reval,
        'normalCore':{'sha256':export['normalCoreSha256'],'methods':19281,'resources':42,'changedResources':['HD2ModCore.PhysBone.physbone_runtime.lua'],'runtimeWrapper':'SkeletonRuntime','compatAlreadyEmbedded':True,'note':export['addonRouting']},
        'vrdClassifier':manifest['vrdClassifier'],'diagnosticSafety':manifest['diagnosticSafety'],'comparisonContract':manifest['comparisonContract'],
        'driverBoneWriteCaveat':driver_caveat,'baseA22RuntimeSha256':manifest['baseA22RuntimeSha256'],
        'gatesApplied':gates['appliedGates'],'gatesNotApplied':gates['notAppliedGates'],
        'fullFkRerunThisTurn':False,'protectedFiles':len(frozen),'protectedHashesUnchanged':True,
        'gameFpsMeasured':False,'mainProductionPromoted':False,'managerOrGameLaunched':False,'installedOrDeployed':False,'notForAcceptance':True,
        'healthSamplingSafety':manifest['healthSamplingSafety'],
        'knownLimits':[
            'C is DIAGNOSTIC ONLY: VRD skirt physics is intentionally absent, so skirt/bone motion that A renders is missing in C — a visual difference is EXPECTED and is NOT a bug; C must NOT be accepted as a production replacement or daily driver',
            'No C game FPS/CPU/GPU frametime measurement; the driver+VRD cost is NOT yet quantified in FPS — real-device same-Core A22-vs-C comparison required',
            'Unit.alive and instruction sampling counts are NOT FPS',
            'Driver BONE writes are 0 in the test01 fixture (static control bones); isolated driver cost = solver-call overhead + VRD spring-write removal, NOT driver bone-write cost',
            'C inherits A22 health-sampling safety gaps: stable non-writing sessions widen node-rebuild detection latency from <=30 to <=900 frames; residual transition-callback ordering gap (prune before RemotePhysics.bind); no pre-write identity guard',
            'Offline call-count/write equivalence is NOT a crash-safety proof; real-device churn (rebuild/换装/重生/切图/进出队) validation required',
            'C actual ZIP runs in the current normal Core which embeds the Direct pipeline; its alive/instruction delta vs the same-old-Core-sandbox C candidate carries Direct discovery overhead independent of C',
            'The clean driver+VRD isolation is the same-Core A22-actual-vs-C-actual cross-round reference (Direct identical, cancels) AND the same-old-Core-sandbox A22-vs-C candidate reference, NOT the C-actual-vs-C-candidate net figure',
            'Frozen A production ship/VRD gate suite (asserts ship evaluateDrivers==true and VRD enabled) intentionally NOT applied: C deliberately removes ship VRD and driver writes; C contract proven by the 789-check probe',
            'Private projection steady-state table allocation removed (inherited from A22), GC time not measured',
            'Successful setter traces cover sample windows (callback frame/Unit/order/node/value), not all transition/release/uninstall write timing',
            'Projection and explicit cleanup probes are not a whole-runtime memory-leak proof',
            'Full FK evidence rehashed against current inputs, not rerun; legacy suites use singleFormalPolicy=false',
            'Normal Core baseline shifted since A21 (ce3a3c40/19802/39 -> 575e97b5/19281/42); C export changes only the runtime resource (A22->C), compat already embedded']}
    new_json(LAB/'final-verification.json',verification)
    new_json(LAB/'delivery.json',{'status':verification['status'],'package':package,'verificationPath':str(LAB/'final-verification.json'),'verificationSha256':sha(LAB/'final-verification.json'),
        'productionBaseline':'A19/B20 accepted unchanged; A21/A22 candidates preserved; C diagnostic candidate only, NOT for acceptance',
        'newUserFeedback':manifest['acceptedFeedback']['newUserWords'],'diagnosticOnly':True,'diagnosticSafety':manifest['diagnosticSafety'],'driverBoneWriteCaveat':driver_caveat})
    # ---- report ----
    def tbl(rows):return '\n'.join(rows)
    iso_rows=[f"|{d['phase']}|{d['aliveA22']}|{d['aliveC']}|{d['regularWritesA22']}|{d['regularWritesC']}|{d['vrdWritesA22']}|{d['vrdWritesC']}|{d['driverSolverCallsA22']}|{d['driverSolverCallsC']}|{d['peakAngleA22']:.3f}|{d['peakAngleC']:.3f}|" for d in decomposition]
    direct_rows=[f"|{d['phase']}|{d['aliveCandidate']}|{d['aliveActual']}|+{d['directAliveOverhead']}|{d['fixtureInstructionSamplesCandidate']}|{d['fixtureInstructionSamplesActual']}|" for d in direct]
    same_rows=[f"|{s['phase']}|{s['aliveA22Actual']}|{s['aliveCActual']}|{s['successfulWritesA22Actual']}|{s['successfulWritesCActual']}|{s['vrdSpringWritesRemoved']}|" for s in samecore]
    instr_rows=[f"|{i['phase']}|{i['fixtureInstructionSamplesA22']}|{i['fixtureInstructionSamplesC']}|{i['fixtureInstructionSamplesActual']}|{i['runtimeLineRangeSamplesA22']}|{i['runtimeLineRangeSamplesC']}|{i['runtimeLineRangeSamplesActual']}|" for i in instr]
    chain_rows=[f"|{d['phase']}|{d['vrdChains']}|{d['vrdDisabled']}|{d['regularChains']}|{d['regularDisabled']}|" for d in decomposition]
    report=ROOT/'docs/agent/physics-C-spring-only-diagnostic-20261117.md';assert not report.exists()
    report_text=f'''# C 仅弹簧骨骼诊断包：隔离 driver＋VRD 性能开销

2026-11-17，Asia/Shanghai。**C2.3.22 / compat1.3.13 已生成可测试 ZIP，离线门禁通过；这是仅诊断候选，不是正式替换、不用于接受。C 故意去掉 VRD 裙摆物理与 driver 骨写入，裙摆/骨骼运动会比 A 少——视觉差异是预期的，不是 bug。未获实机 A22-vs-C 同 Core FPS 差值验收。**

## 用户请求与范围

用户本次原文：「{manifest['acceptedFeedback']['newUserWords']}」。A 包迭代（A22）已另轮完成。本轮按用户拍板「去driver也去VRD裙摆」打 C 诊断包：和上游主线一样只实现弹簧骨骼（主线既无 driver 骨写入也无 VRD 裙摆），**C 同时去掉 driver 骨写入与 VRD 裙摆链，保留常规弹簧**，使 A 与 C 的唯一差异就是 driver＋VRD，从而隔离这两者的性能开销。C 不是生产替换、不用于日常、不接受为正式。

## C 机制（runtime-only，compat 字节不变）

在 A22 runtime（SHA `{manifest['baseA22RuntimeSha256']}`）基础上注入 `spring_only_policy(session)`，仅改 runtime 一个资源：

1. `session.evaluateDrivers=false`：driver 求解路径关闭，`update_drivers` 不再被调用（driver 骨写入＝0）。
2. `session.singleRemoteVrdExcluded=true`：`update_drivers` 即使被调也提前返回 0，跳过 driver 归还。
3. VRD 裙摆链 `item.disabled=true`＋`item.singleSpringOnlyExcluded=true`：弹簧循环与 release 都尊重 disabled，VRD 弹簧写入＝0。
4. 策略在 attach（ownerTag 后、ConsumerRuntime.bind 前，全量链）施加，并在 `RemotePhysics.bind` 的 epoch/owner 切换体重施加。
5. **求解器失效护栏适配**：原 runtime `if item.disabled==true then tripped=true` 会对任何 disabled 链触发退回重挂；C 的永久 VRD disable 会每拍触发它导致证明永不完成。C 用 `item.singleSpringOnlyExcluded` 标记故意的 VRD disable，护栏改为 `if item.disabled==true and item.singleSpringOnlyExcluded~=true then tripped=true`——**仅忽略 C 故意标记的 VRD，对其它任何 disabled 链仍照常触发**，非 VRD 的安全性质保留。
6. `FORMAL_PHYSICS_VARIANT="C"`；`VERSION="2.3.22"`（导出器要求严格数字 semver，无后缀；用变体字母 C 区分 A22，与 A/B 同约定）。

**VRD 分类器**：链首 `chain[1].parentName` 属于**非手腕** driver 骨名（`Compat.is_wrist_driver` 排除武器握持手腕）即 VRD 裙摆链。四真实模型已核：{manifest['vrdClassifier']}

**不变**：compat 完整字节（SHA `{entry['compatSha256']}`，Source2/T16/VRD/弹簧/作者参数/证书/所有 TOC palette/未知回退）；常规弹簧链（头发/胸/手腕锚定）；`singleRemotePhysicsExcluded` 远端任务排除（与 A 完全一致）；本地 stride1；写入会话每拍健康与写前 alive；每拍指针成员 prune；A22 派发/投影/空拒绝/判活降频；正常 Core 与根配置；已接受 A19/B20 与 A21/A22 候选；模型/bind/profile/动画；部署。`validate()` 检查 bind 布局而非 disabled，证书完整；consumer apply/unapply 共享 item 表，disabled/singleSpringOnlyExcluded 持久。

## 诊断安全缺口（必须实机验证）

- C **继承 A22 判活降频安全缺口**：稳定非写入会话节点重建检测延迟 ≤30→≤900 帧；残留切换回调顺序缺口（prune 在 bind 前）；写前身份守卫未实施。
- C **额外去掉 VRD 裙摆物理**：A 渲染的裙摆/骨骼运动在 C 故意缺失，视觉差异预期，非 bug。
- 离线调用计数/写入等价**不是崩溃安全证明**。2026-11-01 的挂起正是越界节点索引野写所致；接受前须实机折腾（重建/换装/重生/切图/进出队）验证。C 仅诊断，不接受为正式。

## 五阶段真实 test01 回放与三口径分解

实际 Chef1.4.1 parser/sandbox、Lua5.1＋Chef 纯 Lua bit、identityWatch 开。每阶段 600 回调，受控组件位移激励物理，**非实机战斗动画或 FPS**。A22 基线/C 候选在**同一旧 Core 沙箱**（loader-size-fix lab，无 Direct）；C 实际 ZIP 在**当前正常 Core**（含 Direct）。

### 口径一：同旧 Core 沙箱 A22 vs C（隔离 driver＋VRD，无 Direct）

`Unit.alive` 完全一致（C 不改发现/判活路径），常规弹簧写入逐 Unit 完全一致，C 把 VRD 弹簧写入与 driver 求解调用降到 0：

|阶段|A22 alive|C alive|A22常规写|C常规写|A22 VRD写|C VRD写|A22 driver调用|C driver调用|A22 peak|C peak|
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{tbl(iso_rows)}

舰船阶段：VRD 弹簧写入 13311→0，driver 求解调用 7200→0，常规弹簧写入 20856 不变，alive 15418 不变。peak 角度 C 低于 A22（去掉 VRD 裙摆链后全会话峰值下降，预期视觉差异）。**driver 骨写入在 A22/C 都是 0**（见下方 caveat）。

### C 链禁用核查（每阶段聚合）

|阶段|VRD链|VRD已禁|常规链|常规已禁|
|---|---:|---:|---:|---:|
{tbl(chain_rows)}

C 每阶段全部 VRD 链禁用、零常规链禁用、所有会话 evaluateDrivers=false。

### 口径二：C 实际 ZIP（当前正常 Core，含 Direct）vs C 同沙箱候选

|阶段|C候选alive|C实际alive|Direct开销|C候选instr|C实际instr|
|---|---:|---:|---:|---:|---:|
{tbl(direct_rows)}

**Direct 管线发现开销独立于 C**：C 实际 ZIP 比同沙箱候选每阶段多 alive +2600(单人)/+7400(四人/舰船)，以及 has_node/num_scene_graph_items/world_position/World.units 等发现调用。这是因为交付 ZIP 基于当前正常 Core（已内嵌 Direct），而候选沙箱用旧 Core（无 Direct）。**这部分开销在 A22 与 C 完全相同，会在 A-vs-C 比较中抵消**，不是 C 的效果，也不是 FPS。

### 口径三：跨轮 A22 实际 vs C 实际（同当前正常 Core，最干净隔离）

引用已完成的 A22 实际 ZIP 探针（同一当前正常 Core、同夹具；A22 ZIP SHA b54e413d…）。Direct 发现开销在 A22/C 相同并抵消，唯一差异是 driver＋VRD：

|阶段|A22实际alive|C实际alive|A22实际成功写|C实际成功写|移除的VRD弹簧写|
|---|---:|---:|---:|---:|---:|
{tbl(same_rows)}

**alive 完全一致**（6462/12198/22818/12198/6462），逐 Unit localOwner/consumerMode/excluded/healthFrames/pendingDt 完全一致（C 远端排除与健康采样与 A22 相同）。成功写入差值恰等于 A22 在同沙箱基线的 VRD 弹簧写入（舰船 34167−20856＝13311）。这是同 Core 下 driver＋VRD 开销的最干净隔离证据。

### driver 骨写入 caveat（必须如实披露）

{driver_caveat}

### 指令采样（含夹具，非 CPU 计时）

|阶段|A22基线instr|C候选instr|C实际instr|A22基线rt行|C候选rt行|C实际rt行|
|---|---:|---:|---:|---:|---:|---:|
{tbl(instr_rows)}

C 候选全夹具指令采样比 A22 基线大幅下降（舰船 76498→44115、四人 22946→14822），因为去掉了 VRD 弹簧求解与 driver 求解路径；C 实际因 Direct 开销回升（舰船→47255）。runtime 行范围归属采样也下降。**采样含夹具且不是 CPU 计时，不能选取下降数值宣称 FPS 收益或已收回帧数。** 投影表分配减少（继承 A22）是结构/身份结论，未测 GC 耗时。

## 离线验证

- 实际应用导出器在隔离 Core 副本导出，不改正常 Core：19281 方法、672 常量、42 资源，身份/常量/引用零变，**只替换一个 runtime 资源**（A22→C）；compat 与正常 Core 内嵌字节一致。正常 Core SHA 锁定 `{export['normalCoreSha256']}`。
- 实际 C ZIP CRC/4 成员/manifest/source/SHA 通过，Lua 资源 `{export['luaResourceBytes']:,}` B < 4,194,304 B，余量 `{export['chefHeadroomBytes']:,}` B。Chef 实际扫描后**解析源码 SHA==执行源码 SHA**（`{source_receipt['executedSourceSha256']}`），`sourceSubstitutionAfterParser=False`、`notCandidatePackageValidation=False`，证明未在扫描后真实替换候选源码；started/sandbox/实际成功 setter/卸载已核。
- C 物理契约探针 789 断言通过（候选与实际各 789）：VRD 独占节点写入＝0、driver 求解调用＝0、driver 骨写入＝0、常规弹簧写入与 A22 逐 Unit 一致、evaluateDrivers=false、全部 VRD 链禁用、零常规链禁用、证书完整、远端任务排除与 A22 一致、A22 继承的判活降频/投影/生命周期安全通过。A22 基线 193 断言。
- 6 种 VM/loader 安装、重复安装、卸载组合通过（SkeletonRuntime 提取标签、动态当前 Core 审计基线、runtime-only 资源变更、变体 C 从路由 skeletonRuntime upvalue 恢复、active.skeleton.options.sceneContext）；编码逐字段 exact、旧超限包负控和 4MiB 含边界测试通过（{sizes['checks']:,} 检查）。
- 投影纯 Lua 差分两 VM 各 1303 步/69436 断言通过（A22 基线 vs C），涵盖重复投影、乱序/移除/重加入、owner 更新、预览数组替换、native __eq 但不同表键、残键清理与固定池身份。
- **冻结 A 生产舰船/VRD 门禁套件故意不施加**（它断言舰船 evaluateDrivers==true 且 VRD 启用，与 C 故意去 VRD/driver 矛盾）；C 物理契约由 789 断言探针证明。见 gate-policy-receipt.json。
- 当前 61profiles/39 资源、真实 bind/config/rig/driver/catalog/harness SHA 门禁及旧 290case/8,744,894 逐值 FK 证据重新核验；**本轮没有重新跑完整 FK**。
- 源/随包/正常根配置检查通过；根 SHA 仍 ff64a88d7a0c786f600a3382db7cfec66a71b0c30e62b755eb2abd9ca413ced6，用户 0.7/0.7/1 及 rotation_compensation=false 完整保留。冻结清单 {len(frozen)} 文件 SHA 一致，范围见 protected-before.json，不宣称全游戏文件扫描。

## 诊断包与实机验收

- [C2.3.22 仅弹簧骨骼诊断候选 ZIP](<{dest}>)，{dest.stat().st_size:,} B。
- ZIP SHA256：`{sha(dest)}`。
- [完整核验](<{LAB/'final-verification.json'}>)；[C 实际 ZIP 五阶段回放](<{LAB/'probe-actual-zip/result.json'}>)；[C 候选探针](<{LAB/'probe-c-candidate/result.json'}>)；[A22 基线探针](<{LAB/'probe-a22-baseline/result.json'}>)；[门禁策略回执](<{LAB/'gate-policy-receipt.json'}>)；[逐行 diff](<{LAB/'runtime.diff'}>)；[候选 manifest](<{LAB/'candidate-manifest.json'}>)。

**C 仅用于诊断 driver＋VRD 开销，不是生产替换。** 测试时只替换当前物理运行时配套，A19/A21/A22/C 共用 owner/GUID 不要同时启用；不需要重导模型、重烘动画或改根配置。先确认 Chef 日志 started 2.3.22 且变体 C。**关键实机比较**：在同一当前正常 Core（含 Direct）、同模型、同四人任务/舰船、同位置/视角/画质、稳定 30–60 秒窗口，分别开 A22 与开 C，记录各组绝对 FPS 和 CPU/GPU frametime（若可用）。A22-vs-C 的 FPS 差值即 driver＋VRD 的实机开销（Direct 开销相同抵消）。**预期 C 裙摆/VRD 骨骼不动、driver 骨不驱动——这是诊断意图，不是故障。** 同时观察 C 是否出现卡死/野写/姿态异常（继承 A22 判活降频缺口）。若需单独量化 driver 骨写入开销，须用控制骨被实际驱动的模型/场景（本 test01 夹具 driver 骨写入＝0）。FPS 收益与折腾安全由实机验收，不因离线绿灯标正式；C 不接受为正式。

本轮仅新 tools、隔离诊断候选/回放/报告及协作记忆，未改 production Lua/DLL/manifest、正常安装/活动配套、B20、A21/A22 候选、根配置、库/profile、模型/GPU/动画或部署；未启动管理器/游戏，未覆盖已接受封档。候选留在隔离输出目录，不自动放入或勾选正常配套。
'''
    report.write_text(report_text,encoding='utf-8',newline='\n')
    (deliver/'测试说明.md').write_text(report_text,encoding='utf-8',newline='\n')
    before=LAB/'before-docs';before.mkdir();shutil.copyfile(ROOT/'AGENTS.md',before/'AGENTS.md')
    note=f'''## C仅弹簧骨骼诊断候选（2026-11-17，仅诊断不接受）

- 用户原文「先找出最新的物理实现，按照优化方向迭代A包。之后打一个和主线一样只实现弹簧骨骼的c包，用于排除driver骨测试性能差距」；A22已另轮完成。C按拍板「去driver也去VRD裙摆」：和主线一样只实现弹簧骨骼，同时去driver骨写入与VRD裙摆链，保留常规弹簧，使A与C唯一差异=driver+VRD。C仅诊断、非生产替换、不接受为正式；裙摆/VRD骨骼运动故意缺失，视觉差异预期非bug。
- C机制(runtime-only，compat字节不变3530bd37)：在A22 runtime(08f3924d)注入spring_only_policy(session)——evaluateDrivers=false(update_drivers不调用)、singleRemoteVrdExcluded=true(跳过driver归还)、VRD链item.disabled=true+item.singleSpringOnlyExcluded=true(弹簧循环/release尊重disabled)；attach全量施加+bind切换体重施加。VRD分类器=链首parentName属非手腕driver骨名(is_wrist_driver排除手腕)，四模型已核(test01 6VRD/Cow 0/test13 5/test15 8，手腕锚定x1/x2/y4/y5保留为常规)。求解器失效护栏适配：原`if item.disabled then tripped`会被C永久VRD disable每拍触发致证明不完成；改为`disabled and singleSpringOnlyExcluded~=true`仅忽略C故意VRD，对其它disabled仍触发(非VRD安全保留)。VARIANT=C/VERSION=2.3.22(导出器要数字semver无后缀，变体字母区分)。
- 三口径分解：①同旧Core沙箱A22vsC——alive完全一致(3862/4798/15418)，常规弹簧写入逐Unit一致(5822/5836/20856/5821/5833)，C把VRD弹簧写(舰船13311→0)与driver求解调用(舰船7200→0)降0，peak C<A22(去VRD预期)。②C实际ZIP在当前正常Core含Direct，比同沙箱候选多alive+2600(1p)/+7400(4p/舰船)发现开销(独立于C，A22/C相同会抵消)。③跨轮A22实际vsC实际同当前Core——alive完全一致(6462/12198/22818)，逐Unit owner/mode/excluded/healthFrames/pendingDt一致，成功写差=VRD弹簧写(舰船34167−20856=13311)，最干净隔离。driver骨写入A22/C都=0(test01夹具控制骨静态)，故隔离的driver开销=求解调用overhead+VRD弹簧写移除，非driver骨写开销；需控制骨实际驱动的模型/场景另测。指令采样含夹具非CPU计时(C候选舰船76498→44115，实际因Direct回升47255)，不宣称FPS收益。
- 实际ZIP真导出/CRC/SHA、Chef扫描后解析==执行源码SHA(cde97877)无真实替换、started/成功writer/卸载通过；Lua4092386B<4MiB余量101918B。C契约探针789断言(候选/实际各789，A22基线193)、6installer、两VM投影各1303步69436断言、编码246765检查通过。冻结A生产舰船/VRD门禁(断言evaluateDrivers==true/VRD启用)故意不施加(与C去VRD矛盾)，C契约由789探针证明。61profiles/39资源当前bind/config与旧290case/8744894FK证据重核，不冒称重跑全FK。282保护文件不变。根ff64/normal Core575e97b5、production A19/B20/manifest、A21/A22候选、当前库/profile/模型/动画/活动配套与旧封档保持；未启动/导入/部署/Git。
- C继承A22判活降频缺口(≤900帧重建延迟/切换回调顺序缺口/无写前身份守卫)，离线等价非崩溃安全证明。候选仅在outputs/physics-C-spring-only-diagnostic-20261117/delivery，ZIP SHA {sha(dest)}；报告docs/agent/physics-C-spring-only-diagnostic-20261117.md。需同当前Core同场景A22-vs-C实机FPS差值量化driver+VRD开销＋折腾安全验证；C不接受为正式、不覆盖接受包。

'''
    agents=ROOT/'AGENTS.md';text=agents.read_text('utf-8-sig');assert text.startswith('# 项目协作记忆\n');agents.write_text(text.replace('# 项目协作记忆\n','# 项目协作记忆\n\n'+note,1),encoding='utf-8',newline='\n')
    assert protected_files()==frozen
    new_json(LAB/'protected-after.json',protected_files())
    print(json.dumps({'status':verification['status'],'package':package,'report':str(report),'protectedFiles':len(frozen),'changedProductionFiles':0,
        'shipVrdWritesRemoved':decomposition[2]['vrdWritesA22']-decomposition[2]['vrdWritesC'],
        'shipDriverSolverCallsRemoved':decomposition[2]['driverSolverCallsA22']-decomposition[2]['driverSolverCallsC'],
        'shipRegularWritesPreserved':decomposition[2]['regularWritesC'],
        'sameCoreShipAliveA22eqC':samecore[2]['aliveA22Actual']==samecore[2]['aliveCActual'],
        'driverBoneWriteCaveat':'0 in test01 fixture (static control bones)'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()