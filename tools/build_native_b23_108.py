"""Incrementally build/audit/package B23 1.0.8 pending-game-test; never deploy."""
from __future__ import annotations
import json
import argparse
import tomllib
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

import prepare_native_v31_b23 as builder
import audit_native_v31_b23 as audit
import audit_native_v31_b23_chef as chef
from repack_native_b23 import build as repack
from audit_native_b23_107_issues import PACKAGE as BASE_PACKAGE, plain
from anim_batch_mod.formats import UnitData

ROOT=builder.ROOT
W=ROOT/'outputs/native-v35-b23-108-pending-20261105'
NAME='B23LR-M-多武器握持修正-1.0.8-待测试.zip'
PROJECT_NAME='B23LR-M-多武器握持测试工程-1.0.8-待测试.zip'
PROJECT_DIR=None


def configure():
    global PROJECT_DIR,W,BASE_PACKAGE
    parser=argparse.ArgumentParser(description='Build frozen test01 1.0.8 project without rebaking animations or deploying')
    parser.add_argument('--project',type=Path,default=ROOT/'projects/test01-native-grip')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if (args.project/'project.json').is_file():
        PROJECT_DIR=args.project.resolve();spec=builder.load(PROJECT_DIR/'project.json')
        if spec['projectId']!='test01-native-grip' or spec['version']!='1.0.8':raise ValueError('Wrong archived project/version')
        BASE_PACKAGE=(PROJECT_DIR/spec['baseline']).resolve()
        if spec.get('baselineSha256') and builder.digest(BASE_PACKAGE)!=spec['baselineSha256']:
            raise ValueError('Archived baseline changed; refusing to execute altered regression fixture')
        W=(args.output or PROJECT_DIR/spec['buildOutput']).resolve()
    elif args.output:
        W=args.output.resolve()
    if not W.is_relative_to(ROOT.resolve()):raise ValueError('Build output must remain within HD2ModManager')


