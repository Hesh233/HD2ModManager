"""Deliver two new A/B ZIPs and docs only; preserve the user's installation."""
from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-test01-remote-ab-20261116';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before=json.loads((OUT/'protected-before.json').read_text('utf8'))
changed=[p for p,h in before.items() if not Path(p).is_file() or sha(Path(p))!=h]
assert not changed, 'User/model/source state changed; never restore it: '+str(changed)
packages=json.loads((OUT/'packages-verification.json').read_text('utf8'));assert packages['status']=='PASS_BOTH_ACTUAL_ZIPS_OFFLINE'
assert json.loads((OUT/'source-route-gate-verification.json').read_text('utf8'))['poisonedRemoteVrdRulesNeverEvaluated']
real={v:json.loads((OUT/(v+'-real-test01-verification.json')).read_text('utf8')) for v in ['A','B']}
for v,r in real.items():assert r['status'].startswith('PASS_') and r['localOutputAndStateExactlyPreserved']
for v in ['A','B']:
 for vm in ['lua51','luajit21']:
  assert '68 checks, 0 failures' in (OUT/(v+'-'+vm+'-single-remote-policy-test.lua-actual-extracted.log')).read_text('utf8')
  for name,count in [('single-mainline-regression-test.lua',87),('multiplayer-skeleton-regression-test.lua',51)]:
   assert str(count)+' checks, 0 failures' in (OUT/(v+'-'+vm+'-'+name+'-full-policy.log')).read_text('utf8')
names={'A':'物理运行时-A-单骨架仅自己物理-2.3.9-r1-待实测.zip','B':'物理运行时-B-单骨架队友保留物理禁VRD-2.3.10-r1-待实测.zip'}
zipdir=NORMAL/'非运行文件/测试包';docdir=NORMAL/'非运行文件/说明文档';zipdir.mkdir(parents=True,exist_ok=True);docdir.mkdir(parents=True,exist_ok=True)
for target in [zipdir,docdir]:assert target.resolve().is_relative_to(ROOT.resolve())
report_path=ROOT/'docs/agent/physics-test01-remote-ab-20261116.md';readme_path=docdir/'单骨架多人性能AB测试说明-20261116.md'
assert not report_path.exists() and not readme_path.exists()
assert all(not (zipdir/name).exists() for name in names.values())
assert '## test01 多人性能 A/B 两包' not in (ROOT/'AGENTS.md').read_text('utf8')
records=[]
for v,name in names.items():
 source=OUT/(v+'-export/physics-runtime.zip');target=zipdir/name
 with target.open('xb') as f:f.write(source.read_bytes())
 proof=next(r for r in packages['reports'] if r['variant']==v);assert sha(target)==sha(source)==proof['zipSha256']
 records.append({'variant':v,'path':str(target),'runtimeVersion':proof['versions']['runtime'],'compatVersion':'1.3.8','bytes':target.stat().st_size,'sha256':sha(target)})
