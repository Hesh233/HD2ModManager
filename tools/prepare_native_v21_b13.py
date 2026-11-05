"""Replace B12's unsafe numeric name lookup; preserve the accepted v15 assets."""
import copy
import os
import shutil
import struct
import zipfile
from pathlib import Path
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.archive import TocArchive

W = ROOT/'outputs/native-v21-b13-20261104'
R = ROOT/'outputs/native-manual-20261103'
OLD = R/'project/diagnostics/B12'
NAMES = {'0':'B13-0-节点校验不位移对照.zip', 'A':'B13-A-持枪控制挂点二分测试.zip',
         'B':'B13-B-辅助挂点二分测试.zip', 'ALL':'B13-ALL-已知候选合并对照.zip'}
DEFERRED = {1965514668, 2088035612}


def main():
    W.mkdir(exist_ok=True)
    baseline = load(R/'delivery-verification.json')
    assert baseline['revision']=='native-v20' and baseline['status']=='PASS'
    if not (W/'baseline-delivery.json').exists(): save_json(W/'baseline-delivery.json', baseline)
    assert load(W/'baseline-delivery.json')==baseline
    before = (OLD/'src/native_attachments.lua').read_text(encoding='utf-8-sig')
    old_module = (OLD/'src/native_attachment_probe.lua').read_text(encoding='utf-8-sig')
    module = (ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua').read_text(encoding='utf-8-sig')
    assert before.count(old_module)==1
    after = before.replace(old_module,module).replace("local M={VERSION='0.11.0'}", "local M={VERSION='0.11.1'}")
    assert after.replace(module,old_module).replace("local M={VERSION='0.11.1'}", "local M={VERSION='0.11.0'}")==before
    source = ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    assert source.read_text(encoding='utf-8-sig') in (before,after)
    source.write_text(after,encoding='utf-8',newline='\n')
    avatar = next(iter(units(R/'project/animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    packages=[];tree={};pack.WORK=W
    for variant in NAMES:
        base_variant = 'ALL' if variant=='0' else variant
        folder = OLD/'variants'/base_variant
        original = (folder/'hd2physbone.lua').read_text(encoding='utf-8-sig')
        assert original.count(before)==1
        prior = load(folder/'profile.json');profile=copy.deepcopy(prior)
        profile['revision']='test01-v21-B13-'+variant
        cfg=profile['attachmentProbe'];cfg['variant']=variant;cfg['validationOnly']=variant=='0'
        cfg['nodes']=[r for r in cfg['nodes'] if r['hash'] not in DEFERRED]
        for r in cfg['nodes']:
            assert not r['name'].startswith('hash_') and bone_name_hash(r['name'])==r['hash']
            assert avatar.name_hashes.count(r['hash'])==1 and avatar.name_hashes[r['index']]==r['hash']
            assert avatar.parents[r['index']]==r['parentIndex'] and r['hash']!=2781352283
        selected={r['index'] for r in cfg['nodes']};affected=set()
        for i,parent in enumerate(avatar.parents):
            if i in selected or parent in affected: affected.add(i)
        assert affected==selected
        roots=[r['index'] for r in cfg['nodes'] if r['parentIndex'] not in selected]
        tree[variant]=dict(nodes=cfg['nodes'], roots=roots, affectedIndices=sorted(affected),validationOnly=variant=='0')
        assert len(roots)==({'0':14,'A':8,'B':6,'ALL':14}[variant])
        restored=copy.deepcopy(profile);restored['revision']=prior['revision'];restored['attachmentProbe']=prior['attachmentProbe']
        assert restored==prior
        start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
        end=original.index('\nend)()',start);old_profile=original[start:end]
        new_profile='-- B13: engine-created name IDs; unresolved names deferred.\nreturn '+lua(profile)+'\n'
        code=original.replace(before,after).replace(old_profile,new_profile)
        assert code.replace(after,before).replace(new_profile,old_profile)==original
        data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data
        patch=bytearray((folder/'container-header.bin').read_bytes())+payload;patch.extend(bytes(-len(patch)%16))
        struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
        assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data==payload
        dest=W/'runtime'/variant;dest.mkdir(parents=True,exist_ok=True)
        path=dest/'9ba626afa44a3aa3.patch_0';path.write_bytes(patch)
        for suffix in ('.stream','.gpu_resources'): Path(str(path)+suffix).write_bytes(b'')
        manifest=load(folder/'manifest.json')
        manifest.update(Name='test01 B13-'+variant+' 挂点排查',Description=('仅校验23个已知名称节点，不施加探针位移。先完成本项。' if variant=='0' else '仅 test01 身体匹配时，原位4秒/上移60厘米4秒；须先通过 B13-0。')+'一次仅启用一个 test01 Lua。替代已退役的 B12。')
        save_json(dest/'manifest.json',manifest)
        shutil.copy2(ROOT/'docs/native-v21-B13-20261104.md',dest/'测试说明.txt')
        save_json(W/('B13-'+variant+'.json'),profile)
        (W/('hd2physbone-B13-'+variant+'.lua')).write_bytes(data)
        packages.append(pack.archive('AB测试/'+NAMES[variant],files(dest)))
    save_json(W/'static-packages.json',packages)
    save_json(W/'candidate-tree.json',dict(status='PASS',groups=tree,excludedHellpad=2781352283,
        deferred=[dict(hash=h,reason='Real node name unresolved; no verified engine ID constructor for serialized integers.') for h in sorted(DEFERRED)],
        strategy='Keep original B12 families: A 8 roots/17 nodes; B 6 roots/6 nodes; defer two unknown names. 0 and ALL cover the same 23 known nodes.'))
    save_json(W/'scope-audit.json',dict(status='PASS',control='v20-B12',probe='v21-B13',
        onlyProbeModuleAndVersionChanged=True,sameArmSolver=True,samePhysics=True,sameAttachmentRules=True,
        profileChanges=['revision','probe variant','validationOnly','two unresolved names removed'],
        callback='render',roundtripEnabled=False,animationSha256=digest(R/'test01-配套动画.zip'),
        sourceSha256=digest(source),probeSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'),gameTested=False))
    shutil.copy2(ROOT/'outputs/native-v20-b12-20261104/B10-game-findings.json',W/'B10-game-findings.json')
    save_json(W/'feedback.json',dict(B12='A twice and B once crashed before first probe phase; same native AV location.',
        hellpadUserConfirmed='手臂面板，与武器无关',B13GameTested=False))
    print('B13 prepared: validation-only 0, A 17 nodes, B 6 nodes, ALL 23; two unknown names deferred.')


if __name__=='__main__':main()
