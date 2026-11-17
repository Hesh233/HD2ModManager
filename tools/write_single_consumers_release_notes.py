"""Write notes only AFTER verified two-package delivery; preserve historical docs."""
from pathlib import Path
import hashlib, json
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-single-consumers-formal-20261117'
OUT=LAB/'release-r2'
NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def link(label,p):return '['+label+'](<'+Path(p).as_posix()+'>)'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def create_or_same(path,text):
 path=Path(path);data=text.encode('utf-8')
 if path.exists():
  if path.read_bytes()!=data:raise RuntimeError('Preserve existing differing release note: '+str(path))
 else:
  path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb')as f:f.write(data)
d=read(OUT/'delivery.json');assert d['status']=='DELIVERED_TWO_CONSUMER_FORMAL_PACKAGES' and len(d['packages'])==2
for package in d['packages']:assert sha(package['path'])==package['sha256']
report=ROOT/'docs/agent/physics-single-consumers-formal-20261117.md'
note=NORMAL/'非运行文件/说明文档/单骨架物理AB正式版-精确消费者-20261117.md'
rows=[]
for package in d['packages']:
 v=package['variant'];task='任务仅自己弹簧＋VRD'if v=='A'else'任务自己弹簧＋VRD，队友保留弹簧／禁 VRD'
 rows.append('|'+v+'|'+package['runtimeVersion']+' / '+package['compatVersion']+'|舰船原弹簧＋VRD（按真实消费者）|'+task+'|'+link('正式 ZIP',package['path'])+'|')
