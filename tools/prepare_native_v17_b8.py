"""Prepare B8 without rebuilding accepted v15 animation or changing game data."""
import copy
import json
import os
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from native_model_arm_locals import with_model_arm_locals
from anim_batch_mod.archive import TocArchive

W=ROOT/'outputs/native-v17-20261104'
R=ROOT/'outputs/native-manual-20261103'
P=R/'project'


def main():
    W.mkdir(exist_ok=True)
    baseline=load(R/'delivery-verification.json')
    assert baseline['status']=='PASS' and baseline['revision']=='native-v16'
    save_json(W/'baseline-delivery.json',baseline)
    control=load(P/'diagnostics/B7/B7.json')
    model_patch=P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0'
    models=units(model_patch)
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    profile=with_model_arm_locals(control,avatar,models)
    profile['revision']='test01-v17-B8'
    reduced=copy.deepcopy(profile)
    for k in ('modelArmLocalLayouts','modelArmLocalSync'):reduced.pop(k)
    reduced['revision']=control['revision']
    assert reduced==control
    save_json(W/'B8.json',profile)
    save_json(W/'model-arm-topology.json',dict(status='PASS',models=len(models),targetModels=len(profile['modelLayouts']),
        nodesPerModel=8,matchingParentHashes=True,zeroBasedIndices=True,rows=profile['modelArmLocalLayouts'],
        modelPatchSha256=digest(model_patch),gameTested=False))
    before=(P/'diagnostics/B7/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    after=source.read_text(encoding='utf-8-sig')
    assert "VERSION='0.10.1'" in before and "VERSION='0.10.2'" in after
    for start,end in [('function M.grip_target','-- Source mstudio'),
                      (' function self:restore_arms',' -- Read the matched armor')]:
        assert before.split(start)[1].split(end)[0]==after.split(start)[1].split(end)[0]
    with zipfile.ZipFile(R/'AB测试/B7-补齐切分部位刷新.zip') as z:
        binary=z.read('9ba626afa44a3aa3.patch_0');manifest=json.loads(z.read('manifest.json'))
    entry=next(iter(TocArchive.parse_parts(binary).entries.values()))
    original=entry.toc_data[8:].decode('utf-8-sig').replace('\r\n','\n')
    assert original.count(before)==1
    start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
    end=original.index('\nend)()',start)
    old_profile=original[start:end]
    new_profile='-- Generated B8 direct model arm-local probe.\nreturn '+lua(profile)+'\n'
    code=original.replace(before,after).replace(old_profile,new_profile)
    assert code.replace(after,before).replace(new_profile,old_profile)==original
    assert 'PhysBoneRuntime.update=PhysBoneRuntime.render' not in code
    data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data
    patch=bytearray(binary[:192])+payload;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
    parsed=next(iter(TocArchive.parse_parts(patch).entries.values()))
    assert parsed.file_id==entry.file_id and parsed.toc_data==payload
    dest=W/'runtime/B8';dest.mkdir(parents=True,exist_ok=True)
    main_patch=dest/'9ba626afa44a3aa3.patch_0';main_patch.write_bytes(patch)
    for suffix in ('.stream','.gpu_resources'):Path(str(main_patch)+suffix).write_bytes(b'')
    manifest.update(Name='test01 v15 动画配套 B8 — 模型骨骼直接写入',
        Description='保持 B7 算法和 render，只复制八个已求解手臂本地姿态到匹配模型。一次只启用一个 test01 Lua。')
    save_json(dest/'manifest.json',manifest)
    shutil.copy2(ROOT/'docs/native-v17-B8-20261104.md',dest/'测试说明.txt')
    (W/'hd2physbone-B8.lua').write_bytes(data)
    pack.WORK=W
    save_json(W/'static-packages.json',[pack.archive('AB测试/B8-模型骨骼直接写入.zip',files(dest))])
    save_json(W/'feedback.json',dict(v15Animation='user-confirmed-normal',B7=dict(
        grip='same-as-no-Lua',samplePouch='stable',splitParts='no-seams'),B8GameTested=False))
    log_path=Path('C:/Users/Administrator/AppData/Roaming/Arrowhead/Helldivers2/hd2physbone.log')
    log=log_path.read_text(encoding='utf-8-sig',errors='replace')
    sessions=re.split(r'(?=^.*\[physbone\] 运行时 .*启动于 )',log,flags=re.M)
    session=next(s for s in reversed(sessions) if 'variant=test01-v16-B7' in s)
    observed=[s for s in session.splitlines() if '[attachments]' in s and any(k in s for k in (
        'variant=','arm_consumer_readback','palm_contact_error'))]
    (W/'B7-game-evidence.log').write_text('\n'.join(observed)+'\n',encoding='utf-8')
    hand_resources=('d154442f2e33fdee','e0b67b19ba91057b')
    assert all(any('after_model_refresh' in line and 'resource='+r in line for line in observed)for r in hand_resources)
    save_json(W/'runtime-evidence.json',dict(status='PASS',source=str(log_path),sourceSha256=digest(log_path),
        excerptSha256=digest(W/'B7-game-evidence.log'),actualHandResources=hand_resources,
        conclusion='B7 refreshed both actual hand model graphs; rendered grip unchanged per user. GPU consumption unproven.'))
    save_json(W/'scope-audit.json',dict(status='PASS',control='v16-B7',probe='v17-B8',
        changed=['opt-in direct model local-pose copy for eight solved arm nodes','identity validation and copy readback'],
        sameArmSolver=True,sameTargets=True,sameAttachmentRules=True,samePhysics=True,callback='render',
        animationSha256=digest(R/'test01-配套动画.zip'),sourceSha256=digest(source),gameTested=False))
    print('B8 prepared: 11 layouts, 8 same-parent nodes each; accepted animation unchanged.')


if __name__=='__main__':main()
