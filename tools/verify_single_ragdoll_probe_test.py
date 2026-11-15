"""Read-only observer regression against real 139-node model, synthetic stretch and opaque IDs."""
from pathlib import Path
import sys,json,zipfile,struct,hashlib,re
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));import build_detailed_grip_test as b
import build_single_ragdoll_probe_test as builder
OUT,VERSION=builder.OUT,builder.VERSION
from prepare_native_v31_b23 import lua
from lupa.lua51 import LuaRuntime
from verify_test04_lua_entry import exercise

def run(source,mapped=False,with_refs=False,guarded=False):
 p=b.load(OUT/'single-observer-profile.json');rid='540784804ddf0003';spec=p['resources'][rid]
 vm=LuaRuntime(unpack_returned_tuples=True)
 live_rid='34a40a5ae7a392ba' if mapped else rid
 if mapped:
  if builder.REVISION=='s3' and not guarded:p=dict(p,warmupSeconds=0)
  assert live_rid in p['resources'] and p['resources'][live_rid]['sourceResource']==rid
  spec=dict(spec,sourceResource=rid,deployedAlias=True)
 else:
  p=dict(p,motionSeconds=None,fullSnapshots=False,captureNames=None,compactPoseRecords=False,requireModelToSample=False,missionOnly=False,renderOnly=False,warmupSeconds=None,strictPoseLayout=False)
 selected={live_rid:spec}
 if with_refs:selected['4d1c334d294dfa97']=p['resources']['4d1c334d294dfa97']
 vm.globals().withReferences=with_refs;vm.globals().guarded=guarded
 vm.globals().profile=vm.table_from(dict(p,resources=selected),recursive=True);vm.globals().probe=vm.execute(source)
 raw=next(raw for id,t,raw in b.resources(ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/test-library/[单骨架模型]test01/vpk2patch/9ba626afa44a3aa3.patch_0') if t==b.UNIT_TYPE_ID and f'{id:016x}'==rid)
 unit=b.UnitData.parse(raw)
 vm.globals().fixture=vm.table_from(dict(resource=live_rid,locals=b.matrices(unit),parents=unit.parents,nodes=spec['nodes'],count=spec['count']),recursive=True)
 return vm.execute(r'''
local function cp(v)local r={};for k,x in pairs(v)do r[k]=type(x)=='table'and cp(x)or x end;return r end
local u={alive=true,resource=fixture.resource,count=fixture.count,locals=cp(fixture.locals),nodes=fixture.nodes,parents=fixture.parents,names={},cache={}}
for _,n in ipairs(u.nodes)do if n.name then u.names[n.name]=n.index+1 end end
local function mul(a,b)local r={};for c=0,2 do for i=1,3 do local v=0;for k=0,2 do v=v+a[k*3+i]*b[c*3+k+1]end;r[c*3+i]=v end end;for i=1,3 do r[i+9]=a[i+9]+a[i]*b[10]+a[i+3]*b[11]+a[i+6]*b[12]end;return r end
local function refresh()u.cache={};local function node(i)if u.cache[i]then return u.cache[i]end;local p=u.parents[i];u.cache[i]=p and mul(node(p+1),u.locals[i])or cp(u.locals[i]);return u.cache[i]end;for i=1,u.count do node(i)end end
refresh();local original=cp(u.locals);local scratch={};local function tmp(v)for k in pairs(scratch)do scratch[k]=nil end;if v then for i,x in ipairs(v)do scratch[i]=x end end;return scratch end
local tokens={};local invalid=0;local reads=0;local mutations=0;local unsafeAnimatorCalls=0;local nativeNoFsmModeCalls=0;local hasFSM=true;local mode='transform';local logs={}
local S={Application={},World={},Unit={},IdString64={},Matrix4x4={}};local U=S.Unit;S.Matrix4x4.to_elements=function(m)return unpack(m)end
S.Application.worlds=function()return {1}end;S.Application.string_to_id32=function(name)local token={};tokens[token]=name;return token end
local refs={};if withReferences then for i=1,25 do refs[#refs+1]={alive=true,resource='4d1c334d294dfa97'}end end
S.World.units=function()local rows={};for _,ref in ipairs(refs)do rows[#rows+1]=ref end;rows[#rows+1]=u;rows[#rows+1]={alive=true,resource='ffffffffffffffff'};return rows end
S.IdString64.to_hex=function(x)tmp();return x end
U.alive=function(x)return x.alive end;U.resource_name=function(x)tmp();return x.resource end;U.num_scene_graph_items=function(x)tmp();return x==u and u.count or 107 end
U.has_node=function(x,id)tmp();if not tokens[id]then invalid=invalid+1;error('raw numeric id')end;return x==u and u.names[tokens[id]]~=nil end
U.node=function(_,id)tmp();if not tokens[id]then invalid=invalid+1;error('raw numeric id')end;return u.names[tokens[id]]end
U.local_pose=function(_,i)assert(u.alive and i<=u.count,'read outside live rig');reads=reads+1;return tmp(u.locals[i])end
U.world_pose=function(_,i)assert(u.alive and i<=u.count,'read outside live rig');reads=reads+1;return tmp(u.cache[i])end
U.scene_graph_parent=function(_,i)tmp();if u.names['l_hand']==i then return nil end;local p=u.parents[i];return p and p+1 or 0 end
U.has_animation_state_machine=function(x)tmp();if x==u then unsafeAnimatorCalls=unsafeAnimatorCalls+1;error('model has no animation object')end;return hasFSM end;U.animation_bone_mode=function(x)tmp();if x==u then unsafeAnimatorCalls=unsafeAnimatorCalls+1;error('native-style NULL animator read at 0x164')end;if not hasFSM then nativeNoFsmModeCalls=nativeNoFsmModeCalls+1;error('no native FSM')end;return mode end
U.set_local_pose=function()mutations=mutations+1;error('observer wrote a bone')end;S.World.update_unit=function()mutations=mutations+1;error('observer refreshed graph')end
local mission=true;local rt=probe.new(S,profile,function(line)logs[#logs+1]=line end,{inMission=function()return mission end})
if guarded then
 mission=false;rt:tick('update',0);rt:tick('render',0);assert(reads==0,'S3 read poses on ship/loading')
 mission=true;rt:tick('update',.1);assert(reads==0,'S3 update sampled poses')
 rt:tick('render',.1);assert(reads==0,'S3 new instance sampled before warmup')
 profile.warmupSeconds=0
end
rt:tick('update',1);rt:tick('render',1);rt:tick('render',1.04);rt:tick('render',1.08)
local root=cp(u.cache[1]);for _,m in ipairs(u.cache)do for j=10,12 do m[j]=root[j]+(m[j]-root[j])*1.4 end end
hasFSM=false;mode='ignore';rt:tick('update',2);rt:tick('render',2)
u.count=100;for k,i in pairs(u.names)do if i>100 then u.names[k]=nil end end;rt:tick('render',3)
u.alive=false;local oldReads=reads;rt:tick('render',4);assert(reads==oldReads,'observer read dead actor');rt:stop();rt:stop()
assert(mutations==0 and invalid==0,'observer mutated or passed raw ID')
for i,m in ipairs(u.locals)do for j,x in ipairs(m)do assert(x==original[i][j],'observer altered local pose')end end
return {logs=logs,reads=reads,mutations=mutations,invalidIds=invalid,errors=rt.errors,unsafeAnimatorCalls=unsafeAnimatorCalls,nativeNoFsmModeCalls=nativeNoFsmModeCalls}
''')

def validate(result):
 rows=[json.loads(v) for v in result['logs'].values()];poses=[r for r in rows if r['event']=='single_ragdoll_pose'];assert len(poses)==5 and result['errors']==0
 normal=poses[0];stretch=poses[2];assert normal['actualCount']==139 and stretch['boneMode']['available'] is False and stretch['animationState']['available'] is False
 assert result['unsafeAnimatorCalls']==0 and result['nativeNoFsmModeCalls']==0,'model/native without FSM animator queried'
 assert all(n.get('available') for n in normal['poses']);assert any(n.get('parentInterpretation')=='exported_parent_fallback_not_solver_parent' for n in normal['poses'])
 assert max(n.get('worldVsLocalParentFK',0) for n in normal['poses'])<1e-6,'normal matrices borrowed/corrupted'
 assert max(n.get('worldVsLocalParentFK',0) for n in stretch['poses'])>.01,'synthetic physics stretch not observed'
 assert any(not n.get('available') for n in poses[-1]['poses']),'removed nodes falsely available'
 assert sum(r['event']=='complete' for r in rows)==1
 return dict(samples=len(poses),nodeReads=result['reads'],poseWrites=result['mutations'],opaqueIdErrors=result['invalidIds'],normalAndSyntheticStretch=True,missingParentAndChangedCount=True,deadActorNoReads=True,notLiveRagdollProof=True)

def main():
 global OUT,VERSION
 OUT,VERSION=builder.OUT,builder.VERSION
 source=(ROOT/'HD2PhysBoneCompat/src/single_ragdoll_probe_test.lua').read_text(encoding='utf-8-sig');result=validate(run(source));controls={}
 broken=source.replace('local v={X.to_elements(m)}','local v=m',1);assert broken!=source
 try:validate(run(broken))
 except Exception:controls['borrowedPoseCopy']=True
 else:raise AssertionError('Observer borrowed-pose control failed')
 if builder.REVISION in ('s2','s3'):
  def check_s2(source):
   result=run(source,mapped=True);rows=[json.loads(x) for x in result['logs'].values()]
   motion=[r for r in rows if r['event']=='single_model_motion'];poses=[r for r in rows if r['event']=='single_ragdoll_pose']
   assert len(motion)>=4,'S2 fast motion not sampled'
   if builder.REVISION=='s2':assert any(r.get('fullHierarchySnapshot') and len(r['poses'])==139 for r in poses),'S2 full mapped snapshot missing'
   else:
    assert not any(r.get('fullHierarchySnapshot') for r in poses),'S3 raw full hierarchy read'
    assert all(n.get('nameAvailable') for r in poses for n in r['poses']),'S3 unnamed indices read'
    assert result['unsafeAnimatorCalls']==0 and result['nativeNoFsmModeCalls']==0
   assert all(r['resource']=='34a40a5ae7a392ba' for r in motion+poses),'S2 wrong resource sampled'
   assert max(v[7] for r in motion for v in r['values'])>.01,'S2 world-only stretch missed'
   assert result['mutations']==0 and result['invalidIds']==0 and result['errors']==0
   return dict(mappedResource='34a40a5ae7a392ba',motionSamples=len(motion),poseSamples=len(poses),nodeReads=result['reads'],poseWrites=0,full139Snapshot=builder.REVISION=='s2',worldOnlyStretchObserved=True,unsafeAnimatorCalls=result['unsafeAnimatorCalls'])
  result['mappedS2']=check_s2(source)
  priority=run(source,mapped=True,with_refs=True);rows=[json.loads(x) for x in priority['logs'].values()]
  inventories=[r['instances'] for r in rows if r['event']=='observer_scan' and r.get('instances')]
  assert inventories and any(any(x['resource']=='34a40a5ae7a392ba' for x in inv) for inv in inventories),'S2 mapped model starved by native refs'
  assert all(sum(x['kind']=='native_avatar_reference' for x in inv)<=2 for inv in inventories),'S2 native-reference cap not applied'
  assert any(r['event']=='single_model_motion' for r in rows) and priority['errors']==0 and priority['mutations']==0
  result['mappedS2']['twentyFiveNativeReferencesDoNotStarveModel']=True
  broken=source.replace('if p.maxNativeReferences then','if false then',1);assert broken!=source
  bad=run(broken,mapped=True,with_refs=True);badrows=[json.loads(x) for x in bad['logs'].values()]
  assert any(sum(x['kind']=='native_avatar_reference' for x in r.get('instances',[]))>2 for r in badrows if r['event']=='observer_scan')
  controls['modelFirstReferenceCap']=True
  broken=source.replace("if phase=='render' and p.motionSeconds and self.primary", "if false and p.motionSeconds and self.primary",1);assert broken!=source
  try:check_s2(broken)
  except Exception as e:assert 'S2 fast motion not sampled' in str(e);controls['fastMotion']=True
  else:raise AssertionError('S2 fast-motion control failed')
  profile=b.load(OUT/'single-observer-profile.json')
  assert len(profile['deployedAliases'])==11 and profile['maxNativeReferences']==2 and profile['startBudgetOnSingleModel']
  for rid,source_id in profile['deployedAliases'].items():
   assert profile['resources'][rid]['sourceResource']==source_id and profile['resources'][rid]['count']==139
   assert profile['resources'][rid]['layoutSha256']==profile['aliasProvenance'][rid]['layoutSha256']
  controls['s1MissingMappedIdDetected']='34a40a5ae7a392ba' not in b.load(builder.ROOT/'outputs/single-test01-ragdoll-probe-20261109/single-observer-profile.json')['resources']
  assert controls['s1MissingMappedIdDetected']
  if builder.REVISION=='s3':
   gated=run(source,mapped=True,with_refs=True,guarded=True)
   assert gated['unsafeAnimatorCalls']==0 and gated['nativeNoFsmModeCalls']==0 and gated['mutations']==0 and gated['errors']==0
   result['safeS3']=dict(missionRenderAndWarmupGates=True,modelAnimatorNeverQueried=True,nativeWithoutFSMModeNeverQueried=True,rawFullHierarchyDisabled=True,poseWrites=0)
   broken=source.replace("if item.spec.kind=='native_avatar_reference' then\n   animationState=", "if true then\n   animationState=",1);assert broken!=source
   bad=run(broken,mapped=True);assert bad['unsafeAnimatorCalls']>0,'S3 native crash-path negative control not exercised';controls['modelNullAnimatorGetter']=True

 entry=(OUT/'observer-entry.lua').read_text(encoding='utf-8');smoke=exercise(entry);assert smoke['started'] and smoke['version']==VERSION and smoke['writes']==0 and smoke['closed']==1,smoke
 row=b.load(OUT/'build-report.json')
 with zipfile.ZipFile(row['package'])as z:
  assert z.testzip()is None
  ar=b.TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_0'),load_external_data=False);assert len(ar.entries)==1;e=next(iter(ar.entries.values()));raw=bytes(e.toc_data);n,v=struct.unpack_from('<II',raw);assert v==2 and raw[8:8+n]==entry.encode('utf-8')
  assert e.file_id!=0xcfdf231bc0803b9d and e.type_id not in (b.UNIT_TYPE_ID,b.BONE_TYPE_ID)
 for f,h in row['originalInputs'].items():assert hashlib.sha256(Path(f).read_bytes()).hexdigest()==h
 report=dict(status='PASS_PENDING_GAME_TEST',observer=result,negativeControls=controls,entrySmoke=smoke,luaOnlyPackage=True,originalModelInputsUnchanged=True,animationRebaked=False,gameDeployed=False,gameTested=False)
 (OUT/'observer-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='entrySmoke'},ensure_ascii=False,indent=2))
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',choices=('s1','s2','s3'),default='s1');builder.configure_revision(parser.parse_args().revision)
 sys.stdout.reconfigure(encoding='utf-8');main()