def prepare():
    W.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(BASE_PACKAGE) as z:
        profile=json.loads(z.read('B23-profile.json').decode('utf-8-sig'))
        fixture=json.loads(z.read('runtime-fixture.json').decode('utf-8-sig'))
        # Copy only known inputs/companions, never unrelated historical reports.
        names=['container-header.bin','v30-avatar.toc','runtime-avatar.toc','native-parenting.json',
            'wrist-registration.json','weapon-targets.json','runtime-fixture.json','legacy-arm-math.lua']
        names += [f'9ba626afa44a3aa3.patch_{n}{suffix}' for n in (4,5) for suffix in ('','.stream','.gpu_resources')]
        for name in names:(W/name).write_bytes(z.read(name))
    if PROJECT_DIR:
        spec=builder.load(PROJECT_DIR/'project.json')
        profile=builder.load(PROJECT_DIR/spec['profile'])
        components=builder.load(PROJECT_DIR/spec['components'])
        shutil.copy2(PROJECT_DIR/spec['observedParts'],W/'observed-marked-parts.json')
    else:
        profile['variant']='test01-v35-B23LR-M-1.0.8-pending'
        profile['packageName']=NAME
        profile['performance']=dict(strictConsumers=True,cacheIdentity=True,scopedRefresh=True,batchRefresh=True,refreshRadius=1.5)
        profile['previewGuard']=dict(enabled=True,minimumWorldUnits=128)
        profile['leftGrip']['intent']=dict(enabled=True,primaryEnterMetres=.10,primaryLeaveMetres=.14,
            sidearmEnterMetres=.035,sidearmLeaveMetres=.055,
            weaponThresholds={'a955c4ea6f6d4203':dict(enterMetres=.14,leaveMetres=.18)},
            semantics='experimental unswapped-native-hand pose proxy; NOT true ADS/reload flags')
        survey=builder.load(ROOT/'outputs/native-weapon-survey-20261105/weapon-grip-survey.json')
        allowed=set(profile['leftGrip']['weaponTargets'])|{r['resource'] for r in survey['accessories']}
        allowed|={r['resource'] for r in fixture['carried']}
        # Verified hand-carried items from the live audit, not arbitrary ship props.
        allowed|={'1c8764d62e12925a','a9936cbe561e8180'}
        # Retain marker-verified parts actually seen with 1.0.7. This excludes the
        # generic linked_item category containing ship infrastructure.
        observed_path=W/'observed-marked-parts.json'
        if observed_path.exists():
            observed=set(builder.load(observed_path)['resources'])
        else:
            log=Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2/hd2_grip_b23.log')
            observed=set();active=False
            for line in log.open(encoding='utf-8'):
                row=json.loads(line[line.index('{'):])
                if row.get('event')=='loaded':active=row.get('version')=='1.0.7'
                if active and row.get('event')=='consumer' and row.get('kind') in {
                    'weapon_magazine','weapon_optic','weapon_grip','weapon_underbarrel','weapon_muzzle','foregrip'}:
                    observed.add(row['resource'])
            builder.save(observed_path,dict(resources=sorted(observed),source=str(log),scope='marker-confirmed parts only; no generic linked_item props'))
        allowed|=observed
        profile['allowedConsumers']={key:True for key in sorted(allowed)}
        components=[]
        from probe_native_b18_components import SPECS
        for resource,spec in SPECS.items():
            unit=UnitData.parse((ROOT/f'outputs/native-v26-b18-20261105/assets/{resource}.toc').read_bytes())
            nodes=[dict(row,hash=unit.name_hashes[row['index']],parent=unit.parents[row['index']]) for row in spec['signature']]
            profile['consumers'][resource]=dict(kind='weapon_magazine',resource=resource,count=spec['count'],
                nodes=nodes,root=spec['markerIndex'],order=1)
            components.append(dict(resource=resource,hashes=unit.name_hashes,parents=unit.parents,matrices=builder.matrices(unit)))
        profile['sync']['enabled']=False
        profile['logSeconds']=1.0;profile['maxRecords']=5000
        profile['diagnostics']=dict(consumers=False)
    builder.save(W/'B23-profile.json',profile)
    if PROJECT_DIR:
        builder.save(W/'manifest.json',builder.load(PROJECT_DIR/'config/manifest.json'))
    else:
        builder.save(W/'manifest.json',dict(Version=1,Guid=str(uuid.uuid5(uuid.NAMESPACE_URL,'hd2:test01:B23LR-M:1.0.8-pending')),
            Name='[骨骼挂点修正]test01 B23-LR-M 1.0.8 待测试',
            Description='1.0.7 增量待测：消费者收窄/批刷新、原生左手姿态代判定、纪元精确部件、预览小世界隔离。不是实机验收版；停用旧 B23 两组补丁。'))
    (W/'测试说明.md').write_text(TEST_INSTRUCTIONS,encoding='utf-8')
    (W/'hd2attachmentfix-B23.lua').write_bytes(builder.compose_source(profile).encode('utf-8'))
    for name in ('native_grip_transfer_test.lua','native_grip_transfer_test_entry.lua','attachment_fix_runtime.lua'):
        target=W/'src'/name;target.parent.mkdir(exist_ok=True);shutil.copy2(builder.SRC/name,target)
    shutil.copy2(ROOT/'tools/repack_native_b23.py',W/'repack_native_b23.py')
    result=repack(W)
    for folder,number in (('runtime',4),('native-parenting',5)):
        (W/folder).mkdir(exist_ok=True)
        for suffix in ('','.gpu_resources','.stream'):
            name=f'9ba626afa44a3aa3.patch_{number}{suffix}';shutil.copy2(W/name,W/folder/name)
    (W/'physics-companion').mkdir(exist_ok=True)
    for name in ('9ba626afa44a3aa3.patch_3','9ba626afa44a3aa3.patch_3.gpu_resources','9ba626afa44a3aa3.patch_3.stream'):
        shutil.copy2(ROOT/'outputs/native-v34-b23-integrated-20261105/physics-companion'/name,W/'physics-companion'/name)
    builder.save(W/'build-audit.json',dict(result,status='PASS',basePackageSha256=builder.digest(BASE_PACKAGE),
        parentingByteIdenticalTo107=True,sourceVersion='1.0.8',gameTested=False,
        experimentalPolicies=profile['leftGrip']['intent'],previewGuard=profile['previewGuard']))
    return profile,fixture,components


