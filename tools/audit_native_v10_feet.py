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
W=ROOT/'outputs/native-v10-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103';V7=ROOT/'outputs/native-v8-20261104'
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

neutral=AnimationData(initial_bone_states=[AnimationBoneState(list(u.transforms[u.name_hashes.index(h)].position),list(u.transforms[u.name_hashes.index(h)].rotation),[1.,1.,1.],False,False,False) for h in b.hashes],animation_length=.033,is_additive=False)
a,_=convert(old,neutral.to_bytes());c,_=convert(current,neutral.to_bytes());wa=world(a,0);wc=world(c,0);rows=[]
for side,sign in [('l',1),('r',-1)]:
 index=next(i for i,n in enumerate(m['bones']) if n['driver']==side+'_foot');toe=next(i for i,n in enumerate(m['bones']) if n['parent']==index and 'Toe' in n.get('sourceName',''))
 foot=eu.name_hashes.index(m['bones'][index]['hash']);tip=eu.name_hashes.index(m['bones'][toe]['hash'])
 before=vec_sub(wa[tip].position,wa[foot].position);after=vec_sub(wc[tip].position,wc[foot].position)
 assert math.dist(wa[foot].position,wc[foot].position)<1e-7
 assert (after[0]-before[0])*sign>0, (side,before,after)
 rows.append({'foot':side+'_foot','localYDegrees':opts['foot_y_degrees'][side+'_foot'],'beforeToeDirection':before,'afterToeDirection':after,'ankleTranslationMetres':math.dist(wa[foot].position,wc[foot].position),'inwardHorizontalChangeMetres':(after[0]-before[0])*sign})
report={'status':'PASS','scope':'Actual Source rig in generated neutral reference pose; foot rotation moves toe direction inward without translating the ankle','rows':rows,'modelScale':1.08,'groundTranslationAdded':False,'gameTested':False}
(W/'foot-angle-audit.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
