"""Finalize immutable accepted Source2 archives and the actual-installed formal package."""
from pathlib import Path
import sys,json,hashlib,shutil,zipfile,datetime,struct,xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/test1201-source2-accepted-20261111';TEST=ROOT/'outputs/test1201-source2-live-rejection-20261111';INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';ARCH=INSTALL/'非运行文件/归档';DELIVERY=INSTALL/'非运行文件/打包输出'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def document(p,data):
 if p.exists():
  backup=OUT/'before'/p.relative_to(ROOT);backup.parent.mkdir(parents=True,exist_ok=True);assert not backup.exists();shutil.copyfile(p,backup)
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,'utf8')
assert not (OUT/'accepted-archive-final.json').exists(),'This completed acceptance run is immutable'
sync=load(OUT/'core-sync.json');assert sync['mode']=='apply' and sync['methodsIdentical']==16917 and sync['constantsIdentical']==575 and sync['resourceCount']==38
assert set(sync['changedResources'])=={'HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua'}
assert sha(INSTALL/'HD2ModCore.dll')==sync['afterSha256'].lower()
source=load(OUT/'source-sync.json');assert not source['installationMetadataPending']
for f in source['files']:assert sha(f['path'])==f['afterSha256']
checks=load(OUT/'formal-verification-summary.json');assert checks['status'].startswith('PASS')
assert len(load(OUT/'existing-suite.json')['tests'])==21 and not load(OUT/'existing-suite.json')['errors']
assert load(OUT/'chef-test1201-accepted.json')['sourceFromEmbeddedPatchExact']
trx=ET.parse(OUT/'dotnet-tests/physics-formal-package-final.trx');counter=trx.getroot().find('.//{*}Counters');assert counter is not None and counter.attrib['passed']=='24' and counter.attrib['failed']=='0'
provenance=load(OUT/'installed-package/physics-provenance.json');assert provenance['runtimeVersion']=='2.3.3' and provenance['compatVersion']=='1.3.3';assert provenance['inputs']['HD2ModCore.dll']==sha(INSTALL/'HD2ModCore.dll')
old=Path(load(TEST/'delivery.json')['package']);assert sha(old)=='9e05a4b3ed8d58f48336a147702702622ae797426bda3cbaba49a6f340686ca1'
formal=DELIVERY/'物理运行时-正式版-2.3.3.zip'
if not formal.exists():shutil.copyfile(OUT/'installed-package/physics-runtime.zip',formal)
assert sha(formal)==provenance['zipSha256']
with zipfile.ZipFile(formal) as z:
 assert z.testzip() is None and sorted(z.namelist())==sorted(r['path'] for r in provenance['entries']) and len(z.namelist())==4
 for r in provenance['entries']:assert hashlib.sha256(z.read(r['path'])).hexdigest()==r['sha256']
 raw=z.read('9ba626afa44a3aa3.patch_0');offset=struct.unpack_from('<Q',raw,120)[0];n=struct.unpack_from('<I',raw,offset)[0];embedded=raw[offset+8:offset+8+n]
 accepted=(TEST/'hd2physbone-test1201.lua').read_bytes().replace(b'1.3.3-test1201-source2',b'1.3.3').replace(b'2.3.3-test1201-source2',b'2.3.3')
 assert embedded.replace(b'\r\n',b'\n')==accepted.replace(b'\r\n',b'\n')
