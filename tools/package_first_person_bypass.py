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
  p=json.loads((BASE/'attachment-profile.json').read_text(encoding='utf-8'));p['variant']=p['variant'].replace('1.0.11','1.0.13')+'-fp-presentation'
  (TARGET/'第一人称门禁-test07-profile.lua').write_text('return '+lua(p)+'\n',encoding='utf-8')
  (TARGET/'第一人称门禁-test07-profile.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8');return
 source=(TARGET/'第一人称门禁-test07.lua').read_bytes();raw=(TARGET/'第一人称门禁-test07.patch').read_bytes()
 archive=TocArchive.parse_parts(raw,load_external_data=False);payload=bytes(next(iter(archive.entries.values())).toc_data)
 n,v=struct.unpack_from('<II',payload);assert v==2 and payload[8:8+n]==source
 assert b"VERSION = '1.0.13'" in source and b'fp_camera_matches_main_view' in source and b'-- INSERT ' not in source
 for name in ('native_grip_transfer_test.lua','native_first_person_guard.lua','attachment_fix_runtime.lua'):
  part=(ROOT/'HD2PhysBoneCompat/src'/name).read_text(encoding='utf-8-sig').strip()
  assert part in source.decode('utf-8'),f'Installed Core embeds stale source: {name}'
 installed=TARGET/'HD2ModCore.dll'; staging=ROOT/'outputs/single-hd2-fix-20261106/manager/HD2ModCore.dll'
 assert installed.read_bytes()==staging.read_bytes(),'Installed Core differs from published Core'
 info=json.loads((TARGET/'anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'))
 assert info['luaVersion']=='1.0.13' and info['pipelineVersion']=='1.0.15'
 accepted=(BASE/'hd2attachmentfix.lua').read_text(encoding='utf-8');new=source.decode('utf-8')
 a=accepted.index('    local function solve_source_arm(');b=accepted.index('    function self:tick(',a)
 x=new.index('    local function solve_source_arm(');y=new.index('    -- FP presentation still needs',x)
 assert accepted[a:b]==new[x:y],'Accepted grip/arm/attachment routines changed'
 rig=TocArchive.parse_parts((BASE/'9ba626afa44a3aa3.patch_1').read_bytes(),load_external_data=False)
 assert len(UnitData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID)).parents)==248
 manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'));manifest['Description']='Lua1.0.13：第一人称挂点/姿态写入旁路，保留原生图与已验证模型接收缓存刷新（含隐藏模型）；第三人称保持1.0.11握持。248节点配套未改，手臂残留修正待实机。'
 note='''# 第一人称缓存维护修正 1.0.13（待实机）

1.0.12已在实机触发第一人称门禁并完成局部回滚，但直接返回也停止了模型接收/cache刷新。
本版将“挂点/手臂/躯干姿态写入”和“呈现缓存维护”分开：
- 第一人称进入时仅恢复上一帧待处理输出；持续第一人称不修改任何挂点或骨骼姿态。
- 任务内确认第一人称时，render按Avatar→已验证body模型→附近已分类组件依次World.update_unit。
- 隐藏的已知body模型也刷新，避免原生renderer再次显示后仍留旧世界缓存。
- 不改可见性、不重新挂接、不启用第三人称IK、不写枪/弹夹内部动画。
- 未确认视图或舰船/加载中不执行此维护；切回第三人称重扫，保持1.0.11副武器/下挂。

判定仍基于FP63图camera与主视图相机对应；不是ADS/FOV或图存在。
新增fp_presentation模型实例/可见性/父状态/手骨刷新前后世界矩阵日志。
当前无法从Lua观测最终蒙皮palette；不能将离线缓存测试视为实机视觉通过。

禁用旧1.0.12（以及重复1.0.11挂点包），整包导入此ZIP。
模型→动画→本挂点包最后覆盖；248节点骨架字节未改，不重烘模型/动画。
部署后重启游戏；第一人称移动/转向/瞄准并切回第三人称，确认手臂不再停留世界原点。
若仍残留，提供本次hd2_grip_b23.log与画面；新fp_presentation可辨别模型receiver世界矩阵是否跟随。
管理器DLL如被占用，关闭后执行现有同步脚本；ZIP由新Core生成，可独立导入。
本任务未自动修改活动库或部署游戏；第一人称视觉效果仍待用户实机验收。
'''
 out=TARGET/'test07-第一人称挂点旁路-1.0.13-待测试.zip'
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
 result=dict(status='PASS_PENDING_GAME_TEST',luaVersion='1.0.13',package=str(out),packageSha256=sha(out.read_bytes()),
  acceptedGripCodeUnchanged=True,firstPersonPoseWrites=False,firstPersonCacheMaintenance=True,
  visibilityOrLinksChanged=False,companionNodes=248,unchangedCompanions=companions,sourceSha256=sha(source),
  installedCoreSha256=sha(installed.read_bytes()),installedCoreMatchesPublished=True,
  composedEmbeddedSourcesMatchCurrent=True,pipelineVersion=info['pipelineVersion'],singleSkeletonPipelineVersion=info['singleSkeletonPipelineVersion'],
  newDirectoriesCreated=False,modelRebaked=False,animationRebaked=False,gameDeployed=False,gameTested=False)
 (TARGET/'第一人称门禁-包验证.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
