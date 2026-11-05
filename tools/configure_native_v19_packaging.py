"""Derive versioned packaging scripts; keep the previous delivered scripts intact."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
tools=ROOT/'tools'


def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    repack=(tools/'repack_native_b9.py').read_text(encoding='utf-8').replace('B9','B10').replace('只读父空间观测','模型自身姿态原样回写')
    (tools/'repack_native_b10.py').write_text(repack,encoding='utf-8')
    cleanup=(tools/'Cleanup-Native-V18Imports.ps1').read_text(encoding='utf-8-sig').replace('native-v18-20261104','native-v19-20261104')
    (tools/'Cleanup-Native-V19Imports.ps1').write_text(cleanup,encoding='utf-8')
    s=(tools/'package_native_v18_b9.py').read_text(encoding='utf-8')
    s=s.replace('native-v18','native-v19').replace('native-v17','native-v18').replace('v18-before','v19-before')
    s=s.replace('B9','B10').replace('native_v18','native_v19').replace('repack_native_b9','repack_native_b10').replace('V18Imports','V19Imports')
    s=replace_once(s,"REQUIRED=['model-arm-topology.json','scope-audit.json','scene-observer-audit.json','chef-compatibility-audit.json']",
        "REQUIRED=['B9-game-findings.json','scope-audit.json','scene-observer-audit.json','scene-roundtrip-audit.json','chef-compatibility-audit.json']")
    s=s.replace("RETIRED='AB测试/B8-模型骨骼直接写入.zip'\nRETIRED_DEST=BACKUP/'retired/B8-模型骨骼直接写入.zip'\n",'')
    s=replace_once(s,"    for row in report['packages']:\n        if row['name']==RETIRED:row.update(name=RETIRED_DEST.as_posix(),status='retired-game-test-failed')\n",'')
    s=replace_once(s,"    retired=(R/RETIRED).resolve();saved_retired=(R/RETIRED_DEST).resolve()\n    assert retired.is_relative_to(R.resolve())and saved_retired.is_relative_to(backup)\n    assert digest(retired)==expected[RETIRED]and not saved_retired.exists()\n",'')
    start=s.index('    # Single verified file retirement;')
    end=s.index('    for relative,sha in expected.items():assert digest(R/relative)==sha,relative',start)
    s=s[:start]+s[end:]
    s=s.replace("'previousIncrement':'B8-增量排查工程.zip'","'previousIncrement':'B9-增量排查工程.zip'")
    s=s.replace("{k:load(W/'feedback.json')[k]for k in ('B7','B8')}","{'B9':load(W/'feedback.json')['B9']}")
    start=s.index("        if group['group']=='B8':")
    end=s.index("    assert not any(g['group']=='B10'",start)
    s=s[:start]+"        if group['group']=='B9':group.update(status='tested-scene-space-confirmed',gameTested=True,\n            result='手形、样本瓶和切分接缝正常；2432 对同帧节点记录确认局部恒等、父空间为 Avatar 同名骨。')\n"+s[end:]
    s=s.replace("status='awaiting-game-observation'","status='awaiting-game-roundtrip'")
    s=s.replace("description='B7 稳定基准，只读采集真实父节点、完整局部/世界矩阵和缩放。'","description='B9 基准，限频原样回写模型自身 local，校验并在同帧失败时回滚。'")
    s=s.replace("R/'project/diagnostics/B7/src/native_attachments.lua',Path('src/control/native_attachments-B7.lua')", "R/'project/diagnostics/B9/src/native_attachments.lua',Path('src/control/native_attachments-B9.lua')")
    s=s.replace("(observer,Path('src/native_scene_observer.lua')),","(observer,Path('src/native_scene_observer.lua')),\n        (ROOT/'HD2PhysBoneCompat/src/native_scene_roundtrip.lua',Path('src/native_scene_roundtrip.lua')),")
    s=s.replace("'scene_observer_harness.lua')],","'scene_observer_harness.lua','scene_roundtrip_harness.lua')],")
    s=s.replace("('analyze_native_b9_log.py','native_model_arm_locals.py'","('analyze_native_b9_log.py','analyze_native_b10_log.py','audit_native_v18_b9.py','native_model_arm_locals.py'")
    s=s.replace("    reports=diag/'reports';reports.mkdir(exist_ok=True)","    reports=diag/'reports';reports.mkdir(exist_ok=True)\n    shutil.copy2(ROOT/'outputs/native-b9-observation-20261104/分析报告.md',reports/'B9-实机分析报告.md')")
    s=s.replace("    assert digest(R/'test01-配套动画.zip')", "    roundtrip=ROOT/'HD2PhysBoneCompat/src/native_scene_roundtrip.lua'\n    assert digest(roundtrip)==load(W/'scope-audit.json')['roundtripSha256']==load(W/'scene-roundtrip-audit.json')['roundtripSha256']\n    assert digest(roundtrip)==load(W/'chef-compatibility-audit.json')['embeddedSourceSha256']['native_scene_roundtrip.lua']\n    assert digest(R/'test01-配套动画.zip')")
    start=s.index("    (diag/'README.txt').write_text(")
    end=s.index('    pack.WORK=W',start)
    s=s[:start]+"    (diag/'README.txt').write_text('B10: B9 baseline plus same-model local roundtrip, all-model final validation and same-frame rollback. Run python repack_native_b10.py here to reproduce the patch with standard Python. tools/analyze_native_b10_log.py needs numpy. Other audit tools need the original workspace. Game roundtrip acceptance and grip correction are pending.\\n',encoding='utf-8')\n"+s[end:]
    s=s.replace('Incremental B10 delivery with B8 retirement, byte checks and guarded import.','Incremental B10 delivery with byte checks and guarded import; keep B9.')
    s=s.replace('v15 and B7 retained, B8 archived, game not deployed.','v15 and B9 retained; game not deployed.')
    s=s.replace("probe='v18-B10'","probe='v19-B10'")
    s=s.replace('actual scene observation remains pending.','in-game setter roundtrip remains pending.')
    assert 'RETIRED'not in s
    compile(s,str(tools/'package_native_v19_b10.py'),'exec')
    (tools/'package_native_v19_b10.py').write_text(s,encoding='utf-8')
    print('Versioned B10 repack, cleanup and delivery tools generated; no delivery mutation.')


if __name__=='__main__':main()
