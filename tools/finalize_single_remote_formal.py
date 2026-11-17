"""Seal the accepted A/B run and publish the two formal packages, without apply."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,re,statistics,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-ads-once-release-20261117';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';PROD=ROOT/'HD2PhysBoneCompat/src/production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,data):
 assert not p.exists(),str(p)
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb')as f:f.write(data)
before=json.loads((OUT/'protected-before.json').read_text('utf8'));changes=[p for p,h in before.items() if not Path(p).is_file()or sha(Path(p))!=h];assert not changes,changes
verified=json.loads((OUT/'formal-verification.json').read_text('utf8'));assert verified['status']=='PASS_TWO_FORMAL_PACKAGES'
for v in ['A','B']:
 for vm in ['lua51','luajit21']:
  assert '53 checks, 0 failures' in (OUT/(v+'-'+vm+'-single-ads-formal-test.lua-actual-zip.log')).read_text('utf8')
  for name,count in [('single-mainline-regression-test.lua',87),('multiplayer-skeleton-regression-test.lua',51)]:
   assert str(count)+' checks, 0 failures' in (OUT/(v+'-'+vm+'-'+name+'-full-baseline.log')).read_text('utf8')
feedback=json.loads((OUT/'log-snapshot.json').read_text('utf8'));assert all(x['stableSizeAndMtime']for x in feedback['records'])
observations={}
for v in ['A','B']:
 text=(OUT/'logs'/('hd2physbone_test01_'+v+'_perf.log')).read_text('utf8')
 records=[]
 for line in text.splitlines():
  if not line.startswith('TEST01_PERF t='):continue
  fields=dict(re.findall(r'([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)',line))
  if fields.get('identity')!='fp-confirmed':continue
  row={k:(float(fields[k])if k in ['t','avgMs']else int(fields[k])) for k in ['t','avgMs','players','sessions','chains','selfUnits','selfChains','remoteUnits','remoteChains','physicsExcluded','vrdExcluded']}
  row['remoteVrdWriteAvg']=float(fields['remoteVrdWriteAvg']);records.append(row)
 groups={}
 for n in sorted({x['players']for x in records}):
  items=[x for x in records if x['players']==n];values=[x['avgMs']for x in items]
  groups[str(n)]={'records':len(items),'sampledPluginMeanMsRange':[min(values),max(values)],'sampledPluginMeanMsMedian':statistics.median(values),'NOT_FPS':True}
 observations[v]={'runtimeVersion':'2.3.9'if v=='A'else'2.3.10','header':text.splitlines()[0],'groupsByObservedPlayers':groups,'lastConfirmedRecord':records[-1],'normalShutdown':text.rstrip().endswith('TEST01_PERF_SHUTDOWN')}
 assert records and all(x['remoteVrdWriteAvg']==0 for x in records)
assert observations['A']['lastConfirmedRecord']['players']==3 and observations['B']['lastConfirmedRecord']['players']==4
analysis={'userFeedback':{'A':'性能有大幅优化，仍比不过主线','B':'有小幅优化，仍有主线性能差距'},'observations':observations,'actualFpsCsvSupplied':False,'differentPlayerCountsNotDirectABFpsComparison':True,'scope':'Archive only; multiplayer all-physics optimization deferred to TODO'}
(OUT/'accepted-run-analysis.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
# A sealed archive uses copies, never moving/removing live logs or old libraries.
archive_dir=NORMAL/'非运行文件/归档';archive_dir.mkdir(parents=True,exist_ok=True);assert archive_dir.resolve().is_relative_to(ROOT.resolve())
archive=archive_dir/'单骨架物理AB实测版本与运行日志-20261117-封档.zip';assert not archive.exists()
items={}
for p in (OUT/'logs').iterdir():
 if p.is_file():items['logs/'+p.name]=p.read_bytes()
for p in (OUT/'accepted-inputs').rglob('*'):
 if p.is_file():items['accepted/'+p.relative_to(OUT/'accepted-inputs').as_posix()]=p.read_bytes()
items['log-snapshot.json']=(OUT/'log-snapshot.json').read_bytes();items['accepted-run-analysis.json']=(OUT/'accepted-run-analysis.json').read_bytes()
items['README.md']='''# 单骨架物理 A/B 实测封档（2026-11-17）
用户确认 A 大幅性能改善，B 小幅改善，二者仍落后主线。只封存该定性结果，不虚构具体 FPS/1% low。
日志均来自实际 Roaming Arrowhead 会话，原字节保存；A 末段3人/B末段4人，不能直接作同人数 FPS 比值。
accepted/ 内保留原2.3.9/2.3.10测试包、各自源码，以及仍在库内的A实机载荷校验。B已从当前库移除，不能声称本次重比了当前B patch。
原测试包冻结；不再发布新的测试包或请求追加测试。新一次激活逻辑按用户要求直接正式发布，离线门禁不等于新游戏实测。
'''.encode('utf8')
entries=[{'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}for name,data in sorted(items.items())]
items['manifest.json']=(json.dumps({'schema':'hd2-physics-accepted-run-archive-v1','sealedDate':'2026-11-17','timezone':'Asia/Shanghai','status':'SEALED_COPY_NO_ORIGINAL_DELETION','entries':entries},ensure_ascii=False,indent=2)+'\n').encode('utf8')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9)as z:
 for name,data in sorted(items.items()):z.writestr(name,data)
with zipfile.ZipFile(archive)as z:
 assert z.testzip()is None
 for entry in entries:assert hashlib.sha256(z.read(entry['path'])).hexdigest()==entry['sha256']
# Independent formal family: deliberately do not select an embedded manager default.
formal_dir=NORMAL/'运行时配套';formal_dir.mkdir(exist_ok=True);assert formal_dir.resolve().is_relative_to(ROOT.resolve())
names={'A':'物理运行时-单骨架-A-仅自己物理-2.3.11-正式版.zip','B':'物理运行时-单骨架-B-多人保留物理禁VRD-2.3.12-正式版.zip'}
packages=[]
for v,name in names.items():
 target=formal_dir/name;source=OUT/(v+'-export/physics-runtime.zip');save(target,source.read_bytes())
 proof=next(p for p in verified['packages']if p['variant']==v);assert sha(target)==proof['zipSha256']
 packages.append({'variant':v,'path':str(target),'runtimeVersion':proof['runtimeVersion'],'compatVersion':'1.3.9','bytes':target.stat().st_size,'sha256':sha(target)})
# Append only the requested TODO; preserve the existing paused FP task unchanged.
todo=ROOT/'docs/TODO.md';raw=todo.read_bytes();assert '多人同时开启单骨架物理的主线性能对齐'not in raw.decode('utf8')
addition='''
## 多人同时开启单骨架物理的性能优化（2026-11-17）

- [ ] **多人同时开启单骨架物理的主线性能对齐**（用户要求列为 TODO，本轮不继续做）。
  - 当前实测反馈：A仅自己物理大幅改善但仍不如主线；B保留队友物理、只禁VRD小幅改善，仍有主线性能差距。最大4玩家，不是4件衣物上限。
  - 后续重点对比主线逐Unit实际消费者/骨集合与本地完整rig重复求解、全局发现/负匹配重试、VRD职责；不只降低自己的物理刷新率或依据资源名去重。
  - 需在同模型/同场景/同设置1→2→4人取得实际FPS/帧时间，并保护每模型真实bind/contacts/FK、作者参数和已有物理表现。不得将离线Lua计时/调用次数当FPS。
  - 本轮原A2.3.9/B2.3.10实际日志与测试版本已封档；A末段3人、B末段4人，不将这两段计时直接归因于同人数性能。
  - 暂不重导/裁骨/重烘/改库配置/游戏部署，不再要求本轮追加测试版测试；待后续明确授权再实施。
'''
todo.write_bytes(raw+addition.encode('utf8'))
readme=NORMAL/'非运行文件/说明文档/单骨架物理AB正式版-首次瞄准激活与封档-20261117.md'
links={r['variant']:'['+r['variant']+' 正式版 '+r['runtimeVersion']+'](<'+Path(r['path']).as_posix()+'>)'for r in packages}
text=f'''# 单骨架物理 A/B 正式版（2026-11-17）

用户确认：A 性能大幅优化、B 小幅优化，但均仍落后主线。按要求结束测试版迭代，直接发布两正式策略。

|包|首次确认前|确认后|
|---|---|---|
|{links['A']}|单骨架物理/VRD均不运行|只运行自己的完整物理和VRD，其他人物不运行|
|{links['B']}|所有未确认角色只运行弹簧物理，不运行VRD|自己完整物理/VRD；其他人物保留弹簧、禁VRD|

共同 compat 1.3.9。仅单骨架；双骨架/native/direct不变。没有改变模型、动画、作者物理参数、bind/contacts/FK或根配置。

## 一次激活

- 首次第一人称瞄准时，用当前主视角相机与原生FP Avatar @BT@d0cf4d493ca08bed@BT@ 的相机节点51位置匹配，再确认唯一TP玩家实例。不是仅判断相机最近、资源同名、FOV或鼠标按键。
- 连续3次瞄准期证据确认后，锁定该实例。此后不再查询FP图/相机节点或重做自己身份识别；退出瞄准、队友进出、同人物换装不会重新检查。
- 只在自己的实例/世界确实失效时重新等待首次瞄准，避免重生后读旧Unit；不为猜身份而自动把队友认作自己。
- 仍保留必要的静止预览清理、近远调度、死亡/加载安全和新部位归属。它们不是持续的自己身份确认。
- 正式包没有原20分钟1:8性能采样，只保留事件日志 @BT@hd2physbone_A_identity.log@BT@ / @BT@hd2physbone_B_identity.log@BT@，位于Chef现有Roaming日志根；确认事件为 @BT@LOCKED_NO_MORE_ID_CHECKS@BT@。

## 正常使用

只启用你选的一份正式物理，停用旧测试物理；按正常流程手动应用并完整重启游戏。没有自动导入、改勾选、应用或游戏部署，也没有替你选择/覆盖管理器内置默认A/B策略。不要从旧内置入口再导出旧包替代本次正式ZIP。

无需继续测试版测试，也无需重导模型或重烘动画。新一次激活实现已过离线发布门禁；不冒称这一新改动另有一次游戏FPS验收。

## 归档与 TODO

- [原A/B实际日志、版本与源码封档](<{archive.as_posix()}>)：11份实际日志，原字节/SHA/CRC留存，原文件未删改。
- [多人同时开启单骨架物理的性能 TODO](<{todo.as_posix()}>)：B仅禁VRD仍落后主线，后续再按1/2/4玩家真实帧时间、逐Unit负载和发现成本优化。此轮不继续实施。
- 不把A末段3人与B末段4人的插件计时当同人数FPS对比；用户未提供精确FPS CSV。
'''.replace('@BT@',chr(96))
save(readme,text.encode('utf8'))
report=ROOT/'docs/agent/physics-single-ads-once-formal-20261117.md'
report_text=f'''# 单骨架 A/B 实测封档与首次瞄准一次激活正式发布

日期2026-11-17，Asia/Shanghai。最新用户请求：A性能大幅优化但仍逊于主线，B小幅优化；归档实际日志，不再继续测试版测试，首次第一人称瞄准确认对应玩家后停止检查，双包直接正式，多人同时物理的性能列TODO。

## 交付与边界

{links['A']} / {links['B']}，共用1.3.9。正式源码来自production/single_ads_identity.lua.in、single_remote_policy.lua.in、single_remote_A/B_runtime.lua、single_remote_compat.lua及single_remote_release_manifest.json。基于已反馈接受的2.3.9/2.3.10源码，并非只给旧测试ZIP改名。

真实主视角与FP原生camera51位置匹配采用已有production/native_first_person_guard1.0.0证据形式，不新增未经实录的骨/相机轴对齐假设。只读root5/camera51名称与实际节点数，扩展FP输出仍不能授权写原生FP骨或借旧bind。唯一TP根水平0.35m、3次证明后instance锁定，生命周期内停止所有FP/自己身份检查；仅实例失效重置。正式A确认前全停、之后仅自己；正式B始终保留弹簧、确认后自己的VRD启用，其他人物VRD关闭。每会话仅epoch/owner变化时应用策略，停止每帧逐玩家/VRD条目重算；保留已有预览清理和必要生命周期，不停安全检查。

删除正式长时Perf代码与clock/GC采样，事件日志独立，不覆盖原测试性能日志。没有降自己的刷新率、裁骨、改作者参数/模型/动画/配置、选默认策略或写normal Core/游戏。独立双正式包由各自候选Core的实际导出器生成，39资源中仅2物理不同，19802方法/670常量/身份/引用不变；standard owner/GUID及四根CRC/长度/SHA/源码和production输入同源。整个compat仅从已测1.3.8改版本1.3.9，全部数学/driver/真实bind/contacts/FK/T1201/T16数据逐字节保持。

## 验证

默认正式策略各53检查，Lua5.1/LuaJIT2.1通过；实际ZIP提取源码两VM再过53。覆盖未瞄准不确认、保留FP图不误激活、首次唯一瞄准后不再查询、相机更近队友、换装/新玩家不重检、死亡重生/世界失效、FP97保留原生prefix、歧义两人拒绝与17件不裁。full-baseline显式singleFormalPolicy=false各87+51两VM通过，非默认正式行为的虚假全开验收。实导源码/producer输入/完整compat/两VMplain-Chef-Cowboy元数据安装卸载与重复回调通过；新逻辑按用户要求直接正式，未重新做游戏试包测试或宣称新增实际FPS成绩。

{len(before)}冻结当前程序/模型/用户输入SHA不变；完整rootConfig {sha(NORMAL/'config.toml')}，双手0.7/0.7/1、single false与后续自定义保留。normal Core {sha(NORMAL/'HD2ModCore.dll')}未写，不自动导入应用部署、启动GUI游戏、提交Git或替用户选默认。

## 实际运行封档

[封档ZIP](<{archive.as_posix()}>)，SHA {sha(archive)}，{archive.stat().st_size}B。11份真实Roaming日志含A/B perf、compact、Chef main/old/health/trace/settings/state、armor registry与hd2physbone.log；原字节逐项hash/CRC验证，原文件与旧库不删改。accepted保存原测试ZIP、两套源码和仍在库内A载荷（与已发A完全一致）。B已从库删除，本次只记录版本/实际mode日志，不声称重比其当前patch。

A最后已确认记录：3玩家、27Unit/324链，自己9/108，远端18/216全排除，avgMs2.082，远端VRD写0。
B最后已确认记录：4玩家、36Unit/432链，自己9/108，远端27/324物理保留、162 VRD排除，avgMs6.352，远端VRD写0。
这些是不同人数下采样插件CPU平均，不是FPS；用户定性验收保留，不虚构130+/1%low或作直接A/B比例。

## TODO

[docs/TODO.md](<{todo.as_posix()}>)新增“多人同时开启单骨架物理的主线性能对齐”：4为玩家非件数，后续看真正逐Unit消费者/骨集合、完整rig重复负载、负重试全局发现与VRD职责、同场景真实FPS/帧时间，保护当前参数与各模型真实配置。仅登记，未继续实施或要求新测试版测试。

证据 {OUT.as_posix()}：log-snapshot、accepted-run-analysis、accepted-inputs、source-build、A/B core-audit、formal-verification、实际提取Lua门禁、delivery JSON。使用说明：[正式双包说明](<{readme.as_posix()}>)。
'''
save(report,report_text.encode('utf8'))
agent=ROOT/'AGENTS.md';raw=agent.read_bytes();assert '## 单骨架 A/B 实测封档与一次瞄准正式包'not in raw.decode('utf8')
section=f'''
## 单骨架 A/B 实测封档与一次瞄准正式包（2026-11-17）

- 用户已反馈A大幅优化但仍不如主线、B小幅；结束测试版测试，双包直接正式；多人同时物理的性能列docs/TODO.md，本轮不继续优化或要求试包。不是精确FPS验收，不虚构130+/1%low。
- 正式独立A2.3.11（仅自己）/B2.3.12（别人弹簧保留禁VRD），共用compat1.3.9，normal运行时配套两ZIP；生产family在src/production/single_remote_*与single_ads_identity.lua.in+manifest。不暗选/替换程序内置默认A/B，normal Core/主默认2.3.7入口保留，用户配置/库/勾选不写、不应用部署启动或Git提交。
- 按已有production FP视角证据：resource d0cf4d493ca08bed、原生root5/camera51、主相机位置8cm、唯一TP水平35cm/连续3次。只有真实FP匹配后识别自己，确认后整个实例生命周期停止FP/自己身份查询；换装队友变化不重检，自己重生/换world才重新待瞄准。A确认前全停；B确认前所有仅弹簧/禁VRD，确认后自己完整VRD。不用相机最近/FOV/鼠标键猜身份。
- 策略仅会话epoch/owner变化应用，不每帧遍历玩家/VRD记录；删除正式Perf长采样，只有独立A/B identity事件日志32k。保留预览清理、近远调度与活体/世界安全；自己stride1，4是玩家非件数、作者参数/真实bind/contacts/FK/T16/Source2/腕排除不变。
- 默认53两VM+真ZIP提取53两VM、显式旧full87+51两VM、整个compat仅版本改动/实导CRC/SHA/owner/GUID/生产source/安装卸载通过；19802方法/670常量/39资源仅2 Lua不同。170冻结输入SHA不变，root ff64a88...不变。新一次逻辑直接正式，未新游戏实测。
- 原测试包与11真实日志封档normal非运行文件/归档/单骨架物理AB实测版本与运行日志-20261117-封档.zip SHA {sha(archive)}。原日志/旧ZIP不删改；A末3玩家27unit/324链排216、CPU2.082ms，B末4玩家36/432保324排162VRD、CPU6.352ms，不能当同人数FPS比较；A实际当前载荷同已发包，B已移库不可冒称重比。report docs/agent/physics-single-ads-once-formal-20261117.md，证据outputs/physics-single-ads-once-release-20261117；已归档发布，不重复发测试版。

'''
head=raw.index(b'\n')+1;agent.write_bytes(raw[:head]+section.encode('utf8')+raw[head:])
changes=[p for p,h in before.items()if not Path(p).is_file()or sha(Path(p))!=h];assert not changes,changes
result={'status':'TWO_FORMAL_PACKAGES_DELIVERED_ACCEPTED_RUN_SEALED_TODO_ONLY','packages':packages,'archive':{'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'realLogs':11,'entries':len(items),'crcAndHashesPassed':True},'readme':str(readme),'report':str(report),'todo':str(todo),'protectedInputs':len(before),'protectedChanges':[],'managerEmbeddedDefaultChanged':False,'normalCoreChanged':False,'gameDeployment':False,'newGameplayTestRequested':False}
(OUT/'delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))
