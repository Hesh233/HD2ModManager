"""B11 read-only grip motion observation after accepted B10 setter roundtrip."""
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
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.archive import TocArchive
W=ROOT/'outputs/native-v20-20261104';R=ROOT/'outputs/native-manual-20261103';P=R/'project'


def main():
    W.mkdir(exist_ok=True);baseline=load(R/'delivery-verification.json')
    assert baseline['status']=='PASS'and baseline['revision']=='native-v19'
    if not(W/'baseline-delivery.json').exists():save_json(W/'baseline-delivery.json',baseline)
    assert baseline==load(W/'baseline-delivery.json')
    findings=load(ROOT/'outputs/native-b10-observation-20261104/game-findings.json')
    assert findings['status']=='PASS'and findings['passedTrials']==64 and not any(findings['errors'].values())
    save_json(W/'B10-game-findings.json',findings)
    control=load(P/'diagnostics/B10/B10.json');profile=copy.deepcopy(control)
    profile['revision']='test01-v20-B11';profile['sceneRoundtrip']['enabled']=False
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    rows=[]
    def add(role,name):
        h=bone_name_hash(name);assert avatar.name_hashes.count(h)==1,name
        rows.append(dict(role=role,name=name,index=avatar.name_hashes.index(h)))
    names={'native_root':'skeleton','native_boss':'boss','native_boss_aim':'boss_aim','native_chest':'chest',
        'native_left_upper':'l_shoulder','native_left_elbow':'l_elbow','native_left_hand':'l_hand','native_left_grip':'attach_hand_l',
        'native_right_upper':'r_shoulder','native_right_elbow':'r_elbow','native_right_hand':'r_hand','native_right_grip':'attach_hand_r',
        'native_weapon_attach':'attach_weapon','native_aim_weapon':'aim_weapon','native_weapon_aim':'weapon_aim',
        'native_sling':'sling','native_samplepouch':'attach_samplepouch'}
    for role,name in names.items():add(role,name)
    for chain in profile['armChains']:
        side='left'if chain['side']=='l'else'right';by_index={r['index']:r['name']for r in chain['nodes']}
        for role,key in [('upper','root'),('elbow','mid'),('hand','hand')]:add('source_'+side+'_'+role,by_index[chain[key]])
    pouch=next(r for r in profile['vpk']if r['standardName']=='attach_samplepouch')
    add('native_samplepouch_reference',pouch['referenceName'])
    hands={}
    for resource,side,offset in [('d154442f2e33fdee','l',0),('e0b67b19ba91057b','r',3)]:
        rows0=profile['sceneObservation']['layouts'][resource][offset:offset+3]
        hands[resource]=dict(side=side,nodes=[dict(role=role,name=r['name'],index=r['index'])for role,r in zip(('upper','elbow','hand'),rows0)])
    profile['gripObservation']=dict(enabled=True,avatarNodes=rows,handModels=hands)
    reduced=copy.deepcopy(profile);reduced.pop('gripObservation');reduced['revision']=control['revision'];reduced['sceneRoundtrip']['enabled']=True
    assert reduced==control
    save_json(W/'B11.json',profile)
    before=(P/'diagnostics/B10/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    module=(ROOT/'HD2PhysBoneCompat/src/native_grip_observer.lua').read_text(encoding='utf-8')
    init=''' local gripObserver=nil
 do
  local ok,value=pcall(GripObserver.new,S,profile,self.logger)
  if ok then gripObserver=value else pcall(self.logger,'[grip_probe] init_unavailable: %s',tostring(value))end
 end
 function self:observe_grip(phase,owners)
  if not gripObserver then return end
  local ok,err=pcall(gripObserver.capture,gripObserver,self.frame,self.lastTime,phase,
   self.avatars,self.armor,owners,self.consumers,alive,visible,resource)
  if not ok and (self.gripErrors or 0)<3 then
   self.gripErrors=(self.gripErrors or 0)+1
   pcall(self.logger,'[grip_probe] capture_unavailable: %s',tostring(err))
  end
 end
'''
    prelude='-- BEGIN READ ONLY GRIP OBSERVER\nlocal GripObserver=(function()\n'+module+'\nend)()\n-- END READ ONLY GRIP OBSERVER\n'
    edits=[("local M={VERSION='0.10.4'}",prelude+"local M={VERSION='0.10.5'}"),(' function self:tick(frame)',init+' function self:tick(frame)'),
        ("  self:observe_scene('pre_apply',modelOwners)","  self:observe_scene('pre_apply',modelOwners)\n  self:observe_grip('pre_apply',modelOwners)"),
        ("  self:observe_scene('post_refresh',modelOwners)","  self:observe_scene('post_refresh',modelOwners)\n  self:observe_grip('post_refresh',modelOwners)")]
    after=before
    for old,new in edits:assert after.count(old)==1;after=after.replace(old,new)
    reverse=after
    for old,new in reversed(edits):reverse=reverse.replace(new,old)
    assert reverse==before
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    if not(W/'native_attachments-before-B10.lua').exists():
        assert digest(source)==digest(P/'diagnostics/B10/src/native_attachments.lua');shutil.copy2(source,W/'native_attachments-before-B10.lua')
    source.write_text(after,encoding='utf-8',newline='\n')
    with zipfile.ZipFile(R/'AB测试/B10-模型自身姿态原样回写.zip')as z:
        binary=z.read('9ba626afa44a3aa3.patch_0');manifest=json.loads(z.read('manifest.json'))
    entry=next(iter(TocArchive.parse_parts(binary).entries.values()));original=entry.toc_data[8:].decode('utf-8-sig').replace('\r\n','\n')
    assert original.count(before)==1
    start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
    end=original.index('\nend)()',start);old_profile=original[start:end]
    new_profile='-- B11 read-only grip motion capture; roundtrip disabled.\nreturn '+lua(profile)+'\n'
    code=original.replace(before,after).replace(old_profile,new_profile)
    assert code.replace(after,before).replace(new_profile,old_profile)==original
    data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data
    patch=bytearray(binary[:192])+payload;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
    assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data==payload
    dest=W/'runtime/B11';dest.mkdir(parents=True,exist_ok=True);main_patch=dest/'9ba626afa44a3aa3.patch_0';main_patch.write_bytes(patch)
    for suffix in('.stream','.gpu_resources'):Path(str(main_patch)+suffix).write_bytes(b'')
    manifest.update(Name='test01 v15 动画配套 B11 — 握持运动只读观测',Description='保持既有算法，关闭已验证的原样回写，仅增加手骨/挂点/武器候选的同帧只读观测。一次仅启用一个 test01 Lua。')
    save_json(dest/'manifest.json',manifest);shutil.copy2(ROOT/'docs/native-v20-B11-20261104.md',dest/'测试说明.txt')
    (W/'hd2physbone-B11.lua').write_bytes(data);pack.WORK=W
    save_json(W/'static-packages.json',[pack.archive('AB测试/B11-握持运动只读观测.zip',files(dest))])
    save_json(W/'scope-audit.json',dict(status='PASS',control='v19-B10',probe='v20-B11',reversibleInsertionExactlyMatchesB10=True,
        sameArmSolver=True,sameTargets=True,samePhysics=True,sameAttachmentRules=True,callback='render',roundtripEnabled=False,
        animationSha256=digest(R/'test01-配套动画.zip'),sourceSha256=digest(source),
        gripObserverSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_grip_observer.lua'),
        observerSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua'),gameTested=False))
    save_json(W/'feedback.json',dict(B10=findings['userFeedback'],B11GameTested=False))
    print('B11 prepared:',len(rows),'Avatar channels, both actual hand models, bounded unverified equipment candidates.')


if __name__=='__main__':main()
