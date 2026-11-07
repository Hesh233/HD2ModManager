"""Build fixed-folder test01 Lua; preserve the complete 229-node companion."""
import hashlib,json,sys,struct,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from prepare_native_v31_b23 import lua
from anim_batch_mod.native_config import apply_grip_fixes
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import bone_name_hash
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
BASE=TARGET/'test-library/[骨骼挂点修正]test01'
PREFIX='test01-武器握持修正-1.0.17'
def digest(data):return hashlib.sha256(data).hexdigest()
def main():
 if '--prepare' in sys.argv:
  # Reuse the tested 1.0.15 calibration/policy verbatim; only identify the new runtime.
  p=json.loads((TARGET/'test01-武器握持修正-1.0.15-profile.json').read_text(encoding='utf-8-sig'))
  assert p['avatar']['count']==229 and p['sourceRight']['name'].startswith('hd2n_4e4fb4fa303d_')
  assert p['maxWristMountDistance']==.5
  p['variant']=p['variant'].replace('-weapons-1.0.15','-weapons-1.0.17-bounded-log')
  p['logging']=dict(compact=True,recordSeconds=90,maxBytes=524288,exceptionIntervalSeconds=2)
  p['logSeconds']=5.;p['maxRecords']=2000
  p['sidearmDiagnostics']=dict(p['sidearmDiagnostics'],intervalSeconds=5.,maxSamplesPerPath=12)
  (TARGET/(PREFIX+'-profile.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf8')
  (TARGET/(PREFIX+'-profile.lua')).write_text('return '+lua(p)+'\n',encoding='utf8');return
 p=json.loads((TARGET/(PREFIX+'-profile.json')).read_text(encoding='utf8'))
 prior=json.loads((TARGET/'test01-武器握持修正-1.0.15-profile.json').read_text(encoding='utf8'))
 for key in ['variant','logging','logSeconds','maxRecords','sidearmDiagnostics']:prior[key]=p[key]
 assert prior==p,'Existing calibrated weapon/FP policy changed'
 source=(TARGET/(PREFIX+'.lua')).read_bytes();raw=(TARGET/(PREFIX+'.patch')).read_bytes()
 code=TocArchive.parse_parts(raw,load_external_data=False);assert len(code.entries)==1
 payload=bytes(next(iter(code.entries.values())).toc_data);n,v=struct.unpack_from('<II',payload)
 assert v==2 and payload[8:8+n]==source and len(payload)==n+8
 for name in ['native_grip_transfer_test.lua','native_first_person_guard.lua','attachment_fix_runtime.lua']:
  assert (ROOT/'HD2PhysBoneCompat/src'/name).read_text(encoding='utf-8-sig').strip() in source.decode('utf8'),name
 assert b"VERSION = '1.0.17'" in source and b'-- INSERT ' not in source
 rig=TocArchive.parse_parts((BASE/'9ba626afa44a3aa3.patch_1').read_bytes(),load_external_data=False)
 u=UnitData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID))
 assert len(u.parents)==229
 rows=list(p['avatar']['nodes'])+p['leftGrip']['nodes']+p['leftGrip']['outputs']+p['rightGrip']['nodes']+p['rightGrip']['outputs']
 rows += [p[x] for x in ['sourceRight','sourceLeft','originalMount','sourceRightMount','target','nativeRight','nativeLeft'] if p.get(x)]
 for a in p['attachments']:rows += [a[x] for x in ['node','source','native','reference','sourceMount'] if a.get(x)]
 for b in p['bodySync']['outputs']:rows += [b[x] for x in ['node','native','reference','positionParent']]
 for row in rows:
  assert u.name_hashes[row['index']]==bone_name_hash(row['name']),row
  if row.get('parent') is not None:assert u.parents[row['index']]==row['parent'],row
 # Actual model signatures, including wardrobe's one-to-many body mappings.
 models={};modelRoot=TARGET/'test-library/[原比例模型]test01'
 for folder in ['vpk2patch','Overwrite']:
  for file in (modelRoot/folder).glob('*.patch_*'):
   if not file.suffix.rsplit('_',1)[-1].isdigit():continue
   a=TocArchive.parse_parts(file.read_bytes(),load_external_data=False)
   for e in a.entries.values():
    if e.type_id==UNIT_TYPE_ID:models[f'{e.file_id:016x}']=UnitData.parse(e.toc_data)
 for rid,spec in p['models'].items():
  m=models[rid];assert len(m.parents)==spec['count'],rid
  for row in spec['nodes']:
   assert m.name_hashes[row['index']]==bone_name_hash(row['name']),(rid,row)
   if row.get('parent') is not None:assert m.parents[row['index']]==row['parent'],(rid,row)
 manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8-sig'))
 manifest['Description']='test01 Lua 1.0.17：最终握点越界验证回滚后按帧重试，硬错误仍停用；AR-11标准弹匣/瞄具/附挂霰弹枪与P-92弹匣精确资源识别；P-92不可达握点位置补偿，保留朝向与配件动画；原229节点配套，模型/全量动画不重烘，待实机。'
 note='''# test01 武器握持修正 1.0.17（待实机）

最新日志：2026-11-07 14:52:49–14:56:52，test01 / Lua1.0.15 / 229节点；14:55:29最终挂点越界导致停用。
使用现有 test01 模型与原比例混合动画，不改冻结的历史1.0.8工程。

本轮日志缩减：
- 新hd2_grip_b23_compact.log每次启动只保留当前会话，旧大日志不再追加也不删除。
- 从首次第三人称修正开始录制90秒；每文件512KiB硬上限，常规5秒采样，配件每条路径最多12组。
- 常规矩阵改为positions-v1位置摘要、去掉重复variant和部件local矩阵；异常完整矩阵保留但同类2秒限流。记录log_recording_stopped/log_summary。
- 停止录制只停日志，不停握点/物理求解；新的0.5m回滚重试机制保持。

保留的运行时修正：
- 最终挂点超过0.5米不再永久停用：原参考越界时零setter跳过；最终候选越界时验证回滚及模型/武器/配件刷新后跳过本帧，下一render重试。
- 只有距离越界的私有异常可恢复；身份/拓扑/保护骨/读回/恢复失败继续停用，不提高0.5米上限。
- 异常帧强制日志mount_skipped，记录frame/time/phase、来源挂点local/world、source/desired、距离/阈值、已选择副武器及rollbackVerified/retry。
- 原1.0.15武器/配件/第一人称行为与229节点配套保留，只改运行时，不需要重烘模型或动画。

保留的武器修正：
- AR-11标准弹匣20c03774d6e1d87f、附挂霰弹枪b9c209b4f99b5335、瞄具129e5fb1b13c2018、P-92弹匣fc1f0a3b3fc97238按游戏原始节点/hash/count/父级精确识别。刷新顺序为枪→附挂武器→弹匣/瞄具，不写枪或部件local、不重新挂接。只涵盖这些已审计资源，不声称所有未审计配件通用通过。
- 附挂武器的实时IK_left优先，仍保留唯一位置+朝向匹配、自由手/换弹/第一人称/舰船门禁。
- P-92右臂用原求解器跟随实时IK_right。可达时不移枪；不可达时只把挂点平移到实际手部端点，不拉长骨骼、不改原生瞄准朝向，不累计位置。
- 只读分阶段诊断补采AR-11/P-92/附挂与配件；空场景不消耗采样预算。

安装：导入本ZIP作为test01挂点包更新，只启用一份attachment_fix；保持模型→原比例混合动画→本Lua/UNIT/BONES包的最终覆盖顺序，然后重启游戏。本包携带原229节点配套（字节不变），不是历史260节点或test07 248节点。
当前不自动修改活动库、游戏部署或设置，也不重烘模型/全量动画。

验收：AR-11瞄准/移动/换弹及瞄具弹匣；附挂霰弹枪握持及切回主枪；P-92单手/瞄准双手/跑动/换弹收枪；其他玩家与舰船/第一人称回归。
日志应见version=1.0.17、mountOutOfRangePolicy=preflight_skip_or_verified_rollback_retry；遇越界应见mount_skipped/retry=next_render及随后applied，不能再因单次越界disabled。另保留gripResource=b9c209b4f99b5335、gripKind=underbarrel；P-92不可达时policy=live_right_ik_reachable_registered_hand、reachCorrection，分阶段sidearm_probe可观察配件。离线通过不等于最终蒙皮/视觉已经通过。
'''
 out=TARGET/(PREFIX+'-待测试.zip');companions={}
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  z.writestr('9ba626afa44a3aa3.patch_0',raw)
  for suffix in ['.stream','.gpu_resources']:z.writestr('9ba626afa44a3aa3.patch_0'+suffix,b'')
  for suffix in ['','.stream','.gpu_resources']:
   name='9ba626afa44a3aa3.patch_1'+suffix;data=(BASE/name).read_bytes();companions[name]=digest(data);z.writestr(name,data)
  z.writestr('attachment-profile.json',json.dumps(p,ensure_ascii=False,indent=2))
  z.writestr('attachment-fix.json',(BASE/'attachment-fix.json').read_bytes())
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2));z.writestr('测试说明.md',note)
 with zipfile.ZipFile(out) as z:
  assert z.testzip() is None
  for name,sha in companions.items():assert digest(z.read(name))==sha
 result=dict(status='PASS_PENDING_GAME_TEST',luaVersion='1.0.17',package=str(out),packageSha256=digest(out.read_bytes()),avatarNodes=229,verifiedAvatarRows=len(rows),modelBindings=len(p['models']),sourceSha256=digest(source),companionsUnchanged=companions,modelRebaked=False,animationRebaked=False,gameDeployed=False,gameTested=False)
 (TARGET/(PREFIX+'-包验证.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 (TARGET/(PREFIX+'-说明.md')).write_text(note,encoding='utf8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
