"""Summarize immutable B9 real-game captures separately from synthetic tests."""
import json
from collections import defaultdict
from package_native_v12 import ROOT,load,save_json,digest
W=ROOT/'outputs/native-b9-observation-20261104'


def main():
    observations=load(W/'analysis/observations.json');summary=load(W/'analysis/summary.json')
    assert summary['status']=='OBSERVED' and summary['unavailableRecords']==summary['malformedLines']==0
    assert not summary['incompletePhasesOrModels']
    latest=max(r['session']for r in observations);rows=[r for r in observations if r['session']==latest]
    sessions=0;raw=[];identity=[1,0,0,0,1,0,0,0,1,0,0,0];latest_nodes=[]
    for line_no,line in enumerate((W/'hd2physbone-captured.log').read_text(encoding='utf-8-sig').splitlines(),1):
        if '[scene_probe] ' not in line:continue
        e=json.loads(line.split('[scene_probe] ',1)[1])
        if e.get('event')=='phase_begin'and e['sample']==1 and e['phase']=='pre_apply':sessions+=1
        if sessions!=latest:continue
        raw.append(line)
        if e.get('event')=='node':
            assert e['model']['localMatrix']==identity and e['model']['localScale']==[1,1,1]
            assert e['model']['runtimeParent']=='nil'
            latest_nodes.append(dict(e,line=line_no,wallTime=line.split()[0]))
    groups=defaultdict(list)
    for r in rows:groups[(r['avatar'],r['phase'])].append(r)
    details=[]
    for (avatar,phase),values in sorted(groups.items()):
        details.append(dict(avatar=avatar,phase=phase,records=len(values),samples=len({r['sample']for r in values}),
            maxParentVsAvatarPosition=max(r['parentVsAvatarSame']['positionMeters']for r in values),
            maxParentVsAvatarLinear=max(r['parentVsAvatarSame']['linearMaxAbs']for r in values),
            maxWorldVsAvatarPosition=max(r['worldVsAvatarSame']['positionMeters']for r in values),
            maxWorldVsAvatarLinear=max(r['worldVsAvatarSame']['linearMaxAbs']for r in values)))
    for r in rows:
        assert r['parentVsAvatarSame']['positionMeters']==r['parentVsAvatarSame']['linearMaxAbs']==0
        assert r['worldVsAvatarSame']['positionMeters']==r['worldVsAvatarSame']['linearMaxAbs']==0
        if 'sameFrameLocalChange'in r:
            assert all(r['sameFrameLocalChange'][k]==0 for k in ('positionMeters','linearMaxAbs','axisLengthMaxAbs'))
    result=dict(status='PASS',evidenceType='actual-game-log',sourceSha256=digest(W/'hd2physbone-captured.log'),
        latestSession=latest,latestNodePairs=len(rows)//2,samples=len({r['sample']for r in rows}),
        timeRange=[latest_nodes[0]['wallTime'],latest_nodes[-1]['wallTime']],models=sorted({r['resource']for r in rows}),
        allObservedRuntimeParentsNil=True,allObservedModelLocalsIdentity=True,allObservedLocalScalesUnity=True,
        effectiveParentMatchesAvatarSameBoneExactly=True,modelWorldMatchesAvatarSameBoneExactly=True,
        modelLocalUnchangedAcrossB7Apply=True,details=details,
        userVisualFeedback=dict(handShape='normal',samplePouch='normal',splitSeams='normal',
            actionsReported=['aim','stand','holster','run'],actionDurationsSecondsApprox=10,actionTimesNotLabeled=True),
        nextStep='same-model local roundtrip with same-frame validation and rollback',
        limitations=['Only sampled eight nodes on the observed models; not all game Units.',
            'No exact per-action timestamps in telemetry.','GPU skinning consumption not measured.','No model setter roundtrip tested yet.'])
    save_json(W/'game-findings.json',result)
    save_json(W/'latest-game-nodes.json',latest_nodes)
    (W/'latest-B9-scene.log').write_text('\n'.join(raw)+'\n',encoding='utf-8')
    text=f'''# B9 实机观测结果（2026-11-04）

最新一轮采样时间 {result['timeRange'][0]}—{result['timeRange'][1]}，{result['samples']} 组采样，{result['latestNodePairs']} 对同帧节点记录，覆盖 8 个实际模型。两轮合计 4864 对；报告结论使用最新一轮。未发现缺失接口、无效矩阵或不完整采样。

每个模型被测八个手臂／腕辅助节点均返回运行时 parent=nil；local 完整矩阵为恒等矩阵，local scale=(1,1,1)。World × inverse(Local) 与同帧 Avatar 同名骨骼世界矩阵逐元素相同，而不是与序列化父骨相同。这将此前的外部逐骨挂接推断提升为针对这些采样节点的实机空间对应证据；没有查询到引擎底层 link 的目标对象句柄。

B7 修正前和全部刷新后，模型的可读世界矩阵均与 Avatar 同名骨骼逐元素相同；模型 local 没有变化。B8 复制 Avatar local 会重复叠加骨段姿态。这个结论不证明 GPU 已按这些矩阵更新，也不证明手部接触目标正确；不能继续把握持偏移简单归为遗漏刷新。

用户确认瞄准、站立、收枪和奔跑各约 10 秒，手部形状、样本瓶、切分接缝正常。日志未逐项标注动作时间，未据此推定某一帧对应某姿势。

下一步 B10 仅原样回写模型自己的 local，检查位置、完整线性矩阵和各轴缩放，同帧失败即恢复保存值并停止试验。目标空间转换与握持校准仍需后续验证。v15 动画、B7 算法及挂点保持原样。
'''
    (W/'分析报告.md').write_text(text,encoding='utf-8')
    print(json.dumps({k:result[k]for k in ('status','latestNodePairs','samples','timeRange')},ensure_ascii=False))


if __name__=='__main__':main()
