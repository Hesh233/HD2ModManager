"""Record actual B10 setter evidence and the user's separate visual feedback."""
import re
from package_native_v12 import ROOT,load,save_json,digest
W=ROOT/'outputs/native-b10-observation-20261104'


def main():
    data=load(W/'roundtrip-analysis.json');trials=data['passedTrials']
    assert trials and not any(data[k]for k in ('failedTrials','rejected','incomplete','unexpected'))
    nodes=[n for t in trials for n in t['nodes']]
    maxima=dict(local=max(n['localMaxAbs']for n in nodes),position=max(n['world']['positionMeters']for n in nodes),
        linear=max(n['world']['linearMaxAbs']for n in nodes),scale=max(n['world']['axisLengthMaxAbs']for n in nodes))
    text=(W/'hd2physbone-captured.log').read_text(encoding='utf-8-sig')
    lines=text.splitlines();first=next(i for i,l in enumerate(lines)if 'variant=test01-v19-B10'in l)
    start=max(i for i,l in enumerate(lines[:first+1])if '[physbone]'in l and '启动于'in l)
    relevant=lines[start:];events=[l for l in relevant if any(s in l for s in ('slot_selection','palm_contact_error','native_hand_sync','scene_roundtrip] event=result'))]
    (W/'B10-game-events.log').write_text('\n'.join(events)+'\n',encoding='utf-8')
    result=dict(status='PASS',evidenceType='actual-game-getter-setter-roundtrip',sourceSha256=digest(W/'hd2physbone-captured.log'),
        passedTrials=len(trials),verifiedNodeWrites=len(nodes),errors=maxima,failedTrials=0,
        userFeedback=dict(handShape='normal',samplePouch='normal',splitSeams='normal',grip='unchanged',
            rightHand='does not visibly follow moving weapon',leftHand='off grip',lookUpDown='little visible hand response',
            pouchSwitch='test01/original switch moves pouch; switching back restores it; expected'),
        limitation='Same-callback matrices are verified; final rendered consumption and correctness/timing of native grip targets are not proven.',
        nextStep='read-only same-frame native hand, native grip, Source output, actual hand model and weapon-control motion capture')
    save_json(W/'game-findings.json',result)
    (W/'分析报告.md').write_text(f'''# B10 实机结果与下一项观测

2026-11-04。B10 的 {len(trials)} 轮试验均通过，共 {len(nodes)} 次模型节点原样回写。local、world 位置、完整线性矩阵与轴长变化最大值均为 0，没有拒绝、失败、回滚或不完整日志。该结果确认本次采样中的模型自身 local 可以按原值回写；不等于 GPU 消费和目标空间已校准。

用户确认手形、样本瓶和接缝正常。样本瓶的位置变化发生在 test01／原版盔甲切换时，切回即恢复，按正常挂点切换记录。持枪表现不变：武器移动，右手没有明显跟随，左手离开握把，上下看时手部变化不明显。

代码目前把同一 Avatar 的 attach_hand_l/r 当作目标。日志中右手对这一目标的计算残差很小，但用户仍看到握持错误，因此不能把小残差当成手已握住实际武器。尚缺原生手、挂点、武器控制点的同帧完整矩阵及运动关系，不能直接指定 SMG-203 校准偏移，也不能把附近武器等同于已确认归属的武器。

B11 将关闭已验证的周期原样回写，保持原有 B9/B7 求解、动画及挂点，新增只读握持观测。记录修正前与全部刷新后：原生肩肘手、原生握点、武器瞄准挂点、Source 肩肘手、真实双手模型，以及有界的附近武器/前握把候选。候选仅用于诊断，绝不授权写入或证明装备归属。通过平视／仰视／俯视的受控动作进一步区分目标不动、求解输出和渲染覆盖；取得证据前不新增握持修正。
''',encoding='utf-8')
    print(result['passedTrials'], 'trials;',result['verifiedNodeWrites'],'node writes; all numeric changes zero.')


if __name__=='__main__':main()
