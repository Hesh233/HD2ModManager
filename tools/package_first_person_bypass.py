"""Package FP-gated Lua with unchanged accepted 248-node companions; no new folders."""
import hashlib,json,struct,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from prepare_native_v31_b23 import lua
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
BASE=ROOT/'outputs/test07-sidearm-fix-111-20261106/candidate-111'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 if '--prepare' in sys.argv:
  p=json.loads((BASE/'attachment-profile.json').read_text(encoding='utf-8'));p['variant']=p['variant'].replace('1.0.11','1.0.14')+'-fp-hide-arms'
  library=TARGET/'test-library/[原比例模型]test07'
  arms={}
  for section in (library/'vpk2patch/sections.json',library/'Overwrite/sections.json'):
   for row in json.loads(section.read_text(encoding='utf-8-sig'))['units']:
    if row.get('slot') in ('LeftArm','RightArm') and row['fileId'] in p['models']:
     arms[row['fileId']]=row['slot']
  assert arms.get('4c28e97d1bf51e2b')=='LeftArm' and arms.get('e6980827cce04d17')=='RightArm'
  p['firstPersonArmHide']=dict(enabled=True,modelResources=arms,matchTolerance=.01,
   policy='temporary_hide_selected_fp_receiver_only_restore_per_mesh_default')
  (TARGET/'第一人称门禁-test07-profile.lua').write_text('return '+lua(p)+'\n',encoding='utf-8')
  (TARGET/'第一人称门禁-test07-profile.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8');return
 source=(TARGET/'第一人称门禁-test07.lua').read_bytes();raw=(TARGET/'第一人称门禁-test07.patch').read_bytes()
 archive=TocArchive.parse_parts(raw,load_external_data=False);payload=bytes(next(iter(archive.entries.values())).toc_data)
 n,v=struct.unpack_from('<II',payload);assert v==2 and payload[8:8+n]==source
 assert b"VERSION = '1.0.14'" in source and b'fp_camera_matches_main_view' in source and b'-- INSERT ' not in source
 for name in ('native_grip_transfer_test.lua','native_first_person_guard.lua','attachment_fix_runtime.lua'):
  part=(ROOT/'HD2PhysBoneCompat/src'/name).read_text(encoding='utf-8-sig').strip()
  assert part in source.decode('utf-8'),f'Installed Core embeds stale source: {name}'
 installed=TARGET/'HD2ModCore.dll'; staging=ROOT/'outputs/single-hd2-fix-20261106/manager/HD2ModCore.dll'
 installedMatches=installed.read_bytes()==staging.read_bytes()
 info=json.loads((staging.parent/'anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'))
 assert info['luaVersion']=='1.0.14' and info['pipelineVersion']=='1.0.15'
 accepted=(BASE/'hd2attachmentfix.lua').read_text(encoding='utf-8');new=source.decode('utf-8')
 a=accepted.index('    local function solve_source_arm(');b=accepted.index('    function self:tick(',a)
 x=new.index('    local function solve_source_arm(');y=new.index('    -- FP presentation still needs',x)
 assert accepted[a:b]==new[x:y],'Accepted grip/arm/attachment routines changed'
 rig=TocArchive.parse_parts((BASE/'9ba626afa44a3aa3.patch_1').read_bytes(),load_external_data=False)
 assert len(UnitData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID)).parents)==248
 manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'));manifest['Description']='Lua1.0.14临时方案：第一人称隐藏已验证的当前玩家Source左右臂，第三人称/退出逐网格恢复原可见性；挂点零写。VPK第一人称骨骼位置改写列TODO，248节点配套不改，待实机。'
 note='''# 第一人称临时隐藏手臂 1.0.14（待实机）

按用户2026-11-07要求临时隐藏第一人称手臂，不在本轮改写VPK骨骼位置。
- 已确认第一人称且处于任务：只对profile中验证过的LeftArm/RightArm资源，并通过当前FP Avatar的肩/肘/手三处原生骨世界矩阵校验的实例隐藏。
- 同资源多实例同时匹配时跳过，避免隐藏其他玩家；不以资源ID/距离或冻结Source骨单独认领。
- render逐网格记录原可见性，仅Unit.set_mesh_visibility(...,'default')；原本隐藏网格不会在退出时被强行显示。武器、躯干、腿、头盔和其他渲染上下文不修改。
- 引擎重新显示时下次render再次隐藏；未知视图不接纳新对象。切回第三人称、确认非任务或关闭运行时恢复记录；失效Unit不写，失败保留账本重试。
- 第一人称挂点/Source骨姿态仍不写，不重新挂接；第三人称保留已确认1.0.11副武器/下挂逻辑。

## TODO（本轮不实施）
- [ ] 第一人称VPK骨骼位置改写：以FP Avatar63为驱动，修复自定义Source骨的坐标与接收映射，替代临时隐藏；保持原生FP通道/骨名hash契约与TP248门禁，验证FP动画及TP切回。

禁用旧1.0.13和重复挂点包，整包导入此ZIP。
模型→动画→本Lua/UNIT/BONES配套最后覆盖；248节点配套原字节不变，无需重烘模型/整套动画。部署后重启游戏。
实测第一人称移动/瞄准时手臂不显示、枪正常；切回第三人称手臂恢复，副武器/下挂握持正常；舰船/换甲/关闭模组不能残留隐藏状态。
日志应loaded.version=1.0.14、fpTemporaryArmHide=true，FP记录fp_arm_hidden，退出记录fp_arm_visibility_restored；无匹配则fp_arm_hide_skipped说明原因。
固定管理器DLL如被占用，关闭管理器后运行现有UpdateIntegratedManager.ps1 -SkipBuild同步；此ZIP由新发布Core生成，可独立导入。
本任务不自动部署游戏、不改活动库；临时隐藏视觉效果仍待用户实机验收。
'''
 out=TARGET/'test07-第一人称隐藏手臂-1.0.14-待测试.zip'
 companions={}
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  z.writestr('9ba626afa44a3aa3.patch_0',raw)
  for suffix in ('.gpu_resources','.stream'):z.writestr('9ba626afa44a3aa3.patch_0'+suffix,b'')
  for suffix in ('','.gpu_resources','.stream'):
   name='9ba626afa44a3aa3.patch_1'+suffix;data=(BASE/name).read_bytes();z.writestr(name,data);companions[name]=sha(data)
  z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
  z.writestr('测试说明.md',note)
  z.writestr('attachment-profile.json',(TARGET/'第一人称门禁-test07-profile.json').read_bytes())
  z.writestr('attachment-fix.json',(BASE/'attachment-fix.json').read_bytes())
 with zipfile.ZipFile(out) as z:assert z.testzip() is None
 result=dict(status='PASS_PENDING_GAME_TEST',luaVersion='1.0.14',package=str(out),packageSha256=sha(out.read_bytes()),
  acceptedGripCodeUnchanged=True,firstPersonPoseWrites=False,firstPersonCacheMaintenance=True,
  defaultArmMeshVisibilityChanged=True,linksChanged=False,firstPersonVpkBonePositionRewrite='TODO',companionNodes=248,unchangedCompanions=companions,sourceSha256=sha(source),
  installedCoreSha256=sha(installed.read_bytes()),publishedCoreSha256=sha(staging.read_bytes()),installedCoreMatchesPublished=installedMatches,managerSyncPending=not installedMatches,
  composedEmbeddedSourcesMatchCurrent=True,pipelineVersion=info['pipelineVersion'],singleSkeletonPipelineVersion=info['singleSkeletonPipelineVersion'],
  newDirectoriesCreated=False,modelRebaked=False,animationRebaked=False,gameDeployed=False,gameTested=False)
 (TARGET/'第一人称门禁-包验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
