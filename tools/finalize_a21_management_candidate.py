"""Finalize ONLY isolated A21 delivery and human-readable evidence; no installation."""
from pathlib import Path
import hashlib,json,shutil,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-A21-management-candidate-20261117'
from analyze_a19_hotpath_candidates import protected_files
from finalize_single_loader_accepted import check_config

def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def new_json(p,v):
    assert not p.exists(),str(p)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    frozen=read(LAB/'protected-before.json');assert protected_files()==frozen
    manifest=read(LAB/'candidate-manifest.json');entry=manifest['sources'][0]
    assert 'formalRelease' not in manifest and manifest['candidateOnly'] and not manifest['automaticallyInstalledOrDeployed']
    assert sha(LAB/'builder-snapshot.py')==manifest['templateSha256']['a21CandidateBuilder']
    assert sha(LAB/'A-source/physbone_runtime.lua')==entry['runtimeSha256']
    assert sha(LAB/'A-source/physbone_compat.lua')==entry['compatSha256']
    base=read(LAB/'probe-baseline/result.json');actual=read(LAB/'probe-actual-zip-final/result.json')
    checks=[]
    compare_keys=['label','frames','sessions','units','lastAttempted','lastChainTotal','staticChains','peakAngle','globalCallbackWriteTraceSha256']
    for variant in ['probe-candidate','probe-actual-zip-final']:
        other=read(LAB/variant/'result.json');assert len(base['phases'])==len(other['phases'])==5
        for b,n in zip(base['phases'],other['phases']):
            for k in compare_keys:assert b[k]==n[k],(variant,b['label'],k)
            delta={k:n['apiCalls'].get(k,0)-b['apiCalls'].get(k,0) for k in set(b['apiCalls'])|set(n['apiCalls']) if n['apiCalls'].get(k,0)!=b['apiCalls'].get(k,0)}
            assert set(delta)=={'Unit.alive'}
            checks.append(dict(variant=variant,phase=b['label'],callbackUnitOrderNodeValueShaEqual=True,healthCadenceAndCountsEqual=True,changedApiCalls=delta))
    source_receipt=read(LAB/'probe-actual-zip-final/sandbox-source-sha.json')
    assert not source_receipt['sourceSubstitutionAfterParser'] and not source_receipt['notCandidatePackageValidation']
    assert source_receipt['parsedCandidateSourceSha256']==source_receipt['executedSourceSha256']
    export=read(LAB/'release-candidate/export-verification.json');zip_path=LAB/'release-candidate/A-export/physics-runtime.zip'
    assert sha(zip_path)==export['zipSha256']==actual['actualCandidateZipSha256']
    assert actual['runtimeSha256']==entry['runtimeSha256'] and len(actual['checks'])==69
    gates=read(LAB/'release-candidate/gate-run.json');assert len(gates['tests'])==33 and all(r['returncode']==0 for r in gates['tests'])
    assert gates['inputs']['ARuntime']==entry['runtimeSha256'] and gates['inputs']['ACompat']==entry['compatSha256']
    for row in gates['tests']:
        assert sha(row['log'])==row['logSha256'] and sha(row['command'][3])==row['scriptSha256']
    installers=read(LAB/'release-candidate/A-formal-verification.json');assert len(installers['installers'])==6 and all(x['installDuplicateInstallUninstall'] for x in installers['installers'])
    sizes=read(LAB/'release-candidate/catalog-and-chef-size-tests.json');assert sizes['status'].startswith('PASS_')
    projection=read(LAB/'projection-verification.json');assert len(projection['results'])==2 and all(r['steps']==1303 and r['checks']==69436 for r in projection['results'])
    config=check_config();assert config==read(LAB/'baseline-consumer-and-config-revalidation.json')['configuration']
    deliver=LAB/'delivery';assert not deliver.exists();deliver.mkdir()
    dest=deliver/'物理运行时-单骨架-A-多人管理热路径优化-2.3.21-测试候选.zip';shutil.copyfile(zip_path,dest)
    assert sha(dest)==sha(zip_path)
    snapshots=LAB/'final-tool-snapshots';snapshots.mkdir()
    for name in ['build_a21_management_candidate.py','probe_a21_management_candidate.py','test_a21_projection_reuse.py','export_a21_management_candidate.py','run_a21_management_gates.py','finalize_a21_management_candidate.py']:
        shutil.copyfile(ROOT/'tools'/name,snapshots/name)
    package={'path':str(dest),'variant':'A','runtimeVersion':'2.3.21','compatVersion':'1.3.13','bytes':dest.stat().st_size,'sha256':sha(dest),'sourceSha256':entry['runtimeSha256']}
    comparisons=[]
    for b,n in zip(base['phases'],actual['phases']):
        comparisons.append({'phase':b['label'],'callbacks':b['frames'],'aliveBefore':b['apiCalls']['Unit.alive'],'aliveAfter':n['apiCalls']['Unit.alive'],'fixtureInstructionSamplesBefore':b['instructionSamples'],'fixtureInstructionSamplesAfter':n['instructionSamples'],'runtimeLineRangeSamplesBefore':b['runtimeInstructionSamples'],'runtimeLineRangeSamplesAfter':n['runtimeInstructionSamples']})
    verification={'status':'PASS_ISOLATED_A21_DELIVERABLE_OFFLINE_GATES_PENDING_REAL_GAME_PHYSICS_AND_FPS','package':package,'luaResourceBytes':export['luaResourceBytes'],'chefLimitBytes':4194304,'candidateZipScannedWithoutSourceSubstitution':True,'freshAGateCommands':33,'installerVmLoaderCases':6,'projectionDifferentialStepsPerVm':1303,'projectionDifferentialAssertionsPerVm':69436,'realModelLifecycleAssertions':69,'comparisons':comparisons,'exactTraceChecks':checks,'configuration':config,'consumerEvidence':read(LAB/'baseline-consumer-and-config-revalidation.json')['acceptedEvidenceRevalidated'],'fullFkRerunThisTurn':False,'protectedFiles':len(frozen),'protectedHashesUnchanged':True,'gameFpsMeasured':False,'mainProductionPromoted':False,'managerOrGameLaunched':False,'installedOrDeployed':False,'knownLimits':['No A21 game FPS/CPU/GPU frametime measurement','Unit.alive and instruction sampling reductions are not FPS','Private projection steady-state table allocation removed, GC time not measured','All health/prune/project work for remote sessions still exists; no excluded lightweight health ledger','Successful setter traces cover sample windows, not all transition/release/uninstall write timing','Projection and explicit cleanup probes are not a whole-runtime memory-leak proof','Full FK evidence rehashed against current inputs, not rerun; legacy suites use singleFormalPolicy=false']}
    new_json(LAB/'final-verification.json',verification)
    new_json(LAB/'delivery.json',{'status':verification['status'],'package':package,'verificationPath':str(LAB/'final-verification.json'),'verificationSha256':sha(LAB/'final-verification.json'),'productionBaseline':'A19/B20 unchanged; A21 candidate only','newUserFeedback':manifest['acceptedFeedback']['newUserWords']})
    report=ROOT/'docs/agent/physics-A21-management-candidate-20261117.md';assert not report.exists()
    report_text=f'''# A21 多人管理热路径优化：隔离测试候选

2026-11-17，Asia/Shanghai。**A2.3.21 / compat1.3.13 已生成可测试 ZIP，离线门禁通过；未获实机物理/FPS验收，不替换已接受 A19/B20。**

## 新证据与来源

用户本次确认：四名玩家使用 A 包时，经 CHEF 关闭物理插件至少回升15帧，达到不安装物理时的帧数。这支持优先优化“插件开启带来的额外成本”，而非把全部多人掉帧归因于游戏本体；没有给出开启/关闭绝对FPS或CPU/GPU frametime，不能把15 FPS直接换算成插件毫秒成本，也不能据此确定纯Lua求解/引擎姿态取样/管理/flush哪项主导。

两份附件是分析材料，其历史“只读”“下轮不实施”不是本次用户授权范围。本次依据用户继续优化请求制作隔离候选；材料没有授权覆盖根配置、重烘或部署。`Unit识别与性能对比.md` 首轮记载 A15/B16，不能当当前来源：本次以生产 manifest、实际接受 A19 ZIP及其 runtime SHA交叉确认，compat完整 SHA为 `{entry['compatSha256']}`。

## 实施范围

1. **有效会话单独派发**：沿用此前 `active-dispatch-r3` 已补五处清理的原型。每拍在消费者证明、Single策略/预览处理之后重建派发表；总 `runtime.sessions` 原样保留作发现、生命期、总链/峰值账本。任务中excluded队友和已证空消费者不再逐项走驱动分支。
2. **空消费者在派发前拒绝**：纯表 `hasWork` 判断位于派发表构建阶段，从而省去原先先alive再拒绝空工作的调用。未知消费者继续全量回退；driver-only继续由原hasWork决定，不用链数0冒充无工作。
3. **私有投影表复用**：原project每次分配的current、owned、seen、present、wrappers、sessions、added七张顶层表改为四张scratch表和两套三张输出表复用。首次创建池后，稳态不再新建这七张顶层表；新avatar clone/wrapper仍按原语义创建。每次project都重投影，不按frame缓存；同拍prepare/tick不同输入、avatar顺序、wrapper元表/身份、owner更新和预览替换均保留。scratch及退役输出立即清空，五处终结路径撤掉池拥有字段。

**未实施**远端轻量health账本、稀疏prune、减少本地步频、跨实例合并、Source/FP63映射或真裁骨。完整inventory→健康检查顺序、节点重建/换装发现和归还不改；peak仍扫描全会话，因为消费者unapply可能恢复旧rotations，不能从excluded标记推断可删。compat的Source2/T16/VRD/弹簧/作者参数/证书/所有TOC palette和未知回退完整字节不变；不追加Unit flush。

## 五阶段真实test01回放

实际A19/A21 ZIP、Chef1.4.1 parser/sandbox/starter、Lua5.1＋Chef纯Lua bit；identityWatch开启。每阶段600回调，以受控组件位移激励物理，**非实机战斗动画或FPS**。

|阶段|A19 Unit.alive|A21 Unit.alive|有效派发/拍|
|---|---:|---:|---:|
|单人任务|8582|6182|3|
|四人任务|21698|19298|3|
|四人舰船|34298|24698|12|
|四人再次任务|21698|19298|3|
|离队后单人|8582|6182|3|

四人任务alive调用减少约11.1%，舰船约28.0%，不是CPU耗时或FPS降幅。任务本地3个有效会话仍合计1800次solver/窗口，远端solver/成功setter/pendingDt均0；舰船本地1800＋远端5400，保留全队原舰船物理。会话仍7→28→28→28→7，总链、static、peak、healthFrames和逐会话状态与A19一致。

本轮重新采集的成功setter哈希包含**runtime callback帧、具体Unit、跨Unit写入顺序、节点和数值**，A21源码候选与实际A21 ZIP均与A19五窗口完全一致。切换/归还/卸载窗口之外的所有写入时序未作逐值等价声明。

全夹具1000指令一次的采样数，五阶段A19→A21依次为19620→19612、24246→23858、77299→76967、24244→23856、19638→19630；runtime行范围归属采样在部分单人阶段反而增加。采样包含夹具且不是CPU计时，不能选取多人下降数值宣称全面提速。投影表分配减少是结构/身份测试结论，**没有测到GC耗时降低，也没有证明已收回15帧**。

## 离线验证

- 实际应用导出器在隔离Core副本导出，不改正常Core：19802方法、身份/常量/引用零变，只有两物理资源替换；compat与A19完整字节一致。
- 实际A21 ZIP CRC/4成员/manifest/source/SHA通过，Lua资源 `{export['luaResourceBytes']:,}` B，小于4,194,304 B，余量 `{export['chefHeadroomBytes']:,}` B。Chef实际扫描后的源码SHA与执行SHA一致，**未在扫描后替换候选源码**，started/sandbox/实际成功setter/卸载已核。
- A-only33条回归命令通过：真实模型runtime四环境、inventory/epoch两VM、舰船/ADS/旧单骨架/多人两VM、4模型palette三环境及5种错误证书负控。旧单骨架/多人套件明确singleFormalPolicy=false，不冒充正式A真实模型证明。
- 6种VM/loader安装、重复安装、卸载组合通过；编码逐字段exact、旧超限包负控和4MiB含边界测试通过。
- 投影纯Lua差分两VM各1303步/69436断言通过，涵盖重复投影、乱序/移除/重加入、owner更新、预览数组替换、native __eq但不同表键、残键清理与固定池身份。
- 真实模型五阶段＋七类退出/恢复探针共69断言通过：World消失、inventory不可读、长加载空档、部件全消失但avatar在、solver无处理故障注入、owner离开仅剩无装备avatar、卸载；未新增dead Unit/stale World调用。这不是全runtime零引用/GC泄漏证明。
- 当前61profiles/39资源、真实bind/config/rig/driver/catalog/harness SHA门禁及旧290case/8,744,894逐值FK证据重新核验；**本轮没有重新跑完整FK**。本轮33命令与此前已接受49命令分别记录，不累加成新82套。
- 源/随包/正常根配置检查通过；根SHA仍ff64a88d7a0c786f600a3382db7cfec66a71b0c30e62b755eb2abd9ca413ced6，用户0.7/0.7/1及rotation_compensation=false完整保留。冻结清单{len(frozen)}文件SHA一致，范围见protected-before.json，不宣称全游戏文件扫描。

## 测试包与实机验收

- [A2.3.21 测试候选 ZIP](<{dest}>)，{dest.stat().st_size:,} B。
- ZIP SHA256：`{sha(dest)}`。
- [完整核验](<{LAB/'final-verification.json'}>)；[实际ZIP五阶段回放](<{LAB/'probe-actual-zip-final/result.json'}>)；[33命令记录](<{LAB/'release-candidate/gate-run.json'}>)；[逐行diff](<{LAB/'runtime.diff'}>)；[候选manifest](<{LAB/'candidate-manifest.json'}>)。

测试时只替换当前物理运行时配套，A19/A21共用owner/GUID不要同时启用；不需要重导模型、重烘动画或改根配置。先看舰船物理正常和首次ADS后本地物理确实生效，并确认Chef日志started 2.3.21。再在同一四人任务、同位置/视角/画质、稳定30–60秒窗口比较A19开/A21开/本物理关；记录三组绝对FPS和CPU/GPU frametime（若可用），保留进出队/重生/切图是否异常。FPS收益由这一步验收，不因离线绿灯标正式。

本轮仅新tools、隔离候选/回放/报告及协作记忆，未改production Lua/DLL/manifest、正常安装/活动配套、B20、根配置、库/profile、模型/GPU/动画或部署；未启动管理器/游戏，未覆盖已接受封档。候选留在隔离输出目录，不自动放入或勾选正常配套。
'''
    report.write_text(report_text,encoding='utf-8',newline='\n')
    (deliver/'测试说明.md').write_text(report_text,encoding='utf-8',newline='\n')
    before=LAB/'before-docs';before.mkdir();shutil.copyfile(ROOT/'AGENTS.md',before/'AGENTS.md')
    note=f'''## A21多人管理热路径测试候选（2026-11-17，未实机接受）

- 用户新证据：四人A经Chef关闭物理至少回升15FPS并回到无物理水平；支持优先插件开销，不据此推定纯Lua主导或精确毫秒成本。
- 从接受A19＋compat1.3.13生成隔离A2.3.21：active-dispatch-r3＋空消费者派发前拒绝＋project七顶层表改私有scratch/双缓冲。完整会话账本、每拍fresh inventory/健康/节点重建、peak/归还、自己stride1、全部compat数学/证书/catalog/bind/effective参数原样；没有远端轻量健康账本/裁骨/FP63映射。五处退出清理池/派发表。
- 实际新ZIP真导出/CRC/SHA、Chef扫描后无源码替换启动/成功writer/卸载通过；Lua3896968B低于4MiB。A-only33命令/6installer、两VM投影各1303步69436断言、真实test01五阶段＋清理69断言通过。五采样窗口成功写入含callback/Unit顺序/节点/数值SHA逐值同A19；health/solver/状态同，远端任务solver/writer0，本地1800。alive四人任务21698→19298，舰船34298→24698，非FPS；GC时间未测，单人runtime行采样有增加，不宣称已收回15帧。
- 61profiles/39资源当前bind/config与旧290case/8744894FK证据重核，不冒称本轮重跑完整FK。{len(frozen)}保护文件不变。根ff64/normal Core、production A19/B20/manifest、当前库/profile/模型/动画/活动配套与旧封档保持；未启动/导入/部署。
- 候选仅在outputs/physics-A21-management-candidate-20261117/delivery，ZIP SHA {sha(dest)}；报告docs/agent/physics-A21-management-candidate-20261117.md。需要同场景四人A19/A21/OFF实机物理与FPS验收，不能升级正式或覆盖接受包。

'''
    agents=ROOT/'AGENTS.md';text=agents.read_text('utf-8-sig');assert text.startswith('# 项目协作记忆\n');agents.write_text(text.replace('# 项目协作记忆\n','# 项目协作记忆\n\n'+note,1),encoding='utf-8',newline='\n')
    assert protected_files()==frozen
    new_json(LAB/'protected-after.json',protected_files())
    print(json.dumps({'status':verification['status'],'package':package,'report':str(report),'protectedFiles':len(frozen),'changedProductionFiles':0},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
