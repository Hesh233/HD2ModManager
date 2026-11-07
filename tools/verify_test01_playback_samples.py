"""Sample validation for test01 native playback clocks, tail pose, and source controls."""
import copy,json,struct,sqlite3,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
import lz4;sys.modules['utils.lz4_311']=lz4
from anim_batch_mod import processor as p,single_skeleton as s
from anim_batch_mod.archive import ResourceIndex,PackageStore
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from audit_single_against_normal import OUT as INSTALL,angle
OUT=ROOT/'outputs/test01-single-jitter-20261107';PACK=INSTALL/'test-library/[单骨架动画](test01)/9ba626afa44a3aa3.patch_0'
cfg=p.ModConfig.load(PACK.parent/'single-config.toml')
idx=ResourceIndex(PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));db=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';idx.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
_,e=idx.resolve(s.REFERENCE_UNIT,UNIT_TYPE_ID);u=UnitData.parse(e.toc_data);_,e=idx.resolve(u.bones_ref,BONE_TYPE_ID);b=BonesData.parse(e.toc_data)
timing=json.loads((OUT/'timing.json').read_text(encoding='utf-8'));ids=[int(r['id'],16) for r in sorted(timing['samples'],key=lambda r:r['current']['tailExcess'],reverse=True)[:10]]+ [int(r['id'],16) for r in timing['samples'][:8]]
ids+= [0x0004fd6ec81ff21c,0x258c6e03a38bbeb2,0x003ad49517e19bec];report={'samples':[]}
for fid in dict.fromkeys(ids):
 _,e=idx.resolve(fid,ANIMATION_TYPE_ID);src=AnimationData.parse(e.toc_data);out=copy.deepcopy(src)
 st=p.modify_animation_with_world_compensation(out,b,u,cfg,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True,preserve_unmodified_channels=True,source_arm_constraints=True,preserve_playback_timing=True)
 decoded=AnimationData.parse(out.to_bytes());new_times=[e.time for e in decoded.entries if e.is_position or e.is_rotation];source_times=[e.time for e in src.entries if e.is_position or e.is_rotation]
 duration=src.animation_length*1000;sourceTail=max(source_times,default=duration)-duration;tail=max(new_times,default=duration)-duration
 assert struct.pack('<f',src.animation_length)==struct.pack('<f',decoded.animation_length)
 assert tail<=max(sourceTail,0)+.001,(hex(fid),tail,sourceTail)
 names=['boss','hips','spine1','spine2','chest','neck','head'];ot,nt=p._build_tracks(src),p._build_tracks(decoded)
 poserror=0.;rotationerror=0.
 for name in names:
  i=b.names.index(name);offset=[0,0,0] if src.is_additive else cfg.offsets.get(name,[0,0,0]);mult=1. if src.is_additive else cfg.distance_multipliers.get(name,1.)
  times=[0.,duration,*[e.time for e in src.entries if e.is_position and e.bone==i]]
  for t in times:
   expect=[(x+y)*mult for x,y in zip(ot[0][i].evaluate(t),offset)];poserror=max(poserror,math.dist(expect,nt[0][i].evaluate(t)))
   rotationerror=max(rotationerror,angle(ot[1][i].evaluate(t),nt[1][i].evaluate(t)))
 row=dict(id=f'{fid:016x}',durationMs=duration,newTailExcessMs=tail,nativeTailExcessMs=sourceTail,bodyPositionControlError=poserror,bodyRotationError=rotationerror,ikEvaluations=st.ik_evaluations)
 assert rotationerror<.0001
 assert poserror<1e-4,(hex(fid),poserror)
 report['samples'].append(row);print(row,flush=True)
idx.close();report['status']='SAMPLE_PLAYBACK_VERIFIED_GAME_PENDING';(OUT/'playback-samples.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
