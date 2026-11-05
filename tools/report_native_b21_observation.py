"""Write the measured B21 result and a reproducible evidence verification."""
from pathlib import Path
import shutil
from package_native_v12 import ROOT, load, save_json, digest

W = ROOT / 'outputs/native-b21-observation-20261105/20261105-092343'
SOURCE_LEFT = 'hd2n_4e4fb4fa303d_anim_008_l_hand'


def link(label, name):
    return '[' + label + '](' + (W / name).as_posix() + ')'


def main():
    d = load(W / 'observed-correspondence.json')
    source = load(W / 'snapshot-manifest.json')
    generic = load(W / 'capture-analysis.json')
    deploy = load(W / 'deployment-audit.json')
    total = d['allRender']
    selected = d['rightAttachmentCoincidentRender']
    contact = d['bothHandsCoincidentRender']
    assert d['sourceSha256'] == source['snapshotSha256'] == generic['inputSha256'] == digest(W / 'native-grip-latest.log')
    assert d['latestSessionOrdinal'] == source['totalSessions'] == 2
    assert d['rawCompletePairs'] == generic['completedSamplePairs'] == 1455
    assert not generic['parseErrors']
    assert generic['sessions'][0]['issues'] == {'unavailable': 848}
    assert d['exactNativeModelWorldMatrixMatches'] == dict(left=2460, right=2460)
    assert not any(d['modelNonIdentityLocalPoseCounts'].values())
    assert total['samples'] == 1230 and selected['samples'] == 1049
    assert selected['leftForegripCoincident'] == contact['samples'] == 990 and total['leftGunIKCoincident'] == 0
    assert deploy['effectiveAvatar']['entirePatchMatchesV15'] and not deploy['effectiveAvatar']['entirePatchMatchesV30']
    assert deploy['captureAddonMatchesDelivered']
    assert all(not rows for rows in deploy['observedNativeUnitOverrides'].values())
    assert not source['chefWarnings']
    assert set(r['event']['id'] for r in source['diagnostics']) == set(range(1,9))
    assert all(r['event']['phase'] == 'update' for r in source['diagnostics'])
    old_time_end = max(r['timestamp'] for r in source['diagnostics'])
    assert old_time_end < d['unitSelection']['left_model']['firstLogTime']
    assert all(v['maximum'] == 0 for k,v in d['callbackChanges'].items() if k == 'callbackGapSeconds')
    m = selected['metrics']
    report = f"""# B21 最新实机数据分析

本报告只分析 **{d['sessionStart']} 至 {d['sessionEnd']}**（本机时间，Asia/Shanghai）的最后一轮。前一轮 09:16:25 的姿态数据没有混入本报告。

**左手对应已经收窄到：垂直前握把 IK_left ⇄ Avatar l_hand ⇄ 原生左手模型 l_hand。** 在枪身与右挂点对齐的 1049 个样本中，有 990 个（{990/1049:.1%}）同时与前握把 IK_left 对齐；枪身自带 IK_left 的同时对齐次数为 0。

这轮穿戴的手部模型是原生资源，但 **Avatar 和动画仍由 v15 扩展包覆盖**，所以它是“原生手模＋扩展 Avatar/动画”的观测，不能作为未经修改的原版校准数据。

## 数据质量和残留来源

- 1455 组完整 update/render 回调；其中后半段有 1230 组同时包含 Avatar、左右原生手模、SMG-203 和垂直前握把，覆盖样本 226–1455。
- JSON 解析错误、callback_error、不完整回调对均为 0。848 条 unavailable 全部发生在 09:24:31–09:24:32，来自旧实例 1–8 的销毁/重建；本报告对象组 9–13 的完整采样从 09:24:46 开始。
- 矩阵日志输出 9 位有效数字；“逐项相同”指记录精度内相同，不能排除更小差异。
- Chef 正常退出，没有本轮采集器超时、沙箱拒绝或超预算警告。Chef 本轮列出的 addon 是 B21；另有 QuickDebrief 启动脚本，未宣称所有其他模组都已停用。
- 游戏目录中的 **9ba626afa44a3aa3.patch_9** 包含 1 个 Avatar Unit、1 个 Bones、1 个状态机和 3180 条动画。其整个文件 SHA-256 与旧 v15 配套动画 patch 完全一致；与新 v30/B22 动画包不一致。
- 该 Avatar 是 **255 节点**，而提取的原生 Avatar 为 **107 节点**。当前 Lua 采集包与交付 B21 完全一致；本轮左右原生手模、SMG 和前握把的 Unit 资源没有被当前松散 patch 覆盖。

## 实测对应关系

以下索引均是 **Lua 运行时从 1 开始的索引**。旧静态表从 0 开始，不可直接混用。

| A | B | 最新后半段数据 |
| --- | --- | --- |
| Avatar attach_hand_r（85） | SMG boss（11） | 1049/1230 个 render 样本位置相同，旋转差最大约 0.000002° |
| SMG attach_underbarrel（24） | 前握把 skeleton（8） | 1230 个 render 样本全部近似重合，位置差最大 0.0019 mm |
| 前握把 IK_left（9） | Avatar l_hand（48） | 990/1230 个 render 样本满足位置差 <1 mm、角差 <0.1°；这 990 个全部属于上述右挂点对齐组 |
| Avatar l_hand（48） | 原生左手模型 l_hand（16） | 1230 个 update＋1230 个 render，12 个世界矩阵数值全部逐项相同 |
| Avatar r_hand（72） | 原生右手模型 r_hand（16） | 1230 个 update＋1230 个 render，12 个世界矩阵数值全部逐项相同 |

这些是观察到的世界姿态对应关系，双向符号不表示引擎的因果方向或调用先后。

原生手部模型在这 2460 次观察中的本地姿态都是单位矩阵，父接口返回外部/根，而世界姿态精确跟随 Avatar 的同名手骨。这支持运行时跨 Unit 驱动的存在；仅凭 scene_graph_parent 返回值尚不能确定其具体父 Unit 或内部实现。

## 左手应比较哪个 IK

下面的分组**只使用右挂点与枪身是否重合**来选择 1049 个样本，没有预先按左手匹配情况挑选。

| 左手比较目标 | 原点距离中位数 | 朝向差中位数 | 满足 1 mm / 0.1° 的样本 |
| --- | ---: | ---: | ---: |
| 前握把 IK_left | {m['left_foregrip_m']['median']*1000:.4f} mm | {m['left_foregrip_deg']['median']:.6f}° | 990/1049 |
| 枪身 IK_left | {m['left_gun_ik_m']['median']*1000:.3f} mm | {m['left_gun_ik_deg']['median']:.5f}° | 0/1049 |

两个 IK 标记之间的关系也稳定：全部 1230 个 render 样本的距离为 **129.608–129.638 mm**，朝向差约 **76.37178°**。它们是不同握持参考，不能按同名互换。

这为“本次 SMG-203＋垂直前握把的左手跟随前握把 IK_left”提供强证据。它不证明所有武器/配件都使用相同优先级。其余未重合区间没有动作标签，不能全部当作握持失败或全部解释为换弹。

最长连续左手重合区间是 **09:25:21–09:26:08**，共 232 个样本。990 个左右同时重合样本中的左腕/前握把误差中位数为 {contact['metrics']['left_foregrip_m']['median']*1000:.4f} mm，95 分位为 {contact['metrics']['left_foregrip_m']['p95']*1000:.4f} mm。这个子集按左手重合选择，仅描述该段误差，不作为独立验证。

## 与 test01 失败现象的关系

扩展 Avatar 中的 Source 左手 **{SOURCE_LEFT}**（116）没有取得相同世界姿态。在上述仅按右挂点选择的 1049 个样本中，它到前握把 IK_left 的距离中位数为 **{m['source_left_foregrip_m']['median']*100:.2f} cm**，范围为 {m['source_left_foregrip_m']['minimum']*100:.2f}–{m['source_left_foregrip_m']['maximum']*100:.2f} cm。

结合 B21 已验证的静态蒙皮引用：原生手模使用原生 l_hand；test01 手模使用 Source 手骨。当前结果与“修改原生手腕并未把握持结果传到 Source 手部”一致，比继续移动原生 attach_hand_l 更能缩小排查范围。

本轮没有捕获 test01 的 Source 手部模型 Unit，所以上述 Source 距离是扩展 Avatar 内的骨骼读数，不能直接称作 test01 可见手掌的偏移，也不能据此直接写入修正参数。

右侧实测重合关系是 **attach_hand_r ↔ 枪身 boss**；原生 r_hand 与枪身 IK_right 并不重合。在左右同时重合的 990 个样本中，后者距离中位数约 32.27 mm。当前混合动画环境下，不应直接把这个值或此前的目测 90° 当作纯原版校准量。

## 回调与视觉平移

两个回调之间世界姿态确实有变化：后半段左手位移中位数 {d['callbackChanges']['avatar_left_world_delta_m']['median']*1000:.2f} mm、右手 {d['callbackChanges']['avatar_right_world_delta_m']['median']*1000:.2f} mm。原生模型和 Avatar 的对应骨在两种回调中都保持逐项一致，因此在这些观察时点，没有发现原生 Avatar → 原生手模这条路径额外不同步。

这不能排除旧 B19/B20 写入或 test01 Source 手模的时序问题。游戏 Application.time_since_launch 在每一组 update/render 返回相同值，即使矩阵发生变化；不能用日志里的 0 秒差推断回调没有时间间隔，更不能据此命名“IK 前／IK 后”。

## 下一次原版对照

继续使用同一个 B21 采集包。先在管理器停用残留的 **v15/test01 配套动画**并重新部署，确认全局 Avatar 覆盖已撤下，再完全重启游戏。当前的 .patch_9 是定位证据；重新部署后编号可能改变，不宜把编号当作固定模组身份。

用相同 B-01、SMG-203、垂直前握把再做一次原生对照。验收条件是新日志出现 **native_107**，同时仍能读取原生手模和武器/前握把。之后才将已收窄的握持关系用于 v30/B22 重新生成骨架的映射，当前没有填充挂点修正 Lua 或改动模型/动画。

## 证据文件

- {link('最新会话来源与索引', 'snapshot-manifest.json')}
- {link('实测对应关系与分组统计', 'observed-correspondence.json')}
- {link('全部回调和关系统计', 'capture-analysis.json')}
- {link('逐样本姿态比较 CSV', 'pose-timeseries.csv')}
- {link('部署补丁与原始包比较', 'deployment-audit.json')}
- {link('本轮 Chef 日志', 'chef-latest.log')}

本报告处理真实游戏采集；上一轮交付包中的 fixture 日志没有参与统计。原始日志和游戏目录均未写入。
"""
    # Keep report generation data-only; do not alter historical packages or the
    # parallel v30/attachment-fix implementation.
    (W / 'B21-最新实机分析.md').write_text(report, encoding='utf-8')
    doc = ROOT / 'docs/native-v29-B21-observed-20261105.md'
    doc.write_text(report, encoding='utf-8')
    source_dir = W / 'analysis-tools'
    source_dir.mkdir(exist_ok=True)
    for name in ('capture_native_b21_latest.py','audit_native_b21_deployment.py','analyze_native_b21_observation.py',
                 'report_native_b21_observation.py','analyze_native_b21_capture.py'):
        shutil.copy2(ROOT / 'tools' / name, source_dir / name)
    checked = ('snapshot-manifest.json','native-grip-latest.log','chef-latest.log','deployment-audit.json',
               'capture-analysis.json','observed-correspondence.json','pose-timeseries.csv',
               'callback-timeseries.csv','B21-最新实机分析.md')
    unchanged = digest(Path(source['source'])) == source['sourceSha256']
    assert unchanged, 'The game log changed after the selected latest-session snapshot'
    save_json(W / 'analysis-verification.json', dict(status='PASS',
        sessionStart=d['sessionStart'], sessionEnd=d['sessionEnd'], latestSessionOnly=True,
        sourceLogUnchanged=unchanged,
        completePairs=1455, completeConsumerPairs=1230,
        exactMatrixComparisons=dict(left=2460,right=2460), genuineGameCapture=True,
        nativeBaselineValid=False, reason='Deployed v15 Avatar plus 3180 animation overrides; observed layout test01_255.',
        B21RuntimeMatchesDelivery=deploy['captureAddonMatchesDelivered'],
        inputAndOutputSha256={name:digest(W/name) for name in checked},
        toolSha256={p.name:digest(p) for p in source_dir.glob('*.py')},
        gameFilesWritten=False, runtimeOrModelEdits=False))
    print('PASS: latest real session analyzed; left foregrip relationship measured; residual v15 Avatar identified; report saved.')


if __name__ == '__main__':
    main()
