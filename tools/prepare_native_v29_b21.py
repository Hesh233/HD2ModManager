"""Build a standalone read-only B21 collector from verified original layouts."""
import runpy
import shutil
import struct
import uuid
from package_native_v12 import ROOT, load, save_json, digest, files, lua
import package_native_v12 as pack
from anim_batch_mod.archive import TocArchive

W = ROOT / 'outputs/native-v29-b21-20261105'
SRC = ROOT / 'HD2PhysBoneCompat/src'
NAME = 'mods/hd2modmanager/native_grip_capture'
CORE = {'StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','root','boss','hips','spine1','spine2','chest',
        'l_clavicle','l_shoulder','l_elbow','l_hand','l_hand_twist',
        'r_clavicle','r_shoulder','r_elbow','r_hand','r_hand_twist',
        'attach_hand_l','attach_hand_r','weapon_aim','attach_weapon'}
WEAPON = {'StingrayEntityRoot','FbxAxisSystem_ConvertNode','root','skeleton','boss','game_mesh',
          'IK_left','IK_right','attach_underbarrel','attach_muzzle','muzzle'}


def main():
    layouts = load(W / 'native-capture-layouts.json')
    p = load(ROOT / 'outputs/native-v28-b20-20261105/B20-R.json')
    hand_inputs = {'l_hand','r_hand','l_hand_twist','r_hand_twist'}
    manifest = load(ROOT / 'outputs/native-manual-20261103/project/source-skeleton.json')
    source_names = {b['name'] for b in manifest['bones'] if b['driver'] in CORE}
    source_names |= {b['name'] for b in manifest['bones'] if b['sourceIndex'] in (24,47,64,65)}
    resources = {}

    def add(row, kind, label, watched):
        nodes = [dict(name=n['name'],index=n['index'],parentIndex=n['parentIndex'],hash=n['hash'],
                      skinInput=n['index'] in row['skin']['skinNodeIndices'])
                 for n in row['nodes'] if n['name'] in watched]
        assert nodes and len(nodes) <= 55
        r = resources.setdefault(row['resource'],dict(kind=kind,layouts={}))
        assert r['kind']==kind and str(row['nodeCount']) not in r['layouts']
        r['layouts'][str(row['nodeCount'])] = dict(count=row['nodeCount'],label=label,nodes=nodes,assetSha256=row['sha256'])

    add(layouts['nativeAvatar'],'avatar','native_107',CORE)
    add(layouts['test01Avatar'],'avatar','test01_255',CORE|source_names)
    for row in layouts['resources'].values():
        if row['kind']=='native_armor':
            if set(row['skin']['skinNodeNames']) & hand_inputs:
                add(row,'native_armor','native_B01',CORE)
        else:
            add(row,row['kind'],row['kind'],WEAPON)
    for row in layouts['test01Models'].values():
        if any(n['name'] in source_names and ('anim_008_l_hand' in n['name'] or 'anim_031_r_hand' in n['name'])
               for n in row['nodes'] if n['index'] in row['skin']['skinNodeIndices']):
            add(row,'test01_model','test01_model_205',CORE|source_names)
    config = dict(revision='native-v29-B21',resources=resources,intervalSeconds=.2,scanSeconds=2,
                  maxSamples=1800,maxRecords=48000,maxTracked=24,maxWorlds=8,maxScanUnits=10000,radiusMetres=3)
    assert len(resources)==12
    module = (SRC / 'native_reference_capture.lua').read_text(encoding='utf-8')
    entry = (SRC / 'native_reference_capture_entry.lua').read_text(encoding='utf-8')
    assert entry.count('-- INSERT CAPTURE MODULE')==entry.count('-- INSERT CAPTURE PROFILE')==1
    code = entry.replace('-- INSERT CAPTURE MODULE',module).replace('-- INSERT CAPTURE PROFILE','return '+lua(config))
    (W / 'native-grip-capture.lua').write_text(code,encoding='utf-8',newline='\n')
    save_json(W / 'capture-profile.json',config)
    body=code.encode('utf-8');payload=struct.pack('<II',len(body),2)+body
    header=(ROOT / 'outputs/native-v28-b20-20261105/runtime/R/9ba626afa44a3aa3.patch_0').read_bytes()[:192]
    murmur=runpy.run_path(str(ROOT.parents[1] / 'utils/hashing.py'))['murmur64_hash']
    resource=murmur(NAME.encode('utf-8'))
    patch=bytearray(header)+payload;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<Q',patch,104,resource)
    struct.pack_into('<I',patch,160,len(payload))
    archive=TocArchive.parse_parts(patch)
    assert len(archive.entries)==1
    e=next(iter(archive.entries.values()));assert e.file_id==resource and e.toc_data==payload
    folder=W / 'runtime';folder.mkdir(exist_ok=True)
    path=folder / '9ba626afa44a3aa3.patch_0';path.write_bytes(patch)
    for suffix in ('.gpu_resources','.stream'):path.with_name(path.name+suffix).write_bytes(b'')
    manifest=dict(Version=1,Guid=str(uuid.uuid5(uuid.NAMESPACE_URL,NAME+'/B21')),
        Name='B21 原生握持只读采集',Description='读取原生B-01、Avatar、SMG-203及前握把的局部/世界姿态。不写骨骼，不强制刷新。使用Chef加载器。')
    save_json(folder / 'manifest.json',manifest)
    shutil.copy2(ROOT / 'docs/native-v29-B21-20261105.md',folder / '测试说明.txt')
    shutil.copy2(ROOT / 'docs/native-v29-B21-20261105.md',W / '先读我-B21.md')
    pack.WORK=W
    package=pack.archive('B21-原生握持只读采集.zip',files(folder))
    save_json(W / 'static-packages.json',[package])
    prior=load(ROOT / 'outputs/native-v28-b20-20261105/delivery-verification.json')
    save_json(W / 'capture-scope.json',dict(status='PREPARED',addonName=NAME,addonResource=f'{resource:016x}',
        sourceSha256={n:digest(SRC / n) for n in ('native_reference_capture.lua','native_reference_capture_entry.lua')},
        profileSha256=digest(W / 'capture-profile.json'),assembledSha256=digest(W / 'native-grip-capture.lua'),
        legacySourceSha256=prior['sourceSha256'],legacyPackageSha256={r['name']:r['sha256'] for r in prior['packages']},
        runtimeResourceCount=1,modelOrAnimationResourceCount=0,resourcesObserved=len(resources),
        gameDeployed=False,gamePoseCaptured=False,modelsAndExistingRuntimeUnchanged=True))
    print('Prepared B21 standalone read-only collector:',len(resources),'resource identities; native / extended layouts distinguished.')


if __name__=='__main__':
    main()