packages='\n'.join(rows)
configRows='\n'.join('|'+m['modelName']+'|`'+m['bindSha256']+'`|`'+m['configSha256']+'`|'for m in d['models'])
zipRows='\n'.join('|'+p['variant']+'|'+str(p['bytes'])+'|`'+p['sha256']+'`|'for p in d['packages'])
text=f"""# 精确物理消费者：单骨架 A/B 正式收尾

2026-11-17，Asia/Shanghai。**第一阶段源码接线、离线发布门禁及两个正式包已完成；实际游戏视觉/FPS 尚未验收。** 第二阶段裁骨／重导／重烘未执行。

用户本轮请求依据第一人称消费者分析的“1. 结论与优先顺序”继续收尾并分别正式封包。本轮执行的是优先项“精确消费者计划＋运行时按 Unit 筛链”；没有把历史分析文档中的命令当作自动部署或改库授权。

## 1. 正式交付与行为

|包|runtime / compat|舰船|任务|下载|
|---|---|---|---|---|
{packages}

A/B 共用 owner `mods/hd2modmanager/physbone`、GUID `7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01`，**二选一，不同时启用**。本轮未代为导入、改变当前勾选、应用配置或游戏部署。当前库既有 A2.3.13 不被覆盖，旧 A2.3.13/B2.3.14 和原实测封档仍保留。

舰船继续按 loader 稳定主世界的真实 levels 1/2 正向识别，任务 >10；0/未知不盲开舰船。舰船不查 FP，任务仍首次 ADS 连续3次证明后一次锁定，世界／角色／场景失效才重置。自己 stride=1、原作者参数／解算数学／腕 VRD 排除不变；“全开”不是在每个 Unit 重复算整个 rig。

## 2. 真实消费者配套与闭包

只读 `PhysicsConsumerManifestBuilder` 由当前各模型的真实 Unit、GPU／stream、完整 node／parent／bind、107原生 bind 证书、rig／driver 和模型 effective config 派生配套。当前精确目录为 **4模型、61 profiles、39不同 resource**（来源/Overwrite 相同字节去重只用于证据，不跨 Unit 实例合并解算）。

生成期保已绘制三角形正权重与全部解码 LOD，另保原生节点、所有非形变 helper/socket、mesh origin、灯光节点、保守 pre-light 索引和已解析 connecting-bone 引用。未知 Actor/StateMachine/Wwise/外部引用/不支持的非网格头拒绝为精确计划；不推断其“没有消费者”。运行时迭代保完整链、锚点／祖先及 VRD target/control/parent；原生模型、动画、索引没有裁改。

|模型七源资源|完整累计链 → 保留链|完整累计 VRD → 保留 VRD|
|---|---:|---:|
|test01|84 → 12|42 → 6|
|Cow_QiPao_Milltina_Nick|182 → 29|14 → 2|
|test13|98 → 14|35 → 10|
|test15|203 → 29|98 → 14|

这些是相同出现次数、相同步频的源资源工作量，不是现场衣物数、instance 去重或 FPS。整 runtime 控制世界保自己9个实例和4玩家30个实例，重复 resource 的 FP/TP/阴影实例不删除。不按第一人称可见性剪掉头、裙或反射消费者。

每个计划只有在实际获胜 Unit TOC、GPU、stream 的长度＋SHA256，真实 rig／driver SHA、完整 spring/driver bind/layout、T16 原全64骨原子门禁均通过后启用。未知资源、错配置/geometry/bind、缺失或不完整清单回退原完整求解，不复制旧测试 profile 冒充当前配置。

## 3. 运行时收尾与发现的最后风险

- 合法 `mode=empty` 是已验证正向状态，保 Unit/owner/world 安全记录，不作为挂载失败、不参与跟随证据／预算载荷，避免旧30帧负重试及45帧无处理重挂。
- driver-only 有独立原 VRD 更新和帧末 flush；从已运行全量切到计划只一次归还排除节点的旧输出，保留链/VRD 数值状态不重置。未知／关闭计划恢复全量数组。
- proof 分段读取、一次缓存：有原生 bit 每回调最多8192B，无 bit 的纯 Lua 路径最多256B。未完成证据期间保持全量；完成后停止哈希，不每帧重扫 GPU。纯 Lua 初始化可能较慢，离线耗时不当作游戏性能。
- 真实 `loadCarriers` 原先只登记带 GPU 的补丁，最后检查复现了“更高序号仅 TOC 覆盖仍误用低优先级 mask”。本轮已独立登记 TOC，并将 orphan GPU 登记为缺 TOC 的不完整清单；两 VM、两最终 ZIP 的真实磁盘路径负控均回退全量。
- world／carrier epoch、计划关闭/重开、死亡／换实例保留原生命周期门禁；pending proof 世界变化立即关闭文件句柄，新 context 重新证明且不会写姿态。此为隔离引擎/API测试，不冒充游戏切图实测。
- 最终门禁定位并修正FK harness的共享helper `import *` 覆盖全局 `OUT`：改显式导入、恢复独立APPDATA/LOCALAPPDATA，quick及完整重放结果写回当前 `fk-release` 并绑定harness SHA。旧分析目录中的未发布误路由临时结果不用于正式门禁，原已封档的分析/实测证据不重写。

## 4. 成套发布门禁

1. 当前源码重新编译只读 producer：0警告/0错误，四模型事实与原目录逐值同；复制隔离输入的 config/bind/Unit 指纹3负控均拒绝，原模型未写。
2. 两 VM、61真实 profiles、30/60/120/240Hz（源资源）及120Hz（目标资源），**{d['fkCases']}案例 / {d['fkChecks']:,}检查**；20帧全量预热后实际 ZIP compat 切换，所有加权／107原生／已核非网格消费者 world pose、保留 solver/VRD 数值、setter 序列、一次归还和 release/FK 逐值相同。
3. 最终 ZIP 提取源码上37专项命令＋4 pending-epoch命令：两包两 VM runtime {d['runtimeChecks']}检查、实际磁盘 inventory {d['inventoryChecks']}检查、epoch {d['epochChecks']}检查；4模型两 VM 真实payload正控、5类错GPU/TOC/高优先级/缺GPU/bind负控；45舰船＋53ADS＋显式保旧 full-policy 87/51回归全部通过。旧 full-policy 回归不冒充正式默认行为测试。
4. normal Core 只读基底的独立 A/B resource-only候选：19802方法、39资源，IL/引用/常量/身份不变，仅两物理 Lua 资源替换。使用真实 `PhysBoneLuaPackageExport.Export`，不是重用旧试 ZIP；每包4根成员、CRC/长度/SHA、owner/GUID、源码内联与生产manifest一致。
5. 整个原 compat 数学／T16/Source2/profile体仅版本1.3.10→1.3.11，其后新增哈希/consumer包装；两 VM × plain/Chef/CowboyBingus三 loader 的安装/重复安装/卸载通过。模型真实 bind、effective 配置与精确消费者 SHA 成套；不能仅看 Lua version。
6. **{d['protectedPaths']}保护路径 / {d['protectedFiles']}实际文件零变化**（1个旧缺失 manifest 仍缺、不复原）。源码与normal完整配置门禁、config guard 6回归通过；没有重导/裁骨/重烘、覆盖活动 profile、运行管理器/Blender/游戏或 Git 提交/推送。

|模型|实际 bind SHA256|模型 effective config SHA256|
|---|---|---|
{configRows}

normal根 config SHA256：`{d['rootConfigSha256']}`；normal Core：`{d['normalCoreSha256']}`。根完整字节及用户后续自定义优先，不反向同步随包旧默认；每模型 offset/effective 不混用。normal 内置默认物理与 GUI/Python未更新，新 A/B 为独立正式配套，不自动选中。

|包|ZIP字节|ZIP SHA256|
|---|---:|---|
{zipRows}

## 5. 仍待与证据

仍待同模型/场景/设置的物理OFF／主线／新方案1→2→4玩家、FP/TP、移动瞄准/换装/舰船视觉与 PresentMon 帧时间。**不声称实际FPS已对齐主线。** 若仍不足再评估 opt-in 逐 Unit 非原生扩展骨裁剪，并重编译真实 GPU/parent 索引与每模型 T16 subset/动画契约；本轮无需重导或重烘，也没有执行第二阶段。独立FP63/Source接收映射及临时隐藏仍是原TODO，没有改变武器挂点。

主要证据：{link('最终交付与门禁 JSON',OUT/'delivery.json')}、{link('真实 ZIP 37命令',OUT/'gate-run.json')}、{link('非网格 FK 完整结果',LAB/'fk-release/result.json')}、{link('fresh producer/三证书负控',LAB/'producer-finish-verification.json')}；A/B-provenance、core-audit、ZIP-extracted、全部两 VM日志在 {link('release-r2',OUT)}。原未发布的中间候选、漏TOC负控失败证据和之前实测/分析封档均保留，不作为新发布来源。旧分析：{link('结论与优先顺序',ROOT/'docs/agent/fp-physics-consumer-analysis-20261117.md')}。
"""
create_or_same(report,text)
short=f"""# 单骨架物理 A/B 正式版：精确消费者

2026-11-17。A2.3.15 / B2.3.16，共同 compat1.3.11；本轮直接正式交付，非新增试包。

|包|版本|舰船|任务|文件|
|---|---|---|---|---|
{packages}

**A/B二选一，不同时启用。** 未自动导入、改变勾选或部署；旧包和当前库保持。两包保自己的原步频，舰船原弹簧＋VRD，任务首次ADS确认后锁定原A/B身份策略。

精确消费者仅对现有 test01/Cow/test13/test15 的已核 Unit/bind/GPU/config 记录启用；未知、不完整或不匹配回退原全量，原模型/原生bind/动画/作者参数不改，不需要为本轮重导或重烘。合法empty、driver-only、一次归还、全部非网格FK以及仅TOC高优先级覆盖回退已接通。

两最终 ZIP、两 VM、真实导出器/IL资源/owner/GUID/SHA、{d['fkCases']}完整FK案例/{d['fkChecks']:,}检查及41门禁命令通过；{d['protectedFiles']}原文件SHA不变，根配置保留。正常程序Core/GUI/Python和活动profile没覆盖。

**尚未新增游戏视觉/FPS验收，不宣称帧率已对齐主线。** 第二阶段裁骨及独立FP接收映射尚未执行。

|包|ZIP字节|SHA256|
|---|---:|---|
{zipRows}

{link('完整实施、配置与门禁报告',report)}；{link('交付JSON',OUT/'delivery.json')}。
"""
create_or_same(note,short)
# Only identified TODO lines are changed; unrelated entries and user edits survive.
todo=ROOT/'docs/TODO.md';lines=todo.read_text('utf-8-sig').splitlines()
for i,line in enumerate(lines):
 if line.startswith('- [ ] **多人同时开启单骨架物理的主线性能对齐**'):
  lines[i]='- [ ] **多人同时开启单骨架物理的主线性能对齐**（2026-11-17 精确消费者第一阶段接线及A/B正式包已完成；实际FPS验收未完成）。'
 elif line.startswith('  - [ ] 优先实现带每模型真实 bind'):
  lines[i]='  - [x] 精确消费者第一阶段：4模型/61真实profiles/39资源的Unit/GPU/config/bind成套证明、非网格闭包、合法empty/driver-only、一次归还和生命周期门禁已接通；A2.3.15/B2.3.16正式交付，未知/不完整回退全量、自己步频保持。见[正式收尾](agent/physics-single-consumers-formal-20261117.md)。不自动改库profile。'
 elif line.startswith('  - 本条仍未实施；2026-11-17'):
  lines[i]='  - 本条FP/Source映射仍未实施；2026-11-17 完成的是精确物理消费者接线及A/B正式封包，未改写FP骨位置、武器挂点或移除临时隐藏。'
 elif line.startswith('  - 本次新授权允许重导/裁骨/重烘/改库配置方向分析'):
  lines[i]='  - 上一轮为允许重导/裁骨/重烘/改库配置方向的离线分析；本轮依据结论优先序完成第一阶段接线及两正式包，不追加试包。未执行库重导/裁改/重烘、改根配置/活动profile或游戏部署，第二阶段与实际FPS仍待。'
