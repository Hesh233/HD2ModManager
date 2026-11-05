"""Compare frozen v7 and v8 using neutral input and selected real game clips."""
import copy,importlib.util,json,math,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import native_skeleton as current
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.processor import ModConfig,_build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_rotate,vec_add,vec_sub
W=ROOT/'outputs/native-v9-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103';V7=ROOT/'outputs/native-v8-20261104'
spec=importlib.util.spec_from_file_location('anim_batch_mod.frozen_v7',V7/'manager/anim_batch_mod/native_skeleton.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes());m=current.load_manifest(P/'source-skeleton.json')
eu=UnitData.parse(current.append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(current.append_bones((B/'bones.toc').read_bytes(),m))
cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
sm={n['driver']:eu.name_hashes.index(n['hash']) for n in m['bones'] if n['driver']};am=[eu.name_hashes.index(h) for h in eb.hashes]
def world(a,t):
    tr=_build_tracks(a);local=list(eu.transforms)
    for ai,ui in enumerate(am):local[ui]=WorldTransform(*(x[ai].evaluate(t) for x in tr))
    return _calculate_world_transforms(local,eu.parents)
def convert(mod,raw):
    data,metrics=mod.convert_clip(raw,b,u,m,cfg,opts);return AnimationData.parse(data),metrics

lookup={int(r['id']):r for r in json.loads((V7/'project/animations/build-report.json').read_text())['animations']}
fid=18053434533899883251;row=lookup[fid];archive=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),row['package']);raw=archive.entries[fid,ANIMATION_TYPE_ID].toc_data
for label,stable,soft in [('baseline',False,0.),('soft',False,.008),('pole',True,0.),('both',True,.008)]:
 options={**opts,'stable_grip_pole':stable,'grip_soft_distance':soft}
 data,metrics=current.convert_clip(raw,b,u,m,cfg,options);clip=AnimationData.parse(data);tr=_build_tracks(clip);peaks=[]
 for i,node in enumerate(m['bones']):
  if node['driver'] not in ('l_shoulder','l_elbow','r_shoulder','r_elbow'):continue
  prev=None
  for frame in range(math.floor(clip.animation_length*60)+1):
   q=tr[1][90+i].evaluate(frame*1000/60)
   if prev:
    angle=math.degrees(2*math.acos(min(1.,abs(sum(x*y for x,y in zip(prev,q))))));peaks.append((angle,node['driver'],frame/60))
   prev=q
 print(label,sorted(peaks,reverse=True)[:5],flush=True)
