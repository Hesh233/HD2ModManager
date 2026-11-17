"""Publish the corrected ship-full A/B formal packages; no game apply."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-ship-vrd-formal-20261117';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def new(p,b):
 assert not p.exists(),str(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb')as f:f.write(b)
protected=json.loads((OUT/'protected-before.json').read_text('utf8'));changed=[p for p,h in protected.items()if not Path(p).is_file()or sha(Path(p))!=h];assert not changed,changed
verification=json.loads((OUT/'formal-verification.json').read_text('utf8'));assert verification['status']=='PASS_TWO_FORMAL_PACKAGES'
for v in ['A','B']:
 for vm in ['lua51','luajit21']:
  for name,count in [('single-ship-formal-test.lua',45),('single-ads-formal-test.lua',53)]:
   assert str(count)+' checks, 0 failures' in (OUT/(v+'-'+vm+'-'+name+'-actual-zip.log')).read_text('utf8')
  for name,count in [('single-mainline-regression-test.lua',87),('multiplayer-skeleton-regression-test.lua',51)]:
   assert str(count)+' checks, 0 failures' in (OUT/(v+'-'+vm+'-'+name+'-full-baseline.log')).read_text('utf8')
names={'A':'物理运行时-单骨架-A-舰船全开任务仅自己-2.3.13-正式版.zip','B':'物理运行时-单骨架-B-舰船全开任务队友禁VRD-2.3.14-正式版.zip'}
folder=NORMAL/'运行时配套';assert folder.resolve().is_relative_to(ROOT.resolve());packages=[]
for v,name in names.items():
 source=OUT/(v+'-export/physics-runtime.zip');target=folder/name;new(target,source.read_bytes());proof=next(x for x in verification['packages']if x['variant']==v)
 assert sha(target)==proof['zipSha256'];assert zipfile.ZipFile(target).testzip()is None
 packages.append({'variant':v,'runtimeVersion':proof['runtimeVersion'],'compatVersion':'1.3.10','path':str(target),'bytes':target.stat().st_size,'sha256':sha(target)})
links={x['variant']:'['+x['variant']+' '+x['runtimeVersion']+' 正式版](<'+Path(x['path']).as_posix()+'>)'for x in packages}
readme=NORMAL/'非运行文件/说明文档/单骨架物理AB正式版-舰船弹簧VRD全开修订-20261117.md'
report=ROOT/'docs/agent/physics-single-ship-vrd-formal-20261117.md'
text=f'''# 单骨架 A/B 正式版：舰船弹簧与 VRD 全开修订（2026-11-17）

按用户最新要求：**舰船没有第一人称，因此 A、B 在舰船均开启弹簧和 VRD，不等待瞄准，也不查询第一人称图。** 这是新正式包，不再发布测试版。

|包|舰船|任务|
|---|---|---|
|{links['A']}|所有单骨架人物弹簧＋VRD开启|首次FP瞄准确认后仅自己完整物理＋VRD；其他人物停算|
|{links['B']}|所有单骨架人物弹簧＋VRD开启|首次FP瞄准确认后自己完整物理＋VRD；其他人物弹簧保留、VRD关闭|

共同 compat 1.3.10；两包选一，停用旧物理，按正常使用流程手动应用并完整重启。无需重导模型、重绑或重烘动画；本次没有自动改库勾选/应用/部署或替你选程序内置默认。

## 场景与生命周期

- 优先从加载器稳定主世界读取真实 @TICK@World.num_levels@TICK@：舰船1/2 levels，任务大于10；零层/加载/无法确认不直接当舰船。
- 实际Chef1.4.1的 @TICK@api@TICK@ 是数字版本，原生函数调用使用受保护的 @TICK@loader.call@TICK@。无层数API时参考加载器稳定世界/任务信号，任务暂时checking同id的false不会打开舰船VRD。
- 即使engine World和玩家Unit没有换，只要舰船↔任务内容改变，也重置策略epoch，船上VRD不会泄漏给实战队友。
- 任务首次FP确认后不再查询FP图或重新确认自己；回舰船立即恢复所有单骨架人物弹簧与VRD。新任务/新实例重新待首次瞄准。
- 保留预览清理、活体/世界安全和原预算调度；只单骨架，双骨架/native/direct、作者参数、真实bind/contacts/FK、胸骨/Source2/腕排除和根配置不改。
- 不新增连续性能采样。事件日志仍为Chef日志根中的 @TICK@hd2physbone_A_identity.log@TICK@ / @TICK@hd2physbone_B_identity.log@TICK@，舰船事件 @TICK@SHIP_VRD_ENABLED@TICK@，任务 @TICK@MISSION_WAIT_AIM@TICK@，首次锁定 @TICK@LOCKED_NO_MORE_ID_CHECKS@TICK@。

离线发布门禁已通过：45舰船往返＋53瞄准/生命周期，两VM和实际ZIP提取源码都通过；旧full87＋51不变性、源码/完整compat/CRC/SHA/安装卸载与实际loader参数接入通过。**不是新增游戏FPS验收**，不再请求测试版测试。

旧2.3.11/2.3.12正式ZIP及此前A/B实际日志封档原样保留；本次使用这里的新2.3.13/2.3.14。多人同时物理性能对齐主线仍留 [TODO](<{(ROOT/'docs/TODO.md').as_posix()}>)，本轮不额外实施。

[完整修订报告](<{report.as_posix()}>)。
'''.replace('@TICK@',chr(96))
new(readme,text.encode('utf8'))
summary=f'''# 舰船弹簧与 VRD 全开：单骨架双正式包修订

2026-11-17。用户指出舰船没有第一人称、必须启用VRD，随后明确A舰船也要同时开启弹簧。因此最终A/B舰船行为完全一致：所有正向识别单骨架实例运行原弹簧＋VRD；任务保持A仅自己/B远端弹簧保留禁VRD。中途VRD-only草案未发布且已从生产代码移除。

## 同源与范围

{links['A']} / {links['B']}；共同1.3.10。整个compat相对上一正式1.3.9仅版本字节变化，数学/driver/所有真实bind/contacts/FK/T1201/T16/profile数据完全相同，没有引入VRD-only新求解器、裁骨或新参数。

生产single_ship_scene.lua.in读取loader稳定主世界、levels/in_mission/world_id；实际Chef源码make_api定义api=1和call(name,...)，不误当api函数、不绕过其安全包装。层数优先判定ship1/2与mission>10；0/未知不自动舰船，missinglevels下正向任务优先，旧任务同idcheckingfalse为unknown，新稳定非任务id才允许回舰船。每30回调低频取levels，信号/world/id变化即时重判。不用单位数量、没有瞄准、资源同名或相机最近猜舰船。

生产runtime安装从真实导出单文件词法loader参数取得sceneContext，隔离source可显式传context；已通过真实导出器结果的loader→state.options.sceneContext相等门禁。Single.tick舰船跳过ADS查询，两包船上预算/距离调度均按原逻辑，策略epoch变化同时清除旧ADS身份和更新所有会话，不让同World内容变化遗漏。任务仍一次证明锁定，角色/世界/场景失效才重置。每会话epoch/owner不变时不重复应用策略；日志仍独立事件型，无旧Perf采样。

## 交付校验

兩资源候选各19802方法/670常量/39资源，IL/引用/身份不变仅两物理；实际导出4根CRC/长度/SHA/owner/GUID、容器源码/内联两Lua与production manifest一致。默认45舰船1/2层、1/2/4玩家、sameWorld ship→mission→ship、checking假信号、实际Chef call/API数值和0/unstable世界门禁；原53FP/生命周期，两VM与实际ZIP提取源码全部通过。显式singleFormalPolicy=false旧87＋51两VM通过（不冒充默认正式行为验收）。whole accepted compat仅版本变化，两VM三loader元数据形态安装/重复安装/卸载、实际词法loader接入通过。

{len(protected)}当前程序/模型/库JSON/根配置/旧正式ZIP/原日志封档SHA均无变；rootConfig {sha(NORMAL/'config.toml')}，normal Core {sha(NORMAL/'HD2ModCore.dll')}未写。用户后续自定义保留，不导入/改勾选/应用/部署/启动GUI游戏/提交。此为用户要求直接正式重打包，未做新增游戏FPS测量或再次发试包；多人全物理与主线性能差距仍TODO。

旧正式包和f8b69c6e...原实测封档未覆盖，新包以[说明](<{readme.as_posix()}>)为准。证据 {OUT.as_posix()}：before全旧来源、source-build、protected-before、A/B core-audit/actual exports/extracted/门禁日志、formal-verification与delivery JSON。
'''
new(report,summary.encode('utf8'))
agent=ROOT/'AGENTS.md';old=agent.read_bytes();assert '## 舰船弹簧＋VRD双正式修订'not in old.decode('utf8')
section=f'''
## 舰船弹簧＋VRD双正式修订（2026-11-17）

- 用户补充舰船没有第一人称需VRD，最后明确A舰船也开弹簧；最终A/B舰船都全弹簧＋VRD，不等待/查询FP；任务仍A只自己/B远端弹簧保留禁VRD，首次ADS确认一次。未发中间VRD-only草案，生产无其代码。
- 新normal运行时配套A2.3.13/B2.3.14正式ZIP、compat1.3.10；整个compat相对1.3.9只有版本字节改，作者数学/真实bind/contacts/FK/T16/Source2/腕排除全保。旧2.3.11/12及实测封档不覆，新说明单骨架物理AB正式版-舰船弹簧VRD全开修订-20261117.md。
- single_ship_scene.lua.in按loader稳定主世界真实levels1/2 ship、>10 mission，0/未知不盲船；实际Chef api=1数字、call为受保护函数；missing层数任务checking同idfalse不误开船VRD。scene/world/id变化清epoch与ADS latch，sameWorld往返也正确，船不查FP；任务一次后停查询，船上两包原预算调度。
- 45舰船＋53ADS两VM及真ZIP提取同门禁、旧full87＋51两VM、整compat仅version、源码/CRC/SHA/owner/GUID/19802方法0变仅2Lua、安装卸载/真实导出loader→sceneContext过。173冻结程序/config/模型/库/旧正式包/封档SHA不变，ff64...根保持；normal/Core默认不改、不导入应用部署启动或Git提交。
- 用户要正式不再试包，未新增游戏FPS验收；多人全物理差距仍docs/TODO.md，不额外优化/降自己刷新率。report docs/agent/physics-single-ship-vrd-formal-20261117.md；证据outputs/physics-single-ship-vrd-formal-20261117，before留原1.3.9/A11/B12，生成器build_single_ship_vrd_formal.py与scene模板/清单成套，避免再次导旧不识船包。

'''
at=old.index(b'\n')+1;agent.write_bytes(old[:at]+section.encode('utf8')+old[at:])
changed=[p for p,h in protected.items()if not Path(p).is_file()or sha(Path(p))!=h];assert not changed,changed
result={'status':'SHIP_FULL_SPRINGS_VRD_A_B_FORMAL_REPACKED','packages':packages,'shipPolicy':{'A':'springs+VRD','B':'springs+VRD'},'missionPolicyUnchanged':True,'readme':str(readme),'report':str(report),'protectedInputs':len(protected),'protectedChanges':[],'oldFormalPackagesAndArchivePreserved':True,'gameDeployment':False,'newGameplayTestRequested':False}
(OUT/'delivery.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))
