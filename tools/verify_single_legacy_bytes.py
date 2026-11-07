"""Read-only full byte regression for the untouched legacy/default batch route."""
import copy,json,sqlite3,sys
from pathlib import Path
from collections import deque
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_single_elbow_torso as a
from audit_single_against_normal import NORMAL

def compare(raw,gold,unit,bones,config):
 clip=a.AnimationData.parse(raw)
 result=a.p.modify_animation_with_world_compensation(clip,bones,unit,config,allow_additive=True,apply_offsets_to_additive=False,apply_rotate_multipliers=True,apply_rotation_compensations=False,apply_ik_correction=True,preserve_hand_bend_frame=False,preserve_source_key_times=True)
 return (raw if result.unchanged else clip.to_bytes())==gold

def main():
 index=a.ResourceIndex(a.PackageStore(Path('E:/Steam/steamapps/common/Helldivers 2/data')));db=a.ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3';index.connection=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True)
 _,e=index.resolve(a.single.REFERENCE_UNIT,a.UNIT_TYPE_ID);unit=a.UnitData.parse(e.toc_data);_,e=index.resolve(unit.bones_ref,a.BONE_TYPE_ID);bones=a.BonesData.parse(e.toc_data);cfg=a.p.ModConfig.load(a.OUT/'config.toml')
 report=dict(total=0,byteExact=0,mismatches=[],readOnly=True)
 rows=a.records(NORMAL);pending=deque();items=iter(rows)
 with NORMAL.open('rb') as f,ProcessPoolExecutor(max_workers=4) as executor:
  def submit():
   r=next(items,None)
   if r is None:return False
   _,entry=index.resolve(r[0],a.ANIMATION_TYPE_ID);f.seek(r[2]);pending.append((r[0],executor.submit(compare,bytes(entry.toc_data),f.read(r[7]),unit,bones,cfg)));return True
  for _ in range(8):
   if not submit():break
  while pending:
   fid,future=pending.popleft();same=future.result();report['total']+=1;report['byteExact']+=same
   if not same:report['mismatches'].append(f'{fid:016x}')
   if report['total']%100==0:print(report['total'],report['byteExact'],flush=True)
   submit()
 index.close();report['status']='PASS' if report['total']==report['byteExact']==3180 else 'FAIL'
 (a.DEST/'legacy-byte-regression.json').write_text(json.dumps(report,indent=2),encoding='utf-8');assert report['status']=='PASS'
if __name__=='__main__':main()
