# 项目协作记忆

- 2026-11-06 按第一人称残留分析实施Lua1.0.13（待实机）：挂点/Source臂/躯干零setter与呈现维护分离；任务内main+实际FP World按Avatar→已知body（含隐藏）→附近已分类组件update_unit，不改pose/visibility/link。未知/舰船旁路、错误重试、TP重扫；FP实例/父状态/世界矩阵日志补齐，最终skin palette不可观测，具体残留Unit仍未实证。Lua323571含冻结cache负对照/.NET17/Python68/Chef通过；已确认1.0.11求解与248配套不改。固定manager安装Core+build-info已同步（锁已解除，2文件），单链实际1.0.17及进度保留；同目录1.0.13待测ZIP，无新目录/重烘/游戏部署。详见记忆三十三与固定目录第一人称门禁说明；不标记实机已解决。

- 2026-11-06 用户实机否定1.0.12 FP修复：进入FP臂残留固定world、回TP恢复。22:19–22:23门禁实触发/局部回滚平衡/无pending或disable；Source右输出回到引用。直接旁路同时停止了模型/Source呈现维护，FP63无自定义Source通道，具体残留实例/cache链仍缺FP段矩阵，不可宣称已定位到某Unit或已解决。此轮只读，固定目录第一人称残留-排查说明，详见记忆三十二节；TP已确认行为保持。

- 2026-11-06 用户确认1.0.11副武器表现正常；新增Lua1.0.12第一人称全挂点/Source臂/躯干输出旁路，update/render进入先恢复、TP重扫。实际FP63节点camera与主视图相机对应判定，图存在/ADS不够、未知视图保守旁路可恢复；Lua319526/.NET16/Chef通过，248配套与已确认握持函数不改。交付仅固定manager目录，未新建目录。Release暂存完成，但安装Core DLL被占用、更新器复制前停止，未强制覆盖/杀进程；待关闭管理器同步。ZIP可独立导入，未部署游戏/未FP视觉验收，详见记忆三十一节与固定目录第一人称门禁说明。

- 2026-11-06 单骨架动画实时进度已对齐混合打包并同步固定manager-1.0.7（单链1.0.16）：stdout错误流向修为stderr逐行flush，两路线共用进度回调，含校验/索引/0到N逐条生成/写包/成功完成；失败或取消不报完成。Python107/.NET16/路径过滤17通过，实际目标Python到管理器回调在子进程退出前触发，12条旧样本与原batch字节一致。未重烘用户模型动画/未游戏部署/未新建发布目录，原1.0.15模型无需因进度变更重导。详情同目录单骨架进度说明/验证JSON与记忆三十节。

- 2026-11-06 副武器修复已实现为Lua1.0.11/生成链1.0.15（待实机）：23副武器保持原生实时持枪路径，Source右臂3未动画输出同步；test07245→248节点、16绑定与原生107/左臂保持，模型动画不重烘。下挂选择/意图前段与1.0.10逐字相同。P4内部动画不写，新增原生/Lua分阶段只读采样。Lua316631/Python68/.NET15及真实248/120命名父记录/槽位/Core+Chef通过；独立ZIP与报告 outputs/test07-sidearm-fix-111-20261106/。未更新manager安装目录/活动库/游戏，导入需新248配套最后覆盖并重启；未标记P4全部分离或性能实机通过，详见二十八节。

- **用户固定目录约定（2026-11-06）**：“修复到\outputs\native-v34-b23-integrated-20261105\manager-1.0.7 ，以后不再新建目录”。后续管理器修复直接增量更新此固定目录，不新建其他发布/版本/备份目录；复用已存在的构建暂存，恢复副本仅为原目录内 .bak 文件。保留设置、用户配置、索引和模组库，未经要求不重烘/部署游戏。单骨架1.0.16（含实时进度）已同步，目标哈希/运行时校验通过；详情同目录单骨架修复说明与更新记录，记忆二十九节。