links={v:'['+names[v]+'](<'+(zipdir/names[v]).as_posix()+'>)' for v in names}
logroot=Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2')
readme=f'''# 单骨架 test01 多人性能 A/B 测试

**两个独立测试包；不是帧率已修复的正式版。正常程序、原 R2、模型/动画和用户配置未覆盖。**

|包|版本|玩家自己|其他玩家的单骨架人物|
|---|---|---|---|
|A：{links['A']}|runtime 2.3.9 / compat 1.3.8|原 R2 物理、VRD、参数和步长保持|跳过完整 Lua 物理更新：弹簧和 VRD 均停算|
|B：{links['B']}|runtime 2.3.10 / compat 1.3.8|原 R2 物理、VRD、参数和步长保持|原物理/近远调度保持，只停 VRD 控制读取、规则求值和写入|

范围仅本次单骨架路线。不停止对方动画或游戏原生物理，不优化或停算双骨架/native/direct。

## 测试步骤

1. **完整退出游戏，每轮只启用 A 或 B 中的一份物理**，停用 R2/r4 等其它物理运行时。两个包保持同一 physics owner/GUID，不能同时开启比较；Chef 只跑最后一份并不等于两种模式同时生效。
2. 手动导入指定 ZIP、选择这一份物理并点“应用”，再完整启动游戏。test01 模型和动画保持原样，**无需重导、重绑或重烘**。本次没有替你导入、应用或部署。
3. 统计前短暂切到**第一人称瞄准约 1 秒**，让原主线身份逻辑确认自己；日志应为 `identity=fp-confirmed`。多人仍为 `ambiguous-aim-first-person` 时，为避免误停自己暂时保留全部处理，**该段不能用于判定 A/B**。单一 avatar 不误停唯一人物；自己死亡后不把幸存队友自动认成自己。
4. 同一个 test01、同地图/位置/视角/画质分别测 **1→2→4 人**，每阶段建议 120 秒。记录第二/第三/第四人进入的准确时间，不只比较两次不同战况或加载过程。
5. 切另一包须退出游戏、重新应用和完整启动；已运行 Lua 不会因勾选变化自动热切换。每轮录制 20 分钟，之后只停日志，物理模式继续有效。

## 需要回传

- A 实际日志：`{(logroot/'hd2physbone_test01_A_perf.log').as_posix()}`
- B 实际日志：`{(logroot/'hd2physbone_test01_B_perf.log').as_posix()}`
- 同会话 `chef_loader.log`、各人数段实际 FPS/1% low，最好附现有便携 PresentMon CSV：[实际FPS采集说明](<{(NORMAL/'非运行文件/实际FPS采集/实际FPS采集说明.md').as_posix()}>)。

确认头部 `variant=A/B` 和版本。看 `selfUnits/selfChains`、`remoteUnits/remoteChains`、`physicsExcluded`、`vrdExcluded`、`remoteVrdWriteAvg` 与各阶段成本来证明排除生效。`sessions/chains` 是保留的发现会话总数，**不是 A 实际求解量**。A 仍保留队友会话作身份/生命周期检查，不积累停算 dt。B 的 `remoteVrdWriteAvg` 应为 0。

`os.clock` 阶段平均和离线调用次数都**不是实际 FPS**。两包保留相同发现/身份/生命周期逻辑，A 仍可能承担原全局发现成本。

## 怎样看结果

- **A 恢复、B 仍明显慢**：优先查远端弹簧/完整链重复负载，不只是 VRD。
- **B 明显恢复且接近 A**：优先查远端 VRD；仍需核对人数、链数与阶段日志。
- **两包都慢**：再查发现/调度、场景或其它开销。

以上是排查方向，不是仅凭两个 FPS 数确认根因。详细代码、SHA 与离线证据：[本轮报告](<{report_path.as_posix()}>)。
'''
readme_path.write_text(readme,encoding='utf8',newline='\n')
rows='\n'.join('|'+r['variant']+'|'+r['runtimeVersion']+'|'+str(r['bytes'])+'|`'+r['sha256']+'`|' for r in records)
report=f'''# test01 单骨架远端物理/VRD A/B 测试包（2026-11-16）

## 请求与状态

用户已确认 test01 多人物理正常，但超过 1 人后实战 FPS 严重下降；最多 4 名玩家。最新要求：A 非自己人物全物理停算；B 非自己人物保留物理、排除 VRD。**本轮只交付两套单骨架测试包，不宣称实际 FPS 已恢复，不更新正常程序或正式物理源码。**

基于已部署确认的 2.3.7 R2（此前主线 `b78e63ebc77017aa6c70d52e0bf9e06e46360b92` / 2.1.45 单骨架发现/身份/调度对齐）与独立 20 分钟分段采样。前轮实际 Chef 会话 20:17:33–20:30:50，物理平均舰船 1.606ms，任务中后期约 8.4–9.0ms；这是插件 CPU 计时，不是 FPS。旧 compact 90 秒录制止于实战前，没有实战人数/链数，不能把舰船 9 Units/108 链当作多人实战负载。本轮 A/B 长日志用于填补缺口。

## 实现边界

- 仅已有 `singleMainline` 正向识别会话受模式控制，不把 4 玩家限制成 4 件衣物，不跨相同资源名实例去重。
- 用主线学得的自己 avatar 实例比较会话 owner，不以相机排序第一作为身份。多人未知 fail-open 并记录，先第一人称确认再比。自己死亡后不把幸存队友自动认成自己，世界失效清身份，重生重新学得实例。
- A 在 dispatch 前阻断完整 `Compat.update`：无远端弹簧/VRD/姿态写入，`pendingDt=0`；保留发现和安全生命周期。先前已经写过的帧仅一次交还，不每帧 release。
- B 每会话 `evaluateDrivers=false`，保留完整链、作者参数、原 near/far stride 和自己 stride 1；另防 VRD 直调、release、既有 Source 内联路径绕过。Source 路径读当前未由本模式写入的 helper 姿态作为弹簧锚点，不重新求 VRD 或伪造 bind。
- 不修改共享 rig.drivers、模型父子、蒙皮/真实 bind/contacts/FK、test16 胸修正、Source2、腕排除或动画。compat 1.3.8 仅为两包共用的隔离资源；数字版本满足导出门禁，不代表正式物理升级。生产源码 2.3.7/1.3.7 和 normal Core 保持。

## 实际导出 ZIP

|包|runtime|bytes|SHA256|
|---|---|---:|---|
{rows}

A：{links['A']}  
B：{links['B']}  
使用说明：[单骨架多人性能AB测试说明](<{readme_path.as_posix()}>)。

从正常 Core 的两个隔离资源候选分别导出，非旧 ZIP 改名。各 19802 方法/670 常量/39 资源；方法、引用、常量、身份全不变，仅两物理资源不同；normal Core SHA `{sha(NORMAL/'HD2ModCore.dll')}` 保持。四根文件 CRC/长度/SHA、标准 owner/GUID、容器源码、内联两 Lua 与输入候选一致，两包 compat 同 SHA。

## 已通过的离线验证（不是游戏 FPS）

- 默认 A/B 各 68 检查，两 VM 通过；实际 ZIP 提取源码又各过 68。覆盖 1/2/4 人、7/17 件、同名资源、相机更近队友、未知身份、恢复无 dt 补算、死亡重生、世界失效和双骨架不变。
- 基线 full 路径各 87 单骨架 + 51 多人，两 VM 通过；显式 `singleRemoteTestPolicy=full` 验证不变性，不冒充默认 A/B 多人全开通过。
- 当前真实 test01 **7 个来源 Unit**、17 物理骨、每 Unit 完整 12 链、6 VRD/排 2 腕，1/2/4 人 × 120 受控帧：A {real['A']['checks']} / B {real['B']['checks']} 检查。自己每帧 pose、spring/VRD 数字状态、引擎调用次数逐值同 R2；A 远端更新与回调 0；B 2/4 人远端保留 840/2520 次物理更新、VRD 写入 0。**真实数据+假引擎回调，不是 GPU 表面或实际多人 FPS 验收。**
- 同控制中 4 人 `Unit.world_rotation` 从全开 67200 降到 A 16800、B 36960，不把比例或倒数当 FPS。旧 attach 会给 rig.bones 加派生 bind 缓存：在 attach 后冻结并与基线比较，不将原有注释误判为本轮改作者数据。
- 生产 T1201/T16 完整 literal 和物理数学正文保持。专用 Source 路径以**当前生产 literal 的合成夹具**加坏 VRD 规则验证禁算：A 零读写，B 49 弹簧节点/30 步、VRD 0，release 只还 49 非 VRD 节点；该合成测试不冒充真实 bind 预检。
- 实导单文件 plain/Chef/Cowboy loader 元数据形态，安装/重复安装/回调还原、两 VM 长采样通过。1200 秒/每 10 秒/1:8/250000 字节，跨旧 90 秒正常；不是重新运行游戏内 Chef 沙箱。日志仍是 loader 根单层 .log。
- {len(before)} 个冻结输入保护 SHA 零变化（当前 test01 文件、库 JSON、根配置、正常程序/生产物理）。完整根 `{sha(NORMAL/'config.toml')}`，双手0.7/0.7/1、single rotation_compensation=false保持。无正常 DLL/源码替换、自动导入应用、重绑重烘、游戏部署启动或 Git 提交。

证据目录：`{OUT.as_posix()}`；关键 source-build、core-audit、package-verification、real-test01-verification、实际提取 Lua 的 policy 日志、source-route-gate-verification 和 delivery JSON。目录内采样日志是合成数据，勿和 Roaming 实机日志混用。前轮 2.3.8 纯诊断包不另交付，本轮仅两个 A/B 包。

下一步同场景同画质 1→2→4 记录加入时间、实际 FPS/CSV 和 A/B/chef 日志，再决定真正优化 VRD、远端完整链或发现成本。
'''
report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(report,encoding='utf8',newline='\n')
agent=ROOT/'AGENTS.md';raw=agent.read_bytes();(OUT/'before-AGENTS.md').write_bytes(raw)
section='''
## test01 多人性能 A/B 两包（2026-11-16，FPS 待实测）

- 用户确认test01多人物理正常、超1人实战FPS下降；最新A其它人物全物理停算，B其它人物保物理排VRD。只单骨架，4为玩家非件数；自己R2参数/VRD/stride1保持，native/dual/direct不优化。未正式升级主src/normal/Core。
- 仅normal非运行文件/测试包两新ZIP：A单骨架仅自己物理2.3.9-r1（337308B/SHA 5ed974520b26c1b62c23446cfb62f32a8a324fe6d0cd8b8dda48bf89d2a80d05）；B队友保留物理禁VRD2.3.10-r1（337310B/SHA 4006f2db5dc3b28d59d3a89c7f72b5f598b7610cf9ca450db94da10da4922ee7）。共用隔离compat1.3.8，不是正式/FPS验收升级；normal Core ce3a...及生产2.3.7/1.3.7保留、原R2不覆。
- 主线FP学得自己avatar INSTANCE比较owner，不按相机第一/资源名。未知多人fail-open记ambiguous-aim-first-person，先FP瞄准1s确认fp-confirmed。A跳整Compat.update/pendingDt=0保留发现生命周期；B会话evaluateDrivers=false防直调/release/Source内联绕过，不改共享rig/bind/裁骨。旧写入仅一次交还，死亡重生/世界失效恢复。
- 默认68两VM+实际ZIP提取68过；基线full显式87+51两VM过。真实test01七源Units1/2/4×120受控帧A7827/B7832：自己pose/spring/VRD/调用逐值同R2，A远端0，B840/2520弹簧更新VRD0；非实际FPS/GPU。生产T1201/T16完整literal与数学同源，Source合成坏VRD规则A0/B49物理且0VRD，不冒称实际bind选择。
- 两隔离Core各19802方法/670常量/39资源，0IL/引用/身份变仅2物理；真导ZIP四根CRC/SHA/owner/GUID/源码、两VM安装卸载/重复回调/1200s诊断过。10s日志hd2physbone_test01_A_perf.log/B_perf.log、1:8采样250k，timer非FPS；证据日志合成、实机在Roaming Arrowhead。157冻结用户/模型/config/程序输入SHA无变，ff64a88...全配置保持，无导入应用/重绑重烘/部署启动/提交。
- 实验single_remote_ab_*模板、single-remote-*测试与tools/build/run/verify/deliver_single_remote_ab_*；不写正式配置/默认发布来源。报告docs/agent/physics-test01-remote-ab-20261116.md，证据outputs/physics-test01-remote-ab-20261116；用户每轮仅一物理、手动应用重启，同场景1→2→4记录加入时间+真实FPS/CSV+长日志再定优化。

'''
head=raw.index(b'\n')+1;agent.write_bytes(raw[:head]+section.replace('\n','\r\n').encode('utf8')+raw[head:])
changed=[p for p,h in before.items() if not Path(p).is_file() or sha(Path(p))!=h];assert not changed
result={'status':'DELIVERED_TWO_TEST_PACKAGES_NOT_GAME_FPS_ACCEPTED','packages':records,'readme':str(readme_path),'report':str(report_path),'protectedCount':len(before),'protectedChanges':[],'normalCoreUpdated':False,'productionSourcesModified':False,'userConfigModified':False,'gameDeployment':False,'actualGameFpsMeasured':False}
(OUT/'delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))
