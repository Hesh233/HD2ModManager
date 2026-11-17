"""Finalize ONLY isolated A22 delivery and human-readable evidence; no installation.
A22 = A21 (active-dispatch-r3 + empty-consumer pre-alive rejection + private
projection double-buffer/scratch reuse) + non-writing-session health sampling.
Cross-round A21 probe data (same old-Core sandbox) isolates the health-sampling
increment; the actual A22 ZIP runs in the current normal Core which embeds the
Direct pipeline, so its net delta carries Core-baseline-shift discovery overhead
independent of A22. All disclosures are written into the report and receipts."""
from pathlib import Path
import hashlib,json,shutil,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'
A21LAB=ROOT/'outputs/physics-A21-management-candidate-20261117'
NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
from analyze_a19_hotpath_candidates import protected_files
from finalize_single_loader_accepted import check_config

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def new_json(p,v):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

CK=['label','frames','sessions','lastAttempted','lastChainTotal','staticChains','peakAngle','globalCallbackWriteTraceSha256']
UK=['unitId','localOwner','consumerMode','excluded','solverCalls','successfulWrites','writeTraceSha256','pendingDt']

def delta(x,y):
    ks=set(x['apiCalls'])|set(y['apiCalls'])
    return {k:y['apiCalls'].get(k,0)-x['apiCalls'].get(k,0) for k in ks if y['apiCalls'].get(k,0)!=x['apiCalls'].get(k,0)}

