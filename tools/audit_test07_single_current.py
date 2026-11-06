"""Read-only audit of the freshly delivered test07 single-HD2 model/animations."""
import copy,hashlib,json,math,sqlite3,struct,sys,tomllib
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
import lz4
# Use installed Python 3.11 LZ4 for reading game bundles; no production module changes.
sys.modules['utils.lz4_311']=lz4
from anim_batch_mod.archive import PackageStore,ResourceIndex
from anim_batch_mod.binary import BinaryReader
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState,reverse_bits,decompress_position,decompress_rotation
from anim_batch_mod.math3d import quat_multiply,quat_inverse,quat_normalize
from anim_batch_mod.processor import ModConfig,_build_tracks,_calculate_world_transforms,modify_animation_with_world_compensation
from anim_batch_mod.single_skeleton import _validate_prepared_model
OUT=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';LIB=OUT/'test-library'
MODEL=LIB/'[单骨架模型]test07/vpk2patch';ANIM=LIB/'[单骨架动画](test07)'
ARMS=['l_clavicle','l_shoulder','l_elbow','l_hand','l_shoulder_twist','l_hand_twist','r_clavicle','r_shoulder','r_elbow','r_hand','r_shoulder_twist','r_hand_twist']
def angle(a,b):
 a=quat_normalize(a);b=quat_normalize(b)
 return math.degrees(2*math.acos(min(1,abs(sum(x*y for x,y in zip(a,b))))))
