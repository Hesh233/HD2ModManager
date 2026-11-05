"""Deliver H/W and preserve both B15 trial results with the unchanged runtime."""
from pathlib import Path
source=Path(__file__).with_name('package_native_v23_b15.py').read_text(encoding='utf-8')
for old,new in (
    ('native-v23-b15-20261105','native-v24-b16-20261105'),
    ('v23-b15-before-20261105','v24-b16-before-20261105'),
    ('native-v23','native-v24'),('native-v22','native-v23'),
    ('v23-B15','v24-B16'),('B15','B16'),('b15','b16'),
    ('B14-A','B15-A1'),
    ('B14-增量排查工程.zip','B15-增量排查工程.zip'),
    ('native_v23_b16','native_v24_b16'),
    ('analyze_native_b14_a.py','analyze_native_b15_results.py'),
    ("('A1','A2')","('H','W')"),
    ("probe='B16-A1/A2'","probe='B16-H/W'"),
    ("nextTest='B16-A1'","nextTest='B16-H'"),
    ('B15-A1的四个父级组','B15-A1的两个父级组'),
    ('test A1, then A2','test H, then W'),('Test A1, then A2','Test H, then W'),
    ('B14 controls','B15 controls'),
):
    source=source.replace(old,new)
# The archived wrapper dependencies retain their original filenames.
source=source.replace("toolnames=(", "toolnames=('prepare_native_v23_b15.py','audit_native_v23_b15.py','audit_native_v23_b15_chef.py','package_native_v23_b15.py',")
source=source.replace("report.setdefault('priorUserResults',{})['B15-A1']='左右手位置未变，武器整体上移。'",
    "report.setdefault('priorUserResults',{})['B15-A1']='武器和握把周期上移；右手短暂到准确握持位置后回退；左手无明显变化。'\n    report['priorUserResults']['B15-A2']='无可见效果；18次位移已回读通过，采集的枪械/配件标记位移为零。'")
source=source.replace("result='武器整体上移，左右手未变；15次17节点位移回读通过，具体驱动节点待二分。'",
    "result='武器/握把周期上移；右手短暂正确握持后回退，左手无明显变化；23次6节点位移回读通过。',rightHandTransientCorrectContactReported=True")
marker="    save_json(W/'package-report.json',report)"
extra="""    report['gameResults']['B15-A2']=dict(status='no-observed-weapon-response',
        report='project/diagnostics/B16/evidence/B15-A2-game-result.json',
        sha256=digest(W/'evidence/B15-A2-game-result.json'),candidateDisplacementVerified=True)
"""
assert marker in source;source=source.replace(marker,extra+marker)
marker="    for variant,row in zip(('H','W'),packages):"
extra="""    negative=next(g for g in matrix['groups']if g['group']=='B15-A2')
    negative.update(status='tested-no-observed-weapon-response',gameTested=True,
        result='用户无效果；18次11节点位移回读通过，采集的枪械/配件标记位移为零。',
        resultReport='project/diagnostics/B16/evidence/B15-A2-game-result.json')
"""
assert marker in source;source=source.replace(marker,extra+marker)
source=source.replace("lastGameResult='project/diagnostics/B16/evidence/B15-A1-game-result.json'", "lastGameResult='project/diagnostics/B16/evidence/B15-comparison.json'")
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