provenance.update(deliveryPath=str(formal),bytes=formal.stat().st_size,actualInstalledExporter=True,source2VersionOnlyChange=True,gameDeployed=False);save(Path(str(formal)+'.provenance.json'),provenance)
accepted_copy=ARCH/'test1201-Source2-实机接受原测试包-20261111.zip'
if not accepted_copy.exists():shutil.copyfile(old,accepted_copy)
assert sha(accepted_copy)==sha(old)
before=load(OUT/'protected-before.json');after={p:sha(p) if Path(p).is_file() else None for p in before};allowed={str(INSTALL/'HD2ModCore.dll')}|{f['path'] for f in source['files']};changed=[dict(path=p,beforeSha256=h,afterSha256=after[p]) for p,h in before.items() if h!=after[p]]
unexpected=[r for r in changed if r['path'] not in allowed]
assert all(r['path']==str(INSTALL/'settings.json') for r in unexpected),unexpected
for r in unexpected:r.update(actionTaken='none; current settings preserved, never rolled back',classification='task-concurrent settings change; not written by physics synchronization scripts')
if unexpected:shutil.copyfile(INSTALL/'settings.json',OUT/'settings-observed-after.json')
save(OUT/'protected-after.json',after);save(OUT/'protection-verification.json',dict(status='PASS',capturedFiles=len(before),unchanged=sum(h==after[p] for p,h in before.items()),expectedChanges=[r for r in changed if r['path'] in allowed],concurrentSettingsChanges=unexpected,unexpectedAgentChanges=[],gameDeployed=False,staleGameSnapshotRestored=False,olderSingleFixStagingPreserved=True))
feedback=load(OUT/'accepted-feedback-and-live.json');now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
archive=ARCH/'test1201-Source2-已验收-源码与二进制-20261111.zip'
report=f'''# test1201 Source2：已接受、正式代码同步及封档（2026-11-11）

## 当前状态

用户反馈原文：**“{feedback['userFeedbackVerbatim']}”**。

本轮 Source2 已据用户实际试用反馈接受并冻结；正式 runtime **2.3.3** / compat **1.3.3** 已同步根源码、`HD2ModManager_main` 镜像物理源码和指定 `manager-1.0.7` 的 Core。正式源码相对已接受 Source2 仅去除两处测试版本后缀，不调参数、不移除严格资源/bind 闸、不增加风或碰撞。`[test1201-source]`/`[test1201-front]` 为保留的历史取证标签，不表示正式包仍是待测版。

## 正式物理包

- [物理运行时-正式版-2.3.3.zip]({formal.as_posix()})
- 大小：**{formal.stat().st_size:,} 字节**；SHA-256：`{sha(formal)}`。
- 从**实际安装的** `HD2ModCore.PhysBoneLuaPackageExport.Export` 导出，不是重命名旧测试 ZIP。
- ZIP 根目录恰好 `manifest.json`、`9ba626afa44a3aa3.patch_0`、其 `.stream` / `.gpu_resources` 四文件；sidecar 为零字节。沿用 owner `mods/hd2modmanager/physbone` / Guid `7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01`，保持已接受 Arsenal 平铺布局。
- 只保留一份物理模块：停用 Source1/Source2/旧正式物理，导入本 ZIP、正常应用配置并重启游戏。现有模型/动画不需重导或重烘。**本轮未导入活动库、未应用配置、未写游戏部署。**

## 实机证据与验收边界

`{feedback['sessionStart']}` 会话启动 `2.3.3-test1201-source2`；8 个护甲实例全部 `SELECTED identity=Unit.resource_name`，未见 scoped 资源拒绝。实际 Hips `34a40a5ae7a392ba` 同一次最终 flush 的 READBACK **58 节点**，最大世界旋转误差 **0.000011°**、位置误差 **0.000002553 m**，flushCount=1。前裙取证 {feedback['frontSampleCount']} 行，实测日志完整保留。

用户“暂无明显问题”覆盖本轮试用，不扩张为所有模型/全动作/长期多人/精确 FPS 或几何碰撞穷尽验收。正式无后缀 2.3.3 尚未再次单独实机运行；与已接受 Source2 的完整内联 Lua 经 LF 归一化后只差版本字符串。受控自由回放 `pd.010/pd.011` 最大约 7.19° / 9.2mm 数值敏感性仍保留原记录，不宣称全骨架与 L4D2 完全一致。

## 同步与复核

- 当前正式 Core **16,917** 方法（含 IL、栈/局部变量/异常区域）、**575** 常量和程序集身份相同；**38** 内嵌资源中 **36** 不变，恰好两份物理 Lua 更新。B3/FP/挂点资源、GUI DLL、其它管理器逻辑均未混入变化。
- 两份物理源码、物理版本元数据/构建脚本及限定版本断言同步根目录与镜像；只更新物理字段，不覆盖单骨架/R2/B3/第一人称其它字段。源码与安装 DLL 资源一致。
- 较旧 `outputs/single-hd2-fix-20261106/manager` 是不同的 31 资源旧基线，本轮保持冻结，没有拿当前 38 资源 B3 Core 覆盖或虚报升级。
- 正式候选：**95,444 FK/lifecycle**、**102 资源身份**、**30,498 边界**、**100,920 位置/受控跑动**检查、**21 既有/真实 Chef**套件通过；镜像既有 test06 回归 **14,397** 项通过。
- Chef 1.4.1 实际解析器/沙箱/模块选择验证正式 2.3.3，60 update/render 空场景零写入；实际正式导出 payload 逐字读回一致。
- 正式安装资源冻结构建下 **24 项 .NET LuaAddonPackageTests** 全过。最初未冻结资源的直接构建遇到旧物理版本断言及既有未组合 B3 模板占位符：物理断言已定向更新，未借本轮改动其它 B3 模板；按正式构建的资源冻结流程完成复核。
- 本轮新快照 **{len(before)}** 个当前保护文件，**{sum(h==after[p] for p,h in before.items())}** 不变，同步脚本差异仅为明确物理同步白名单；另观察到运行期间 `settings.json` 变化（共 {len(unexpected)} 文件），原样保留，未由本轮脚本改写/回滚。模型、动画、模组库、启用配置和游戏 patch 保持。未按旧游戏快照回滚；未 Git 提交/推送。

## 归档与回退

- [Source2 原测试包同字节归档]({accepted_copy.as_posix()})；原测试包文件名和字节冻结，SHA-256 仍为 `{sha(old)}`。原“待测试”名称是历史交付名，不代表当前验收状态。
- [源码与二进制封档 ZIP]({archive.as_posix()})：正式代码/版本断言/工具、已接受原测试包及 Source2 原模板、当前实机日志、所有验证报告、正式安装 Core 和构建 PDB、**本轮当前基线** Core/源码/元数据备份、逐文件 SHA-256。
- 物理效果回退：停用正式 2.3.3，重新导入归档的已接受 Source2 或旧正式 2.3.1，正常应用并重启。管理器回退需要一并恢复归档 `before` 中对应 Core 与安装 `build-info.json`；先退出管理器，不只改版本号。不要回填过期 game patch。

工作证据：[本轮目录]({OUT.as_posix()})。封档时间 `{now}`。
'''
doc=ROOT/'docs/test1201-source2-accepted-20261111.md';guide=INSTALL/'非运行文件/说明文档/test1201-Source2-正式物理2.3.3-已验收-封档.md'
assert not doc.exists() and not guide.exists();document(doc,report);document(guide,report);document(ROOT/'HD2ModManager_main/docs/test1201-source2-accepted-20261111.md',report)
old_doc=ROOT/'docs/test1201-source2-resource-identity-20261111.md';text=old_doc.read_text('utf8');lines=text.splitlines(keepends=True);lines.insert(2,f'> **最新状态（2026-11-11）：用户本轮实测暂无明显问题，已接受并封档，正式 runtime 2.3.3 / compat 1.3.3 已同步。** 实机 SELECTED 8 / READBACK 58 已确认；下文“尚未验收/未改正式代码”等为原 Source2 测试交付时的历史状态。当前交付见 [正式同步与封档报告]({doc.as_posix()})。\n\n');document(old_doc,''.join(lines))
memory=f'- 2026-11-11 用户原文“{feedback["userFeedbackVerbatim"]}”：test1201 Source2本轮试用已接受冻结（非全模型/全动作/长期多人/FPS/几何穷尽）。20:36:54实机2.3.3-source2，8 SELECTED identity=Unit.resource_name/174节点，Hips34a40a5ae7a392ba同一次flush READBACK58 maxQ.000011deg/maxP.000002553m；仅去两处测试版本后缀升正式runtime2.3.3/compat1.3.3，完整源码/49spring+9VRD/2腕排除/11精确资源/bind守卫/数学参数保持。根与main镜像物理源码/版本断言/物理元数据同步；当前manager-1.0.7 Core16917方法(含IL/local/EH)/575常量/身份不变，38资源只2物理变化，B3/FP36资源及GUI不动。验证自锁已改shadow-copy，实际安装导出正式平铺4根文件ZIP297150B/SHA{sha(formal)}，非测试ZIP改名。95444FK+102身份+30498边界+100920位置/受控跑动+21既有/真Chef+24.NET+镜像test06 14397过；保留pd10/11自由回放7.19deg/9.2mm分歧，正式无后缀未另实机。旧31资源single-fix staging冻结不混B3；当前保护167文件除物理同步外观察到settings.json并发变化（保留未回滚），未库导入/模型重导/动画重烘/配置改写/game部署或过期快照恢复/Git推送。原Source2 ZIP名字/字节SHA9e05a4b3...冻结，同字节归档与源码二进制备份/实测日志/验证成套；正式包在既有非运行文件/打包输出/物理运行时-正式版-2.3.3.zip，封档在非运行文件/归档/test1201-Source2-已验收-源码与二进制-20261111.zip；docs/test1201-source2-accepted-20261111.md、outputs/test1201-source2-accepted-20261111成套。\n\n'
for p in [ROOT/'AGENTS.md',ROOT/'HD2ModManager_main/AGENTS.md']:
 text=p.read_text('utf8');head,tail=text.split('\n',1);document(p,head+'\n\n'+memory+tail.lstrip('\n'))
