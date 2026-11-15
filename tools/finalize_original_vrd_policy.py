"""Freeze the Lua-only original-format VRD policy delivery; never deploy the game."""
from pathlib import Path
import json,hashlib,shutil,zipfile,xml.etree.ElementTree as ET,datetime
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physical-original-vrd-guard-20261111';INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
assert not (OUT/'final-verification.json').exists(),'Completed policy delivery is immutable'
policy=load(OUT/'policy-verification.json');legacy=load(OUT/'legacy-regression.json');sync=load(OUT/'core-sync.json');source=load(OUT/'source-sync.json');proof=load(OUT/'installed-package/physics-provenance.json')
assert policy['status'].startswith('PASS') and legacy['status'].startswith('PASS') and not legacy['errors']
assert sync['mode']=='apply' and sync['methodsIdentical']==16917 and sync['constantsIdentical']==575 and sync['resourceCount']==38
assert sha(INSTALL/'HD2ModCore.dll')==proof['inputs']['HD2ModCore.dll']==sync['afterSha256'].lower();assert not source['installedMetadataPending']
for f in source['files']:assert sha(f['path'])==f['afterSha256']
for name,expected in [('physics-original-vrd-guard.trx',25),('physics-original-vrd-mirror.trx',4)]:
 c=ET.parse(OUT/'dotnet-tests'/name).getroot().find('.//{*}Counters');assert c is not None and c.attrib['failed']=='0' and int(c.attrib['passed'])==expected
candidate=load(OUT/'candidate-package/physics-provenance.json');assert candidate['entries']==proof['entries'],'Actual client exporter differs from tested candidate'
formal=INSTALL/'非运行文件/打包输出/物理运行时-正式版-2.3.4.zip';assert not formal.exists();shutil.copyfile(OUT/'installed-package/physics-runtime.zip',formal);assert sha(formal)==proof['zipSha256']
with zipfile.ZipFile(formal) as z:
 assert z.testzip() is None and len(z.namelist())==4
 for f in proof['entries']:assert hashlib.sha256(z.read(f['path'])).hexdigest()==f['sha256']
