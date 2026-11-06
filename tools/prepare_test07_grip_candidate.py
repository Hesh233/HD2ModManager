"""Prepare/package the exact current test07 Lua companion without rebaking or deploying."""
import argparse,copy,hashlib,json,shutil,struct,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.native_config import apply_grip_fixes
from anim_batch_mod.archive import TocArchive,InlinePatchWriter
from anim_batch_mod.attachment_skeleton import sidearm_right_outputs
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData
from prepare_native_v31_b23 import lua
SOURCE=ROOT/'outputs/test07-grip-fix-20261106/candidate'
OUT=ROOT/'outputs/test07-sidearm-fix-111-20261106'

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy_preserved(source,destination):
    # copy2 preserves immutable-library flags. Repeated builds must not try to
    # rewrite an identical read-only companion or clear any library protection.
    if destination.exists() and digest(source)==digest(destination):return
    shutil.copy2(source,destination)

def main():
    args=argparse.ArgumentParser();args.add_argument('--package',action='store_true');args=args.parse_args()
    OUT.mkdir(exist_ok=True)
    if not args.package:
        profile=apply_grip_fixes(json.loads((SOURCE/'attachment-profile.json').read_text(encoding='utf-8-sig')))
        profile['variant']=profile['variant'].replace('1.0.10','1.0.11')+'-native-right'
        rig=TocArchive.parse_parts((SOURCE/'9ba626afa44a3aa3.patch_1').read_bytes(),(SOURCE/'9ba626afa44a3aa3.patch_1.gpu_resources').read_bytes(),(SOURCE/'9ba626afa44a3aa3.patch_1.stream').read_bytes())
        avatar=UnitData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID))
        assert len(avatar.parents)==profile['avatar']['count']==245
        assert len([e for e in rig.entries.values() if e.type_id==BONE_TYPE_ID])==1
        ue=next(e for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID)
        be=next(e for e in rig.entries.values() if e.type_id==BONE_TYPE_ID)
        raw,bones,layout=sidearm_right_outputs(ue.toc_data,be.toc_data,profile)
        candidate=OUT/'candidate-111';candidate.mkdir(exist_ok=True)
        writer=InlinePatchWriter(TocArchive(0,bytes(56),{}),candidate/'9ba626afa44a3aa3.patch_1',
            {UNIT_TYPE_ID:1,BONE_TYPE_ID:1},standalone=True)
        for entry,data in ((ue,raw),(be,bones)):
            edited=copy.deepcopy(entry);edited.toc_data=bytearray(data);writer.append(edited)
        writer.finish()
        assert profile['avatar']['count']==248
        (OUT/'right-output-layout.json').write_text(json.dumps(layout,indent=2),encoding='utf-8')
        (OUT/'attachment-profile.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
        (OUT/'attachment-profile.lua').write_text('return '+lua(profile)+'\n',encoding='utf-8')
        print('Prepared actual test07 profile + 248-node companion; native/left/model/animation contracts preserved');return
    candidate=OUT/'candidate-111'
    old=TocArchive.parse_parts((SOURCE/'9ba626afa44a3aa3.patch_0').read_bytes(),load_external_data=False)
    new=TocArchive.parse_parts((candidate/'9ba626afa44a3aa3.patch_0').read_bytes(),load_external_data=False)
    assert set(old.entries)==set(new.entries)
    payload=bytes(next(iter(new.entries.values())).toc_data);n,version=struct.unpack_from('<II',payload)
    code=(candidate/'hd2attachmentfix.lua').read_bytes();assert version==2 and payload[8:8+n]==code
    assert b"VERSION = '1.0.11'" in code and b"VERSION = '1.0.10'" not in code and b'-- INSERT ' not in code
    companions={}
    for name in ['9ba626afa44a3aa3.patch_1'+s for s in ('','.gpu_resources','.stream')]:
        assert (candidate/name).is_file();companions[name]=digest(candidate/name)
    for name in ('attachment-fix.json',):
        copy_preserved(SOURCE/name,candidate/name)
    copy_preserved(OUT/'attachment-profile.json',candidate/'attachment-profile.json')
    copy_preserved(OUT/'right-output-layout.json',candidate/'right-output-layout.json')
    build_report=json.loads((SOURCE/'attachment-build-report.json').read_text(encoding='utf-8-sig'))
    build_report['sourceBuildPipelineVersion']=build_report.get('pipelineVersion')
    build_report.update(pipelineVersion='1.0.15',luaVersion='1.0.11',avatarNodes=248,
        rightArmOutputs=3,modelRebaked=False,animationRebaked=False,gameTested=False)
    build_report['rig']['rightSidearm']=json.loads((OUT/'right-output-layout.json').read_text(encoding='utf-8'))
    build_report['files']=[dict(name=name,sha256=digest(candidate/name)) for name in companions]
    (candidate/'attachment-build-report.json').write_text(json.dumps(build_report,ensure_ascii=False,indent=2),encoding='utf-8')

    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8-sig'))
    manifest['Description']='test07 Lua 1.0.11：保留副武器原生握持/瞄准路径，Source右臂未动画输出同步，P-4分阶段只读诊断；248节点配套，模型/动画不重烘，待实机验收。'
    (candidate/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    note='''# test07 副武器修正 1.0.11（待实机测试）

导入本ZIP更新同源test07挂点包，关闭旧1.0.10后部署；不要同时启用两个挂点版本。
保持模型 → 全量动画 → 本挂点包顺序，UNIT/BONES都必须由本包最终覆盖。
**本包骨架为248节点，新增3个未动画右臂输出。不能只换Lua，不能继续使用245节点旧配套。**
不重烘模型和全量动画；本包保留原生107节点、左臂/下挂、模型Unit和动画通道顺序。

- 被确认握在右手的副武器保持原生实时枪根，不再被拉到低位Source腕。
- Source右臂使用现有IK跟随实时IK_right；普通副武器左手仍仅按瞄准代判定，换弹/自由左手不锁。
- 收枪后释放右臂输出，重新持枪再跟随；不改原生瞄准骨，不改P-4弹巢旋转/装填局部动画。
- 下挂选择/左手求解规则保持1.0.10已确认实现。
- 日志right_applied、sidearm_aligned.policy；sidearm_probe采集Lua/原生两条路径及
  next_input/before_write/after_mount_refresh/final_output的P-4 root/IK/game_mesh/弹巢和独立部件。
- sidearm_probe只是只读图谱，不能冒充最终蒙皮验收；若P-4仍分离，用新日志定位具体支路。

游戏待测：P-4瞄准/跑动/换弹/收枪；其他副武器；GP-20双手；既有下挂；舰船往返。
本ZIP离线回归通过，不表示实机视觉已通过。未写入活动库、管理器安装目录或游戏目录。
管理器自动配套排序仍未修复，务必检查最终248节点配套胜出。
'''
    (candidate/'测试说明.md').write_text(note,encoding='utf-8')
    archive=OUT/'test07-副武器握持修正-1.0.11-待测试.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(candidate.iterdir()):
            if p.is_file() and p.suffix!='.lua':z.write(p,p.name)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    report=dict(status='PASS_PENDING_GAME_TEST',luaVersion='1.0.11',sourceDirectory=str(SOURCE),package=str(archive),packageSha256=digest(archive),
        luaSha256=digest(candidate/'hd2attachmentfix.lua'),companions=companions,rigNodes=248,rightOutputs=3,native107Preserved=True,leftRulesPreserved=True,
        pairedUnitBonesFinalWinnerRequired=True,avatarBindingModelCount=len(json.loads((OUT/'attachment-profile.json').read_text(encoding='utf-8'))['models']),
        composedByRebuiltCore=True,modelRebaked=False,animationRebaked=False,managerInstalled=False,gameDeployed=False,gameTested=False)
    (OUT/'package-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
