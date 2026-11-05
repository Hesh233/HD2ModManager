"""Record the successful B14-0 game gate without rebuilding runtime packages."""
import copy
import hashlib
import re
import shutil
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest

R=ROOT/'outputs/native-manual-20261103'
W=ROOT/'outputs/native-b14-observation-20261104/B14-0'
REL=Path('project/diagnostics/B14/game-results/B14-0')
BACKUP=Path('backups/v22-b14-zero-result-before-20261104')
GAME=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2'


def main():
    baseline=load(R/'delivery-verification.json')
    assert baseline['status']=='PASS' and baseline['revision']=='native-v22'
    expected={r['path']:r['sha256']for r in baseline['verified']}
    for name,sha in expected.items():assert digest(R/name)==sha,name
    assert not (R/BACKUP).exists(),'Result already recorded; do not overwrite its baseline.'
    profile=load(R/'project/diagnostics/B14/variants/0/profile.json')
    nodes={(r['name'],r['index']+1)for r in profile['attachmentProbe']['nodes']}
    assert len(nodes)==23 and profile['attachmentProbe']['validationOnly']
    path=GAME/'hd2physbone.log';data=path.read_bytes();text=data.decode('utf-8',errors='replace')
    at=text.rfind('[attach_probe] variant=0 event=loaded version=1.2.0');assert at>=0
    start=text.rfind('\n',0,at)+1;session=text[start:]
    rows=[r for r in session.splitlines()if '[attach_probe]'in r]
    assert rows and all('[attach_probe] variant=0 'in row for row in rows)
    assert not any(any('event='+event in row for event in ('disabled','validation_mismatch','phase','applied','rollback','restore_failed'))for row in rows)
    pending=[];cycles=[]
    for row in rows:
        fields=dict(re.findall(r'(\w+)=([^ ]+)',row))
        if fields['event']=='validate_node':pending.append(fields)
        elif fields['event']=='validated':
            assert fields['nodes']=='23' and fields['validation_only']=='true'
            assert len(pending)==46
            for stage in ('name_query','parent_query'):
                observed={(r['name'],int(r['index']))for r in pending if r['stage']==stage}
                assert observed==nodes and sum(r['stage']==stage for r in pending)==23
            assert {r['avatar']for r in pending}=={fields['avatar']}
            cycles.append(dict(time=row[:8],frame=int(re.search(r' f(\d+)',row)[1]),avatar=int(fields['avatar']),nodes=23))
            pending=[]
    assert cycles and not pending
    loader_path=GAME/'chef_loader.log';loader_data=loader_path.read_bytes()
    loader_lines=loader_data.decode('utf-8',errors='replace').splitlines()
    loader_rows=[r for r in loader_lines if rows[0][:8]<=r[:8]]
    assert loader_rows and 'shutdown (clean)'in loader_rows[-1]
    W.mkdir(parents=True,exist_ok=True)
    (W/'probe-excerpt.log').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    (W/'loader-excerpt.log').write_text('\n'.join(loader_rows)+'\n',encoding='utf-8')
    def meta(p,d):return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
    next_package='AB测试/B14-A-持枪控制挂点二分测试.zip'
    report=dict(status='PASS',variant='B14-0',userReportedNoCrash=True,cleanShutdown=True,
        probeValidationPassed=True,validatedCycles=len(cycles),nodesPerCycle=23,cycles=cycles,
        disabledEvents=0,mismatchEvents=0,appliedEvents=0,sessionStart=rows[0][:8],sessionEnd=loader_rows[-1][:8],
        sources=[meta(path,data),meta(loader_path,loader_data)],
        scope='All configured known-node name/index/parent queries completed in a validation-only game session. Displacement and weapon response remain untested.',
        nextPackage=next_package,nextPackageSha256=digest(R/next_package))
    assert report['nextPackageSha256']==expected[next_package]
    save_json(W/'game-result.json',report)
    (W/'结果与下一步.md').write_text(
        'B14-0 实机校验通过。用户报告无崩溃；日志共有 '+str(len(cycles))+
        ' 次完整校验，每次全部 23 个节点的名称、索引、父节点均通过；无 disabled、validation_mismatch、phase 或 applied，游戏正常退出。\n\n'
        '下一步：停用 B14-0 和其他 test01 Lua，仅启用 B14-A，保留 v15 动画与模型，部署并完全重启。普通持枪、瞄准平视/仰视/俯视、收枪各至少 16 秒；观察 4 秒原位 / 4 秒上移 60 厘米的周期中，枪身、枪口、前握把、左右手分别是否响应。换原版甲后循环应停止。完成退出并反馈，结合 applied 和 node 日志再决定下一步。\n\n'
        '此结论只验证 0 包的节点校验路径，尚不证明位移稳定性或已找到武器驱动链。原始发行包与源码压缩包保留封包时状态，本文件是后续游戏测试记录。\n',encoding='utf-8')
    matrix=load(R/'ab-matrix.json')
    group=next(g for g in matrix['groups']if g['group']=='B14-0')
    group.update(status='tested-validation-pass',gameTested=True,
        result=f'用户无崩溃；{len(cycles)}次完整23节点校验通过，无停用/不匹配/位移，正常退出。A/B位移未测。',
        resultReport=(REL/'game-result.json').as_posix())
    matrix['nextTest']='B14-A'
    save_json(W/'ab-matrix.json',matrix)
    package=load(R/'package-report.json')
    package.setdefault('gameResults',{})['B14-0']=dict(status='validation-pass',
        report=(REL/'game-result.json').as_posix(),sha256=digest(W/'game-result.json'),displacementTested=False)
    save_json(W/'package-report.json',package)
    pairs=[(W/name,Path(name))for name in ('ab-matrix.json','package-report.json')]
    pairs.extend((W/name,REL/name)for name in ('game-result.json','probe-excerpt.log','loader-excerpt.log','结果与下一步.md'))
    backup=(R/BACKUP).resolve();assert backup.is_relative_to(R.resolve())
    backup.mkdir(parents=True)
    shutil.copy2(R/'delivery-verification.json',backup/'delivery-verification.json')
    expected[(BACKUP/'delivery-verification.json').as_posix()]=digest(backup/'delivery-verification.json')
    for source,relative in pairs:
        dest=(R/relative).resolve();saved=(backup/relative).resolve()
        assert dest.is_relative_to(R.resolve())and saved.is_relative_to(backup)
        if dest.exists():
            assert digest(dest)==expected[relative.as_posix()]
            saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,saved)
            expected[(BACKUP/relative).as_posix()]=digest(saved)
        else:assert relative.as_posix()not in expected
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
        expected[relative.as_posix()]=digest(source)
    for name,sha in expected.items():assert digest(R/name)==sha,name
    verification=copy.deepcopy(baseline)
    verification.update(files=len(expected),lastGameResult=(REL/'game-result.json').as_posix(),
        lastMetadataBackup=str(backup),verified=[dict(path=p,sha256=s)for p,s in sorted(expected.items())])
    save_json(R/'delivery-verification.json',verification)
    print('Recorded B14-0 PASS:',len(cycles),'complete cycles x 23 nodes; no probe mutation; next B14-A; all',len(expected),'file hashes verified.')


if __name__=='__main__':main()