proof.update(deliveryPath=str(formal),bytes=formal.stat().st_size,actualInstalledExporter=True,luaOnlyOriginalVrdPolicy=True,gameDeployed=False);save(Path(str(formal)+'.provenance.json'),proof)
before=load(OUT/'protected-before.json');after={p:sha(p) if Path(p).is_file() else None for p in before};allowed={f['path'] for f in source['files']}|{str(INSTALL/'HD2ModCore.dll')};changes=[dict(path=p,beforeSha256=h,afterSha256=after[p]) for p,h in before.items() if h!=after[p]];concurrent=[r for r in changes if r['path'] not in allowed]
observed={str(INSTALL/p) for p in ['settings.json','test-library/library.json','test-library/profiles.json']};game=Path(r'E:\Steam\steamapps\common\Helldivers 2\data')
assert all(r['path'] in observed or Path(r['path']).is_relative_to(game) for r in concurrent),concurrent
for r in concurrent:r.update(actionTaken='none; concurrent user/client state preserved without rollback')
save(OUT/'protected-after.json',after);save(OUT/'protection-verification.json',dict(status='PASS_NO_UNEXPECTED_AGENT_WRITES',capturedFiles=len(before),unchanged=sum(h==after[p] for p,h in before.items()),expectedSourceAndClientChanges=[r for r in changes if r['path'] in allowed],observedConcurrentStateChanges=concurrent,gameDeployed=False))
archive=INSTALL/'非运行文件/归档/物理非骨架VRD门禁-2.3.4-源码与同步验证-20261111.zip';doc=ROOT/'docs/physics-original-vrd-policy-20261111.md';guide=INSTALL/'非运行文件/说明文档/非骨架版禁用VRD-正式物理2.3.4-20261111.md';assert not doc.exists() and not guide.exists() and not archive.exists()
report=f'''# 非骨架版本 Lua 侧禁用 VRD：正式物理 2.3.4（2026-11-11）

## 用户确认的方向

用户原文：**“不能仅靠替换客户端 Lua则，改为lua侧遇到非骨架版不应用vrd功能”**。

本轮落实的是 **跳过非骨架版本 VRD**，不是补 VRD 导出，不改 VPK 生成链/模型/骨架/动画。根源码、`HD2ModManager_main` 对应物理源码与当前客户端 Core 已同步到 runtime **2.3.4** / compat **1.3.4**。

## Lua 策略

- 正式入口固定开启 `vrdSkeletonOnly=true`。原版、无 driver 记录、未知或无法确认的 driver 规范，不建立 VRD driver 行、不查 driver 缓存、不执行 VRD update/release 写入；**弹簧链仍照原逻辑运行**。
- 骨架数据的正向依据是已有导出契约：单骨架 v3 的完整单位控制 bind 四元数；双骨架 v1/v2 的完整同一 12hex 命名空间、aux/anim/phys 角色和弹簧配套。不是凭 174 节点、资源 ID 或名称猜模型版本。
- test1201 原版与已接受骨架版可能同资源/同节点数。完整 Source 专用 rig 在正式门禁开启时，先延迟旧 VRD 行；只有既有完整资源/节点/命名/bind 守卫全过，才由 Source 分支驱动 **49 spring + 9 VRD**。守卫拒绝时**不再回落到旧 VRD**，不复活旧缓存。两腕仍排除。
- 原版不会因禁 VRD 而关掉 49 根 spring。Source `sJiggle` 函数与上一正式版逐字相同，原 539 参数和 Source 数学/限位/重力/VRD 曲线均未改。
- 通用兼容库的历史直接调用保持兼容；正式内置/外置入口均使用本门禁。支持与否按实际导出记录判断，未声称 Lua 能读取 GPU 蒙皮权重或凭模型名识别任意伪造元数据。

## test1201 当前事实与复核

当前非骨架源模型 128 骨、49 spring、11 VRD；`vpk2patch` 与 `Overwrite` 只嵌 `hd2_spring_rig.bin`，没有 driver 记录。原 21:27:05 实机日志正常加载 2.3.3，8 实例/224 链、无 VRD 激活。本轮基于当前真实原版 Unit 和数据检查，未替换它们。

- **{policy['checks']:,} 项门禁检查通过**，原版 11 个资源共 **55** 场景：无记录、混入裸名 v1/v2、坏 v3、混入完整 Source v3，以及预热旧缓存。VRD 行/更新/释放写入均为零；49 spring 保留，数值与上一无 VRD 原版基线逐元素误差 **{policy['originalSpringMaxElementError']}**。
- **{len(policy['existingSkeletonContracts'])}** 份当前真实骨架数据契约继续通过，涵盖 native v1/v2 与 single v3；真实 VRD 缓存/写入路径保留。
- 受控 Source2 fixture 根据旧保存的 bind 与 parent 契约重构；60 帧含移动 Hips/摆腿，两腕仍排除、9 VRD 保留、58 节点恢复，旧/新全部局部姿态逐元素误差 **{policy['controlledScopedMaxElementError']}**。这是受控重构，不冒称完整旧 UNIT 逐字复原或新实机/GPU动作录像。
- **20 项现有回归套件**通过，包括实际 Chef 1.4.1 解析/沙箱/模块选择；2.3.4 正式 payload 逐字读回相同、60 update/render 空场景零写入。
- 当前 test07 单骨架 fixture 已不在活动库：单前裙整套及两个测试中的 test07-single 子例未重跑，报告明确列出；没有为测试重导它或修改金标准文件。其余现存子例继续测试。
- 正式冻结资源构建下 .NET 包测试 **25** 全过；镜像限定物理包测试 **4** 全过。新游戏会话/性能/几何穿透仍未验收。

## 客户端同步与正式包

- [物理运行时-正式版-2.3.4.zip]({formal.as_posix()})：**{formal.stat().st_size:,} 字节**，SHA-256 `{sha(formal)}`。
- 从实际安装 `HD2ModCore.PhysBoneLuaPackageExport.Export` 导出。ZIP 根四文件，保持 Arsenal 平铺布局、owner `mods/hd2modmanager/physbone` / Guid `7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01`。
- 当前 Core **16,917 方法、575 常量、程序集身份不变**；38 资源只替换 2 份物理 Lua，其余 36 个 B3/FP/挂点等资源不变。GUI（包含已补原版导入选项）不动，旧 staging 未覆盖。
- 源码、限定版本断言、构建脚本与运行时元数据仅更新物理版本；其它 pipeline / R2 / B3 字段保持。
- **已同步客户端导出链，但未导入活动物理模块/未应用配置/未部署游戏。** 要在游戏使用本策略，请重启管理器，导入上述 2.3.4 ZIP，停用其它物理副本（B3 基础/面板不属于物理副本），正常应用配置并重启游戏。不需模型重导或动画重烘。
- 新日志检查 `[physbone][VRD-policy] contract=original-or-no-driver-record legacyAllowed=false recordBones=0 springs=49`；有误混记录时同样不拥有旧 VRD。真正骨架版由正向契约或 Source SELECTED 显示正常 VRD。

## 保留、证据与回退

当前 {len(before)} 个保护文件中 {sum(h==after[p] for p,h in before.items())} 不变，差异只在本轮源代码/物理 Core/元数据；另观察到 {len(concurrent)} 个并发用户/客户端状态变化，原样保留，不回滚。原 test1201 模型/动画/当前游戏文件未由本轮写入；已发布 2.3.3 正式 ZIP 和 Source2 封档 ZIP 字节冻结。

- [本轮代码、客户端备份及验证证据]({OUT.as_posix()})。
- [源码与同步验证 ZIP]({archive.as_posix()})：本轮前基线/新 Core、PDB、Lua、工具、正式物理包、日志、测试和逐文件 SHA-256；这是同步与离线验证归档，不标为新实机已验收。
- 回退外置物理时停用 2.3.4，导回冻结的 2.3.3 ZIP并正常应用/重启；回退管理器须先退出，恢复本轮 `before` 中的 Core 与对应安装 `build-info.json`。不恢复过期 game patch 快照。

未 Git 提交/推送。
'''
doc.write_text(report,'utf8');guide.write_text(report,'utf8');(ROOT/'HD2ModManager_main/docs/physics-original-vrd-policy-20261111.md').write_text(report,'utf8');(OUT/'修正与同步报告.md').write_text(report,'utf8')
memory=f'- 2026-11-11 用户确认“不能仅靠替换客户端 Lua则，改为lua侧遇到非骨架版不应用vrd功能”：已Lua侧禁非骨架VRD，非补导出。正式入口vrdSkeletonOnly=true；原版/无记录/未知规范无driver行/cache/update/release写，spring保留。单v3完整控制bind与nativev1/v2同12hex aux/anim/phys正向契约允许；test1201精确Source rig先延迟旧VRD，全资源174命名bind闸后仍49+9/排2腕，拒绝不回落旧VRD（原版与单版同ID/174不能按数量猜）。1458检查/11原版资源55场景含混v1/v2/坏v3/完整Sourcev3+缓存皆VRD0、spring旧基线元素误差0；当前6骨架契约允许，重构保存bind/parent受控Source60帧移动/摆腿旧新误差0（非原UNIT/实机GPU）；sJiggle与539参数不变。现有20套+真Chef2.3.4解析/沙箱/60空0写过，test07single已删除导致1整套+2子例未跑明示不重导；.NET包25/镜像物理4过。根/main源码/物理元数据同步runtime2.3.4/compat1.3.4，当前managerCore16917方法/575常量/身份与36其他资源不变，只2Lua，GUI原版选项/B3不动。实际安装导出平铺4根文件物理2.3.4 ZIP {formal.stat().st_size}B/SHA{sha(formal)}；旧2.3.3/Source2封档冻结。未活动物理入库/配置应用/重导/重烘/game部署/Git推送；需导新ZIP只保留1物理并正常应用重启。outputs/physical-original-vrd-guard-20261111、docs/physics-original-vrd-policy-20261111.md、固定说明文档/非骨架版禁用VRD-正式物理2.3.4-20261111.md成套；备份归新验证ZIP，不标新实机接受。\n\n'
for p in [ROOT/'AGENTS.md',ROOT/'HD2ModManager_main/AGENTS.md']:
 backup=OUT/'before'/p.relative_to(ROOT);backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,backup);head,tail=p.read_text('utf8').split('\n',1);p.write_text(head+'\n\n'+memory+tail.lstrip('\n'),'utf8')