- 2026-11-06 最新1.0.10实机反馈：用户确认下挂已修复，保持冻结；P-4副武器瞄准仍低/分离。19:51–19:59同帧61瞄准代判定样本证明Source腕低于原生腕中位27.6cm，Lua枪根下拉中位27.9cm，原副武器目标选错/右臂未动态同步；内部弹巢不等于独立speedloader，部件矩阵缺项，不能记整枪已修好。本轮只读对比未改代码/包/部署，报告 outputs/test07-sidearm-followup-20261106/，详见记忆二十七节。

- 2026-11-06 test07握持Lua已增量修至1.0.10（待游戏）：下挂IK_left优先、23副武器实时IK_right、P-4独立装弹器、Chef任务/舰船隔离与数值/校验/成员表优化；Lua275656/Python65/.NET14与真实245节点/16绑定/Chef组合入口通过。独立待测ZIP及报告 outputs/test07-grip-fix-20261106/；未更新指定manager/活动库/游戏、不重烘模型动画，自动配套排序仍待修。详见记忆二十六节。

**最新实施：2026-11-06 生成链1.0.14已同步指定manager-1.0.7；Source挂点父记录/矩阵序列化、坏缓存父记录门禁与Lua入口版本修正完成，test01–08相关离线联调通过。十八节的“仅更新记忆”、二十三节的“源码待发布”均为历史状态；当前实施/验证边界以二十五节为准：test07最终覆盖顺序漏检已定位，外部重排后游戏已有写入，管理器自动配套排序仍待修；未完成视觉验收。**

- 最新用户结论（2026-11-06）：挂点对调不可行；非 HD2 骨骼仍需要 Lua 挂点动态修正。名称/hash 对调、静态改挂或离线 FK 不能作为 Lua 的替代。model-candidate 的对调产物不作为可行方案部署或推广；后续回到原模型基线 + 现有 Lua 修正链，并处理换甲后完整一对多 Unit ID 同步。此结论覆盖前面对调路线的试验/预期；历史已确认基线保持冻结，不擅自重烘或删改。本轮仅更新记忆，未启用 Lua、修改模型/代码/配置或部署。详见 docs/test01-grip-memory.md 第十八节。

- 用户约定（2026-11-05）：每次 AB 测试代码迭代都在现有实现上增量修正，复用已有模块、配置、构建脚本和回归测试，不从头重写或另起一套同功能代码。
- 完整握持约定和已确认的实机行为记录在 [docs/test01-grip-memory.md](docs/test01-grip-memory.md)。
- 用户确认（2026-11-05）：B23-LR 1.0.4 本轮左手握持与上身同步等问题已解决，作为已确认基线归档。下一步 TODO 是其他武器及握把组合的握持适配测试；目前其他武器握持未适配，不能把本轮确认视为通用适配完成。
- 用户澄清（2026-11-05）：GP-20 最后通牒全程双手，其他副武器仅瞄准时双手；平时左手分离。缺少左手握持的武器为 LAS-44 新星。排除头部子节点，只整合其他挂点；左右手单持物品须独立处理。
- 当前 test01 1.0.8 用户反馈“暂无发现明显问题”，仅记本轮观察通过。规范工程唯一入口 projects/test01-native-grip/（build.ps1 一键打包）；配置/小型输入/共享源码/不可变发布包/临时构建分离，详见记忆第十四节。ADS仍为姿态代判定，预览为小世界隔离，不扩大为全武器验收或手指根因彻底修复。

- 历史实现记录（以最新用户结论为准）：挂点代码曾共用 attachment_swap_plan 与 validate_attachment_transfer_contract，生成契约为最终手臂参考后互换、正确逆父级缩放并拒绝歧义/重叠/错参考；这些源码/离线契约不证明对调可替代 Lua。已观察的1.0.8和B22动作仍冻结，不重烘、不改字节。19个哈希确认动作副本已清理（12.950GiB），ZIP/当前动作/原生参考/基线保留；记录见 outputs/project-archive-cleanup-20261105/。

- 2026-11-06 manager-1.0.7重生成核查：随包源码已与当前/staging一致并含v2，但通用TOML缺test01参考手臂/模板校准；GUI transfer_profile仍B23-1.0.7默认策略（1.0.8 intent/performance/previewGuard未启用）。新1.1/183通道/205节点组不等价于原1.08/238/260观察组。仅换config不足、不能拷旧模型地址；修正说明与诊断示例见 outputs/manager-107-config-audit-20261106/修正说明.md。尚未修改或发布目标管理器。