record=dict(status='ACCEPTED_SYNCED_ARCHIVED_FORMAL_PACKAGE_DELIVERED',acceptedAt=now,userFeedbackVerbatim=feedback['userFeedbackVerbatim'],formalPackage=dict(path=str(formal),bytes=formal.stat().st_size,sha256=sha(formal)),acceptedTestArchive=dict(path=str(accepted_copy),bytes=accepted_copy.stat().st_size,sha256=sha(accepted_copy)),guide=str(guide),report=str(doc),coreSynced=True,gameDeployed=False,oldStagePreserved=True,protectedFiles=len(before),unexpectedAgentProtectionChanges=0,concurrentSettingsChanges=unexpected)
save(OUT/'acceptance-final-record.json',record)
files={}
def include(p,name):
 assert p.is_file() and name not in files,(p,name);files[name]=p
include(formal,'正式物理包/'+formal.name);include(Path(str(formal)+'.provenance.json'),'正式物理包/导出来源.json');include(accepted_copy,'已接受Source2原包/'+accepted_copy.name)
for p in (OUT/'before').rglob('*'):
 if p.is_file():include(p,'before/'+p.relative_to(OUT/'before').as_posix())
for f in source['files']:p=Path(f['path']);include(p,'正式源码/'+p.relative_to(ROOT).as_posix())
for p in ROOT.glob('tools/*'):
 if p.is_file() and p.name in ['archive_test1201_source2_accepted.py','Prepare-AcceptedPhysicsCore.ps1','Sync-AcceptedPhysicsCore.ps1','Sync-Test1201AcceptedSources.py','verify_test1201_source2_accepted.py','Finalize-Test1201AcceptedPhysics.py']:include(p,'本轮工具/'+p.name)
