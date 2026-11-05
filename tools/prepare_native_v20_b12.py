"""Build explicit test01-only bisection probes without changing animations."""
import copy
import json
import os
import shutil
import struct
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.archive import TocArchive

W=ROOT/'outputs/native-v20-b12-20261104'
R=ROOT/'outputs/native-manual-20261103';P=R/'project'
NAMES={'A':'B12-A-持枪控制挂点二分测试.zip','B':'B12-B-辅助挂点二分测试.zip','ALL':'B12-ALL-全候选阳性对照.zip'}


def main():
    W.mkdir(exist_ok=True)
    baseline=load(R/'delivery-verification.json');assert baseline['revision']=='native-v19'and baseline['status']=='PASS'
    if not(W/'baseline-delivery.json').exists():save_json(W/'baseline-delivery.json',baseline)
    assert baseline==load(W/'baseline-delivery.json')
    control=load(P/'diagnostics/B10/B10.json')
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    manifest=load(P/'source-skeleton.json');source_names={r['hash']:r['name']for r in manifest['bones']}
    def named(name):
        h=bone_name_hash(name);assert avatar.name_hashes.count(h)==1,name
        i=avatar.name_hashes.index(h);return dict(name=name,hash=h,index=i,parentIndex=avatar.parents[i])
    groups={
        'A':[named(n)for n in ['attach_hand_l','attach_hand_r','weapon_aim','attach_weapon','aim_weapon','boss_aim','head_aim']]
            +[named(r['sourceWeaponBone'])for r in control['weaponCandidates']],
        'B':[named(n)for n in ['sling','backpack','support_mg','support','target_designator']]
    }
    for i in (92,104):groups['B'].append(dict(name=f'hash_{avatar.name_hashes[i]:08x}',hash=avatar.name_hashes[i],index=i,parentIndex=avatar.parents[i]))
    for variant,suffix in [('A','_valvebiped_weapon_bone_clip2'),('B','_valvebiped_weapon_bolt_l')]:
        name=next(n for n in source_names.values()if n.endswith(suffix));groups[variant].append(named(name))
    # Include every descendant in its parent's family. These extra descendants
    # are Source weapon clip/bolt/charger helpers, not hand/finger joints.
    for rows in groups.values():
        selected={r['index']for r in rows}
        for i,parent in enumerate(avatar.parents):
            if parent in selected and i not in selected:
                name=source_names.get(avatar.name_hashes[i]);assert name and '_valvebiped_weapon_'in name
                rows.append(named(name));selected.add(i)
    for rows in groups.values():rows.sort(key=lambda r:r['index'])
    groups['ALL']=sorted(groups['A']+groups['B'],key=lambda r:r['index'])
    assert len(groups['ALL'])==25 and len({r['hash']for r in groups['ALL']})==25
    assert not any(r['hash']==2781352283 for r in groups['ALL'])
    tree={}
    for variant,rows in groups.items():
        selected={r['index']for r in rows};affected=set()
        for i,parent in enumerate(avatar.parents):
            if i in selected or parent in affected:affected.add(i)
        assert affected==selected,('unexpected descendant',variant,affected-selected)
        roots=[r['index']for r in rows if r['parentIndex']not in selected]
        tree[variant]=dict(nodes=rows,roots=roots,affectedIndices=sorted(affected))
    assert len(tree['A']['roots'])==len(tree['B']['roots'])==8
    save_json(W/'candidate-tree.json',dict(status='PASS',groups=tree,excludedHellpad=2781352283,
        strategy='16 parent families split 8/8; nested aim and Source weapon-helper nodes remain with their parents; no hand, finger, head, sample-pouch or seam-control joints in descendant closure.',
        candidateCoverage='First-round Avatar attachment/control candidates; independent gun IK roots require separate evidence if both halves are negative.'))
    before=(P/'diagnostics/B10/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    module=(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    init=""" local attachmentProbe=AttachmentProbe.new(S,profile,self.logger)
 function self:restore_attachment_probe()
  if attachmentProbe then
   for world in pairs(attachmentProbe:restore_all())do self.dirtyWorlds[world]=true end
  end
 end
"""
    prelude='-- BEGIN EXPLICIT ATTACHMENT BISECTION PROBE\nlocal AttachmentProbe=(function()\n'+module+'\nend)()\n-- END EXPLICIT ATTACHMENT BISECTION PROBE\n'
    edits=[("local M={VERSION='0.10.4'}",prelude+"local M={VERSION='0.11.0'}"),
        (' function self:tick(frame)',init+' function self:tick(frame)'),
        ('  self.frame=frame\n  if frame-self.lastScan', '  self.frame=frame\n  self:restore_attachment_probe()\n  if frame-self.lastScan'),
        ("   if any and self.mode=='apply' then", "   if attachmentProbe and not selected.body then attachmentProbe:apply(a,false,now,frame,self.consumers)end\n   if any and self.mode=='apply' then"),
        ('    self:update_procedures(a,selected.body,joints)',
         '    self:update_procedures(a,selected.body,joints)\n    if attachmentProbe and attachmentProbe:apply(a,selected.body,now,frame,self.consumers)then self.dirtyWorlds[a.world]=true end'),
        ("  self:observe_scene('post_refresh',modelOwners)","  self:observe_scene('post_refresh',modelOwners)\n  if attachmentProbe then attachmentProbe:after_refresh()end"),
        (' function self:release()\n',' function self:release()\n  self:restore_attachment_probe()\n'),
        ('  for _,a in pairs(self.avatars) do if a.active then pcall(self.restore,self,a) end end\n  self:refresh_consumers()',
         '  for _,a in pairs(self.avatars) do if a.active then pcall(self.restore,self,a) end end\n  if attachmentProbe then\n   for _,item in ipairs(self.armor)do\n    if self.dirtyWorlds[item.world]and alive(item.unit)and S.Unit.num_scene_graph_items(item.unit)==item.count and resource(item.unit)==item.resource then pcall(S.World.update_unit,item.world,item.unit)end\n   end\n  end\n  self:refresh_consumers()')]
    after=before
    for old,new in edits:assert after.count(old)==1,old;after=after.replace(old,new)
    reverse=after
    for old,new in reversed(edits):reverse=reverse.replace(new,old)
    assert reverse==before
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    if not(W/'native_attachments-before-B12.lua').exists():shutil.copy2(source,W/'native_attachments-before-B12.lua')
    source.write_text(after,encoding='utf-8',newline='\n')
    with zipfile.ZipFile(R/'AB测试/B10-模型自身姿态原样回写.zip')as z:
        binary=z.read('9ba626afa44a3aa3.patch_0');manifest=json.loads(z.read('manifest.json'))
    original=next(iter(TocArchive.parse_parts(binary).entries.values())).toc_data[8:].decode('utf-8-sig').replace('\r\n','\n')
    assert original.count(before)==1
    start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
    end=original.index('\nend)()',start);old_profile=original[start:end]
    packages=[];pack.WORK=W
    for variant,rows in groups.items():
        profile=copy.deepcopy(control);profile['revision']='test01-v20-B12-'+variant
        profile['sceneRoundtrip']['enabled']=False
        profile['attachmentProbe']=dict(enabled=True,variant=variant,nodes=rows,anchorIndex=71,worldDelta=[0,0,.6],phaseSeconds=4)
        reduced=copy.deepcopy(profile);reduced.pop('attachmentProbe');reduced['revision']=control['revision'];reduced['sceneRoundtrip']['enabled']=True
        assert reduced==control
        save_json(W/('B12-'+variant+'.json'),profile)
        new_profile='-- Explicit test01-only attachment bisection.\nreturn '+lua(profile)+'\n'
        code=original.replace(before,after).replace(old_profile,new_profile)
        assert code.replace(after,before).replace(new_profile,old_profile)==original
        data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data
        patch=bytearray(binary[:192])+payload;patch.extend(bytes(-len(patch)%16))
        struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
        assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data==payload
        dest=W/'runtime'/variant;dest.mkdir(parents=True,exist_ok=True)
        path=dest/'9ba626afa44a3aa3.patch_0';path.write_bytes(patch)
        for suffix in ('.stream','.gpu_resources'):Path(str(path)+suffix).write_bytes(b'')
        m=copy.deepcopy(manifest);m.update(Name='test01 B12-'+variant+' 挂点二分位移测试',Description='仅 test01 身体匹配时，原位4秒/上移60厘米4秒；一次仅启用一个测试Lua。不是握持修正版。')
        save_json(dest/'manifest.json',m)
        shutil.copy2(ROOT/'docs/native-v20-B12-20261104.md',dest/'测试说明.txt')
        (W/('hd2physbone-B12-'+variant+'.lua')).write_bytes(data)
        packages.append(pack.archive('AB测试/'+NAMES[variant],files(dest)))
    save_json(W/'static-packages.json',packages)
    findings=load(ROOT/'outputs/native-b10-observation-20261104/game-findings.json');save_json(W/'B10-game-findings.json',findings)
    save_json(W/'scope-audit.json',dict(status='PASS',control='v19-B10',probe='v20-B12',
        reversibleInsertionExactlyMatchesB10=True,sameArmSolver=True,samePhysics=True,sameAttachmentRules=True,
        newWrites='Explicit probe selected Avatar nodes only; 4-second baseline / 4-second +0.6m world Z',
        callback='render',roundtripEnabled=False,animationSha256=digest(R/'test01-配套动画.zip'),
        sourceSha256=digest(source),probeSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'),gameTested=False))
    save_json(W/'feedback.json',dict(B10=findings['userFeedback'],hellpadUserConfirmed='手臂面板，与武器无关',B12GameTested=False,
        B11='Unshipped read-only draft retained in native-v20-20261104; replaced by user-requested bisection workflow.'))
    print('B12 prepared: A/B each 8 parent families, 25 total nodes; ALL control; no animation or deployment writes.')


if __name__=='__main__':main()
