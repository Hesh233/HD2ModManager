"""Write the verified native-session report and scoped matrix reference file."""
import argparse
import json
from pathlib import Path
import shutil

from package_native_v12 import ROOT, load, save_json, digest
from analyze_native_b21_capture import affine_relative, compose

IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def interval(stats, scale=1, decimals=3):
    return f"{stats['minimum']*scale:.{decimals}f}–{stats['maximum']*scale:.{decimals}f}"


def link(path, title):
    return f'[{title}](<{Path(path).resolve().as_posix()}>)'


def matrix_block(m):
    rows = [[m[r+c*3] for c in range(3)] + [m[9+r]] for r in range(3)]
    rows.append([0, 0, 0, 1])
    return '\n'.join('  '.join(f'{v: .9f}' for v in row) for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observation', type=Path)
    args = parser.parse_args()
    output = args.observation.resolve()
    report = load(output / 'observed-native-grips.json')
    verified = load(output / 'analysis-verification.json')
    manifest = load(output / 'snapshot-manifest.json')
    audit = load(output / 'deployment-audit.json')
    assert verified['status'] == 'PASSED'
    assert verified['checkedReportSha256'] == digest(output / 'observed-native-grips.json')
    assert verified['checkedRelativePoseSha256'] == digest(output / 'relative-poses.jsonl')
    mounted = [g for g in report['groups'] if g['group'] in report['conclusions']['verifiedMountedGroups']]
    assert len(mounted) == 1
    g = mounted[0]
    n = g['completedPairs']
    render = g['phases']['render']
    update = g['phases']['update']
    contact = g['leftContactRender']
    rel = render['relations']
    asset = report['nativeAssetLocalMatrices']
    k = asset['right_ik']['localAffine']
    u = asset['underbarrel']['localAffine']
    f = asset['foregrip_ik']['localAffine']
    constants = dict(status='OBSERVATIONAL_REFERENCE', revision='B21-native-094642',
        sessionStart=report['sessionStart'], sessionEnd=report['sessionEnd'], group=g['group'],
        equipment={role: unit['resource'] for role, unit in g['units'].items()}, owner='unverified',
        scope='Native 107-node Avatar with SMG-203 and the observed vertical foregrip; mounted group only',
        convention='T_A_B = inverse(world_A) * world_B; column bases then translation; metres; runtime indices are one-based',
        right=dict(wrist=dict(role='avatar', name='r_hand', index=72),
                   mount=dict(role='avatar', name='attach_hand_r', index=85),
                   weaponRoot=dict(role='weapon', name='boss', index=11),
                   marker=dict(role='weapon', name='IK_right', index=13),
                   weaponBossToIKRight=k, ikRightToWeaponBoss=affine_relative(k, IDENTITY),
                   handToMount='L_R(t): runtime native local pose, varies by sample',
                   handToMarker='C_R(t) = L_R(t) * K_R',
                   worldWeapon='G(t) = H_R(t) * L_R(t)',
                   fixedWristToMarkerCalibrationAvailable=False,
                   allRenderMeasurement=rel['r_wrist_ik'],
                   leftContactSubsetMeasurement=contact['relations']['r_wrist_ik']),
        left=dict(wrist=dict(role='avatar', name='l_hand', index=48),
                  marker=dict(role='foregrip', name='IK_left', index=9),
                  weaponBossToUnderbarrel=u, foregripRootToIKLeft=f,
                  weaponBossToForegripIKLeft=compose(u, f),
                  worldMarker='P_L(t) = G(t) * U * F',
                  wristCoincidenceCondition='Measured contact intervals only; not all actions',
                  coincidentRenderSamples=contact['samples'], renderSamples=n),
        sourceReportSha256=digest(output / 'observed-native-grips.json'),
        perSampleMatrices=str(output / 'relative-poses.jsonl'),
        test01HandFrameMappingAvailable=False, palmSurfaceCalibrationAvailable=False,
        runtimeCorrectionImplemented=False,
        limits=['These constants describe native weapon coordinates; they are not a test01 grip correction profile.',
                'IK_right is a marker from the weapon asset, not an observed equality constraint on r_hand.',
                'Source/test01 hand-frame registration must be established separately; old L4D2 weapon bones are not calibrated references.'])
    save_json(output / 'native-grip-reference-matrices.json', constants)
    groups = report['groups']
    r_right = rel['r_wrist_ik']
    r_left = rel['l_wrist_foregrip']
    right_contact = contact['relations']['r_wrist_ik']
    left_contact = contact['relations']['l_wrist_foregrip']
    lr = render['nativeLocalPoses']['r_mount']
    max_right_error = max(g['phases'][p]['chainResiduals']['wrist_local_to_right_ik']['metres']['maximum'] for p in ('update', 'render'))
    max_left_error = max(g['phases'][p]['chainResiduals']['mount_to_foregrip_ik']['metres']['maximum'] for p in ('update', 'render'))
    lines = [
        '# B21 原生握持实测：左右手与握把的准确坐标关系', '',
        f"本次会话：**{report['sessionStart']}–{report['sessionEnd'][11:]}，Asia/Shanghai**。这是追加日志中的第 {report['latestSessionOrdinal']} 次会话；上一次 09:23:43 的 v15 混合基线没有计入本报告。", '',
        f"**结论：已确认骨骼与挂点层面的原生对应关系。右侧枪体与 `attach_hand_r` 重合，右手腕和武器 `IK_right` 存在随姿态变化的原生偏移；左侧接触时对应独立前握把的 `IK_left`。**", '',
        '## 1. 基线与样本范围', '',
        f"采集共有 {report['rawCompletePairs']} 组完整 update/render 回调。两代 Avatar 都是 107 节点。当前 9 个补丁的数量与 Chef 启动日志一致；B21 在 `.patch_8`，其整包 SHA-256 与交付包一致。", '',
        '部署表中没有 Avatar、左右原生手部、此武器和此前握把的 Unit/Bones/state-machine 覆盖，也没有任何松散动画覆盖。由此确认此次分析所需的原生骨架与相关资源基线；Chef、QuickDebrief 等其他 Mod 仍存在。部署检查读取的是采集结束后的现存文件，启动日志没有保存所有补丁当时的字节。', '',
        '| 实例组 | 时间 | Avatar / 左手模型 / 右手模型 / 枪 / 前握把 | 完整回调对 | 渲染时右挂点与枪体重合 |',
        '| --- | --- | --- | ---: | ---: |',
    ]
    for group in groups:
        t = group['phases']['render']
        ids = ' / '.join(str(group['units'][r]['id']) for r in ('avatar', 'left_model', 'right_model', 'weapon', 'foregrip'))
        lines.append(f"| {group['group']} | {t['firstLogTime'][11:]}–{t['lastLogTime'][11:]} | {ids} | {group['completedPairs']} | {t['relations']['r_mount_gun']['coincidentSamples']} |")
    lines += [
        '', '主结论采用 group_2。它从任务加载阶段开始；Chef 在 09:47:48 才记录 mission 检测。group_1 的枪体未与右手挂点重合，因此保留为独立观察，不用于握持标定。两个实例组之间另有 39 组回调缺少完整的手/枪/前握把组合。', '',
        '同一回调内只配对同一世界编号的数据；所有跨 Unit 的 `owner` 仍标为 `unverified`。前半段出现多件前握把时，用枪的 `attach_underbarrel` 与前握把 `skeleton` 的几何关系消除歧义，未用左手是否重合来选择前握把。group_2 每次只有一件该资源前握把。', '',
        '重合判据统一为原点距离 < 1 mm 且朝向差 < 0.1°。以下位置均为骨骼/标记原点，旋转为完整三维相对旋转角，不能当作某个单独轴的校正角。', '',
        '## 2. 右手：枪体挂点与握把标记是两个坐标系', '',
        '| 比较关系（运行时索引从 1 开始） | render 重合数 | 距离范围 / 中位数 (mm) | 朝向差范围 (°) |',
        '| --- | ---: | --- | --- |',
    ]
    for key, name in (
        ('r_mount_gun', 'Avatar `attach_hand_r[85]` → 枪 `boss[11]`'),
        ('r_wrist_mount', 'Avatar `r_hand[72]` → `attach_hand_r[85]`'),
        ('r_wrist_ik', 'Avatar `r_hand[72]` → 枪 `IK_right[13]`'),
        ('r_twist_ik', 'Avatar `r_hand_twist[71]` → 枪 `IK_right[13]`'),
        ('gun_right_ik', '枪 `boss[11]` → `IK_right[13]`'),
    ):
        m = rel[key]
        lines.append(f"| {name} | {m['coincidentSamples']}/{n} | {interval(m['worldDistanceMetres'],1000)} / {m['worldDistanceMetres']['median']*1000:.3f} | {interval(m['worldRotationDegrees'],decimals=6)} |")
    lines += [
        '', f"右挂点与枪体在 update、render 各 {n} 次读取中，12 个矩阵元素都完全相同。原生右手模型 `r_hand[16]` 与 Avatar `r_hand[72]` 在两类回调的 {n*2} 次读取中也完全相同。这个右手模型确实引用 `r_hand` 和 `r_hand_twist` 作为蒙皮输入；本次未解码非零顶点权重。", '',
        f"右手腕与 `IK_right` 的距离在全部 {n} 组中为 **{interval(r_right['worldDistanceMetres'],1000)} mm**。即使只取左手已与前握把重合的 {contact['samples']} 组，右手仍相差 **{interval(right_contact['worldDistanceMetres'],1000)} mm、{interval(right_contact['worldRotationDegrees'])}°**，没有一组双条件重合。右手 twist 骨同样不匹配该标记。", '',
        '因此，本装备配置下不能把 `IK_right.world == r_hand.world` 当作原生握持应满足的条件。数据支持的链路是右手腕携带原生局部挂点姿态，枪体使用该挂点坐标；`IK_right` 是枪体内固定的右侧握持参考标记，其名字本身不能证明引擎当前把右手腕约束到它。', '',
        '定义 `H_R(t)` 为右手腕世界矩阵，`L_R(t)` 为原生 `attach_hand_r` 的局部矩阵，`G(t)` 为枪 `boss` 世界矩阵，`K_R` 为枪 `boss → IK_right` 的固定矩阵：', '',
        '```text',
        'G(t)    = H_R(t) × L_R(t)',
        'P_R(t)  = G(t) × K_R',
        'C_R(t)  = inverse(H_R(t)) × P_R(t) = L_R(t) × K_R',
        '```', '',
        f"将日志中的 `H_R(t)`、`L_R(t)` 和 `K_R` 连乘，可在全部 {n*2} 次读取中复原右侧握持标记，最大位置残差 **{max_right_error*1000:.6f} mm**。这是该公式在本次原生姿态中的数值验证。", '',
        f"`L_R(t)` 实测有 {lr['recordedExactUniqueCount']} 个不同的局部矩阵；相对本组首帧，局部平移最大变化 **{lr['translationChangeFromFirstMetres']['maximum']*1000:.3f} mm**，朝向最大变化 **{lr['rotationChangeFromFirstDegrees']['maximum']:.6f}°**。所以不能用首帧、平均偏移或一个固定 ±90° 来替代这段原生关系。", '',
        '右侧固定矩阵 `K_R`（下列按通常 4×4 行格式显示；平移单位 m）：', '',
        '```text', matrix_block(k), '```', '',
        f"其局部平移为 ({k[9]*1000:.6f}, {k[10]*1000:.6f}, {k[11]*1000:.6f}) mm，在全部读取中保持不变。它相对枪体的完整旋转约 112.555963°，该数值不是 test01 需要施加的旋转修正。", '',
        '## 3. 左手：实际匹配的是独立前握把 IK_left', '',
        f"在未按左手结果筛选的 group_2 全部 {n} 组中：", '',
        '| 候选 | update 重合数 | render 重合数 |',
        '| --- | ---: | ---: |',
    ]
    for key, label in (
        ('l_wrist_foregrip', '`l_hand[48]` → 前握把 `IK_left[9]`'),
        ('l_wrist_gun_ik', '`l_hand[48]` → 枪体 `IK_left[17]`'),
        ('l_twist_foregrip', '`l_hand_twist[65]` → 前握把 `IK_left[9]`'),
        ('l_mount_foregrip', '`attach_hand_l[49]` → 前握把 `IK_left[9]`'),
    ):
        lines.append(f"| {label} | {update['relations'][key]['coincidentSamples']}/{n} | {rel[key]['coincidentSamples']}/{n} |")
    lines += [
        '', f"render 的匹配率为 {contact['samples']/n*100:.2f}%。在这 {contact['samples']} 组明确筛选为左手接触的子集中，位置差最大 **{left_contact['worldDistanceMetres']['maximum']*1000:.6f} mm**、朝向差最大 **{left_contact['worldRotationDegrees']['maximum']:.8f}°**。这组子集用来描述接触精度，不用作独立命中率验证。", '',
        f"枪体自己的 `IK_left` 与前握把 `IK_left` 恒定相隔约 **{rel['gun_left_ik_foregrip']['worldDistanceMetres']['median']*1000:.3f} mm、{rel['gun_left_ik_foregrip']['worldRotationDegrees']['median']:.6f}°**。两者不可以互换。左 twist 骨原点接近手腕，但朝向不同，也不可以替代 `l_hand`。", '',
        f"枪 `attach_underbarrel[24]` 与前握把 `skeleton[8]` 在 {n}/{n} 组 render 中满足重合判据，最大距离 {rel['underbarrel_foregrip_root']['worldDistanceMetres']['maximum']*1000:.6f} mm。令 `U` 为枪 boss 到下挂点的固定矩阵，`F` 为前握把 skeleton 到其 IK_left 的固定矩阵：", '',
        '```text', 'P_L(t) = G(t) × U × F', '左手处于本次观测到的接触阶段时：H_L(t) ≈ P_L(t)', '```', '',
        f"该武器侧链路在全部 {n*2} 次读取中的最大位置复原误差为 **{max_left_error*1000:.6f} mm**。原生左手模型 `l_hand[16]` 与 Avatar `l_hand[48]` 的 {n*2} 次世界矩阵读取也完全一致。", '',
        '34 组 render 没有左手接触。前 14 组分布在 09:47:45–09:47:48，其余为场景内较短间隔；完整区间已写入 JSON。采集没有动作名称，不将这些间隔自动归类为换弹、收枪或错误。', '',
        '## 4. 对应关系图', '',
        '图中箭头表示坐标变换关系，不代表已确认的引擎 IK 执行顺序。', '',
        '```mermaid', 'flowchart LR',
        '  RH["Avatar r_hand 72"] -->|"动态 L_R(t)"| A["attach_hand_r 85"]',
        '  A -->|"本组世界矩阵相同"| G["枪 boss 11"]',
        '  G -->|"固定 K_R"| RI["枪 IK_right 13"]',
        '  G -->|"固定 U"| UB["attach_underbarrel 24"]',
        '  UB -->|"本组重合"| FR["前握把 skeleton 8"]',
        '  FR -->|"固定 F"| LI["前握把 IK_left 9"]',
        '  LH["Avatar l_hand 48"] -. "469/503 个 render 接触采样" .-> LI',
        '```', '',
        '## 5. 对之前视觉平移和扭转问题的约束', '',
        f"同一编号的 update/render 之间，右手腕世界位移中位数为 {g['callbackDifferences']['avatar:r_hand_metres']['median']*1000:.3f} mm，最大 {g['callbackDifferences']['avatar:r_hand_metres']['maximum']*1000:.3f} mm；右挂点与枪体同步变化，且各自回调内仍严格重合。因此复核挂点时需要使用同一回调阶段的成组姿态。两回调记录的引擎时间相同，不能据此认为其姿态读取没有时间差，也不能将回调直接命名为 IK 前/后。", '',
        '本次排除了上轮 v15 骨架/动画覆盖这一基线问题，建立了原生参考关系；它没有直接复现 B19/B20 的姿态写入，不能单独证明某个旧脚本的执行冲突。右手腕到 IK_right 的上述偏移在原生条件下已经存在，不能把它全部算作 Mod 错位。', '',
        '后续迁移到重新生成的 test01 骨架时，需要先确认 test01 手腕坐标系与原生手腕坐标系的转换，再使用完整相对矩阵。不能把旧 L4D2 `weapon_bone` / `L_weapon_bone` 自动当作准确握点，也不能从本次原生日志直接算出 test01 专用修正。此处只交付原生参考数据，未填写修正 Lua。', '',
        '**确认范围是骨骼和挂点坐标。B21 没有记录完整手指姿态或蒙皮后的顶点，尚不能将上述标记坐标解释成掌心表面或握把表面的准确接触点。**', '',
        '## 6. 数据与验证', '',
        f"独立验证使用 NumPy 4×4 求逆/连乘和 SVD 旋转分解，从原始日志逐条核对了 {verified['verifiedSnapshots']} 份成组快照、{verified['verifiedRelations']:,} 个相对关系及 {verified['verifiedWorldPoseCopies']:,} 个世界矩阵拷贝。相对矩阵计算最大元素差 {verified['numericalMaximumDifferences']['affineMaximumElementDifference']:.3g}，角度算法最大差 {verified['numericalMaximumDifferences']['rotationMaximumDifferenceDegrees']:.9f}°。", '',
        '原始追加日志与当前补丁的 SHA-256 在分析结束时再次核对，均未改变。日志无解析、回调、扫描或回调配对错误；432 条 unavailable 集中于 09:47:31 的旧实例销毁，不计作姿态样本。', '',
    ]
    for file, label in (
        ('snapshot-manifest.json', '会话边界、原始日志哈希与实例清单'),
        ('deployment-audit.json', '原生基线与当前部署审计'),
        ('observed-native-grips.json', '完整左右手统计及区间'),
        ('native-grip-reference-matrices.json', '固定武器矩阵与动态关系定义'),
        ('relative-poses.jsonl', '每次采样的完整相对矩阵、局部矩阵、原始证据行号'),
        ('right-pose-examples.json', '右手距离/朝向极值对应的真实采样'),
        ('pose-timeseries.csv', '逐采样位置、朝向与重合标志'),
        ('callback-timeseries.csv', '成对回调差异'),
        ('analysis-verification.json', '独立验证结果'),
        ('native-grip-latest.log', '本次会话原始日志副本'),
    ):
        lines.append('- ' + link(output / file, label))
    lines += ['', '原始矩阵数组按三列基向量、平移向量的顺序存储；报告中的 4×4 代码块按行显示。静态资源索引从 0 开始，运行时索引从 1 开始。', '']
    text = '\n'.join(lines)
    report_path = output / 'B21-原生左右手握持关系.md'
    report_path.write_text(text, encoding='utf-8')
    published = ROOT / 'docs/native-v29-B21-native-grips-20261105.md'
    published.write_text(text, encoding='utf-8')
    archive = output / 'analysis-tools'
    archive.mkdir(exist_ok=True)
    for name in ('capture_native_b21_latest.py', 'audit_native_b21_baseline.py',
                 'analyze_native_b21_capture.py', 'analyze_native_b21_native_grips.py',
                 'verify_native_b21_native_grips.py', 'report_native_b21_native_grips.py'):
        shutil.copy2(ROOT / 'tools' / name, archive / name)
    save_json(output / 'report-artifacts.json', dict(status='COMPLETE', report=str(report_path), published=str(published),
        files={p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in output.iterdir() if p.is_file() and p.name != 'report-artifacts.json'},
        runtimeFilesChanged=False, test01BonesChanged=False))
    print(json.dumps(dict(report=str(report_path), published=str(published),
                         rightChainMaximumResidualMm=max_right_error*1000,
                         leftChainMaximumResidualMm=max_left_error*1000,
                         nativeReference=str(output / 'native-grip-reference-matrices.json')), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
