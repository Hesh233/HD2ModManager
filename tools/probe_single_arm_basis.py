"""Numerical prototype; never rewrites production models/animations."""
import copy,json,math,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'));import audit_test07_single_current as a
from anim_batch_mod.processor import _quat_from_to,_calculate_world_transforms,WorldTransform,ModConfig,_build_tracks
from anim_batch_mod.math3d import quat_multiply as qm,quat_inverse as qi,quat_rotate as qr,vec_sub
from anim_batch_mod.formats import AnimationData,UnitData,BonesData
s=a.PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'));index=a.ResourceIndex(s);db=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
_,e=index.resolve(0x4d1c334d294dfa97,a.UNIT_TYPE_ID);n=UnitData.parse(e.toc_data);_,e=index.resolve(n.bones_ref,a.BONE_TYPE_ID);b=BonesData.parse(e.toc_data);bi=dict(zip(b.names,range(len(b.names))));ni={h:i for i,h in enumerate(n.name_hashes)};m=a.unit_rows(a.MODEL/'9ba626afa44a3aa3.patch_0')[0][1];mi={h:i for i,h in enumerate(m.name_hashes)};nw0=_calculate_world_transforms(n.transforms,n.parents);mw0=_calculate_world_transforms(m.transforms,m.parents)
def idx(name):h=b.hashes[bi[name]];return ni[h],mi[h]
def vangle(x,y):return math.degrees(math.acos(max(-1,min(1,sum(v*w for v,w in zip(x,y))/(math.sqrt(sum(v*v for v in x))*math.sqrt(sum(v*v for v in y)))))))
def cross(x,y):return [x[1]*y[2]-x[2]*y[1],x[2]*y[0]-x[0]*y[2],x[0]*y[1]-x[1]*y[0]]
r=json.loads((a.OUT/'test07-单骨架-手臂文件核查.json').read_text(encoding='utf-8'));rows={r[0]:r for r in a.records(a.ANIM/'9ba626afa44a3aa3.patch_0')}
with (a.ANIM/'9ba626afa44a3aa3.patch_0').open('rb') as f:
 for clip in [c for c in r['realClipSamples'] if not c['additive']]:
  fid=int(clip['id'],16);old=AnimationData.parse(a.read(f,rows[fid]));_,e=index.resolve(fid,a.ANIMATION_TYPE_ID);original=AnimationData.parse(e.toc_data);ot,gt=_build_tracks(original),_build_tracks(old);maximum=[0,0];plane=[0,0]
  for frame in range(math.ceil(original.animation_length*60)+1):
   t=min(frame*1000/60,original.animation_length*1000);nl=list(n.transforms);ml=list(m.transforms)
   for i,h in enumerate(b.hashes):nl[ni[h]]=WorldTransform(*(tr[i].evaluate(t) for tr in ot));ml[mi[h]]=WorldTransform(*(tr[i].evaluate(t) for tr in gt))
   ow=_calculate_world_transforms(nl,n.parents)
   for sidei,side in enumerate(['l','r']):
    nr,mr=idx(side+'_shoulder');ne,me=idx(side+'_elbow');nh,mh=idx(side+'_hand');H=_quat_from_to(n.transforms[ne].position,m.transforms[me].position)
    J=_quat_from_to(n.transforms[nh].position,m.transforms[mh].position)
    ru=math.sqrt(sum(x*x for x in m.transforms[me].position))/math.sqrt(sum(x*x for x in n.transforms[ne].position));rl=math.sqrt(sum(x*x for x in m.transforms[mh].position))/math.sqrt(sum(x*x for x in n.transforms[nh].position))
    ml[me].position=[x*ru for x in qr(H,nl[ne].position)];ml[mh].position=[x*rl for x in qr(J,nl[nh].position)]
    ml[mr].rotation=qm(qm(qm(qm(m.transforms[mr].rotation,H),qi(n.transforms[nr].rotation)),nl[nr].rotation),qi(H))
    ml[me].rotation=qm(qm(qm(qm(H,nl[ne].rotation),qi(n.transforms[ne].rotation)),qi(H)),m.transforms[me].rotation)
    mw=_calculate_world_transforms(ml,m.parents);hq=qm(qm(mw0[mh].rotation,qi(nw0[nh].rotation)),ow[nh].rotation);ml[mh].rotation=qm(qi(mw[m.parents[mh]].rotation),hq)
    mw=_calculate_world_transforms(ml,m.parents);np=[ow[i].position for i in [nr,ne,nh]];mp=[mw[i].position for i in [mr,me,mh]];nv=[vec_sub(np[1],np[0]),vec_sub(np[2],np[1])];mv=[vec_sub(mp[1],mp[0]),vec_sub(mp[2],mp[1])];maximum[sidei]=max(maximum[sidei],abs(vangle(*nv)-vangle(*mv)))
    S=qm(qm(mw[mr].rotation,H),qi(ow[nr].rotation));nn=qr(S,cross(*nv));mn=cross(*mv)
    if vangle(*nv)>20 and vangle(*mv)>20:plane[sidei]=max(plane[sidei],vangle(nn,mn))
  print(clip['id'],'bend',maximum,'anatomical-plane',plane,flush=True)
index.close()