def test(profile,fixture,components):
    with zipfile.ZipFile(BASE_PACKAGE) as z:
        original_profile=json.loads(z.read('B23-profile.json').decode('utf-8-sig'))
        harness=z.read('test/native_grip_transfer_harness.lua').decode('utf-8-sig').replace(
            '-- STRICT_ID_FIXTURE',z.read('test/strict_id32_fixture.lua').decode('utf-8-sig'))
    tail=harness.rindex('\nreturn {integratedCases=')
    extension=(ROOT/'HD2PhysBoneCompat/test/native_grip_transfer_108_harness.lua').read_text(encoding='utf-8-sig')
    extra='\nlocal candidate_profile='+builder.lua(profile)+'\nlocal candidate_components='+builder.lua(components)+'\n'+extension
    result=plain(audit.run_harness(original_profile,fixture,harness[:tail]+extra))
    logs=result.pop('logs')
    (W/'runtime-fixture.log').write_text('\n'.join(logs),encoding='utf-8')
    builder.save(W/'runtime-audit.json',result)
    audit.W=W;chef.W=W
    if PROJECT_DIR:
        from anim_batch_mod.attachment_skeleton import validate_attachment_transfer_contract
        from anim_batch_mod.formats import BonesData
        from anim_batch_mod.archive import TocArchive
        from anim_batch_mod.constants import BONE_TYPE_ID
        spec=builder.load(PROJECT_DIR/'project.json')
        patch=TocArchive.parse_parts((W/'9ba626afa44a3aa3.patch_5').read_bytes(),
            (W/'9ba626afa44a3aa3.patch_5.gpu_resources').read_bytes(),b'')
        bones=BonesData.parse(next(e.toc_data for e in patch.entries.values() if e.type_id==BONE_TYPE_ID))
        contract=validate_attachment_transfer_contract(profile,UnitData.parse((W/'runtime-avatar.toc').read_bytes()),bones,
            builder.load(PROJECT_DIR/spec['sourceSkeleton']),
            tomllib.loads((PROJECT_DIR/spec['animationConfig']).read_text(encoding='utf-8-sig'))['attachment_swap'])
        contract.update(tested108PayloadUnchanged=True,animationRebaked=False,futureBakeStage='after-final-arm-reference')
        builder.save(W/'attachment-contract-audit.json',contract)
    audit.parenting_check()
    audit.registration_animation_check()
    chef.main(version="1.0.8")