for p in OUT.rglob('*'):
 if p.is_file() and not p.is_relative_to(OUT/'before') and not any(part.startswith('certification-') for part in p.relative_to(OUT).parts) and not p.is_relative_to(OUT/'resource-freeze') and not p.is_relative_to(OUT/'candidate') and not p.is_relative_to(OUT/'candidate-package') and not p.is_relative_to(OUT/'installed-package') and not p.is_relative_to(OUT/'patch'):include(p,'本轮证据/'+p.relative_to(OUT).as_posix())
include(INSTALL/'HD2ModCore.dll','正式安装/HD2ModCore.dll');include(OUT/'candidate/HD2ModCore.pdb','构建符号/HD2ModCore.pdb')
for p in TEST.rglob('*'):
 if p.is_file():include(p,'Source2原测试证据/'+p.relative_to(TEST).as_posix())
include(doc,'封档说明.md');include(old_doc,'原测试说明-含最新状态.md');include(ROOT/'AGENTS.md','协作记忆-根.md');include(ROOT/'HD2ModManager_main/AGENTS.md','协作记忆-镜像.md')
members={n:dict(bytes=p.stat().st_size,sha256=sha(p)) for n,p in files.items()};assert not archive.exists()
with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,p in sorted(files.items()):z.write(p,n)
 z.writestr('逐文件SHA256.json',json.dumps(members,ensure_ascii=False,indent=2))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for n,v in members.items():assert hashlib.sha256(z.read(n)).hexdigest()==v['sha256']
record['sourceBinaryArchive']=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive),members=len(members));save(OUT/'accepted-archive-final.json',record);save(Path(str(archive)+'.sha256.json'),record['sourceBinaryArchive'])
# Final readback after documentation and ZIP creation: no protected game/library/model writes.
assert all((sha(p) if Path(p).is_file() else None)==h for p,h in after.items())
print(json.dumps(record,ensure_ascii=False,indent=2))
