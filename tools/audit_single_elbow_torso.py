"""Read-only current single-rig bind / arm / torso diagnostic (no game deployment)."""
import argparse,copy,hashlib,json,math,sqlite3,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
import lz4
sys.modules['utils.lz4_311']=lz4
from anim_batch_mod import single_skeleton as single,processor as p
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.math3d import quat_rotate,quat_inverse_rotate,quat_multiply,vec_sub
from audit_single_against_normal import records,angle
OUT=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
MODEL=OUT/'test-library/[单骨架模型]test07/vpk2patch'
PACK=OUT/'test-library/[单骨架动画](test07)/9ba626afa44a3aa3.patch_0'
DEST=ROOT/'outputs/single-rig-elbow-torso-audit-20261107'
TORSO=['boss','hips','spine1','spine2','chest','neck','head','weapon_aim','attach_weapon']
ARMS=[s+'_'+n for s in ['l','r'] for n in ['clavicle','shoulder','elbow','hand','shoulder_twist','hand_twist']]
def vangle(a,b):
 d=math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
 return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/d)))) if d>1e-12 else None
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def state(unit,bones,tracks,t):
 local=copy.deepcopy(unit.transforms);inds={h:i for i,h in enumerate(unit.name_hashes)}
 for i,h in enumerate(bones.hashes):
  j=inds[h];tr=p.WorldTransform(*(track[i].evaluate(t) for track in tracks))
  local[j]=p._compose_additive_local(unit.transforms[j],tr) if tracks.additive else tr
 return local,p._calculate_world_transforms(local,unit.parents)
