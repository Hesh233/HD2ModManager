"""Split the proven B14-A candidate set; no runtime implementation edits."""
import copy
import os
import shutil
import struct
from pathlib import Path
from package_native_v12 import ROOT,load,save_json,digest,files,lua
import package_native_v12 as pack
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units
from anim_batch_mod.archive import TocArchive

W=ROOT/'outputs/native-v23-b15-20261105';R=ROOT/'outputs/native-manual-20261103'
OLD=R/'project/diagnostics/B14'
NAMES={'A1':'B15-A1-原生持枪挂点二分测试.zip','A2':'B15-A2-来源武器骨二分测试.zip'}


def main():
    W.mkdir(exist_ok=True)
    baseline=load(R/'delivery-verification.json');assert baseline['status']=='PASS'and baseline['revision']=='native-v22'
    if not(W/'baseline-delivery.json').exists():save_json(W/'baseline-delivery.json',baseline)
    assert baseline==load(W/'baseline-delivery.json')
    game=load(W/'evidence/B14-A-game-result.json');assert game['status']=='PASS'and game['candidateSetPositive']
    prior=load(OLD/'variants/A/profile.json');rows=prior['attachmentProbe']['nodes'];by_index={r['index']:r for r in rows}
    avatar=next(iter(units(R/'project/animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    root_set={r['index']for r in rows if r['parentIndex']not in by_index};assert len(root_set)==8
    first_names={'attach_weapon','attach_hand_l','attach_hand_r','head_aim'}
    first_roots={r['index']for r in rows if r['name']in first_names};assert len(first_roots)==4 and first_roots<=root_set
    def root(index):
        while by_index[index]['parentIndex']in by_index:index=by_index[index]['parentIndex']
        return index
    groups={'A1':[r for r in rows if root(r['index'])in first_roots],
            'A2':[r for r in rows if root(r['index'])not in first_roots]}
    assert len(groups['A1'])==6 and len(groups['A2'])==11
    assert sorted(groups['A1']+groups['A2'],key=lambda r:r['index'])==rows
    assert not {r['index']for r in groups['A1']}&{r['index']for r in groups['A2']}
    source=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'
    module=ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'
    assert digest(source)==digest(OLD/'src/native_attachments.lua')and digest(module)==digest(OLD/'src/native_attachment_probe.lua')
    original=(OLD/'variants/A/hd2physbone.lua').read_text(encoding='utf-8-sig')
    start=original.index('local NativeAttachmentProfile = (function()\n')+len('local NativeAttachmentProfile = (function()\n')
    end=original.index('\nend)()',start);old_profile=original[start:end]
    header=(OLD/'variants/A/container-header.bin').read_bytes();packages=[];tree={};pack.WORK=W
    for variant,selected_rows in groups.items():
        selected={r['index']for r in selected_rows};affected=set()
        for i,parent in enumerate(avatar.parents):
            if i in selected or parent in affected:affected.add(i)
        assert affected==selected
        roots=[r['index']for r in selected_rows if r['parentIndex']not in selected];assert len(roots)==4
        for row in selected_rows:
            assert avatar.name_hashes[row['index']]==row['hash']and avatar.parents[row['index']]==row['parentIndex']
        tree[variant]=dict(nodes=selected_rows,roots=roots,affectedIndices=sorted(affected))
        profile=copy.deepcopy(prior);profile['revision']='test01-v23-B15-'+variant
        profile['attachmentProbe']['variant']=variant;profile['attachmentProbe']['nodes']=selected_rows
        restored=copy.deepcopy(profile);restored['revision']=prior['revision'];restored['attachmentProbe']['variant']='A';restored['attachmentProbe']['nodes']=rows
        assert restored==prior
        new_profile='-- B15 subset of game-positive B14-A; unchanged runtime.\nreturn '+lua(profile)+'\n'
        code=original.replace(old_profile,new_profile);assert code.replace(new_profile,old_profile)==original
        data=code.encode('utf-8');payload=struct.pack('<II',len(data),2)+data;patch=bytearray(header)+payload;patch.extend(bytes(-len(patch)%16))
        struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
        assert next(iter(TocArchive.parse_parts(patch).entries.values())).toc_data==payload
        dest=W/'runtime'/variant;dest.mkdir(parents=True,exist_ok=True)
        path=dest/'9ba626afa44a3aa3.patch_0';path.write_bytes(patch)
        for suffix in ('.stream','.gpu_resources'):Path(str(path)+suffix).write_bytes(b'')
        manifest=load(OLD/'variants/A/manifest.json')
        manifest.update(Name='test01 B15-'+variant+' 武器挂点二分',Description='已确认有效的 B14-A 候选再次二分；仅 test01，4秒原位/4秒上移60厘米。一次只启用一个 Lua。')
        save_json(dest/'manifest.json',manifest);shutil.copy2(ROOT/'docs/native-v23-B15-20261105.md',dest/'测试说明.txt')
        save_json(W/('B15-'+variant+'.json'),profile);(W/('hd2physbone-B15-'+variant+'.lua')).write_bytes(data)
        packages.append(pack.archive('AB测试/'+NAMES[variant],files(dest)))
    save_json(W/'static-packages.json',packages)
    save_json(W/'candidate-tree.json',dict(status='PASS',control='B14-A',groups=tree,rootFamiliesPerGroup=4,
        disjoint=True,unionExactlyEqualsB14A=True,excludedHellpad=2781352283,
        strategy='A1 native hand/weapon/head aim families; A2 boss aim and three Source weapon families.'))
    save_json(W/'scope-audit.json',dict(status='PASS',control='B14-A',probe='B15-A1/A2',
        runtimeImplementationByteIdentical=True,onlyProfileRevisionVariantAndNodeSubsetChanged=True,
        sourceSha256=digest(source),probeSha256=digest(module),animationSha256=digest(R/'test01-配套动画.zip'),
        baselineChefSourceSha256=load(OLD/'reports/chef-compatibility-audit.json')['embeddedSourceSha256'],
        gameTested=False,gameDeployed=False))
    print('B15 prepared: A1 4 roots/6 nodes, A2 4 roots/11 nodes; exact disjoint B14-A partition; runtime unchanged.')


if __name__=='__main__':main()