def package():
    delivery=W/'交付';delivery.mkdir(exist_ok=True)
    # Existing repacker builds the runtime ZIP and preserves both patch groups.
    repack(W);shutil.copy2(W/'rebuilt'/NAME,delivery/NAME)
    files=['hd2attachmentfix-B23.lua','repack_native_b23.py','manifest.json','测试说明.md','container-header.bin',
        'B23-profile.json','runtime-fixture.json','native-parenting.json','runtime-avatar.toc','v30-avatar.toc',
        'legacy-arm-math.lua','wrist-registration.json','weapon-targets.json','observed-marked-parts.json']
    files += [f'9ba626afa44a3aa3.patch_{n}{suffix}' for n in (4,5) for suffix in ('','.gpu_resources','.stream')]
    with zipfile.ZipFile(delivery/PROJECT_NAME,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in files:z.write(W/name,name)
        for path in (W/'src').iterdir():z.write(path,'src/'+path.name)
        for name in ('runtime-audit.json','chef-audit.json','build-audit.json','native-parenting-audit.json','packaged-animation-axis-audit.json'):
            z.write(W/name,'reports/'+name)
        z.write(ROOT/'HD2PhysBoneCompat/test/native_grip_transfer_108_harness.lua','test/native_grip_transfer_108_harness.lua')
        z.write(ROOT/'tools/build_native_b23_108.py','tools/build_native_b23_108.py')
    for path in delivery.glob('*.zip'):
        with zipfile.ZipFile(path) as z:assert z.testzip() is None
    from audit_native_v31_b23_import import audit_project_package
    import_status=[]
    for index,name in enumerate((NAME,PROJECT_NAME)):
        try:
            audit_project_package(delivery/name,W/f'import-{index}',require_project_source=index==1)
            import_status.append(dict(package=name,status='PASS'))
        except AssertionError as error:
            if 'ManagerProcessRunning' not in str(error):raise
            # Never close the user's manager or bypass its global write guard.
            import_status.append(dict(package=name,status='SKIPPED_MANAGER_ACTIVE',
                reason='Manager process is running; no library writes performed'))
            print('IMPORT SKIPPED (manager active):',name)
    builder.save(W/'delivery-verification.json',dict(status='PASS_OFFLINE_IMPORT_SKIPPED' if any(r['status']!='PASS' for r in import_status) else 'PASS_PENDING_GAME_TEST',
        importStatus=import_status,
        packages=[dict(path=str(p),sha256=builder.digest(p),bytes=p.stat().st_size) for p in delivery.glob('*.zip')],
        basePackageSha256=builder.digest(BASE_PACKAGE),gameDeployed=False,gameTested=False,
        previewFingerRootCauseFixed=False,adsIsPoseProxy=True))
    print('DELIVERY',delivery)


TEST_INSTRUCTIONS='''# B23-LR-M 1.0.8 待测试

这是在 1.0.7 上增量修正的实验版，不是五项实机验收通过版。

## 安装
- “修正 ZIP”和“测试工程 ZIP”含同一套补丁，只选一个导入；工程 ZIP 可修改 Lua 后运行 repack_native_b23.py 重打。
- 停用旧 B23 1.0.7/其他 B23 两组补丁，避免 Lua 或 Avatar/Bones 混用。不要同时启用两份新包。
- 保留 test01 原模型、B22 动画及原有必要配套。独立物理包未改，不要拿后一个物理会话的帧率和本包混淆。
- 本次仅替换 Lua，Avatar/Bones 与 1.0.7 字节相同；没有改模型、动画、权重或骨长。
- 导入后重新部署并完全重启游戏。本次没有替你部署。

## 改动和边界
1. 消费者只允许已知武器、配件、已验证手持物及精确独立弹药布局；移除普通船舱 skeleton/game_mesh 物件的泛化识别。身份检查按单次 render 缓存；模型按匹配 Avatar 限定，消费者按两手附近限定；合并部分刷新阶段，关闭重型 sync/消费者矩阵日志。仍每帧验证真实世界成员，避免缓存过期后写错世界。
2. 左手使用“未互换的原生右挂点 + 当前武器自己的动态 IK_left”重建原生意图。主武器/GP-20 超出 10 cm 进入、14 cm 保持范围时释放；其他副武器用 3.5/5.5 cm。AR/GL-21 旧日志握持距离中位约 10.66 cm，单独采用 14/18 cm，避免 10 cm 通用门槛误释放。采用滞回避免门槛抖动。这是姿态代判定，**不是读取了真正 ADS/换弹标志**，必须实测阈值、切换延迟和误释放。
3. 恢复纪元候选 52ff81fcba0c059d、火焰喷射器燃料罐 9c22a90da9c79de3 的精确签名和枪体后刷新。部件 local pose 和引擎转接均不改；视觉身份/效果仍待测试。
4. 少于 128 个 Unit 的小世界跳过本套姿态写入，隔离已观察到 33 Unit 的预览世界；不硬编码 world 11。**不代表已修好手指蒙皮/LOD 根因**；也可能跳过其他小规模世界，属于保守试验。

## 建议按顺序测试并反馈
- 船上同地点、同视角、同画质：旧版/新版 FPS；打开 Chef F9 看 attachment_fix 平均和最高 ms。
- 主武器普通持枪、瞄准、跑动、换弹：左手换弹是否恢复，握持是否意外脱离或抖动。
- GP-20 普通与瞄准仍双手、换弹可操作；其他副武器普通左手分离，瞄准再贴合，切换是否滞后。
- PLAS-45 纪元及 FLAM-40：静止、射击、换弹三种状态的独立弹药部件是否跟随；不要只看静止一次。
- 军械库：两侧手指、手腕、上身是否正常。若仍拉伸，说明需要继续查骨架/动画/蒙皮，不能再归因于预览中的本套左 IK。

退出游戏后保留 hd2_grip_b23.log 和 chef_loader.log，并说明各项结果。新日志仍用原文件名，loaded 版本为 1.0.8、variant 为 test01-v35-B23LR-M-1.0.8-pending，left_skipped 内含 intent 距离/阈值。
'''

if __name__=='__main__':
    configure();profile,fixture,components=prepare();test(profile,fixture,components);package()
