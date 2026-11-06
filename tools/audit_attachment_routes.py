"""Offline QA for the actual published GUI services; no deployment/game writes."""
import sys,json,math,copy,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'outputs/native-fix-20261103/test-runtime'))
from anim_batch_mod.single_skeleton import model_units
from anim_batch_mod.archive import PackageStore,ResourceIndex,TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.native_skeleton import bone_name_hash,row_pose
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,ModConfig,modify_animation_with_world_compensation
from anim_batch_mod.attachment_skeleton import source_attachment_drivers

def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def archive(p):
 p=Path(p);return TocArchive.parse_parts(*(Path(str(p)+s).read_bytes() for s in ('','.gpu_resources','.stream')))
def audit(folder,game_data):
 folder=Path(folder);info=load(folder/'import-regression.json');single=info['singleHd2Skeleton']
 model=Path(info['model']);payload=model/'vpk2patch';report=load(folder/'animations/build-report.json')
 assert report['status']=='complete' and len(report['animations'])==info['samples']
 patch=next((folder/'animations/runtime').glob('*.patch_2'));out=archive(patch)
 store=PackageStore(Path(game_data));index=ResourceIndex(store,folder/'audit-resources.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID});checks=0;max_error=0.
 try:
  index.load_or_build();_,ue=index.resolve(0x4d1c334d294dfa97,UNIT_TYPE_ID);original_unit=UnitData.parse(ue.toc_data)
  _,be=index.resolve(original_unit.bones_ref,BONE_TYPE_ID);native_bones=BonesData.parse(be.toc_data)
  if single:
   assert not (payload/'source-skeleton.json').exists() and not (folder/'attachment').exists()
   marker=load(payload/'single-skeleton.json');assert marker['skeleton']=='hd2' and not marker['sourceRigRetained'] and not marker['attachmentLua']
   assert not out.entries_of_type(UNIT_TYPE_ID) and not out.entries_of_type(BONE_TYPE_ID)
   cfg=ModConfig.load(payload/'single-config.toml')
   for e in out.entries_of_type(ANIMATION_TYPE_ID):
    _,raw=index.resolve(e.file_id,ANIMATION_TYPE_ID);a=AnimationData.parse(raw.toc_data);o=marker['options']
    modify_animation_with_world_compensation(a,native_bones,original_unit,cfg,allow_additive=o['allow_additive'],apply_offsets_to_additive=False,
      apply_rotate_multipliers=o['rotate_multipliers'],apply_rotation_compensations=o['rotation_compensation'],apply_ik_correction=o['ik_correction'])
    assert bytes(e.toc_data)==a.to_bytes(),'Not byte-identical to original batch processor'
    assert len(a.initial_bone_states)==len(native_bones.names);checks+=1
  else:
   manifest=load(payload/'source-skeleton.json');assert len(manifest['sourceAttachmentShadows'])==21
   assert tomllib_load(folder/'animations/config.toml')['native_skeleton']['attachment_swap'] is False
   u=UnitData.parse(out.entries_of_type(UNIT_TYPE_ID)[0].toc_data);b=BonesData.parse(out.entries_of_type(BONE_TYPE_ID)[0].toc_data)
   # Verify native mounts/all original channels, not just file/name/hash exchanges.
   for e in out.entries_of_type(ANIMATION_TYPE_ID):
    _,raw=index.resolve(e.file_id,ANIMATION_TYPE_ID);old=AnimationData.parse(raw.toc_data);new=AnimationData.parse(e.toc_data)
    times=sorted({0.,*(r.time for r in old.entries if r.is_position or r.is_rotation or r.is_scale)})
    times=times[:2]+times[len(times)//2:len(times)//2+2]+times[-2:]
    before,after=_build_tracks(old),_build_tracks(new)
    for t in times:
     for ci in range(len(native_bones.names)):
      for k in range(3):
       a,c=before[k][ci].evaluate(t),after[k][ci].evaluate(t)
       error=min(math.dist(a,c),math.dist(a,[-v for v in c])) if k==1 else math.dist(a,c)
       max_error=max(max_error,error);checks+=1
   assert max_error<1e-4,('HD2 paths were changed/swapped',max_error)
   for _,mu in model_units(payload):
    worlds=_calculate_world_transforms(mu.transforms,mu.parents)
    for row in manifest['sourceAttachmentShadows']:
     pos=worlds[mu.name_hashes.index(row['hash'])].position;expected=row_pose(row['worldMatrix']).position
     assert math.dist(pos,expected)<1e-4;checks+=1
   profile=load(next((folder/'attachment').rglob('attachment-profile.json')))
   discovery=load(next((folder/'attachment').rglob('attachment-build-report.json'))).get('modelDiscovery')
   if info.get('targetArchive'):
    assert discovery and discovery['sourceOwnershipGate'] and discovery['targetBodies']
    assert set(discovery['targetBodies']).issubset(profile['models'])
    auxiliary={r['resource'] for r in discovery['skippedUnits'] if r['reason']=='non_source_auxiliary'}
    assert not auxiliary.intersection(profile['models']), 'Native auxiliaries were registered as Source models'
    checks += len(discovery['targetBodies'])+len(auxiliary)
   assert profile['runtimePolicyVersion']=='b23-1.0.8' and profile['attachmentMode']=='source-lua-native-hd2-v1'
   assert profile['sourceRightMount']['hash']==next(r['hash'] for r in manifest['sourceAttachmentShadows'] if r['standardName']=='attach_hand_r')
   assert set(r['node']['name'] for r in profile['attachments'])|{'attach_hand_r'}==set(source_attachment_drivers())
   assert all('sourceMount' in r for r in profile['attachments'])
   for n in [profile['sourceRightMount']]+[r['sourceMount'] for r in profile['attachments']]:
    assert n['hash']==bone_name_hash(n['name']);checks+=1
   from lupa.lua51 import LuaRuntime
   vm=LuaRuntime(unpack_returned_tuples=True)
   lua_dir=next(p for p in folder.iterdir() if p.is_dir() and p.name.startswith('[骨骼挂点修正]'))
   lua_patch=archive(next(lua_dir.glob('*.patch_4')))
   code=bytes(next(iter(lua_patch.entries.values())).toc_data)[8:].decode('utf-8').rstrip('\x00')
   assert "VERSION = '1.0.9'" in code
   valid,error=vm.eval('function(s) local f,e=loadstring(s);return f~=nil,e end')(code);assert valid,error
  result=dict(status='PASS',singleHd2Skeleton=single,checks=checks,maxNativeChannelError=max_error,gameTested=False,sampleOnly=True)
  (folder/'route-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result));return result
 finally:index.close()
def tomllib_load(p):
 import tomllib
 return tomllib.loads(Path(p).read_text(encoding='utf-8-sig'))
if __name__=='__main__':
 for f in sys.argv[2:]:audit(f,sys.argv[1])
