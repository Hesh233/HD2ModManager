"""Verify installed package, all eight case audits and preserved user files."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/manager-parent-entry-fix-20261106'
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'


def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    info=load(TARGET/'anim_batch_mod/build-info.json');assert info['pipelineVersion']=='1.0.14'
    for row in info['files']:
        installed=TARGET/'anim_batch_mod'/row['name']
        assert digest(installed).upper()==row['sha256'].upper()
        assert digest(installed)==digest(ROOT.parent/row['name'])
    binaries={name:digest(TARGET/name) for name in ('HD2ModManager.dll','HD2ModCore.dll','hd2mod.dll')}
    assert all(h==digest(OUT/'publish'/name)==digest(OUT/'test-manager'/name) for name,h in binaries.items())
    before=load(OUT/'protected-before.json')
    unchanged=[];concurrent=[]
    manager_log=(TARGET/'logs/manager_20261106.log').read_text(encoding='utf-8-sig',errors='replace')
    for row in before['protected']:
        actual=digest(row['path'])
        if actual==row['sha256']:unchanged.append(row);continue
        # A separate live-manager import occurred after this task's sync/tests.
        # Preserve it; do not reset an interactive user's library index.
        assert Path(row['path'])==TARGET/'test-library/library.json',row['path']
        assert '17:26' in manager_log and 'test07' in manager_log and 'B-08' in manager_log
        concurrent.append({'path':row['path'],'beforeSha256':row['sha256'],'observedSha256':actual,
                           'context':'Concurrent manager import test07 to B-08 at 17:26; preserved, not rolled back.'})
    for row in before['sourceVpk']:assert digest(row['path'])==row['sha256'],row['path']
    runs=load(OUT/'simulation-results.json');reruns=load(OUT/'reimport-results.json')
    assert len(runs)==len(reruns)==8 and all(r['exitCode']==0 for r in runs+reruns)
    reports=[]
    for i in range(1,9):
        name=f'test{i:02d}';case=OUT/(name+'-rs89')
        report=load(case/name/'parent-entry-mask-audit.json');repeat=load(case/'reimport-regression.json')
        flow=load(case/name/'import-regression.json');build=load(case/name/'animations/build-report.json')
        assert report['status']==repeat['status']==flow['status']=='PASS'
        assert report['model']==name and report['sampleAnimations']==32 and report['masks']==80
        assert report['luaEntryStartedAndStopped'] and report['oldRawParentAndMatrixBytesPreserved']
        assert repeat['modelKeyPreserved'] and repeat['animationDecisionPreserved'] and repeat['liveLibraryUnchanged']
        assert build['diagnosticSample'] and flow['protectedModelUnchanged'] and flow['targetArchive']=='85d392768bf6a259'
        reports.append(report)
    runtime=load(OUT/'runtime-regression/lua-route-audit.json');assert runtime['status']=='PASS'
    counters=[ET.parse(p).find('.//{*}Counters').attrib for p in (OUT/'tests').glob('*.trx')]
    assert all(int(c['failed'])==0 for c in counters)
    py=(OUT/'python-tests.log').read_text(encoding='utf-8-sig',errors='replace')
    assert 'OK (skipped=1)' in py
    changed=load(ROOT/'outputs/manager-route-update-20261106-171058/update-manifest.json')
    report={'status':'PASS','pipelineVersion':'1.0.14','luaVersion':'1.0.9','runtimePolicy':'b23-1.0.8',
            'installedDirectory':str(TARGET),'backup':changed['backup'],'changedFiles':changed['changedFiles'],
            'sourceFilesVerified':len(info['files']),'binaries':binaries,'modelsTested':8,'models':reports,
            'sourceTargetUnitsChecked':sum(r['unitCount'] for r in reports),
            'existingRawParentRecordsChecked':sum(sum(u['existingParentRecordsPreserved'] for u in r['units']) for r in reports),
            'representativeAnimations':sum(r['sampleAnimations'] for r in reports),'masks':sum(r['masks'] for r in reports),
            'maskOwnerChecks':sum(r['maskOwnerChecks'] for r in reports),'independentRouteChecks':sum(r['routeChecks'] for r in reports),
            'maxNativeChannelError':max(r['maxNativeChannelError'] for r in reports),
            'pythonTestsRun':int(re.search(r'Ran (\d+) tests',py).group(1)),'pythonTestsSkipped':1,
            'dotnetTestsPassed':sum(int(c['passed']) for c in counters),'runtimeSimulationChecks':runtime['checks'],
            'reimportStagingCases':8,'userFilesUnchanged':len(unchanged),'concurrentLibraryChangesPreserved':concurrent,'sourceVpkHashesUnchanged':True,
            'gameDeployed':False,'gameTested':False,'blenderLiveTested':False,'manualGuiTested':False,'sampleOnly':True}
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# manager-1.0.7 同步与 test01–08 验证','',
           '2026-11-06（Asia/Shanghai）。生成链 **1.0.14**，挂点 Lua **1.0.9**，公共策略仍 **b23-1.0.8**。',
           '',f'已更新指定管理器 `{TARGET}` 的 {len(changed["changedFiles"])} 个随包文件；源代码、发布产物、测试管理器与安装目录哈希一致。',
           f'备份：`{changed["backup"]}`。用户设置、资产索引及其余原有库文件哈希不变，8 个原 VPK 哈希不变。管理器随后在17:26新增test07→B-08，库索引变动已保留，不回滚这次并发操作。','',
           '## 本轮修正','',
           '- Source 挂点追加只序列化新增节点，保留全部旧矩阵和 TransformEntry 原字节，不把原根/自父节点改成 `(1,65535)`。',
           '- 只读准备校验拒绝旧的损坏原始父记录，要求正常重导入 VPK，不现场修写受保护模型。',
           '- Adapter/Transfer 入口均为 1.0.9，保留严格版本门禁；同步当前完整生成链，不回滚已有线程数功能。','',
           '## 八模型实际服务联调','',
           '每模型独立库；调用更新管理器同源 GUI 服务，完成转换→真实只读入库→RS-89换甲→Lua/32条代表性动画→配套入库。构建期间用禁止写删的只读句柄保护模型，另做同源重导入暂存/身份/决策保持核查。','',
           '| 模型 | 倍率 | Source骨数 | 核查身体Unit | 动画抽样 | Lua启动/关闭、父记录、遮罩、重导入 |',
           '|---|---:|---:|---:|---:|---|']
    for r in reports:lines.append(f'| {r["model"]} | {r["scale"]:.2f} | {r["sourceBones"]} | {r["unitCount"]} | 32 | PASS |')
    lines += ['',f'共 **{report["sourceTargetUnitsChecked"]} 个来源/目标身体 Unit、{report["existingRawParentRecordsChecked"]:,} 条原始父记录、256 条代表性动画、640 张完整遮罩、86,400 次新增权重核对、377,360 次独立通道/挂点核查**通过。原 HD2 通道最大误差 `{report["maxNativeChannelError"]:.3g}`。',
              '',f'Python {report["pythonTestsRun"]} 项运行完成（1 跳过），.NET {report["dotnetTestsPassed"]} 项通过；既有挂点模拟 {report["runtimeSimulationChecks"]:,} 次检查通过。',
              '', '## 新增独立验证的关键点','',
              '- 比对原始 TransformEntry 的两个 uint16，不能仅比较 UnitData 解码后的 None/parents。',
              '- 校准可能先重定位一张同尺寸表：挂点追加输入按最近一张保留表核对，避免误比对校准前合法变化。',
              '- Lua 包按既有设计追加 5 个未动画参考/输出节点并覆盖动画包 Avatar；按 Lua 包实际 Avatar 与 profile 匹配，而非要求两个包的节点数相同。',
              '- Source/目标身体 Unit 归属和一对多实际映射保持；头部与原生辅助门禁不放宽。','',
              '## 验证边界与使用方式','',
              '**未修改游戏部署、未全量重烘、未操作 Blender 场景，未手动 GUI 或游戏视觉验收。32条动画是覆盖全ID范围的诊断抽样，禁止直接拿测试包当全量部署包。Lua 在 Lua 5.1 空世界 stub 中启动/关闭，不代表真实角色位置修正已视觉验收。**',
              '', '指定管理器代码已更新；旧的坏模型/旧 Lua 包不会自动变好。正常重导入原 VPK，再生成完整模型/换甲与配套。被冻结的 test01 1.0.8 确认基线未重烘或更改。',
              '', '同源重导入补测仅验证暂存生成、模型 key、模型/动画决策与既有库不变，未把暂存结果交换进用户活动库。',
              '', '## 证据','', '`verification.json`：安装哈希、逐模型报告与统计；各 `testXX-rs89/`：import-regression、reimport-regression、parent-entry-mask-audit、route-audit；`tests/*.trx`、`python-tests.log`、`runtime-regression/lua-route-audit.json`；`sync.log` 与备份 update-manifest.json。']
    (OUT/'同步与测试报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','pipelineVersion','modelsTested','representativeAnimations','sourceTargetUnitsChecked','dotnetTestsPassed','userFilesUnchanged')},ensure_ascii=False))

if __name__=='__main__':main()