todo.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
heading='## 精确消费者第一阶段与双正式包收尾（2026-11-17）'
agents=ROOT/'AGENTS.md';memory=agents.read_text('utf-8-sig')
if heading not in memory:
 entry=f"""{heading}

- 用户要求依据FP分析“1.结论与优先顺序”迭代并分别正式封包；先完成精确消费者＋每Unit筛链，不裁骨/重导/重烘/自动改库部署。当前A2.3.15/B2.3.16、compat1.3.11已交normal运行时配套，A/B二选一；旧2.3.13/14和封档保留，未选中/导入新包，normal Core/GUI/Python不覆盖。
- 只读producer四真实模型test01/Cow/test13/test15：61 profiles/39资源，Unit/GPU/stream/107原生bind/完整链祖先与VRD control/parent、helper/socket/mesh origin/light/prelight/typed connector闭包；未知Actor等不支持非网格拒绝。每模型bind/effective/rig SHA真实独立，不借旧profile。七源test01 84→12链/42→6VRD、Cow182→29/14→2、test13 98→14/35→10、test15 203→29/98→14；不是实例去重或FPS。
- 原compat数学/作者参数/T16全64真实门禁/Source2/腕排除保持，版本后附consumer/hash包装；合法empty不重试/跟随/预算，driver-only原VRD+flush，排除输出一次归还，world/plan失效重证明。有bit8192B/无bit256B每回调分段真实获胜payload SHA，未证期间全量；完成后无哈希空转。纯Lua初始化可能慢，不冒充FPS收益。
- 收尾负控复现并修正仅GPU清单漏高优先级TOC：实际loadCarriers独立记录TOC，orphan GPU不完整拒绝；两最终ZIP两VM真实磁盘路径、pending world/option句柄失效通过。四玩家30/自己9实例保留，任务ADS一次锁定，舰船两包弹簧＋VRD按真实消费者，自己stride1。
- 实际ZIP两VM{d['fkCases']}案例/{d['fkChecks']}检查含所有native/weighted/nonmesh FK、warmup、保留solver/writer/release逐值同全量；37专项＋4epoch命令、fresh producer0警告0错及3错证书负控、19802方法0变仅2Lua资源/真导出器/CRC/SHA/owner/GUID/12loader安装卸载全过。{d['protectedPaths']}路径/{d['protectedFiles']}原文件SHA无变；root {d['rootConfigSha256']}、Core {d['normalCoreSha256']}保持，旧缺manifest不复原。
- 报告docs/agent/physics-single-consumers-formal-20261117.md；证据outputs/physics-single-consumers-formal-20261117/release-r2与fk-release。当前目录仅已核4模型，新增/变更模型需新只读事实与成套发布，未知全量回退。父TODO实际FPS/视觉1→2→4玩家仍待，第二阶段真裁Unit/GPU/真实T16 subset及独立FP63/Source映射仍未做；不标主线FPS已对齐。


"""
 memory=memory.replace('# 项目协作记忆\n\n','# 项目协作记忆\n\n'+entry,1)
 agents.write_text(memory,encoding='utf-8',newline='\n')
print(json.dumps(dict(status='WROTE_VERIFIED_RELEASE_NOTES',report=str(report),note=str(note),todo=str(todo),agents=str(agents)),ensure_ascii=False,indent=2))