- 2026-11-06 GUI生成链已修至1.0.9并更新指定manager-1.0.7兼容路径：managed v15模板/参考、旧config补项、公共1.0.8策略、两根原武器骨准确握点重算后互换、真实动画manifest名称[原比例混合动画](VPK名字)/描述[全量动作文件]。实际目标DLL/CLI按test01后test02各6条模拟通过，详情记忆十六/outputs/gui-native-pipeline-fixed-20261106/修复交付说明.md。仅抽样、未部署未游戏验收；旧生成组需重建整套，原1.0.8冻结组不改。

- 2026-11-06 VPK安装WinError5已修至生成链1.0.10：根因为ModLibraryImporter入库设只读后prepare-native-model改写模型。校准/配置快照前移至VpkImportService转换暂存（含同源更新），BuildAttachmentFix/BuildAsync仅--check-only；禁止解除库保护。目标manager-1.0.7路径已更新，实际Convert服务+真实只读入库+禁止写删句柄的test01/test02各6条生成通过；重复test02暂存更新决策/key通过。51 Python、34 .NET通过/1外部ZIP跳过；详情outputs/vpk-install-fix-20261106/修正说明.md，仍未全量重烘/游戏验收。

- 2026-11-06 test02 换 B-08已修正并实际部署：setId 3794083209被B-08/FS-38复用，自动配对改为DLC+set+相反类别，歧义拒绝；物理Unit跨归档合并同源映射、异源冲突拒绝。补齐同目录空sidecar，避免Overwrite混用来源stream。指定manager-1.0.7只更新CLI DLL/PDB、生成链仍1.0.10；实际发布GUI服务将test02换B-08（11 Unit/32隐藏）并保存wardrobe，管理员符号链接部署成功，24文件哈希核验、30原文件/配置未变。37换甲、242CLI通过；头身合并保持off，需B-08护甲+头盔，游戏视觉未验收。详情outputs/test02-target-fix-20261106/修正交付说明.md。

- 2026-11-06 用户实机反馈test02换B-08后挂点无效：实机Chef确认attachment_fix已on，但grip日志actors=1/consumers=53/models=0，attachmentWrites/leftWrites/writes=0、skipped=12183。审计确认Lua cfg.models仍绑定原6个61c014...自定义ID，实际B08身体10个新ID交集0；10个身体和最终Avatar均241节点且静态签名正确，body最终赢家patch3、Avatar配套patch7正确。上次换甲链漏同步独立挂点profile；需完整一对多Source→Target绑定（当前unitMap[from]=to还会漏Stocky/Slim），不能关闭门禁或重烘交换一次掩盖。本次只诊断，未改包/部署；详情outputs/test02-attachment-audit-20261106/诊断说明.md。

- 2026-11-06 挂点流程进一步澄清：用户解包实际test02 vpk2patch/patch0指出attach_*仍跟原生骨。直接Unit绑定/父链审计确认7个模型均如此；Torso attach_hand_r147→原生r_hand110、attach_hand_l133→原生l_hand119，test02武器骨40→test02手37、231→test02手56。动画applied=2仅轨道位置互换、保留Unit父级，不能当模型结构交换；同为241节点不代表模型/Avatar索引相同(模型147 vs Avatar84)。按用户模型层双向交换预期，当前结构未满足；Lua ID缺口是独立问题，单补ID不足。未改模型/部署，补充说明outputs/test02-attachment-audit-20261106/模型骨架交换核对补充.md。

- 2026-11-06 按用户“先改test02模型非头挂点、验证是否无需Lua”制作静态模型单独实验：6身体Unit各21个物品挂点改挂test02 Source骨，左右手/attach_weapon对接两个weapon_bone，cape子链保留，头部Unit/头后代未动。原只读vpk2patch基线保留，修正源模型在outputs/test02-static-mount-test-20261106/model-candidate；当前B08 Overwrite已部署10身体目标新父级、头盔载荷不变。当前配置rev21已去掉挂点Lua，原样保持；Avatar/动画未改，旧动画仍含交换轨道，是否游戏消费模型挂点待测，不能宣告无需Lua。3回归、99322/147366顶点零差、皮肤映射一致、20实际部署FK隔离、18文件哈希/30原文件/配置未变。暂勿换甲/重构建，确认后再合入生成链；说明outputs/test02-static-mount-test-20261106/测试交付说明.md。