record=dict(status='COMPLETE_LUA_POLICY_CLIENT_SYNCED',runtimeVersion='2.3.4',compatVersion='1.3.4',formalPackage=dict(path=str(formal),bytes=formal.stat().st_size,sha256=sha(formal)),clientCoreSha256=sha(INSTALL/'HD2ModCore.dll'),policyChecks=policy['checks'],originalCases=55,originalVrdWrites=0,originalSpringParity=0,existingSkeletonContracts=len(policy['existingSkeletonContracts']),legacySuites=len(legacy['tests']),declaredMissingFixtures=legacy['skippedUnavailableFixtures'],partialMissingCases=legacy['partialMissingCases'],dotnetPackageTests=25,mirrorPhysicsTests=4,sourceJiggleUnchanged=True,gameDeployed=False,clientRuntimeExportSynced=True,report=str(doc));save(OUT/'delivery.json',record)
files={}
def add(p,n):assert n not in files and p.is_file();files[n]=p
for p in OUT.rglob('*'):
 if p.is_file() and not any(x.startswith('certification-') for x in p.relative_to(OUT).parts) and not p.is_relative_to(OUT/'candidate-package') and not p.is_relative_to(OUT/'installed-package') and not p.is_relative_to(OUT/'resource-freeze') and not p.is_relative_to(OUT/'candidate'):
  add(p,'证据与备份/'+p.relative_to(OUT).as_posix())
for f in source['files']:p=Path(f['path']);add(p,'同步源码/'+p.relative_to(ROOT).as_posix())
for name in ['verify_original_vrd_policy.py','verify_original_vrd_regressions.py','finalize_original_vrd_policy.py']:add(ROOT/'tools'/name,'本轮工具/'+name)
add(INSTALL/'HD2ModCore.dll','同步客户端/HD2ModCore.dll');add(OUT/'candidate/HD2ModCore.pdb','构建符号/HD2ModCore.pdb');add(formal,'正式包/'+formal.name);add(Path(str(formal)+'.provenance.json'),'正式包/来源与SHA256.json');add(doc,'修正与边界说明.md')
manifest={n:dict(bytes=p.stat().st_size,sha256=sha(p)) for n,p in files.items()}
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,p in sorted(files.items()):z.write(p,n)
 z.writestr('逐文件SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for n,v in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==v['sha256']
record['archive']=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),files=len(files));save(OUT/'final-verification.json',record);save(Path(str(archive)+'.sha256.json'),record['archive']);assert all((sha(p) if Path(p).is_file() else None)==h for p,h in after.items());print(json.dumps(record,ensure_ascii=False,indent=2))
