"""B9 stable runtime plus same-model local roundtrip; never change targets."""
import copy
import json
import os
import shutil
import struct
import zipfile
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files,lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.archive import TocArchive
W=ROOT/'outputs/native-v19-20261104';R=ROOT/'outputs/native-manual-20261103';P=R/'project'


def main():
    W.mkdir(exist_ok=True);baseline=load(R/'delivery-verification.json')
    assert baseline['status']=='PASS'and baseline['revision']=='native-v18'
    if not(W/'baseline-delivery.json').exists():save_json(W/'baseline-delivery.json',baseline)
    assert baseline==load(W/'baseline-delivery.json')
    findings=load(ROOT/'outputs/native-b9-observation-20261104/game-findings.json')
    assert findings['status']=='PASS' and findings['allObservedRuntimeParentsNil']
    assert findings['effectiveParentMatchesAvatarSameBoneExactly']and findings['modelWorldMatchesAvatarSameBoneExactly']
    save_json(W/'B9-game-findings.json',findings)
    before=(P/'diagnostics/B9/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    module=(ROOT/'HD2PhysBoneCompat/src/native_scene_roundtrip.lua').read_text(encoding='utf-8')
    control=load(P/'diagnostics/B9/B9.json');profile=copy.deepcopy(control)
    profile['revision']='test01-v19-B10'
    profile['sceneRoundtrip']=dict(enabled=True,mode='same_model_local',layouts=copy.deepcopy(control['sceneObservation']['layouts']))
    reduced=copy.deepcopy(profile);reduced.pop('sceneRoundtrip');reduced['revision']=control['revision'];assert reduced==control
    save_json(W/'B10.json',profile)
    init=''' local sceneRoundtrip=nil
 do
  local ok,value=pcall(SceneRoundtrip.new,S,profile,self.logger)
  if ok then sceneRoundtrip=value else pcall(self.logger,'[scene_roundtrip] init_unavailable: %s',tostring(value))end
 end
 function self:roundtrip_scene(owners)
  if not sceneRoundtrip then return end
  local ok,err=pcall(sceneRoundtrip.tick,sceneRoundtrip,self.frame,self.lastTime,
   self.avatars,self.armor,owners,alive,visible,resource,options.settleFrames or 10)
  if not ok then
   sceneRoundtrip.disabled=true
   pcall(self.logger,'[scene_roundtrip] unexpected_error_disabled: %s',tostring(err))
  end
 end
'''
    prelude='-- BEGIN SAME MODEL LOCAL ROUNDTRIP\nlocal SceneRoundtrip=(function()\n'+module+'\nend)()\n-- END SAME MODEL LOCAL ROUNDTRIP\n'
    edits=[("local M={VERSION='0.10.3'}",prelude+"local M={VERSION='0.10.4'}"),
        (' function self:tick(frame)',init+' function self:tick(frame)'),
        ("  self:observe_scene('post_refresh',modelOwners)","  self:roundtrip_scene(modelOwners)\n  self:observe_scene('post_refresh',modelOwners)")]
    after=before
    for old,new in edits:assert after.count(old)==1;after=after.replace(old,new)
    reverse=after
    for old,new in reversed(edits):reverse=reverse.replace(new,old)
    assert reverse==before
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    if not(W/'native_attachments-before-B9.lua').exists():
        assert digest(source)==digest(P/'diagnostics/B9/src/native_attachments.lua');shutil.copy2(source,W/'native_attachments-before-B9.lua')
    source.write_text(after,encoding='utf-8',newline='\n')
    with zipfile.ZipFile(R/'AB测试/B9-只读父空间观测.zip')as z:
        binary=z.read('9ba626afa44a3aa3.patch_0');manifest=json.loads(z.read('manifest.json'))
    entry=next(iter(TocArchive.parse_parts(binary).entries.values()))
    original=entry.toc_data[8:].decode('utf-8-sig').replace('\r\n','\n');assert original.count(before)==1
    start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
    end=original.index('\nend)()',start);old_profile=original[start:end]
    new_profile='-- B10 same-model local roundtrip only.\nreturn '+lua(profile)+'\n'
    code=original.replace(before,after).replace(old_profile,new_profile)
    assert code.replace(after,before).replace(new_profile,old_profile)==original
    data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data
    patch=bytearray(binary[:192])+payload;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
    assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data==payload
    dest=W/'runtime/B10';dest.mkdir(parents=True,exist_ok=True);main_patch=dest/'9ba626afa44a3aa3.patch_0';main_patch.write_bytes(patch)
    for suffix in('.stream','.gpu_resources'):Path(str(main_patch)+suffix).write_bytes(b'')
    manifest.update(Name='test01 v15 动画配套 B10 — 模型自身姿态原样回写',Description='B9 基准，限频原样回写模型自身 local，检查同帧结果并在失败时回滚。一次仅启用一个 test01 Lua。')
    save_json(dest/'manifest.json',manifest);shutil.copy2(ROOT/'docs/native-v19-B10-20261104.md',dest/'测试说明.txt')
    (W/'hd2physbone-B10.lua').write_bytes(data);pack.WORK=W
    save_json(W/'static-packages.json',[pack.archive('AB测试/B10-模型自身姿态原样回写.zip',files(dest))])
    save_json(W/'scope-audit.json',dict(status='PASS',control='v18-B9',probe='v19-B10',
        reversibleInsertionExactlyMatchesB9=True,sameArmSolver=True,sameTargets=True,samePhysics=True,
        sameAttachmentRules=True,callback='render',animationSha256=digest(R/'test01-配套动画.zip'),
        sourceSha256=digest(source),roundtripSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_scene_roundtrip.lua'),
        observerSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua'),gameTested=False))
    save_json(W/'feedback.json',dict(B9=findings['userVisualFeedback'],B10GameTested=False))
    print('B10 prepared: B9 baseline + same-model local roundtrip; v15 animation unchanged.')


if __name__=='__main__':main()