def records(path):
 with path.open('rb') as f:
  h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+32*nt)
  return [struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
def read(f,r):f.seek(r[2]);return f.read(r[7])
def unit_rows(path):
 with path.open('rb') as f:return [(r[0],UnitData.parse(read(f,r))) for r in records(path) if r[1]==UNIT_TYPE_ID]
def framezero(raw):
 r=BinaryReader(raw);unk,count=r.uint32(),r.uint32();duration=r.float32();size=r.uint32();nh,nh2=r.uint32(),r.uint32();r.read(8*(nh+nh2));r.uint16()
 nb=math.ceil(3*count/8);nb+=nb%2;flags=[]
 for v in r.read(nb):flags.extend((reverse_bits(v)>>s)&1 for s in reversed(range(8)))
 states=[]
 for i in range(count):
  cp,cq,cs=map(bool,flags[i*3:i*3+3]);p=decompress_position([r.uint16() for _ in range(3)]) if cp else r.vec3_float();q=decompress_rotation(r.uint32()) if cq else [r.float32() for _ in range(4)];s=decompress_position([r.uint16() for _ in range(3)]) if cs else r.vec3_float()
  states.append(AnimationBoneState(p,q,s,cp,cq,cs))
 return count,duration,any(s.scale[0]==0 for s in states)
def dump(report):
 (OUT/'test07-单骨架-手臂文件核查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 store=PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data'))
 idxpath=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
 index=ResourceIndex(store,idxpath);index.connection=sqlite3.connect(idxpath.resolve().as_uri()+'?mode=ro',uri=True)
 _,e=index.resolve(0x4d1c334d294dfa97,UNIT_TYPE_ID);native=UnitData.parse(e.toc_data)
 _,e=index.resolve(native.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(e.toc_data)
 named={h:n for h,n in zip(bones.hashes,bones.names)};ni={h:i for i,h in enumerate(native.name_hashes)};bi={n:i for i,n in enumerate(bones.names)}
 models=unit_rows(MODEL/'9ba626afa44a3aa3.patch_0');model=models[0][1];mi={h:i for i,h in enumerate(model.name_hashes)}
 config=ModConfig.load(ANIM/'single-config.toml');marker=json.loads((MODEL/'single-skeleton.json').read_text());_validate_prepared_model(MODEL,marker)
 report=dict(scope='read-only file and numerical diagnostics; not game visual acceptance',gameOrLibraryModified=False,gameTested=False,
 model=str(MODEL),animations=str(ANIM),pipelineVersion=marker['pipelineVersion'],modelScale=marker['modelScale'],bindCertificateValid=True,
 configCopiesEqual=(MODEL/'single-config.toml').read_bytes()==(ANIM/'single-config.toml').read_bytes(),nativeNodes=len(native.transforms),modelNodes=len(model.transforms),animationChannels=len(bones.names),ikChains=list(config.ik_chains),rotationCompensations=len(config.rotation_compensations),boneBindRows=[])
 for name in ARMS:
  h=bones.hashes[bi[name]];a=native.transforms[ni[h]];b=model.transforms[mi[h]];c=config.rotation_compensations.get(name,[0,0,0,1])
  report['boneBindRows'].append(dict(name=name,index=mi[h],nativePosition=a.position,modelPosition=b.position,offset=config.offsets.get(name),nativeRotation=a.rotation,modelRotation=b.rotation,compensation=c,
   restErrorCurrentLeftDegrees=angle(quat_multiply(c,a.rotation),b.rotation),restErrorRightDegrees=angle(quat_multiply(a.rotation,c),b.rotation)))
 # Neutral native rest -> prepared model rest is an independent pipeline invariant.
 def neutral(additive):
  states=[]
  for h in bones.hashes:
   t=native.transforms[ni[h]]
   states.append(AnimationBoneState([0,0,0] if additive else list(t.position),[0,0,0,1] if additive else list(t.rotation),[0,0,0] if additive else list(t.scale)))
  return AnimationData(initial_bone_states=states,animation_length=0.0,is_additive=additive)
 rest=neutral(False);modify_animation_with_world_compensation(rest,bones,native,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=True,apply_ik_correction=True)
 delta=neutral(True);modify_animation_with_world_compensation(delta,bones,native,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=True,apply_ik_correction=True)
 rt,dt=_build_tracks(rest),_build_tracks(delta)
 report['neutralProbe']=[dict(name=n,neutralRestOutputErrorDegrees=angle(rt[1][bi[n]].evaluate(0),model.transforms[mi[bones.hashes[bi[n]]]].rotation),zeroAdditiveInjectedDegrees=angle(dt[1][bi[n]].evaluate(0),[0,0,0,1]),zeroAdditivePositionLength=math.sqrt(sum(v*v for v in dt[0][bi[n]].evaluate(0)))) for n in ARMS]
 # Decode weights of the actual GPU triangle vertices using existing production decoder reports.
 skins=json.loads((OUT/'test07-单骨架-来源蒙皮核查.json').read_text())['rows'];report['skin'] = []
 for row in skins:
  weighted=[]
  for w in row['weightedNodes']:
   name=named.get(w['hash'],'not-in-animation-channels')
   if name in ARMS or name=='not-in-animation-channels':weighted.append(dict(w,name=name,parent=dict(models)[int(row['resource'],16)].parents[w['index']]))
  report['skin'].append(dict(resource=row['resource'],nodeCount=row['nodeCount'],armOrHelperWeights=weighted))
 path=ANIM/'9ba626afa44a3aa3.patch_0';rows=records(path);metadata=[]
 with path.open('rb') as f:
  for r in rows:
   f.seek(r[2]);count,duration,add=framezero(f.read(min(r[7],12000)))
   metadata.append(dict(id=f'{r[0]:016x}',channelCount=count,duration=duration,additive=add,bytes=r[7]))
 report['animationInventory']=dict(count=len(rows),counts=dict(Counter(m['channelCount'] for m in metadata)),additive=sum(m['additive'] for m in metadata),nonAdditive=sum(not m['additive'] for m in metadata),allAnimationResources=all(r[1]==ANIMATION_TYPE_ID for r in rows),durationRange=[min(m['duration'] for m in metadata),max(m['duration'] for m in metadata)])
 report['deployment']=[]
 for p in sorted(store.game_data.glob('*.patch_*')):
  if p.suffix.rsplit('_',1)[-1].isdigit():report['deployment'].append(dict(patch=p.name,path=str(p.resolve()),types=dict(Counter(f'{r[1]:016x}' for r in records(p)))))
 dump(report);print(json.dumps({k:report[k] for k in ['bindCertificateValid','configCopiesEqual','ikChains','animationInventory','neutralProbe']},ensure_ascii=False),flush=True)
 # Sample real additive and absolute clips evenly across resource-ID order; no rebuilding.
 chosen=[]
 for flag in [True,False]:
  seq=[m for m in metadata if m['additive']==flag]
  chosen.extend(seq[int((len(seq)-1)*i/7)] for i in range(8))
 byid={r[0]:r for r in rows};report['realClipSamples']=[]
 with path.open('rb') as f:
  for m in chosen:
   fid=int(m['id'],16);out=AnimationData.parse(read(f,byid[fid]));_,entry=index.resolve(fid,ANIMATION_TYPE_ID);original=AnimationData.parse(entry.toc_data)
   ot,gt=_build_tracks(original),_build_tracks(out);values=[]
   times=sorted(set([min(16.6667,original.animation_length*1000),original.animation_length*500,original.animation_length*1000]))
   for n in ARMS:
    i=bi[n];c=config.rotation_compensations.get(n,[0,0,0,1]);a=native.transforms[ni[bones.hashes[i]]].rotation
    injected=quat_multiply(quat_inverse(a),quat_multiply(c,a)) if original.is_additive else c
    for t in times:
     oq,gq=ot[1][i].evaluate(t),gt[1][i].evaluate(t)
     values.append(dict(name=n,timeMs=t,originalVsOutputDegrees=angle(oq,gq),residualCurrentLeftFormulaDegrees=angle(quat_multiply(injected,oq),gq),originalDeltaDegrees=angle(oq,[0,0,0,1]) if original.is_additive else None))
   report['realClipSamples'].append(dict(m,durationOriginal=original.animation_length,additiveOriginal=original.is_additive,rows=values))
   if not original.is_additive:
    from anim_batch_mod.processor import WorldTransform
    from anim_batch_mod.math3d import vec_sub
    def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    def vector_angle(a,b):
     na=math.sqrt(sum(v*v for v in a));nb=math.sqrt(sum(v*v for v in b))
     return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/(na*nb))))) if na*nb>1e-10 else None
    geometry=[];continuity=[]
    for side in ['l','r']:
     names=[side+'_shoulder',side+'_elbow',side+'_hand'];hashes=[bones.hashes[bi[n]] for n in names]
     before=None;maximum=[0,0,0];worst=None;flips=0;max_bend_difference=0;max_plane_difference=0
     for frame in range(math.ceil(original.animation_length*60)+1):
      t=min(original.animation_length*1000,frame*1000/60)
      local_original=list(native.transforms);local_output=list(model.transforms)
      for i,h in enumerate(bones.hashes):
       local_original[ni[h]]=WorldTransform(*(tr[i].evaluate(t) for tr in ot))
       local_output[mi[h]]=WorldTransform(*(tr[i].evaluate(t) for tr in gt))
      nw=_calculate_world_transforms(local_original,native.parents,{ni[h] for h in hashes});mw=_calculate_world_transforms(local_output,model.parents,{mi[h] for h in hashes})
      np=[nw[ni[h]].position for h in hashes];mp=[mw[mi[h]].position for h in hashes]
      nv=[vec_sub(np[1],np[0]),vec_sub(np[2],np[1])];mv=[vec_sub(mp[1],mp[0]),vec_sub(mp[2],mp[1])]
      nb=vector_angle(*nv);mb=vector_angle(*mv);plane=vector_angle(cross(*nv),cross(*mv));diff=abs(nb-mb)
      max_bend_difference=max(max_bend_difference,diff)
      if plane is not None and nb>20 and mb>20:
       max_plane_difference=max(max_plane_difference,plane)
       if plane>120:flips+=1
      if worst is None or diff>worst['bendDifferenceDegrees']:worst=dict(frame=frame,timeMs=t,nativeBendDegrees=nb,modelBendDegrees=mb,bendDifferenceDegrees=diff,bendPlaneDifferenceDegrees=plane,nativePoints=np,modelPoints=mp)
      qs=[gt[1][bi[n]].evaluate(t) for n in names]
      if before:
       for i in range(3):maximum[i]=max(maximum[i],angle(before[i],qs[i]))
      before=qs
     geometry.append(dict(side=side,maxBendDifferenceDegrees=max_bend_difference,maxPlaneDifferenceWithBothBentDegrees=max_plane_difference,bendPlaneFlippedFrames=flips,worst=worst))
     continuity.append(dict(side=side,maxFrameRotationDegrees=dict(zip(names,maximum))))
    report['realClipSamples'][-1]['armGeometry']=geometry;report['realClipSamples'][-1]['continuity60Hz']=continuity
   dump(report);print('sample',m['id'],'additive',m['additive'],'max-left-formula-residual',round(max(v['residualCurrentLeftFormulaDegrees'] for v in values),5),flush=True)
 index.close()
 report['diagnosticStatus']='DIAGNOSTICS_COMPLETE_NOT_VISUAL_ACCEPTANCE';dump(report)
if __name__=='__main__':main()