def main():
    frozen=read(LAB/'protected-before.json');assert protected_files()==frozen
    manifest=read(LAB/'candidate-manifest.json');entry=manifest['sources'][0]
    assert 'formalRelease' not in manifest and manifest['candidateOnly'] and not manifest['automaticallyInstalledOrDeployed']
    assert manifest['realGameAcceptanceStatus']=='A22-ISOLATED-TEST-CANDIDATE-PENDING-PHYSICS-FPS-AND-CHURN-SAFETY'
    assert sha(LAB/'builder-snapshot.py')==manifest['templateSha256']['a22CandidateBuilder']
    assert sha(LAB/'A-source/physbone_runtime.lua')==entry['runtimeSha256']
    assert sha(LAB/'A-source/physbone_compat.lua')==entry['compatSha256']
    base=read(LAB/'probe-baseline/result.json');cand=read(LAB/'probe-candidate/result.json');actual=read(LAB/'probe-actual-zip-final/result.json')
    assert len(base['phases'])==len(cand['phases'])==len(actual['phases'])==5
    assert len(base['checks'])==38 and len(cand['checks'])==len(actual['checks'])==175
    checks=[];comparisons=[]
    for b,c,a in zip(base['phases'],cand['phases'],actual['phases']):
        for k in CK:assert b[k]==c[k]==a[k],(b['label'],k)
        assert [u['unitId'] for u in b['units']]==[u['unitId'] for u in c['units']]==[u['unitId'] for u in a['units']],(b['label'],'unit order')
        bu={u['unitId']:u for u in b['units']};cu={u['unitId']:u for u in c['units']};au={u['unitId']:u for u in a['units']}
        for uid in bu:
            for k in UK:assert bu[uid][k]==cu[uid][k]==au[uid][k],(b['label'],uid,k)
            assert cu[uid]['healthFrames']==au[uid]['healthFrames'],(b['label'],uid,'healthFrames cand!=act')
        skel=delta(b,c);direct=delta(c,a);net=delta(b,a)
        # A22 candidate vs A19 baseline in the SAME old-Core sandbox: only the
        # health-sampling API trio changes (alive + node identity), all reduced.
        assert set(skel)=={'Unit.alive','Unit.has_node','Unit.num_scene_graph_items'},(b['label'],skel)
        assert all(v<0 for v in skel.values()),(b['label'],skel)
        assert net.get('Unit.alive',0)<0,(b['label'],net)
        nwb=sum(u['healthFrames'] for u in b['units'] if u['consumerMode']=='empty' or u['excluded'])
        nwc=sum(u['healthFrames'] for u in c['units'] if u['consumerMode']=='empty' or u['excluded'])
        checks.append(dict(phase=b['label'],callbackUnitOrderNodeValueShaEqual=True,perUnitSolverWriteStateEqual=True,healthFramesCandidateEqualsActual=True,skeletonDeltaCandidateMinusBaseline=skel,directPipelineOverheadActualMinusCandidate=direct,netAliveDeltaActualMinusBaseline=net.get('Unit.alive'),nonWritingHealthFramesBaseline=nwb,nonWritingHealthFramesCandidate=nwc))
        comparisons.append(dict(phase=b['label'],callbacks=b['frames'],aliveBaseline=b['apiCalls']['Unit.alive'],aliveCandidate=c['apiCalls']['Unit.alive'],aliveActualZip=a['apiCalls']['Unit.alive'],fixtureInstructionSamplesBaseline=b['instructionSamples'],fixtureInstructionSamplesCandidate=c['instructionSamples'],fixtureInstructionSamplesActual=a['instructionSamples'],runtimeLineRangeSamplesBaseline=b['runtimeInstructionSamples'],runtimeLineRangeSamplesCandidate=c['runtimeInstructionSamples'],runtimeLineRangeSamplesActual=a['runtimeInstructionSamples']))
    # Cross-round reference: A21 candidate in the SAME old-Core sandbox isolates the
    # health-sampling increment (A22-A21) from the A21 dispatch/projection step (A21-A19).
    a21base=read(A21LAB/'probe-baseline/result.json');a21cand=read(A21LAB/'probe-candidate/result.json')
    assert a21base['runtimeSha256']==base['runtimeSha256'],'A21/A22 must share the A19 baseline reference'
    for p1,p2 in zip(a21base['phases'],base['phases']):
        for k in CK:assert p1[k]==p2[k],('A21-base!=A22-base',p1['label'],k)
    health_only=[]
    for p1,p2 in zip(a21cand['phases'],cand['phases']):
        assert p1['globalCallbackWriteTraceSha256']==p2['globalCallbackWriteTraceSha256'],('A21/A22 global write trace',p1['label'])
        u1={u['unitId']:u for u in p1['units']};u2={u['unitId']:u for u in p2['units']}
        assert set(u1)==set(u2)
        for uid in u1:
            assert u1[uid]['writeTraceSha256']==u2[uid]['writeTraceSha256'],('A21/A22 unit write trace',p1['label'],uid)
            for k in ['solverCalls','successfulWrites','consumerMode','excluded','pendingDt','localOwner']:assert u1[uid][k]==u2[uid][k],(p1['label'],uid,k)
        health_only.append(dict(phase=p1['label'],a19Alive=next(x['apiCalls']['Unit.alive'] for x in base['phases'] if x['label']==p1['label']),a21Alive=p1['apiCalls']['Unit.alive'],a22Alive=p2['apiCalls']['Unit.alive'],a21MinusA19=p1['apiCalls']['Unit.alive']-next(x['apiCalls']['Unit.alive'] for x in base['phases'] if x['label']==p1['label']),healthSamplingOnlyA22MinusA21=p2['apiCalls']['Unit.alive']-p1['apiCalls']['Unit.alive']))
    # Actual ZIP receipt: parsed candidate source == executed source proves NO real
    # post-parse substitution. sourceSubstitutionAfterParser is a variant LABEL
    # (True for dispatch-sampled-health), not evidence of a swap; do not assert it false.
    source_receipt=read(LAB/'probe-actual-zip-final/sandbox-source-sha.json')
    assert source_receipt['parsedCandidateSourceSha256']==source_receipt['executedSourceSha256']
    assert not source_receipt['notCandidatePackageValidation']
    export=read(LAB/'release-candidate/export-verification.json');zip_path=LAB/'release-candidate/A-export/physics-runtime.zip'
    assert sha(zip_path)==export['zipSha256']==actual['actualCandidateZipSha256']
    assert actual['runtimeSha256']==entry['runtimeSha256']
    assert export['luaResourceBytes']<4194304 and export['chefHeadroomBytes']==4194304-export['luaResourceBytes']
    assert export['compatByteIdentical'] and export['frozenNormalCoreCodeChanged'] is False and export['productionSourceChanged'] is False
    assert export['normalCoreSha256']=='575e97b57b2fbb6130b9bf4b5a08c7af16422ca55f08758ea2c718634e5aeb47'
    assert export['coreChangedResources']==['HD2ModCore.PhysBone.physbone_runtime.lua']
    assert export['compatAlreadyEmbeddedInNormalCore'] and export['normalCoreBaselineShiftSinceA21'] and export['addonRuntimeWrapper']=='SkeletonRuntime'
    audit=read(LAB/'release-candidate/A-core-audit.json')
    assert audit['beforeSha256'].lower()==sha(NORMAL/'HD2ModCore.dll') and audit['identityUnchanged']
    assert not audit['changedMethods'] and not audit['changedConstants'] and not audit['changedReferences']
    assert audit['methodsBefore']==audit['methodsAfter']==19281 and audit['resourcesBefore']==audit['resourcesAfter']==42
    assert audit['changedResources']==['HD2ModCore.PhysBone.physbone_runtime.lua']
    gates=read(LAB/'release-candidate/gate-run.json');assert len(gates['tests'])==33 and all(r['returncode']==0 for r in gates['tests'])
    assert gates['status']=='PASS_33_CORRECTION_CANDIDATE_GATES_NOT_GAME_FPS'
    assert gates['inputs']['ARuntime']==entry['runtimeSha256'] and gates['inputs']['ACompat']==entry['compatSha256']
    for row in gates['tests']:
        assert sha(row['log'])==row['logSha256'] and sha(row['command'][3])==row['scriptSha256']
    installers=read(LAB/'release-candidate/A-formal-verification.json');assert len(installers['installers'])==6 and all(x['installDuplicateInstallUninstall'] for x in installers['installers'])
    assert installers['resourcesChanged']==1 and installers['methodsChanged']==0 and installers['originalMathAndProfilesBodyUnchanged']
    sizes=read(LAB/'release-candidate/catalog-and-chef-size-tests.json');assert sizes['status'].startswith('PASS_')
    projection=read(LAB/'projection-verification.json');assert len(projection['results'])==2 and all(r['steps']==1303 and r['checks']==69436 for r in projection['results'])
    config=check_config();assert config==read(LAB/'baseline-consumer-and-config-revalidation.json')['configuration']
    reval=read(LAB/'baseline-consumer-and-config-revalidation.json')['acceptedEvidenceRevalidated']
    deliver=LAB/'delivery';assert not deliver.exists();deliver.mkdir()
    dest=deliver/'物理运行时-单骨架-A-管理热路径与判活降频-2.3.22-测试候选.zip';shutil.copyfile(zip_path,dest)
    assert sha(dest)==sha(zip_path)
    snapshots=LAB/'final-tool-snapshots';snapshots.mkdir()
    for name in ['build_a22_health_sampling_candidate.py','probe_a22_health_sampling_candidate.py','test_a22_projection_reuse.py','export_a22_health_sampling_candidate.py','run_a22_health_sampling_gates.py','finalize_a22_health_sampling_candidate.py']:
        shutil.copyfile(ROOT/'tools'/name,snapshots/name)
    package={'path':str(dest),'variant':'A','runtimeVersion':'2.3.22','compatVersion':'1.3.13','bytes':dest.stat().st_size,'sha256':sha(dest),'sourceSha256':entry['runtimeSha256']}
    verification={'status':'PASS_ISOLATED_A22_DELIVERABLE_OFFLINE_GATES_PENDING_REAL_GAME_PHYSICS_FPS_AND_CHURN_SAFETY','package':package,'luaResourceBytes':export['luaResourceBytes'],'chefLimitBytes':4194304,'chefHeadroomBytes':export['chefHeadroomBytes'],'candidateZipScannedWithoutRealSourceSubstitution':True,'parsedEqualsExecutedSourceSha256':source_receipt['executedSourceSha256'],'freshAGateCommands':33,'installerVmLoaderCases':6,'projectionDifferentialStepsPerVm':1303,'projectionDifferentialAssertionsPerVm':69436,'realModelLifecycleAssertions':175,'comparisons':comparisons,'exactTraceChecks':checks,'healthSamplingOnlyDecomposition':health_only,'configuration':config,'consumerEvidence':reval,'normalCore':{'sha256':export['normalCoreSha256'],'methods':19281,'resources':42,'changedResources':['HD2ModCore.PhysBone.physbone_runtime.lua'],'runtimeWrapper':'SkeletonRuntime','compatAlreadyEmbedded':True,'baselineShiftSinceA21':True,'note':export['normalCoreBaselineNote']},'fullFkRerunThisTurn':False,'protectedFiles':len(frozen),'protectedHashesUnchanged':True,'gameFpsMeasured':False,'mainProductionPromoted':False,'managerOrGameLaunched':False,'installedOrDeployed':False,'healthSamplingSafety':manifest['healthSamplingSafety'],'knownLimits':['No A22 game FPS/CPU/GPU frametime measurement','Unit.alive and instruction sampling reductions are not FPS','TEST-ONLY candidate: offline call-count/write equivalence is NOT a crash-safety proof; real-device churn (rebuild/换装/重生/切图/进出队) validation required before any acceptance','Stable non-writing sessions widen node-rebuild detection latency from <=30 to <=900 frames','Residual ordering gap: per-frame prune runs before RemotePhysics.bind, so the transition callback itself can drive once before the forced mode/exclusion re-check (baseline has the same ordering but <=30-frame detection while excluded)','A pre-write identity guard to fully close the ordering gap is NOT implemented','Actual A22 ZIP runs in the current normal Core which embeds the Direct pipeline (manager-repair-1.01-sync round); net alive delta vs the A19 old-Core baseline carries Direct discovery overhead independent of A22','Pure health-sampling increment is isolated by the cross-round A22-A21 same-old-Core-sandbox reference, not by the actual-ZIP net figure','Private projection steady-state table allocation removed, GC time not measured','Writing-session per-frame health and pre-write alive unchanged; no excluded lightweight health ledger, no real bone culling, no FP63 mapping','Successful setter traces cover sample windows (callback frame/Unit/order/node/value), not all transition/release/uninstall write timing','Projection and explicit cleanup probes are not a whole-runtime memory-leak proof','Full FK evidence rehashed against current inputs, not rerun; legacy suites use singleFormalPolicy=false','Normal Core baseline shifted since A21 (ce3a3c40/19802/39 -> 575e97b5/19281/42); A22 export changes only the runtime resource']}
    new_json(LAB/'final-verification.json',verification)
    new_json(LAB/'delivery.json',{'status':verification['status'],'package':package,'verificationPath':str(LAB/'final-verification.json'),'verificationSha256':sha(LAB/'final-verification.json'),'productionBaseline':'A19/B20 accepted unchanged; A21 candidate preserved; A22 candidate only','newUserFeedback':manifest['acceptedFeedback']['newUserWords'],'healthSamplingSafety':manifest['healthSamplingSafety']})
    # ---- report ----
    rows=[]
    for h in health_only:
        rows.append(f"|{h['phase']}|{h['a19Alive']}|{h['a21Alive']}|{h['a22Alive']}|{h['a21MinusA19']}|{h['healthSamplingOnlyA22MinusA21']}|")
    alive_table='\n'.join(rows)
    act_rows=[]
    for c0 in comparisons:
        act_rows.append(f"|{c0['phase']}|{c0['aliveBaseline']}|{c0['aliveCandidate']}|{c0['aliveActualZip']}|{c0['aliveActualZip']-c0['aliveCandidate']}|{c0['aliveActualZip']-c0['aliveBaseline']}|")
    act_table='\n'.join(act_rows)
    instr_rows=[]
    for c0 in comparisons:
        instr_rows.append(f"|{c0['phase']}|{c0['fixtureInstructionSamplesBaseline']}|{c0['fixtureInstructionSamplesCandidate']}|{c0['fixtureInstructionSamplesActual']}|{c0['runtimeLineRangeSamplesBaseline']}|{c0['runtimeLineRangeSamplesCandidate']}|{c0['runtimeLineRangeSamplesActual']}|")
    instr_table='\n'.join(instr_rows)
    hf_rows=[]
    for ck in checks:
        hf_rows.append(f"|{ck['phase']}|{ck['nonWritingHealthFramesBaseline']}|{ck['nonWritingHealthFramesCandidate']}|")
    hf_table='\n'.join(hf_rows)
    report=ROOT/'docs/agent/physics-A22-health-sampling-candidate-20261117.md';assert not report.exists()
    report_text=f'''# A22 管理热路径＋非写入会话判活降频：隔离测试候选

2026-11-17，Asia/Shanghai。**A2.3.22 / compat1.3.13 已生成可测试 ZIP，离线门禁通过；未获实机物理/FPS/折腾安全验收，不替换已接受 A19/B20，也不覆盖 A21 候选。这是仅测试候选，离线等价不是崩溃安全证明。**

## 用户请求与范围

用户本次原文：「{manifest['acceptedFeedback']['newUserWords']}」。据此先迭代 A 包（A22），再打只实现弹簧骨骼的 C 诊断包（另轮）。A22 范围按用户拍板「按现原型纳入（仅测试）」：在 A21 基础上原样纳入非写入会话判活降频原型，**保留 ≤900 帧重建检测延迟与残留的切换回调顺序缺口**，明确标注仅测试、非崩溃安全证明、接受前须实机折腾验证。用户没有选择先做写前身份守卫，也没有选择停留在 A21 安全范围。

## 最新物理实现与正常 Core 基线漂移

当前正常 manager-1.0.7 的 Core 已不是 A21 导出时的基线。manager-repair-1.01-sync 轮已把 A21/compat1.3.13 与 direct-v1（上游 2.1.45）成套同步进正常 Core：现 Core SHA `{export['normalCoreSha256']}`，19281 方法、672 常量、42 资源，runtime 以 `local SkeletonRuntime = (function()` 包裹，并经 `PhysicsRoutes.new(PhysBoneCompat,SkeletonRuntime,DirectCompat,DirectRuntime)` 路由；compat1.3.13 已内嵌。A21 当时导出基线为 ce3a3c40/19802 方法/39 资源、runtime 包裹名 `PhysBoneRuntime`、无 Direct 路由。

因此 **A22 导出只替换一个 runtime 资源**（A21→A22），compat/路由/Direct/消费者/catalog 全部沿用正常 Core，身份/常量/引用零变。交付 ZIP 的 addon 由源码 Lua 决定，与 Core IL 无关；但 addon 内含 Direct 管线，会在每拍做发现取样（World.units/units_by_resource/has_animation_state_machine/world_position/debug_camera_pose/time_since_launch/Application.worlds/alive/has_node/num_scene_graph_items），对骨架路由模型不写任何骨。这部分开销独立于 A22，见下方分解。

## 实施范围（A22 = A21 ＋ 判活降频）

1. **沿用 A21 三项**：有效会话单独派发（active-dispatch-r3，五处退出清理）、空消费者在派发前拒绝（纯表 hasWork，省去先 alive 再拒绝）、私有投影七顶层表改四 scratch＋两套三输出双缓冲复用（稳态不再新建顶层表，每次 project 仍重投影，退役即清空）。
2. **新增非写入会话判活降频**：非写入会话（`consumerMode=="empty"` 或 `singleRemotePhysicsExcluded==true`）保留每拍指针成员 prune；`Unit.alive`＋节点身份（has_node/num_scene_graph_items）改为每 30 帧采样一次。消费者模式/排除标记变化时**立即强制全量健康检查并对齐 cadence 计数器**，使该次 session_health 同时跑节点身份重检。写入会话与写前 alive 重检完全不变。

**未实施**：写前身份守卫（完全闭合顺序缺口所需）、远端轻量 health 账本、稀疏 prune、减少本地 stride1、跨实例合并、Source/FP63 映射、真裁骨。完整 inventory→健康顺序、节点重建/换装发现与归还、peak 全会话扫描不改。compat 的 Source2/T16/VRD/弹簧/作者参数/证书/所有 TOC palette/未知回退完整字节不变（compat SHA `{entry['compatSha256']}`）；不追加 Unit flush。

## 判活降频安全缺口（必须实机验证）

- **稳定非写入会话**的节点重建检测延迟从 ≤30 帧放宽到 **≤900 帧**（30 帧采样 × 30 帧 identityEvery）。模式/排除变化本身在变化后第一次 prune 即被捕获（探针 ≤2 帧）。
- **残留顺序缺口**：每拍 prune 在 `RemotePhysics.bind` 之前运行，所以切换回调本身可能在强制重检之前先驱动一次。基线有相同结构顺序，但排除期间 ≤30 帧即检测到重建；A22 排除期间放宽到 ≤900 帧。完全闭合需要写前身份守卫，**本轮未实施**。
- 离线调用计数/写入等价**不是崩溃安全证明**。2026-11-01 的挂起正是越界节点索引野写所致；接受前必须在实机做重建/换装/重生/切图/进出队折腾验证。

## 五阶段真实 test01 回放与三口径分解

实际 Chef1.4.1 parser/sandbox、Lua5.1＋Chef 纯 Lua bit、identityWatch 开。每阶段 600 回调，受控组件位移激励物理，**非实机战斗动画或 FPS**。基线/候选在**同一旧 Core 沙箱**（loader-size-fix lab，无 Direct）；实际 ZIP 在**当前正常 Core**（含 Direct）。

### 口径一：同旧 Core 沙箱 A19→A21→A22（隔离每步增量）

跨轮引用已完成的 A21 探针（同一 A19 基线、同沙箱、同夹具；已核 A21 基线==A22 基线、A21 候选与 A22 候选逐 Unit 写入哈希/solver/成功写/状态完全一致）。`Unit.alive` 调用数：

|阶段|A19基线|A21候选|A22候选|A21−A19(派发/投影/空拒绝)|A22−A21(判活降频单独)|
|---|---:|---:|---:|---:|---:|
{alive_table}

判活降频**单独**增量：四人任务 alive −14500、舰船 −9280、单人 −2320。这是本轮新增优化的受控效果，不含 Direct 开销。A21−A19 是上一轮派发/投影/空拒绝增量（四人 −2400、舰船 −9600）。

### 口径二：实际 A22 ZIP（当前正常 Core，含 Direct）vs 同沙箱候选/旧基线

|阶段|A19旧Core基线|A22旧Core候选|A22实际ZIP|Direct开销(实际−候选)|净(实际−A19基线)|
|---|---:|---:|---:|---:|---:|
{act_table}

**Direct 管线发现开销独立于 A22**：实际 ZIP 比同沙箱候选每阶段多 alive +2600(单人)/+7400(四人/舰船)，以及 has_node/num_scene_graph_items/world_position/World.units 等发现调用。这是因为交付 ZIP 基于当前正常 Core 构建（已内嵌 Direct），而基线/候选沙箱用旧 Core（无 Direct）。净 alive 下降（四人 −9500、舰船 −11480、单人 −2120）是「A22 判活降频＋A21 派发」减去「Direct 发现开销」后相对 A19 旧 Core 基线的结果，**不是 A22 单独效果，也不是 FPS**。本轮没有重探 A19-在-当前正常-Core 的同 Core 参照，故净口径以旧 Core A19 为基线并显式标注 Direct 开销。

### 非写入会话 healthFrames（每拍→采样）

|阶段|A19基线|A22候选|
|---|---:|---:|
{hf_table}

非写入会话健康检查帧数大幅下降（如四人任务 36557→1952），写入会话 healthFrames 与写前 alive 不变。逐 Unit 的 unitId/localOwner/consumerMode/excluded/solverCalls/successfulWrites/writeTraceSha256/pendingDt 在基线/候选/实际三者完全一致；候选与实际 healthFrames 一致；总链/static/peak/全局回调写入哈希一致。

### 指令采样（含夹具，非 CPU 计时）

|阶段|全夹具基线|全夹具候选|全夹具实际|runtime行基线|runtime行候选|runtime行实际|
|---|---:|---:|---:|---:|---:|---:|
{instr_table}

全夹具指令采样每 1000 指令一次：候选比基线下降（四人 24246→22939、舰船 77299→76468），但实际 ZIP 因 Direct 开销回升（四人→26078、舰船→79608）。runtime 行范围归属采样在部分单人阶段反而增加。**采样含夹具且不是 CPU 计时，不能选取下降数值宣称全面提速或已收回帧数。** 投影表分配减少是结构/身份结论，未测 GC 耗时。

## 离线验证

- 实际应用导出器在隔离 Core 副本导出，不改正常 Core：19281 方法、身份/常量/引用零变，**只替换一个 runtime 资源**；compat 与正常 Core 内嵌字节一致。正常 Core SHA 锁定 `{export['normalCoreSha256']}`。
- 实际 A22 ZIP CRC/4 成员/manifest/source/SHA 通过，Lua 资源 `{export['luaResourceBytes']:,}` B < 4,194,304 B，余量 `{export['chefHeadroomBytes']:,}` B。Chef 实际扫描后**解析源码 SHA==执行源码 SHA**（`{source_receipt['executedSourceSha256']}`），证明未在扫描后真实替换候选源码（`sourceSubstitutionAfterParser` 仅是 variant 标签，非真实 swap 证据）；started/sandbox/实际成功 setter/卸载已核，`notCandidatePackageValidation=False`。
- A-only 33 条回归命令通过：真实模型 runtime 四环境（含 chef-patch 实际 ZIP）、inventory/epoch 两 VM、舰船/ADS/旧单骨架/多人两 VM、4 模型 palette 三环境及 5 种错误证书负控。路由适配：冻结夹具经隔离快照从 `skeletonRuntime` upvalue 恢复 FORMAL_PHYSICS_VARIANT（同一常量，忠实），不改原夹具。旧单骨架/多人套件明确 singleFormalPolicy=false，不冒充正式 A 真实模型证明。
- 6 种 VM/loader 安装、重复安装、卸载组合通过；编码逐字段 exact、旧超限包负控和 4MiB 含边界测试通过（246765 检查）。
- 投影纯 Lua 差分两 VM 各 1303 步/69436 断言通过，涵盖重复投影、乱序/移除/重加入、owner 更新、预览数组替换、native __eq 但不同表键、残键清理与固定池身份。
- 真实模型五阶段＋七类退出/恢复＋投影身份/池分离探针共 175 断言通过：World 消失、inventory 不可读、长加载空档、部件全消失但 avatar 在、solver 无处理故障注入、owner 离开仅剩无装备 avatar、卸载、投影池退役清空/终结分离；未新增 dead Unit/stale World 调用。这不是全 runtime 零引用/GC 泄漏证明。
- 当前 61profiles/39 资源、真实 bind/config/rig/driver/catalog/harness SHA 门禁及旧 290case/8,744,894 逐值 FK 证据重新核验；**本轮没有重新跑完整 FK**。本轮 33 命令与此前已接受 49 命令分别记录，不累加成新 82 套。
- 源/随包/正常根配置检查通过；根 SHA 仍 ff64a88d7a0c786f600a3382db7cfec66a71b0c30e62b755eb2abd9ca413ced6，用户 0.7/0.7/1 及 rotation_compensation=false 完整保留。冻结清单 {len(frozen)} 文件 SHA 一致，范围见 protected-before.json，不宣称全游戏文件扫描。

## 测试包与实机验收

- [A2.3.22 测试候选 ZIP](<{dest}>)，{dest.stat().st_size:,} B。
- ZIP SHA256：`{sha(dest)}`。
- [完整核验](<{LAB/'final-verification.json'}>)；[实际 ZIP 五阶段回放](<{LAB/'probe-actual-zip-final/result.json'}>)；[33 命令记录](<{LAB/'release-candidate/gate-run.json'}>)；[逐行 diff](<{LAB/'runtime.diff'}>)；[候选 manifest](<{LAB/'candidate-manifest.json'}>)。

测试时只替换当前物理运行时配套，A19/A21/A22 共用 owner/GUID 不要同时启用；不需要重导模型、重烘动画或改根配置。先看舰船物理正常和首次 ADS 后本地物理确实生效，并确认 Chef 日志 started 2.3.22。**重点折腾验证**：在四人任务/舰船反复进出队、重生、切图、换装、部件重建，观察非写入队友会话是否出现卡死/野写/姿态异常（判活降频把稳定非写入会话重建检测放宽到 ≤900 帧，且残留切换回调顺序缺口）。再在同一四人任务、同位置/视角/画质、稳定 30–60 秒窗口比较 A19开/A21开/A22开/本物理关；记录各组绝对 FPS 和 CPU/GPU frametime（若可用）。注意当前正常 Core 已含 Direct 管线，A22 与 A21 都在该 Core 下运行，比较应同 Core 口径。FPS 收益与折腾安全由这一步验收，不因离线绿灯标正式。

本轮仅新 tools、隔离候选/回放/报告及协作记忆，未改 production Lua/DLL/manifest、正常安装/活动配套、B20、A21 候选、根配置、库/profile、模型/GPU/动画或部署；未启动管理器/游戏，未覆盖已接受封档。候选留在隔离输出目录，不自动放入或勾选正常配套。
'''
    report.write_text(report_text,encoding='utf-8',newline='\n')
    (deliver/'测试说明.md').write_text(report_text,encoding='utf-8',newline='\n')
    before=LAB/'before-docs';before.mkdir();shutil.copyfile(ROOT/'AGENTS.md',before/'AGENTS.md')
    note=f'''## A22管理热路径＋判活降频测试候选（2026-11-17，未实机接受）

- 用户原文「先找出最新的物理实现，按照优化方向迭代A包。之后打一个和主线一样只实现弹簧骨骼的c包，用于排除driver骨测试性能差距」；A22范围按拍板「按现原型纳入（仅测试）」，保留≤900帧重建延迟与切换回调顺序缺口，仅测试非崩溃安全证明。C包另轮。
- 正常Core基线已漂移：manager-repair-1.01-sync轮把A21/compat1.3.13＋direct-v1(上游2.1.45)同步进正常Core（575e97b5/19281方法/42资源，SkeletonRuntime包裹＋PhysicsRoutes路由，compat已内嵌）。A22导出只替换一个runtime资源(A21→A22)，身份/常量/引用零变；A21旧基线ce3a3c40/19802/39无Direct。
- A22=A21三项(active-dispatch-r3五处清理/空消费者派发前拒绝/投影七表改scratch双缓冲)＋非写入会话(empty或excluded)判活降频：保留每拍指针prune，alive＋节点身份每30帧采样，模式/排除变化立即强制全量健康并对齐cadence；写入会话与写前alive不变。未做写前身份守卫/轻量health账本/裁骨/FP63。compat完整字节不变(3530bd37)。
- 安全缺口：稳定非写入会话重建检测≤30→≤900帧；prune在bind前致切换回调可先驱动一次(基线同顺序但≤30帧检测)；写前身份守卫未实施；离线等价非崩溃安全证明，接受前须实机折腾(重建/换装/重生/切图/进出队)验证。
- 三口径分解(同旧Core沙箱A19→A21→A22隔离增量)：判活降频单独alive四人−14500/舰船−9280/单人−2320；A21−A19四人−2400/舰船−9600。实际A22ZIP在当前正常Core含Direct，比同沙箱候选多alive+2600(1p)/+7400(4p/舰船)发现开销(独立于A22)；净vs A19旧Core基线四人−9500/舰船−11480/单人−2120，非A22单独效果非FPS。非写入healthFrames四人36557→1952。逐Unit写入哈希/solver/成功写/状态基线==候选==实际，候选==实际healthFrames，总链/static/peak/全局写入哈希一致；跨轮核A21候选==A22候选写入。指令采样含夹具非CPU计时，实际因Direct回升，不宣称提速/收回帧。
- 实际ZIP真导出/CRC/SHA、Chef扫描后解析==执行源码SHA(8b1c9bf6)无真实替换、started/成功writer/卸载通过；Lua4090736B<4MiB余量103568B。A-only33命令(路由快照从skeletonRuntime upvalue恢复VARIANT)/6installer、两VM投影各1303步69436断言、真实test01五阶段＋清理＋投影身份175断言通过。61profiles/39资源当前bind/config与旧290case/8744894FK证据重核，不冒称重跑全FK。{len(frozen)}保护文件不变。根ff64/normal Core、production A19/B20/manifest、A21候选、当前库/profile/模型/动画/活动配套与旧封档保持；未启动/导入/部署/Git。
- 候选仅在outputs/physics-A22-health-sampling-candidate-20261117/delivery，ZIP SHA {sha(dest)}；报告docs/agent/physics-A22-health-sampling-candidate-20261117.md。需要同场景四人A19/A21/A22/OFF实机物理与FPS＋折腾安全验收，不能升级正式或覆盖接受包。

'''
    agents=ROOT/'AGENTS.md';text=agents.read_text('utf-8-sig');assert text.startswith('# 项目协作记忆\n');agents.write_text(text.replace('# 项目协作记忆\n','# 项目协作记忆\n\n'+note,1),encoding='utf-8',newline='\n')
    assert protected_files()==frozen
    new_json(LAB/'protected-after.json',protected_files())
    print(json.dumps({'status':verification['status'],'package':package,'report':str(report),'protectedFiles':len(frozen),'changedProductionFiles':0,'healthSamplingOnlyFourPlayerAliveDelta':health_only[1]['healthSamplingOnlyA22MinusA21'],'directOverheadFourPlayerAlive':checks[1]['directPipelineOverheadActualMinusCandidate'].get('Unit.alive')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()