- 2026-11-06 用户明确纠正：“原骨架”不是test02 Source，要求交换而非单向改挂，且不需要测试。上轮static-mount模型变体已撤销，管理器安全deactivate/redeploy恢复先前B08（当前配置不变、挂点Lua仍未启用），未运行测试。旧候选与报告标记已撤销，不能作为目标实现。真正双向交换尚未改包，需明确是否对调挂点名称/hash并保留各自原父链/绑定姿态，不能再擅自用单向改父级代替交换。

- 2026-11-06 挂点路线还原/单 HD2 骨架生成链已更新至 1.0.11，并同步指定 manager-1.0.7 路径：受管 attachment_swap 强制 false；21 个 Source 非头部挂点用自身锚点重算/烘焙，Lua 1.0.9 读取 Source 挂点，公共策略仍 b23-1.0.8，HD2 原动画通道保持。新增 config/attachment-fix.json，生成前读取可选挂点；换甲扫描实际身体一对多 Unit。用户澄清单原骨架=VPK转一套HD2骨架，复用原 batch processor/patch writer，无 Source 通道/B23/Lua。导入三选项取消/单/双+Lua；重构建保持路线与只读边界。Python121、.NET118通过/1外部ZIP跳过，Lua207595模拟检查通过，两模型两路线各6条只读实生成通过；双各8268检查/原HD2最大误差1.10e-7，单batch字节一致。发布源码/程序集哈希已核对；备份 outputs/manager-route-update-20261106-131852/ 与 -132016/。未全量、未手动GUI、未游戏验收/部署；旧组须重生成整套，不碰冻结基线。详见记忆十九节、docs/attachment-routes-20261106.md 与 outputs/attachment-routes-20261106/delivery-verification.json。


- 2026-11-06 用户 GUI test01 导入并选 O-3 后的 Target body Unit does not belong to this Source rig 已复现/修至生成链 1.0.12：整件换甲 sections 包含原生隐藏辅助 Unit，不能只按非 Helmet 槽位视为 Source 模型。collect_model_units 排除无 Source 签名/来源映射的辅助 Unit，基础 Source/明确来源/部分签名仍拒绝错误；门禁不关闭。test01 1.09/test02 两者实际转换→只读入库→O-3换甲→Lua/各6动画通过，模型6原+10目标、排除6原生辅助与头盔；各8284检查/原HD2最大误差1.10e-7。Python130，.NET29通过/1外部ZIP跳过，Lua207595模拟通过。指定manager目录仅更新6随包文件，DLL未变；备份 outputs/manager-route-update-20261106-144921/，settings/index哈希不变，无游戏部署/活动库修改。关闭报错框后重导入即可；未手动GUI/全量/游戏验收。详见记忆二十节、outputs/attachment-import-fix-20261106/verification.json。

- 2026-11-06 test03 Source root has no blend-mask driver 已复现/修至1.0.13：合法独立Armature无driver但发布父级为native EntityRoot，遮罩按实际父链/hash→Bones channel继承；不删/改/重绑根骨，不借髋骨/任意通道，错误通道/父链/权重仍拒绝。实际80张遮罩原native字节保持/12160新增权重检查通过；test03 1.05→RS89真实同源转换/换甲/只读库/Lua/6动画通过，8290离线检查/HD2最大误差1.10e-7；Python138、Lua207595模拟通过。指定manager-1.0.7更新5随包文件，DLL未变；备份outputs/manager-route-update-20261106-151508/，settings/index不变，无游戏部署/活动库修改。证据 outputs/attachment-root-mask-fix-20261106/verification.json/记忆二十一节；关闭报错框后重导入即可，未全量/手动GUI/游戏验收。

