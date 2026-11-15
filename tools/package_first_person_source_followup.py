"""Publish A2 and timestamped evidence inside the fixed manager's existing non-runtime categories."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile
from build_first_person_source_test import ROOT,BASE,OUT,VERSION,SOURCE_NAME

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def link(path):return path.resolve().as_posix()
def copy_new(source,target):
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():
  if source.read_bytes()!=target.read_bytes():raise FileExistsError(f'Preserve existing delivery: {target}')
 else:shutil.copy2(source,target)
 assert sha(source)==sha(target)
 return dict(path=str(target.resolve()),sha256=sha(target),bytes=target.stat().st_size)

def main():
 nonrun=BASE/'非运行文件';live=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/live-a1-135025';single=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/single-recovery-134120'
 build=json.loads((OUT/'build-report.json').read_text(encoding='utf-8'));receiver=json.loads((OUT/'receiver-validation.json').read_text(encoding='utf-8'));history=json.loads((OUT/'historical-regression-summary.json').read_text(encoding='utf-8'));chef=json.loads((OUT/'chef-fp-source-validation.json').read_text(encoding='utf-8'));fp=json.loads((live/'fp-a1-live-and-melee-analysis.json').read_text(encoding='utf-8'));rag=json.loads((single/'single-recovery-analysis.json').read_text(encoding='utf-8'))
 assert receiver['status']==history['status']=='PASS_PENDING_GAME_TEST' and chef['status']=='PASS'
 assert chef['sourceSha256']==build['luaSha256'] and sha(Path(build['package']))==build['sha256']
 assert history['testedNormalizedTransferSha256']==hashlib.sha256((ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua').read_text(encoding='utf-8-sig').encode()).hexdigest()
 protected=json.loads((OUT/'protected-before.json').read_text(encoding='utf-8'));changed=[p for p,h in protected.items()if not Path(p).is_file()or sha(Path(p))!=h];assert not changed,changed
 package=nonrun/'测试包'/Path(build['package']).name
 archive=nonrun/'交付附件'/'第一人称Source-A2与本轮记录-源码和验证-20261109.zip'
 doc=nonrun/'说明文档'/'第一人称Source接收A2与本轮布娃娃分析-20261109.md'
 fp_report=nonrun/'归档/测试报告'/'test06-FP-A1-实机失败与近战证据-20261109-135025.json'
 rag_report=nonrun/'归档/测试报告'/'test01-S3-落地恢复变形分析-20261109-134120.json'
 plot=nonrun/'归档/测试报告'/'test01-S3-落地恢复骨段变化-20261109-134120.png'
 motion=nonrun/'归档/测试报告'/'test01-S3-落地恢复骨段采样-20261109-134120.csv'
 total=receiver['runtime']['checks']+history['tpChecks']+history['fpChecks'];negative=len(receiver['runtime']['negativeControls'])+len(history['tpNegativeControls'])+history['fpNegativeControls']
 episodes='\n'.join(f"| {r['first'][11:]}–{r['last'][11:]} | {r['hipHeightBeforeWindowMax']:.2f} → {r['hipHeightWindowMinimum']:.2f} m | {r['seconds']:.2f} s |"for r in rag['fallRecoveryEpisodes'])
 text=f'''# 第一人称 Source 接收 A2 与本轮近战、布娃娃记录分析

2026-11-09（Asia/Shanghai）。状态：**源码与独立测试包离线通过，未部署、未实机画面验收。**

## 交付与边界

- [A2测试包：{VERSION}]({link(package)}) — **仅当前test06双骨骼/e6980827cce04d17右臂接收复核**，不是完整FP双臂/全武器握持修复。
- [源码、原始日志与验证归档]({link(archive)})。
- [A1实机失败及近战证据JSON]({link(fp_report)})。
- [本次test01 S3恢复分析JSON]({link(rag_report)})、[骨段图]({link(plot)})、[原始高频数值CSV]({link(motion)})。

换弹左手仍按用户要求暂不处理。磁轨炮弹药、训斥枪口已验收策略保持；没有同步/改写生产管理器EXE/DLL、活动库或配置，没有重导/重烘模型、动画或修改Havok/已验收VRD物理。历史A1、V12、S3包和旧报告保留，不按最高版本名混装。

## 1. A1为什么仍隐藏

读取的是2026-11-09 13:50:25–13:54:15的FP_SOURCE_A1会话，而非猜测活动安装状态。

- 32次FP47原生骨快照的Avatar计数都是 **97**：扩展图已安装，不是原FP63缺少Source输出。
- 目标右臂为 **e6980827cce04d17/264**；Source运行时记录 **1,797次接收匹配**，但也有 **1,539次 `fp_source_world_readback` 失败**。失败立即恢复输出、收回本帧显示许可。因此不能把它当作“始终没有匹配模型”，也不能称FP画面已经通过。
- 11条`fp_arm_source_receiver_visible`只是恢复原mesh mask的日志，**A1没有记录实际可见mesh数量**；原mask若全false，即使有许可也仍不可见。左侧4c28e97d1bf51e2b在阶段A本来就未放行。
- A1强制1Hz原生录制共用了接收日志限频槽，造成 **0条成功接收矩阵事件**。没有失败Source的actual/expected/parent矩阵，不能从该文件直接确定全部引擎根因。

原生FP矩阵scale偏差最大约{fp['maxNativeFpMatrixScaleDeviation']:.3g}，已录原生父/local复算最大误差{fp['nativeParentLocalFk']['maximumError']:.3g} m量级。32份已录原生输入的float32 FK复算最大差 **{fp['float32Replay']['maximumExpectedError']:.6g}**，全低于 **0.0002**；所以本版**不放宽容差**。

A1源码在采样原生世界姿态之后才刷新FP。离线安排“原生外部父已移动25mm，但FP仍是旧缓存”的时序，能复现A1同一回读断言；改为先刷新再采样后通过。**这是一项已复现的时序风险和安全修正，不是该实机文件已经直接记录到的全部根因。** A2补充矩阵用于确认剩余真实失败类型。

## 2. A2具体变化

1. 任务/FP视角及原生图身份通过后，**先刷新已验证FP生产者缓存，再复核视角并采样**；目标模型缓存刷新后仍须精确资源、264节点、命名索引、原生肩肘手三点及唯一接收者匹配。
2. 原FP63节点、47动画通道、相机/枪/挂点/模型pose均零写；只写追加的34个未动画Source输出。FP97图与A1逐字节相同，原模型和TP267配套/GPU/stream逐字节保持。
3. Source世界回读仍严格0.0002；所有Source模型接收仍0.002。若原生输入在输出刷新期间再次变化，拒绝显示并记录，不伪装成功。
4. **至少3个不同连续帧**，并要求Source与模型手都实际移动≥2mm、位移方向/量相符，才放行测试右臂。使用同一连续链的位移跨度，慢速0.4mm/帧动作不再因单帧阈值永远无法证明；模型冻结但矩阵误差落在2mm容差内不能借Source的移动获得许可。重复render不增加证明帧数。
5. 成功接收、原生录制和失败类型各自限频。失败补actual/expected/written local/parent及原生刷新前后；成功补完整Source/模型before-after；下次render明确标记 **update已恢复输出**，不假设上一帧写入仍保持。
6. 恢复Source后也刷新本次严格绑定模型的缓存。仍由原TP可见性账本恢复原逐mesh mask；新增saved/requested/actual可见数量。许可后实际0个可见mesh输出`fp_arm_source_receiver_not_visible`，不盲目显示全部网格/LOD。

本版仍是固定Source骨长FK接收阶段，**还未实现阶段B完整接触IK/双臂入口校准**。即使右臂可见，短Source臂仍可能离枪；不会用拉长骨段、挪枪或解除TP旁路掩盖。

## 3. 近战录制确实包含有效残差，但不能统一偏移

已同时读取11:25:49 V12双骨骼日志及13:50:25 A1日志的TP段。下表为同帧最终**骨架掌接触代理**，不是GPU网格表面；原生挂点位移都是0。

| 记录 | 右手最终残差 | 左手最终残差 |
| --- | ---: | ---: |
| 唯一真旗 11:28:40 / f21674 | 2.646 cm | 本帧无对应左手接触记录 |
| 破门锤 11:29:01 / f24326 | 0.0078 mm | 4.455 cm |
| 唯一真旗 13:53:43 / f24159 | 2.595 cm | 7.751 cm |

这与现有固定骨长IK的不可达残差一致，不能说V12已经修好近战；破门锤右侧代理几乎为0也不能替代用户对握持外观/手轴的反馈。

A1的FP段只录到10份旗帜对象根：位置完全不变、距所选FP右手 **2.704–3.243 m**，没有通过current local复合挂点关联。可能是缓存尚未消费，也可能是不同/脱手对象；**不能将这个对象根当成本机握点校准**。本轮日志没有砍刀、晕眩长矛可用实握样本。

A2因此增加四种精确资源的FP刷新前后根/current local、真实存在的IK_left及TP before/final/restore的原生手、Source手、挂点和链接假设矩阵，并保留近战完整contact/reachDetails。**没有新增统一xyz偏移、假IK_right、改武器local/link或宣称近战握点已修复。**

## 4. 指定S3日志：五次下落/恢复几何交接

原文件：[hd2_single_TEST_DETAILED_test01_RAGDOLL_S3_20261109_134120.log]({link(Path(rag['sourceLog']))})。

- {Path(rag['sourceLog']).stat().st_size:,} bytes；1,881份姿态记录、2,899份主模型高频骨段样本；`errors=0`、`poseWrites=0`，正常完成。
- 实际是 **test01 139节点模型与107节点TP Avatar**，**没有FP Avatar样本**。不能把test06 FP录制跨模型拼成test01落地的同步FP证据。
- 209对同帧低频快照的22个命名核心骨位置与TP Avatar差为0；4,598/4,598模型local平移为0，符合外部逐骨链接读数。导出parent fallback的距离不是“缓存坏了”的直接证明。
- world矩阵scale最大偏差约 **1e-6**；`position_and_rotation`模式在209份Native样本里恒定，并不是直接ragdoll标志。

| 骨段 | 模型尺寸动画常态 | 原生长度区间 | 本次最小/最大 |
| --- | ---: | ---: | ---: |
| 左上臂 | 22.841 cm | 约30.285 cm | 12.133 / 31.071 cm |
| 右上臂 | 22.842 cm | 约30.284 cm | 12.945 / 30.886 cm |
| 左前臂 | 20.960 cm | 约28.736 cm | 11.732 / 30.378 cm |
| 右前臂 | 20.960 cm | 约28.736 cm | **8.359 / 29.211 cm** |

右前臂最短在 **13:44:00 / f21425**，左上臂最短在 **13:43:46 / f19536**。恢复边界压缩约0.04–0.11秒，随后回到模型尺寸；高频主模型捕捉到了这些极值，不将209份低频Native对照扩大成每个高频极值都直接同步观测。

按髋高变化与原生骨长窗口归并的候选区间：

| 区间（2026-11-09） | 髋高观测 | 窗口跨度 |
| --- | --- | ---: |
{episodes}

另外，头→颈的导出父距离由约7.41cm到最大15.33cm、左肩→锁骨由约9.87cm到19.51cm，也说明不只是腕部。它们同样是世界节点间距，不是matrix scale；不将导出父关系当作直接Havok关节图。

![test01本次落地恢复世界骨段变化]({link(plot)})

**结论：更支持“模型尺寸动画与原生物理骨长之间的交接/混合或消费时序”方向，而非矩阵scale整体变大。** 尚未直接读取Havok刚体/关节与最终GPU palette，不能把相关性当作solver根因已证明。本轮只分析，没有改Havok、单骨架模型/动画，也不以Lua抢写所有骨或缩放模型硬压回去。S3原有禁止模型动画getter的防崩溃保护保持，旧S2不恢复使用。

## 5. 验证与保护

- FP97/模型264真实布局：**{receiver['runtime']['checks']:,}检查 + {len(receiver['runtime']['negativeControls'])}负控**；含32份实录FP47 float32输入、旧A1回读复现、慢速连续移动、同帧重复render、冻结模型在容差内拒绝、Source冻结、写期间原生变化、FP63只录制不写、同资源TP隔离/歧义/销毁。
- 历史TP/V12全套：**{history['tpChecks']:,}检查 + {len(history['tpNegativeControls'])}负控**；保留普通握持/C4/标记器/GL/JAR/颈锁骨FK、磁轨炮/训斥、内父与Unit根/脱手门禁，并验证四近战新录制无pose/local/link改动。
- 历史FP/可见性：**{history['fpChecks']:,}检查 + {history['fpNegativeControls']}负控**；原mask、全false mask不误报可见、其他玩家/躯干/预览不受影响、切TP/舰船/销毁/失败重试恢复。
- 合计 **{total:,}个正向检查 / {negative}负控**；实际Chef解析、沙箱、模块选择与60次update/render空场景通过。均为离线验证，非实机GPU/视觉验收。
- 本轮保护快照 **{len(protected)}文件全部SHA256保持**，包括安装Core/物理源码、活动配置与库、原模型、旧A1全部产物及旧报告。TP profile除新只读录制/版本标签外逐字段相同。
- A2 ZIP SHA256：`{build['sha256']}`；组合Lua SHA256：`{build['luaSha256']}`。

## 6. 下一轮短测

仅启用A2并停用A1/V12同名`attachment_fix`，保持当前test06双骨骼模型与已验收物理；**不要把A2用于test01单骨架**。包内FP配套不要删除，不需重导/重烘。

进入任务短测45–60秒：FP静止/小幅上下瞄准/行走/切回TP；有条件再持四种近战各5–8秒并攻击一次。左FP臂仍隐藏是阶段A预期；重点观察右臂是否持续可见且随动作移动。提供同时间视频/截图与`hd2_grip_TEST_PERF_test06_FP_SOURCE_A2_日期时间.partNN.log`。

若仍隐藏，A2日志会区分：未装扩展图、未找到唯一模型、Source回读失败/原生输入变化、动态证明未满足，或许可已通过但原mesh mask实际全false。不要把“receiver匹配/零error”直接当作画面成功，也不要直接取消所有隐藏。

### 源码与复现

- [FP运行时]({link(ROOT/'HD2PhysBoneCompat/src/first_person_source_test.lua')})、[TP握持/可见性与新只读录制]({link(ROOT/'HD2PhysBoneCompat/src/native_grip_transfer_test.lua')})。
- [原生FP图编译器]({link(ROOT.parent/'first_person_skeleton.py')})、[A2构建]({link(ROOT/'tools/build_first_person_source_test.py')})、[接收验证]({link(ROOT/'tools/verify_first_person_source_test.py')})、[历史回归]({link(ROOT/'tools/verify_first_person_source_regressions.py')})、[Chef验证]({link(ROOT/'tools/verify_first_person_source_chef.py')})。
- [A1/近战分析工具]({link(ROOT/'tools/analyze_first_person_source_live.py')})、[S3恢复分析工具]({link(ROOT/'tools/analyze_single_recovery_s3.py')})。

以上构建/验证工具支持`--out`指定新的工作区证据目录；复现时使用新目录，避免覆盖本轮已归档产物。S3使用`--log`明确指定本次134120文件及`--compare`指向旧113311分析，旧报告原字节保持。
'''
 source_doc=ROOT/'docs/first-person-source-a2-live-and-recovery-20261109.md';source_doc.write_text(text,encoding='utf-8')
 published=[copy_new(Path(build['package']),package),copy_new(live/'fp-a1-live-and-melee-analysis.json',fp_report),copy_new(single/'single-recovery-analysis.json',rag_report),copy_new(single/'single-recovery-shape.png',plot),copy_new(single/'single-recovery-motion.csv',motion),copy_new(source_doc,doc)]
 source_zip=OUT/archive.name
 sources=[ROOT/'HD2PhysBoneCompat/src'/name for name in ('first_person_source_test.lua','native_first_person_guard.lua','native_grip_transfer_test.lua','native_grip_transfer_test_entry.lua','single_ragdoll_probe_test.lua')]
 sources += [ROOT/'HD2PhysBoneCompat/test'/name for name in ('first_person_source_receiver_harness.lua','native_grip_first_person_harness.lua','native_grip_left_items_v12_harness.lua','fixtures/first_person_source_live_a1_20261109_135025.json')]
 sources += [ROOT/'tools'/name for name in ('build_first_person_source_test.py','verify_first_person_source_test.py','verify_first_person_source_chef.py','verify_first_person_source_regressions.py','analyze_first_person_source_live.py','analyze_single_recovery_s3.py','package_first_person_source_followup.py','prepare_native_v31_b23.py')]
 evidence=[OUT/name for name in ('build-report.json','receiver-validation.json','receiver-runtime-summary.json','historical-regression-summary.json','chef-fp-source-validation.json','fp-source-contract.json','B23-profile.json',SOURCE_NAME,'fp-expanded-unit.toc','fp-native-unit.toc','fp-native.bones','fp-model-unit.toc','protected-before.json')]
 evidence += [live/name for name in ('fp-a1-live-and-melee-analysis.json','live-native-fk-replay.json','replay_precision.py')]
 evidence += [single/name for name in ('single-recovery-analysis.json','single-recovery-shape.png','single-recovery-motion.csv')]
 evidence += [OUT/'legacy-tp-regression/full-runtime-regression.json',OUT/'legacy-fp-regression/第一人称门禁-Lua验证.json']
 raw_logs=[Path(r['path'])for r in fp['sourceLogs']]+[Path(rag['sourceLog'])]
 with zipfile.ZipFile(source_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  for path in sources:z.write(path,'source/'+path.relative_to(ROOT).as_posix())
  z.write(ROOT.parent/'first_person_skeleton.py','source/anim_batch_mod/first_person_skeleton.py')
  for path in evidence:z.write(path,'evidence/'+path.relative_to(ROOT/'outputs/grip-left-items-analysis-20261109/fp-start').as_posix())
  for path in raw_logs:z.write(path,'logs/'+path.name)
  z.write(source_doc,'说明/'+source_doc.name)
 # Reopen before readback: Windows ZipInfo.orig_filename from write() can
 # retain backslashes until the central directory is parsed on reopen.
 with zipfile.ZipFile(source_zip)as z:
  assert z.testzip()is None
  manifest={name:hashlib.sha256(z.read(name)).hexdigest()for name in z.namelist()}
 with zipfile.ZipFile(source_zip,'a',zipfile.ZIP_DEFLATED,compresslevel=6)as z:z.writestr('SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2))
 with zipfile.ZipFile(source_zip)as z:assert z.testzip()is None
 published.append(copy_new(source_zip,archive))
 for p,h in protected.items():assert sha(Path(p))==h,p
 report=dict(status='PASS_PENDING_GAME_TEST',published=published,totalPositiveChecks=total,totalNegativeControls=negative,protectedFileCount=len(protected),protectedFilesUnchanged=True,sourceArchiveEntryCount=len(manifest)+1,fpNativeWrites=0,modelPoseWrites=0,modelRebaked=False,animationRebaked=False,havokChanged=False,meleeGripFixed=False,reloadLeftDeferred=True,railgunUserAccepted=True,reprimandMuzzleUserAccepted=True,fpStage='A2_RIGHT_RECEIVER_RECHECK_NOT_FULL_FP_ARMS',gameDeployed=False,productionManagerUpdated=False,gameVisualVerified=False)
 (OUT/'delivery-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
