"""Build test06 FP97 receiver A2; retain the frozen A1 graph and TP V12 companions."""
from pathlib import Path
import argparse,hashlib,json,struct,sys,uuid,zipfile
import build_detailed_grip_test as b
import survey_native_weapon_grips as survey
from anim_batch_mod.first_person_skeleton import compile_fp_source_graph
from anim_batch_mod.archive import TocArchive,TocEntry,InlinePatchWriter
from prepare_native_v31_b23 import compose_source
from lupa.lua51 import LuaRuntime
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
OUT=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/receiver-a2'
VERSION='1.0.18-test.fp-source.2'
TAG='FP_SOURCE_A2'
SOURCE_NAME='hd2attachmentfix-FP-A2.lua'
def sha(data):return hashlib.sha256(data).hexdigest()
def main(argv=None):
 global OUT
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,default=OUT)
 OUT=parser.parse_args(argv).out.resolve()
 OUT.mkdir(parents=True,exist_ok=True);model=BASE/'test-library/[原比例模型]test06';rid='e6980827cce04d17';inputs={};raw=None
 for path in(model/'Overwrite').glob('*.patch_*'):
  if not path.suffix.rsplit('_',1)[-1].isdigit():continue
  for id,t,data in b.resources(path):
   if t==b.UNIT_TYPE_ID and f'{id:016x}'==rid:raw=data;inputs[str(path)]=sha(path.read_bytes())
 assert raw is not None
 survey.INDEX=BASE/'data/indexes/asset-index.sqlite';q=survey.Survey();a=q.archive('18235e0c9ec0e636');entry=a.entries[(int('d0cf4d493ca08bed',16),b.UNIT_TYPE_ID)];fp=b.UnitData.parse(entry.toc_data);bone=a.entries[(fp.bones_ref,b.BONE_TYPE_ID)].toc_data;q.db.close()
 expanded,bones,contract=compile_fp_source_graph(entry.toc_data,bone,raw,b.load(model/'vpk2patch/source-skeleton.json'),rid)
 assert bones==bone
 writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),OUT/'9ba626afa44a3aa3.patch_2',{b.UNIT_TYPE_ID:1},standalone=True)
 writer.append(TocEntry(entry.file_id,entry.type_id,bytearray(expanded),entry.gpu_data,entry.stream_data,unknown1=entry.unknown1,unknown2=entry.unknown2,unknown3=entry.unknown3,unknown4=entry.unknown4));fpfiles=writer.finish()
 old=ROOT/'outputs/grip-left-items-test-20261109-v10/v12';profile=b.load(old/'test06/B23-profile.json');profile['testRepairs']['version']=VERSION;profile['testRepairs']['logTag']=TAG;profile['testRepairs']['meleeCapture']=dict(enabled=True,maxItems=4,stages=['before_write','final_output','after_restore'],calibrationChanged=False);contract['meleeProbeSpecs']={rid:dict(resource=rid,count=profile['consumers'][rid]['count'],rootIndices=spec['rootIndices'],leftMarker=spec.get('leftMarker')) for rid,spec in profile['testRepairs']['heldEquipment']['rigidRight'].items() if spec.get('itemType')=='melee'};contract.update(version='1.0.1-test.fp-source.a2',nativeCacheRefreshBeforeSampling=True,receiverCacheRefreshBeforeMatching=True,perEventDiagnosticSlots=True,sourceWorldTolerance=.0002,motionAgreementTolerance=.0002,motionProofKind='source_and_actual_model_displacement_continuous_unique_frames',nextRenderStage='before_refresh_after_update_restore');profile['firstPersonSource']=contract;profile['variant']+='-FP-SOURCE-RECEIVER-A2'
 source=compose_source(profile);ok,error=LuaRuntime().eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(source);assert ok,error
 body=source.encode('utf-8');header=(old/'test06/container-header.bin').read_bytes();payload=struct.pack('<II',len(body),2)+body;patch=bytearray(header)+payload;patch.extend(bytes(-len(patch)%16));struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
 manifest=dict(Guid=str(uuid.uuid4()),Name='[测试用·FP接收复核A2]test06',Description=f'{VERSION}; right FP Source receiver proof with fresh native inputs; not full FP grip, melee calibration or game-verified repair.')
 note='''# test06 第一人称Source接收复核 A2

版本 1.0.18-test.fp-source.2；日志 FP_SOURCE_A2。本包仍是阶段A，只验证test06的e6980827cce04d17右臂；左臂继续临时隐藏，不是完整FP双臂/握枪修复。

A1实机已确认FP97安装、1797次接收匹配，但1539次fp_source_world_readback失败，且共享限频抑制了所有成功接收矩阵日志。本版先刷新已验证FP原生缓存再采样，刷新唯一模型缓存后核对原生三点；不放宽任何矩阵/模型/相机/唯一性容差。只有完整Source回读、至少3个不同连续帧的模型接收，以及Source与模型手实际位移共同证明全部满足才提供测试右臂显示许可。慢速动作按同一连续接收链的位移跨度验证，不要求每帧都移动2mm；模型冻结但落在容差内不能通过动态证明。记录显示许可与实际可见网格数，保存原逐mesh mask，不盲目显示原本隐藏的网格。

原FP63索引/hash/parent/local/world bind与47Bones通道保持；新增34未动画输出构成FP97，和A1图字节相同。原TP267配套/模型/动画/GPU/stream不变。只写FP新增Source节点；原生FP63、枪、挂点、相机、模型pose均零写；切TP/退出恢复Source及其模型缓存。不能将骨回读等同GPU或画面验收。

补充只读取证：FP47、Source和模型before/after/下次render矩阵；四近战根的刷新前后/current local、IK_left（真实存在才读）及双骨骼原生/Source手、挂点和唯一链接假设。A1的FP旗帜根10帧冻结并离手2.7–3.2m，不能作为握点校准。本包没有对近战加统一偏移，也没有修改换弹左手、已验收磁轨炮弹药和训斥枪口策略。

## 短测

停用A1/V12等同名attachment_fix，仅启用本A2；保持当前test06双骨骼模型与已验收物理运行时。不要用test01单骨骼，不需重导/重烘。重启进任务后短测45–60秒：切FP，静止/上下瞄准/行走，切回TP；有条件再依次持砍刀、晕眩长矛、破门锤、唯一真旗各5–8秒并做一次攻击/切换。左臂隐藏是本阶段预期；重点反馈右臂是否持续可见跟随。

请提供同时间段视频/截图，以及hd2_grip_TEST_PERF_test06_FP_SOURCE_A2_日期时间.partNN.log。若仍隐藏，日志将区分Source回读失败、未找到唯一接收者、显示许可未通过或原可见mesh mask为全false；不要删除包中的FP图配套或混装A1。此包未部署、未实机验收。
'''
 dest=OUT/f'test06-第一人称Source接收复核A2-{VERSION}.zip';oldrow=next(r for r in b.load(old/'build-report.json') if r['model']=='test06')
 with zipfile.ZipFile(oldrow['package'])as z,zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6)as w:
  for item in z.infolist():
   if item.filename in('9ba626afa44a3aa3.patch_0','manifest.json','attachment-profile.json')or item.filename.endswith('.md'):continue
   w.writestr(item.filename,z.read(item))
  w.writestr('9ba626afa44a3aa3.patch_0',patch);w.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2));w.writestr('attachment-profile.json',json.dumps(profile,ensure_ascii=False,indent=2));w.writestr('first-person-source-profile.json',json.dumps(contract,ensure_ascii=False,indent=2));w.writestr('测试说明.md',note)
  for path in fpfiles:w.write(path,path.name)
 for name,data in [('fp-native-unit.toc',entry.toc_data),('fp-expanded-unit.toc',expanded),('fp-native.bones',bones),('fp-model-unit.toc',raw),(SOURCE_NAME,body)]: (OUT/name).write_bytes(data)
 (OUT/'fp-source-contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'B23-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'测试说明.md').write_text(note,encoding='utf-8')
 report=dict(status='BUILT_PENDING_TEST',package=str(dest),sha256=sha(dest.read_bytes()),luaSha256=sha(body),fpCount=contract['avatar']['count'],nativeCount=63,animationChannels=47,sourceOutputs=len(contract['avatar']['outputs']),modelCount=contract['model']['count'],modelResource=rid,originalModelInputs=inputs,gameDeployed=False,gameTested=False,phase='A2_FRESH_NATIVE_INPUT_AND_RECEIVER_PROOF',logTag=TAG,sourceName=SOURCE_NAME,meleeGripCalibrated=False,fullFpArmsImplemented=False)
 (OUT/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