- 2026-11-06 test04–08→RS89批量验证完成，1.0倍率，各32条全ID范围代表性动画，实际同源转换/换甲/只读库/Lua/动画/配套入库首轮全通过，无新错误、未改生产逻辑，manager保持1.0.13。五模型Source骨124/100/127/108/80，test06 Armature父通道规则通过；160抽样动画、400完整遮罩、53120权重与235850独立检查通过，HD2通道最大误差4.80e-7。报告 outputs/test04-08-rs89-20261106/verification.json，记忆二十二节。源码/测试/安装哈希同源，原VPK/只读模型未变，无活动库/设置/游戏部署改动；未全量重烘/手动GUI/游戏视觉验收，抽样不可全量部署。

- 2026-11-06 test04实机故障已定位，源码修正待发布：4次启用Lua的启动均Transfer1.0.9/Adapter1.0.8不匹配；5份转储同一父矩阵65535越界。append_model_source_mounts把原根/自父TransformEntry重写成(1,65535)，实际18 Unit/108条损坏；AQ父列表直接索引与Blender截图吻合，未连接实机Blender验收。已改为保留旧矩阵/父记录原字节，仅新增挂点；Adapter1.0.9门禁保留，新增回归。Python177项(1跳过)/.NET13/真实18Unit隔离重序列化/真实profile组合Lua5.1入口/既有207595模拟通过。指定manager安装目录与活动库/游戏/冻结基线均未改，需同步后正常重导入VPK；不得仅重生成Lua或把旧离线PASS当父记录与启动入口PASS。详见记忆二十三、outputs/test04-live-crash-audit-20261106/排查报告.md。

- 2026-11-06 已完成本轮管理器同步/八模型相关测试：生成链1.0.14同步指定manager-1.0.7（10随包文件），原父记录/矩阵原字节保留、新增坏缓存父记录拒绝门禁、Adapter/Transfer均1.0.9。test01–08各独立库实际GUI同源转换/只读入库/RS89换甲/Lua/32代表性动画/配套入库与同源重导入暂存身份/决策保持通过；test04倍率1.05，其余1.0。128身体Unit/28928旧父记录/256动画/640完整遮罩/86400权重/377360独立核查通过，HD2最大误差4.80e-7；Python179(1跳过)/.NET67/Lua207595模拟通过。备份 outputs/manager-route-update-20261106-171058/，报告 outputs/manager-parent-entry-fix-20261106/同步与测试报告.md。源码/发布/测试/安装hash一致；设置/原资产索引/VPK不变。17:26管理器另行新导入test07→B08引起library.json变动已保留、不回滚。未全量/手动UI/Blender/游戏视觉验收，本轮未游戏部署；旧模型/Lua需正常重导入重建，冻结1.0.8不改。最新边界见记忆二十四。

- 2026-11-06 test07实际零写入已确认是部署覆盖顺序：18:57 Lua1.0.9启动成功，但actors0、actual240/expected245，因动画patch7覆盖Lua245节点专用UNIT/BONES（原patch6）。5个Source节点改名私有参考并新增未动画输出，不能放宽计数。ImportService先Lua后动画导入/自动配置排序缺少配套优先级，前轮离线测试漏了最终胜出者；8模型补覆盖模拟均复现少5节点。检查期间外部改为动画patch6→Lua骨架patch8，19:06新会话已actors1/models6并实际左右手/其他挂点/身体写入；本轮只读、未改包/管理器/部署。自动排序逻辑仍待增量修正，画面未验收；详见记忆二十五及 outputs/test07-live-attachment-audit-20261106/排查报告.md。

- 2026-11-06 单骨架偏大/骨位不符已修至单链1.0.15：真实来源尺寸+一次倍率、shared bind、强制必要骨轴补偿/混配门禁、序列化包围盒修正；Python102/.NET676通过+1跳过，test01/test02各6条含additive及真实只读入库通过。独立修复版 outputs/single-hd2-fix-20261106/manager/，未覆盖旧manager/活动库/游戏，未全量重烘3180/未游戏验收。旧单模型需重导并重生整套；双链仍1.0.14/Lua不改。详见记忆二十八节与输出修复说明。
