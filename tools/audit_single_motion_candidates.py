"""Inspect worst motion candidates and additive resampling loss, without edits to packs."""
import copy,json,math,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from audit_single_against_normal import records,scan,NORMAL,CURRENT,OUT,ARM,angle
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,_compose_additive_local,WorldTransform,Track
from anim_batch_mod.math3d import quat_slerp

def main():
 db=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';idx=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));idx.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
 _,e=idx.resolve(0x4d1c334d294dfa97,UNIT_TYPE_ID);unit=UnitData.parse(e.toc_data);_,e=idx.resolve(unit.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(e.toc_data);ui={h:i for i,h in enumerate(unit.name_hashes)};bi={n:i for i,n in enumerate(bones.names)}
 compare=json.loads((OUT/'单骨架-正常包对照-20261107.json').read_text(encoding='utf-8'));nr={r[0]:r for r in records(NORMAL)};cr={r[0]:r for r in records(CURRENT)}
 report=dict(worldReference='Offline FK using the actual original 4d1c avatar; not observed engine skin matrices',worstClipWorldSteps=[],additiveTemporal=[],gameOrLibraryModified=False)
 def read(f,r):f.seek(r[2]);return f.read(r[7])
 def world(clip,tracks,time):
  local=list(unit.transforms)
  for i,h in enumerate(bones.hashes):
   t=WorldTransform(*(tr[i].evaluate(time) for tr in tracks));j=ui[h];local[j]=_compose_additive_local(unit.transforms[j],t) if clip.is_additive else t
  return _calculate_world_transforms(local,unit.parents)
 with NORMAL.open('rb') as nf,CURRENT.open('rb') as cf:
  for c in compare['jumpCandidates'][:12]:
   fid=int(c['id'],16);n=AnimationData.parse(read(nf,nr[fid]));a=AnimationData.parse(read(cf,cr[fid]));nt,at=_build_tracks(n),_build_tracks(a);t0,t1=c['worst']['fromMs'],c['worst']['toMs'];nw0,nw1=world(n,nt,t0),world(n,nt,t1);aw0,aw1=world(a,at,t0),world(a,at,t1)
   side=c['bone'][0];measure={}
   for name in [side+'_shoulder',side+'_elbow',side+'_hand',side+'_hand_twist']:
    i=ui[bones.hashes[bi[name]]];measure[name]=dict(normalWorldRotationStep=angle(nw0[i].rotation,nw1[i].rotation),currentWorldRotationStep=angle(aw0[i].rotation,aw1[i].rotation),normalPositionStep=math.dist(nw0[i].position,nw1[i].position),currentPositionStep=math.dist(aw0[i].position,aw1[i].position))
   report['worstClipWorldSteps'].append(dict(c,worldSteps=measure))
  for fid,nrow in nr.items():
   raw=read(nf,nrow);m=scan(raw)
   if not m['additive']:continue
   n=AnimationData.parse(raw);a=AnimationData.parse(read(cf,cr[fid]));nt,at=_build_tracks(n),_build_tracks(a)
   maximum=0;worst=None;lost_times=0;source_keys=current_keys=0;min_source_gap=1e9
   for i,name in ARM.items():
    st=sorted(set([0.,*[e.time for e in n.entries if e.is_rotation and e.bone==i]]));dt=sorted(set([0.,*[e.time for e in a.entries if e.is_rotation and e.bone==i]]));source_keys+=len(st);current_keys+=len(dt)
    if len(st)>1:min_source_gap=min(min_source_gap,min(y-x for x,y in zip(st,st[1:]) if y-x>0))
    lost_times+=sum(not any(abs(x-y)<.05 for y in dt) for x in st)
    # Isolate cadence alone: sample the NORMAL curve at CURRENT key times,
    # interpolate it back, then evaluate at original control points/midpoints.
    sampled=Track([(t,nt[1][i].evaluate(t)) for t in dt],quat_slerp)
    for t in sorted(set(st+[(x+y)*.5 for x,y in zip(st,st[1:])])):
     error=angle(nt[1][i].evaluate(t),sampled.evaluate(t))
     if error is not None and error>maximum:maximum=error;worst=dict(bone=name,timeMs=t,degrees=error)
   report['additiveTemporal'].append(dict(id=f'{fid:016x}',sourceControlTimesNotRetained=lost_times,normalKeys=source_keys,currentKeys=current_keys,minNormalGapMs=min_source_gap if min_source_gap<1e9 else None,cadenceOnlyMaxError=maximum,worst=worst))
 report['additiveCount']=len(report['additiveTemporal']);report['additiveTemporal'].sort(key=lambda x:x['cadenceOnlyMaxError'],reverse=True);report['additiveWithLostTimes']=sum(c['sourceControlTimesNotRetained']>0 for c in report['additiveTemporal']);report['additiveWithCadenceErrorOver1Degree']=sum(c['cadenceOnlyMaxError']>1 for c in report['additiveTemporal'])
 (OUT/'单骨架-卡顿候选及叠加采样-20261107.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('ADD',report['additiveCount'],report['additiveWithLostTimes'],report['additiveWithCadenceErrorOver1Degree']);print('TOP ADD',report['additiveTemporal'][:6]);print('WORLD',report['worstClipWorldSteps'][0])
 idx.close()
if __name__=='__main__':main()
