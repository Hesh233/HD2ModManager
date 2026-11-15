"""Build an additive read-only test01 SINGLE ragdoll observer Lua ZIP; never rebakes animation."""
from pathlib import Path
import sys,json,struct,zipfile,uuid,hashlib,copy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));import build_detailed_grip_test as b
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
import survey_native_weapon_grips as sv
from prepare_native_v31_b23 import lua
from lupa.lua51 import LuaRuntime
OUT=ROOT/'outputs/single-test01-ragdoll-probe-20261109';BASE=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';VERSION='1.0.0-test.single-ragdoll'
REVISION='s1'
def configure_revision(revision):
 global OUT,VERSION,REVISION
 assert revision in ('s1','s2','s3');REVISION=revision
 OUT=ROOT/'outputs/single-test01-ragdoll-probe-20261109'
 VERSION={'s1':'1.0.0-test.single-ragdoll','s2':'1.0.1-test.single-ragdoll.2','s3':'1.0.2-test.single-ragdoll.3'}[revision]
 if revision!='s1':OUT=OUT/revision
def main():
 OUT.mkdir(parents=True,exist_ok=True);sv.INDEX=BASE/'data/indexes/asset-index.sqlite';survey=sv.Survey();names=dict(survey.bone_names);resources={};inputs={}
 model=BASE/'test-library/[单骨架模型]test01';meta=b.load(model/'vpk2patch/single-skeleton.json')
 for part in ('vpk2patch','Overwrite'):
  for f in (model/part).glob('*.patch_*'):
   if not f.suffix.rsplit('_',1)[-1].isdigit():continue
   inputs[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest();rows=b.resources(f)
   for _,t,raw in rows:
    if t==BONE_TYPE_ID:
     bn=BonesData.parse(raw);names.update(zip(bn.hashes,bn.names))
   for rid,t,raw in rows:
    if t!=UNIT_TYPE_ID or f'{rid:016x}' not in meta['modelResources']:continue
    u=UnitData.parse(raw);m=b.matrices(u);ns=[dict(name=names.get(h),hash=h,index=i,parent=u.parents[i],bind=m[i]) for i,h in enumerate(u.name_hashes)]
    full=f'{rid:016x}'=='540784804ddf0003'
    if not full:
     core={'skeleton','root','boss','hips','spine1','spine2','chest','neck','head','l_clavicle','r_clavicle','l_shoulder','r_shoulder','l_elbow','r_elbow','l_hand','r_hand','l_hand_twist','r_hand_twist','l_thigh','r_thigh','l_knee','r_knee','l_foot','r_foot','l_ball','r_ball'}
     ns=[n for n in ns if n['name'] in core]
    resources[f'{rid:016x}']=dict(kind='single_model',count=len(u.parents),nodes=ns,fullHierarchy=full)
 ar=survey.archive('18235e0c9ec0e636');u=UnitData.parse(ar.entries[(int('4d1c334d294dfa97',16),UNIT_TYPE_ID)].toc_data)
 for e in ar.entries.values():
  if e.type_id==BONE_TYPE_ID:
   bn=BonesData.parse(e.toc_data);names.update(zip(bn.hashes,bn.names))
 matrices=b.matrices(u);resources['4d1c334d294dfa97']=dict(kind='native_avatar_reference',count=len(u.parents),nodes=[dict(name=names.get(h),hash=h,index=i,parent=u.parents[i],bind=matrices[i]) for i,h in enumerate(u.name_hashes)]);survey.db.close()
 profile=dict(label='test01 SINGLE HD2 RAGDOLL S1 TEST DETAILED READ ONLY',resources=resources,scanSeconds=1,renderSeconds=.5,updateSeconds=1,maxInstances=12,maxBytes=64*1024*1024,duration=180,modelBindSha256=meta['bindSha256'])
 profile.update(version=VERSION,logTag={'s1':'RAGDOLL_S1','s2':'RAGDOLL_S2','s3':'RAGDOLL_S3'}[REVISION])
 aliases={};alias_provenance={}
 if REVISION in ('s2','s3'):
  from analyze_left_items_and_single_live import deployed_aliases,digest
  source_paths=[f for f in (model/'vpk2patch').glob('*.patch_*') if f.suffix.rsplit('_',1)[-1].isdigit()]
  alias_root=model/'Overwrite' if REVISION=='s3' else Path('E:/Steam/steamapps/common/Helldivers 2/data')
  aliases,alias_provenance=deployed_aliases(source_paths,alias_root)
  assert len(aliases)>=7,'No complete deployed test01 single-model alias set'
  for rid,source in aliases.items():
   assert source in resources and resources[source]['kind']=='single_model'
   assert alias_provenance[rid]['count']==resources[source]['count']==139
   resources[rid]=copy.deepcopy(resources[source]);resources[rid].update(sourceResource=source,deployedAlias=True,layoutSha256=alias_provenance[rid]['layoutSha256'])
   path=Path(alias_provenance[rid]['patch']);inputs[str(path)]=digest(path)
  core={'root','boss','hips','spine1','spine2','chest','neck','head','l_clavicle','r_clavicle','l_shoulder','r_shoulder','l_elbow','r_elbow','l_hand','r_hand','l_thigh','r_thigh','l_knee','r_knee','l_foot','r_foot'}
  motion={'hips','head','l_shoulder','r_shoulder','l_elbow','r_elbow','l_hand','r_hand','l_knee','r_knee','l_foot','r_foot'}
  profile.update(label='test01 SINGLE HD2 RAGDOLL S2 MAPPED IDS AND 30HZ READ ONLY',scanSeconds=.25,compactPoseRecords=True,
   captureNames={n:True for n in core},motionNames={n:True for n in motion},motionSeconds=1/30,
   fullSnapshots=True,maxNativeReferences=2,maxInstances=20,preferNearestReference=True,modelMatchRadius=5,requireModelToSample=True,startBudgetOnSingleModel=True,
   duration=120,deployedAliases=aliases,aliasProvenance=alias_provenance)
  profile['resources']['4d1c334d294dfa97']['nodes']=[n for n in profile['resources']['4d1c334d294dfa97']['nodes'] if n['name'] in core]
 if REVISION=='s3':
  profile.update(label='test01 SINGLE HD2 RAGDOLL S3 SAFE NATIVE ANIMATOR GUARD',missionOnly=True,renderOnly=True,warmupSeconds=1,
   strictPoseLayout=True,fullSnapshots=False,captureCheckpoints=True,preferNearestReference=False,scanSeconds=.5,unsafeModelAnimatorQueriesForbidden=True)
 module=(ROOT/'HD2PhysBoneCompat/src/single_ragdoll_probe_test.lua').read_text(encoding='utf-8-sig')
 code='''-- HD2-Addon: mods/hd2modmanager/single_ragdoll_probe_test01
local loader=...
assert(type(loader)=='table' and loader.loader=='Chef Shared Loader','requires Chef Shared Loader')
local Probe=(function()\n'''+module+'\nend)()\nlocal profile='+lua(profile)+'''
Probe.VERSION=profile.version or Probe.VERSION
local path=assert(loader.log_directory)..'/hd2_single_TEST_DETAILED_test01_'..profile.logTag..'_'..os.date('%Y%m%d_%H%M%S')..'.log'
local handle=assert(io.open(path,'w'));local bytes=0;local started=nil;local recording=true;local stopped=false;local lastFlush=0
local function log(line)
 local now=stingray.Application.time_since_launch()
 local terminal=line:find('"event":"complete"',1,true)
 if not started and line:find('"event":"single_ragdoll_pose"',1,true) and (not profile.startBudgetOnSingleModel or line:find('"kind":"single_model"',1,true))then started=now end
 if not terminal and (bytes+#line+64>profile.maxBytes-4096 or (started and now-started>profile.duration))then
  if recording then handle:write('[TEST_ONLY_SINGLE_READONLY] {"event":"recording_stopped","poseWrites":0}\\n');handle:flush();recording=false end
  return
 end
 handle:write(os.date('%Y-%m-%d %H:%M:%S'),' [TEST_ONLY_SINGLE_READONLY] ',line,'\\n');bytes=bytes+#line+64
 if terminal or line:find('"event":"observer_capture_checkpoint"',1,true) or now-lastFlush>2 then handle:flush();lastFlush=now end
end
local ok,probe=pcall(Probe.new,stingray,profile,log,{inMission=loader.in_mission});if not ok then handle:close();error(probe)end
local function step(phase)
 if stopped or not recording then return end
 local ok,err=pcall(probe.tick,probe,phase,stingray.Application.time_since_launch())
 if not ok then log(Probe.encode({event='observer_error',error=tostring(err),poseWrites=0}))end
end
local function stop()
 if stopped then return end;probe:stop();handle:flush();handle:close();stopped=true
end
return {version=Probe.VERSION,update=function()step('update')end,render=function()step('render')end,shutdown=stop,on_stop=stop}
'''
 ok,err=LuaRuntime().eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(code);assert ok,err
 header=(ROOT/'outputs/grip-equipment-perf-test-20261108-v9/test01/container-header.bin').read_bytes();body=code.encode('utf-8');payload=struct.pack('<II',len(body),2)+body;patch=bytearray(header)+payload;patch.extend(bytes(-len(patch)%16));struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload));struct.pack_into('<Q',patch,104,int(hashlib.sha256(b'mods/hd2modmanager/single_ragdoll_probe_test01').hexdigest()[:16],16))
 note='''# test01 单骨骼布娃娃观测【测试用·详细·只读】\n\n额外Lua诊断包，不含模型或动画，不修复布娃娃，不写任何骨骼/物品/物理数据，不执行update_unit。只与当前test01单骨骼模型及已验收单骨骼动画搭配。不要安装双骨骼挂点包。\n\n读取7个已核对的139节点单骨骼模型实例及原生Avatar参考：一份参考模型记录完整139节点，其余6份记录关键躯干/双臂/双腿骨链以控制重复日志量。记录动画状态API、骨模式、骨骼local/world、scale、父索引、骨段长度和parent-FK误差；记录当前模型bind供对照。不以FSM/ignore模式直接认定布娃娃，缺失节点及父索引明确标记。未解析名称的节点仅在精确资源/count吻合时按导出索引只读并标记rawHash，不把数值hash传入IdString32接口。不能读取Havok内部/GPU蒙皮，也不擅自修正。\n\n日志 hd2_single_TEST_DETAILED_test01_RAGDOLL_S1_日期时间.log，行TEST_ONLY_SINGLE_READONLY；render约2Hz、update约1Hz，最长180秒/64MiB，达到预算停止观察。详细诊断可能产生短时开销，不作日常包。\n\n保持现用模型/动画/物理，只追加本Lua并重启；先正常活动约10秒，进入布娃娃后保持5–10秒，再恢复活动；短测45–60秒后退出，提供完整日志并标记视觉拉伸时间。测试后停用此诊断包。单骨骼拉伸尚未修复。\n'''
 if REVISION in ('s2','s3'):
  note='''# test01 S2【单骨骼布娃娃·额外只读取证】\n\nS1 实机日志仅抓到原生 Avatar，目标模型样本为0；不是已经定位了单骨骼拉伸。S2补全当前已部署换甲后的11个Unit ID：每个均与test01来源骨名hash、父链和完整bind矩阵精确一致。不要换甲或重导后沿用过期ID包。\n\n仅Lua，无模型/动画/物理改动，不写骨骼、不刷新图、不修改Havok。首次出现单骨骼模型后才开始120秒记录预算；64MiB上限。普通完整local/world矩阵render2Hz、update1Hz；优先一个实际模型约30Hz记录关键骨位置、scale及父FK/骨段摘要，另保留首次完整139节点快照。非直接Havok或GPU读数，nil父采用导出父的比对会明确标记。模型优先，原生参考最多2个，不再由原生Avatar占满取证名额。\n\n停用S1，仅启用S2，保留已验收单骨架模型、动画及物理；不安装双骨架V11握持包。重启，正常移动10秒后复现坠落/落地拉伸，短测约45–60秒后退出。若能标出落地时间更好。详细采样只用于测试，不承诺无性能开销。\n日志 hd2_single_TEST_DETAILED_test01_RAGDOLL_S2_日期时间.log。若observer_target_missing持续出现，说明仍未覆盖当前模型，不能把原生参考当成模型拉伸数据。单骨骼布娃娃修复仍待有效实机数据。\n'''
 if REVISION=='s3':
  note='''# test01 S3【防启动崩溃·单骨骼额外只读取证】\n\n停用已知启动崩溃的S2，只启用S3；保持test01单骨骼模型、动画、物理，不安装双骨骼V12握持包。S3不是布娃娃物理修复包。\n\n两份dump同一bone-mode getter读空动画对象：RVA 0x3f1bc9、读0x164。S3不在外部骨链接模型上调用任何动画API；仅原生Avatar且FSM明确存在才读取bone mode。舰船/加载/未确认任务零姿态读取，任务内仅render、实例稳定1秒后采样。仅精确命名核心骨，原始索引全139读取已关闭；count/命名索引改变则停读。第一次命名读取检查点立即flush。\n\n登记test01指定模组库Overwrite的11个精确映射ID，不从当前已切到test06的活动游戏包误判。换甲/重导后应重生成映射。普通矩阵约2Hz、主模型关键骨约30Hz，首模型起120秒/64MiB。0 set_local_pose、0 update_unit、0 relink、0物理写入；不直接读取Havok或GPU。\n\n重启进入任务，正常活动10秒后复现坠落落地，总计45–60秒后退出。日志 hd2_single_TEST_DETAILED_test01_RAGDOLL_S3_日期时间.log。如再次崩溃保留新日志及dump。详细采样有额外开销，短测后停用。\n'''
  note+='\nS3启动防崩溃：两份dump同一animation_bone_mode原生getter读空动画对象（RVA 0x3f1bc9，地址0x164）。禁止对外部骨链接模型调用动画API；仅原生Avatar且确认FSM存在才读bone mode。舰船/加载/未确认任务零姿态读取；任务内render阶段、实例稳定1秒后采样；不再原始索引全139读取，改已核对命名核心骨。首次命名读取检查点立即flush。模型scale/FK采样仍只读，不修复Havok。停用S2，只启用S3，保持模型/动画/物理。\n'
 manifest=dict(Guid=str(uuid.uuid4()),Name='[测试用·只读布娃娃诊断][单骨架动画]test01',Description=f'TEST ONLY / READ ONLY {VERSION}; additive Lua observer, no animation/model changes.')
 package=OUT/f'test01-单骨骼布娃娃额外Lua检查-测试用详细只读-{VERSION}.zip'
 with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
  z.writestr('9ba626afa44a3aa3.patch_0',patch)
  for suf in ('.gpu_resources','.stream'):z.writestr('9ba626afa44a3aa3.patch_0'+suf,b'')
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2));z.writestr('测试说明.md',note)
 (OUT/'observer-entry.lua').write_bytes(body);(OUT/'single-observer-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'测试说明.md').write_text(note,encoding='utf-8')
 report=dict(status='BUILT_PENDING_TEST',package=str(package),sha256=hashlib.sha256(package.read_bytes()).hexdigest(),luaSha256=hashlib.sha256(body).hexdigest(),models=len(resources)-1,deployedAliases=aliases,aliasProvenance=alias_provenance,expectedModelCount=139,originalInputs=inputs,gameDeployed=False,gameTested=False,poseWrites=0,animationRebaked=False)
 (OUT/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',choices=('s1','s2','s3'),default='s1');configure_revision(parser.parse_args().revision)
 sys.stdout.reconfigure(encoding='utf-8');main()
