"""B7 runtime plus bounded, read-only actual scene graph observation."""
import copy
import os
import shutil
import struct
import zipfile
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from native_model_arm_locals import with_model_arm_locals
from anim_batch_mod.archive import TocArchive

W=ROOT/'outputs/native-v18-20261104'
R=ROOT/'outputs/native-manual-20261103'
P=R/'project'
PACKAGE='AB测试/B9-只读父空间观测.zip'


def main():
    W.mkdir(exist_ok=True)
    baseline=load(R/'delivery-verification.json')
    assert baseline['status']=='PASS' and baseline['revision']=='native-v17'
    if not (W/'baseline-delivery.json').exists():save_json(W/'baseline-delivery.json',baseline)
    assert baseline==load(W/'baseline-delivery.json')
    control=load(P/'diagnostics/B7/B7.json')
    model_patch=P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0'
    models=units(model_patch)
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    metadata=with_model_arm_locals(control,avatar,models)['modelArmLocalLayouts']
    profile=copy.deepcopy(control)
    profile['revision']='test01-v18-B9'
    profile['sceneObservation']=dict(enabled=True,intervalSeconds=3,maxSamples=90,layouts=metadata)
    assert not profile.get('modelArmLocalSync')
    reduced=copy.deepcopy(profile);reduced.pop('sceneObservation');reduced['revision']=control['revision']
    assert reduced==control
    save_json(W/'B9.json',profile)
    save_json(W/'model-arm-topology.json',dict(status='PASS',models=len(metadata),nodesPerModel=8,
        rows=metadata,modelPatchSha256=digest(model_patch),purpose='read-only node identity; runtime parent unknown'))
    before=(P/'diagnostics/B7/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    observer=(ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua').read_text(encoding='utf-8-sig')
    prelude='-- BEGIN READ ONLY SCENE OBSERVER\nlocal SceneObserver=(function()\n'+observer+'\nend)()\n-- END READ ONLY SCENE OBSERVER\n'
    init=''' local sceneObserver=nil
 do
  local ok,value=pcall(SceneObserver.new,S,profile,self.logger)
  if ok then sceneObserver=value else pcall(self.logger,'[scene_probe] init_unavailable: %s',tostring(value))end
 end
 function self:observe_scene(phase,owners)
  if not sceneObserver then return end
  local ok,err=pcall(sceneObserver.capture,sceneObserver,self.frame,self.lastTime,phase,
   self.avatars,self.armor,owners,alive,visible,resource)
  if not ok and (self.sceneErrors or 0)<3 then
   self.sceneErrors=(self.sceneErrors or 0)+1
   pcall(self.logger,'[scene_probe] capture_unavailable: %s',tostring(err))
  end
 end
'''
    edits=[("local M={VERSION='0.10.1'}",prelude+"local M={VERSION='0.10.3'}"),
        (' function self:tick(frame)',init+' function self:tick(frame)'),
        ('  local active=0\n','  self:observe_scene(\'pre_apply\',modelOwners)\n  local active=0\n'),
        ("  emit('selection','active='", "  self:observe_scene('post_refresh',modelOwners)\n  emit('selection','active='")]
    after=before
    for old,new in edits:assert after.count(old)==1;after=after.replace(old,new)
    reverse=after
    for old,new in reversed(edits):reverse=reverse.replace(new,old)
    assert reverse==before
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    if not (W/'native_attachments-before-B8.lua').exists():
        assert digest(source)=='bd3d18d3fd663dd00f99f7f3804eb77836fc16376cdbbdb7cb782f9f4f2e80c9'
        shutil.copy2(source,W/'native_attachments-before-B8.lua')
    source.write_text(after,encoding='utf-8',newline='\n')
    with zipfile.ZipFile(R/'AB测试/B7-补齐切分部位刷新.zip') as z:
        binary=z.read('9ba626afa44a3aa3.patch_0');manifest=__import__('json').loads(z.read('manifest.json'))
    entry=next(iter(TocArchive.parse_parts(binary).entries.values()))
    original=entry.toc_data[8:].decode('utf-8-sig').replace('\r\n','\n')
    assert original.count(before)==1
    start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
    end=original.index('\nend)()',start);old_profile=original[start:end]
    new_profile='-- B9 observation metadata; no model-local writes.\nreturn '+lua(profile)+'\n'
    code=original.replace(before,after).replace(old_profile,new_profile)
    assert code.replace(after,before).replace(new_profile,old_profile)==original
    data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data
    patch=bytearray(binary[:192])+payload;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
    assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data==payload
    dest=W/'runtime/B9';dest.mkdir(parents=True,exist_ok=True)
    main_patch=dest/'9ba626afa44a3aa3.patch_0';main_patch.write_bytes(patch)
    for suffix in ('.stream','.gpu_resources'):__import__('pathlib').Path(str(main_patch)+suffix).write_bytes(b'')
    manifest.update(Name='test01 v15 动画配套 B9 — 只读父空间观测',
        Description='B7 稳定基准加限量只读诊断。保持 v15 动画；一次只启用一个 test01 Lua。')
    save_json(dest/'manifest.json',manifest)
    shutil.copy2(ROOT/'docs/native-v18-B9-20261104.md',dest/'测试说明.txt')
    (W/'hd2physbone-B9.lua').write_bytes(data)
    pack.WORK=W;save_json(W/'static-packages.json',[pack.archive(PACKAGE,files(dest))])
    save_json(W/'feedback.json',dict(v15Animation='user-confirmed-normal',B7=dict(
        grip='same-as-no-Lua',samplePouch='stable',splitParts='no-seams'),B8=dict(
        status='tested-failed',hands='stretched-thin',grip='no-improvement'),B9GameTested=False))
    save_json(W/'scope-audit.json',dict(status='PASS',control='v16-B7',probe='v18-B9',
        reversibleInsertionExactlyMatchesB7=True,observerReadOnly=True,sameArmSolver=True,
        sameTargets=True,sameAttachmentRules=True,samePhysics=True,callback='render',
        animationSha256=digest(R/'test01-配套动画.zip'),sourceSha256=digest(source),
        observerSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua'),gameTested=False))
    print('B9 prepared: B7 exact runtime baseline + bounded read-only observer; accepted animation unchanged.')


if __name__=='__main__':main()
