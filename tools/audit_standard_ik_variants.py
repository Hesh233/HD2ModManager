"""Compare standard-IK variants to the normal absolute clips; diagnostic only."""
import copy,json,math,sqlite3,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from audit_single_against_normal import NORMAL,OUT,records,ARM,angle
from anim_batch_mod import processor as p
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
DB=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
i=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));i.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);_,e=i.resolve(0x4d1c334d294dfa97,UNIT_TYPE_ID);u=UnitData.parse(e.toc_data);_,e=i.resolve(u.bones_ref,BONE_TYPE_ID);b=BonesData.parse(e.toc_data);config=p.ModConfig.load(ROOT.parent/'config.toml');real=p._apply_two_bone_ik
report=[];rowmap={r[0]:r for r in records(NORMAL)}
with NORMAL.open('rb') as f:
 for s in json.loads((OUT/'单骨架-配置参考及IK实证-20261107.json').read_text(encoding='utf-8'))['samples']:
  fid=int(s['id'],16);r=rowmap[fid];f.seek(r[2]);raw=f.read(r[7]);gold=AnimationData.parse(raw);gt=p._build_tracks(gold);_,e=i.resolve(fid,ANIMATION_TYPE_ID);source=AnimationData.parse(e.toc_data);results={}
  for preserve in [True,False]:
   for rotate in [True,False]:
    a=copy.deepcopy(source)
    def solve(*args,**kwargs):kwargs['preserve_bend_frame']=preserve;return real(*args,**kwargs)
    with patch.object(p,'_apply_two_bone_ik',side_effect=solve):p.modify_animation_with_world_compensation(a,b,u,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=rotate,apply_rotation_compensations=False,apply_ik_correction=True)
    at=p._build_tracks(a);maximum=position=0
    for t in p._build_bake_times(gold.animation_length*1000):
     for j in ARM:
      maximum=max(maximum,angle(gt[1][j].evaluate(t),at[1][j].evaluate(t)));position=max(position,math.dist(gt[0][j].evaluate(t),at[0][j].evaluate(t)))
    results[f'preserve={preserve},rotate={rotate}']=dict(byteExact=raw==a.to_bytes(),maxArmRotationDegrees=maximum,maxArmPositionDifference=position)
  report.append(dict(id=s['id'],variants=results))
(OUT/'单骨架-标准IK策略对照-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');i.close()
for s in report:print(s['id'],{k:round(v['maxArmRotationDegrees'],4) for k,v in s['variants'].items()})