class Tracks(tuple):pass
def tracks(a):
 tr=Tracks(p._build_tracks(a));tr.additive=a.is_additive;return tr

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--all',action='store_true');args=ap.parse_args()
 DEST.mkdir(exist_ok=True,parents=True)
 report=dict(status='RUNNING',model=str(MODEL),animation=str(PACK),readOnlyInputs=True,gameDeployment=False)
 marker=json.loads((PACK.parent/'single-skeleton.json').read_text(encoding='utf-8-sig'))
 single._validate_prepared_model(MODEL,marker)
 report['currentManifest']={k:marker[k] for k in ['pipelineVersion','modelScale','configSha256','options','bindSha256']}
 units=list(single.model_units(MODEL));model=units[0][1]
 index=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')))
 db=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
 index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
 _,e=index.resolve(single.REFERENCE_UNIT,UNIT_TYPE_ID);native=UnitData.parse(e.toc_data)
 _,e=index.resolve(native.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(e.toc_data)
 bi={n:i for i,n in enumerate(bones.names)};ni={h:i for i,h in enumerate(native.name_hashes)};mi={h:i for i,h in enumerate(model.name_hashes)}
 config=p.ModConfig.load(PACK.parent/'single-config.toml')
 n0=p._calculate_world_transforms(native.transforms,native.parents);m0=p._calculate_world_transforms(model.transforms,model.parents)
 report['bindRows']=[]
 for name in TORSO+ARMS:
  if name not in bi:continue
  h=bones.hashes[bi[name]];nt=native.transforms[ni[h]];mt=model.transforms[mi[h]]
  row=dict(name=name,nativeLocalPosition=nt.position,modelLocalPosition=mt.position,localDirectionChangeDegrees=vangle(nt.position,mt.position),localRotationDifferenceDegrees=angle(nt.rotation,mt.rotation),worldRotationDifferenceDegrees=angle(n0[ni[h]].rotation,m0[mi[h]].rotation),positionOffset=config.offsets.get(name),nativeLength=math.dist(nt.position,[0,0,0]),modelLength=math.dist(mt.position,[0,0,0]))
  report['bindRows'].append(row)
  print('bind',name,'direction',row['localDirectionChangeDegrees'],'rotation',row['localRotationDifferenceDegrees'],'lengths',row['nativeLength'],row['modelLength'],flush=True)
 rows={r[0]:r for r in records(PACK) if r[1]==ANIMATION_TYPE_ID}
 chosen=[int(c['id'],16) for c in json.loads((OUT/'test07-单骨架-手臂文件核查.json').read_text(encoding='utf-8'))['realClipSamples']]
 chosen+= [3542481557377973498,11623262177752411465,2372646189065085873,7487460257401496141,2079987957316695397]
 ids=sorted(rows) if args.all else list(dict.fromkeys(chosen))
 report['samples']=[]
 def save(): (DEST/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 save()
 with PACK.open('rb') as f:
  for k,fid in enumerate(ids):
   if fid not in rows:continue
   r=rows[fid];f.seek(r[2]);raw=f.read(r[7]);out=AnimationData.parse(raw)
   _,e=index.resolve(fid,ANIMATION_TYPE_ID);original=AnimationData.parse(e.toc_data)
   ot,gt=tracks(original),tracks(out)
   times=sorted(set([0.,original.animation_length*1000,*p._build_bake_times(p._last_transform_time(original)),*(float(e.time) for e in original.entries if e.is_rotation and bones.names[e.bone] in TORSO)]))
   sample=dict(id=f'{fid:016x}',additive=original.is_additive,sourceByteExact=raw==e.toc_data,torso={},arms={})
   for name in TORSO:
    if name not in bi:continue
    i=bi[name];h=bones.hashes[i]
    maximum=max((angle(ot[1][i].evaluate(t),gt[1][i].evaluate(t)),t) for t in times)
    sample['torso'][name]=dict(maxLocalRotationDifferenceDegrees=maximum[0],timeMs=maximum[1])
   if not args.all or fid in chosen:
    for side in ['l','r']:
     hashes=[bones.hashes[bi[side+'_'+n]] for n in ['shoulder','elbow','hand']]
     arm=dict(maxBendDifferenceDegrees=0,maxPlaneDifferenceDegrees=0,maxRootFramePlaneDifferenceDegrees=0,maxElbowMovement=0,maxHandMovement=0,maxRootRotationDifferenceDegrees=0,worst=None)
     for t in times:
      nl,nw=state(native,bones,ot,t);ml,mw=state(model,bones,gt,t)
      np=[nw[ni[h]].position for h in hashes];mp=[mw[mi[h]].position for h in hashes]
      nv=[vec_sub(np[1],np[0]),vec_sub(np[2],np[1])];mv=[vec_sub(mp[1],mp[0]),vec_sub(mp[2],mp[1])]
      nb,mb=vangle(*nv),vangle(*mv);diff=abs(nb-mb)
      plane=vangle(cross(*nv),cross(*mv))
      rootplane=vangle(quat_inverse_rotate(nw[ni[hashes[0]]].rotation,cross(*nv)),quat_inverse_rotate(mw[mi[hashes[0]]].rotation,cross(*mv)))
      if diff>arm['maxBendDifferenceDegrees']:
       arm['maxBendDifferenceDegrees']=diff;arm['worst']=dict(timeMs=t,nativeBendDegrees=nb,modelBendDegrees=mb,nativePoints=np,modelPoints=mp)
      if nb>20 and mb>20 and plane is not None:
       arm['maxPlaneDifferenceDegrees']=max(arm['maxPlaneDifferenceDegrees'],plane)
       arm['maxRootFramePlaneDifferenceDegrees']=max(arm['maxRootFramePlaneDifferenceDegrees'],rootplane or 0)
      arm['maxElbowMovement']=max(arm['maxElbowMovement'],math.dist(np[1],mp[1]))
      arm['maxHandMovement']=max(arm['maxHandMovement'],math.dist(np[2],mp[2]))
      arm['maxRootRotationDifferenceDegrees']=max(arm['maxRootRotationDifferenceDegrees'],angle(nw[ni[hashes[0]]].rotation,mw[mi[hashes[0]]].rotation))
     sample['arms'][side]=arm
   report['samples'].append(sample)
   if k%25==0 or not args.all:
    save();print('clip',sample['id'],'additive',sample['additive'],'bodymax',max(v['maxLocalRotationDifferenceDegrees'] for v in sample['torso'].values()),'armbend',{s:round(a['maxBendDifferenceDegrees'],3) for s,a in sample['arms'].items()},flush=True)
 index.close();report['status']='OFFLINE_DIAGNOSTICS_COMPLETE_NOT_GAME_VERIFIED';report['clips']=len(report['samples'])
 report['bodyMax']={n:max((dict(id=s['id'],**s['torso'][n]) for s in report['samples'] if n in s['torso']),key=lambda r:r['maxLocalRotationDifferenceDegrees']) for n in TORSO if n in bi}
 save();print(json.dumps(report['bodyMax'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
