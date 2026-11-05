import json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID,UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID
WORK=ROOT/'outputs/native-regression-20261103'
all_keys=set(); report={}
for name in ('test01-模型材质.zip','test01-配套动画.zip','test01-物理运行时.zip'):
    types={}; groups=0
    with zipfile.ZipFile(WORK/name) as z:
        assert z.testzip() is None
        for path in z.namelist():
            if '.patch_' not in path or path.endswith(('.gpu_resources','.stream')): continue
            ar=TocArchive.parse_parts(z.read(path),z.read(path+'.gpu_resources'),z.read(path+'.stream'))
            groups+=1
            for key in ar.entries:
                assert key not in all_keys,(name,key)
                all_keys.add(key);types[key[1]]=types.get(key[1],0)+1
    if name=='test01-模型材质.zip':assert types.get(UNIT_TYPE_ID)==17 and types.get(STATE_MACHINE_TYPE_ID,0)==0
    if name=='test01-配套动画.zip':assert types=={UNIT_TYPE_ID:1,BONE_TYPE_ID:1,STATE_MACHINE_TYPE_ID:1,ANIMATION_TYPE_ID:3180}
    if name=='test01-物理运行时.zip':assert groups==1 and sum(types.values())==1
    report[name]=dict(patch_groups=groups,resources=sum(types.values()),types={f'{t:016x}':c for t,c in types.items()})
report.update(status='PASS',resource_collisions=0,game_tested=False)
(WORK/'reports/package-structure.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
