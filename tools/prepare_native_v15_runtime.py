"""Build a Chef update-callback probe with the unchanged B5 grip solver."""
import hashlib
import shutil
import struct
import sys
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from package_native_v12 import load,save_json,digest,files
from anim_batch_mod.archive import TocArchive
import package_native_v12 as pack

W=ROOT/'outputs/native-v15-20261104';R=ROOT/'outputs/native-manual-20261103';P=W/'project'

def main():
    pack.WORK=W
    for f,relative in files(R/'project'):
        if relative.parts[0] in ('animations','reports','source-code'):continue
        target=P/relative
        if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
    with zipfile.ZipFile(R/'AB测试/B5-掌心握持校准.zip') as z:
        binary=z.read('9ba626afa44a3aa3.patch_0');manifest=__import__('json').loads(z.read('manifest.json'))
    entry=next(iter(TocArchive.parse_parts(binary).entries.values()))
    original=entry.toc_data[8:].decode('utf-8-sig')
    assert original.endswith('return PhysBoneRuntime\n') and 'test01-v14-B5' in original
    switch='''-- B6: only move the existing Chef callback from render to update.
if __hd2_chef then
  assert(type(PhysBoneRuntime.render)=='function','B6 missing installed callback')
  PhysBoneRuntime.update=PhysBoneRuntime.render
  PhysBoneRuntime.render=nil
  print('[attachments] callback_phase=update variant=test01-v15-B6')
end
'''
    code=original[:-len('return PhysBoneRuntime\n')]+switch+'return PhysBoneRuntime\n'
    code=code.replace('test01-v14-B5','test01-v15-B6')
    assert code.replace(switch,'').replace('test01-v15-B6','test01-v14-B5')==original
    data=code.encode('utf-8');resource=struct.pack('<II',len(data),2)+data
    patch=bytearray(binary[:192])+resource;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(resource))
    parsed=next(iter(TocArchive.parse_parts(patch).entries.values()))
    assert parsed.toc_data==resource and parsed.file_id==entry.file_id
    dest=P/'ab-runtime/B6';dest.mkdir(parents=True,exist_ok=True)
    main=dest/'9ba626afa44a3aa3.patch_0';main.write_bytes(patch)
    for suffix in ('.stream','.gpu_resources'):Path(str(main)+suffix).write_bytes(b'')
    manifest.update(Name='test01 v15 B6 — Chef update 回调对照',Description='与 v14-B5 相同握持计算，仅将 Chef 回调从 render 改为 update；每次只启用一个运行时。')
    save_json(dest/'manifest.json',manifest)
    doc=ROOT/'docs/native-v15-20261104.md';shutil.copy2(doc,dest/'测试说明.txt')
    profile=load(R/'project/ab-profiles/B5.json');profile['revision']='test01-v15-B6'
    save_json(P/'ab-profiles/B6.json',profile)
    lua=W/'physics-export-delivery/lua版/hd2physbone.lua';lua.parent.mkdir(parents=True,exist_ok=True);lua.write_bytes(data)
    shutil.copytree(dest,W/'physics-export-delivery/patch版',dirs_exist_ok=True)
    save_json(W/'static-packages.json',[pack.archive('AB测试/B6-update时机对照.zip',files(dest))])
    save_json(W/'ab-profile-audit.json',dict(status='PASS',control='v14-B5',probe='v15-B6',
        changed=['profile revision','Chef callback render -> update'],sameGripSolver=True,sameTargets=True,
        controlLuaSha256=hashlib.sha256(original.encode('utf-8')).hexdigest(),probeLuaSha256=hashlib.sha256(data).hexdigest(),gameTested=False))
    source=(ROOT/'tools/audit_native_v14_chef.py').read_text(encoding='utf-8')
    source=source.replace('native-v14-20261104','native-v15-20261104').replace("W/'project/attachment-profile.json'","W/'project/ab-profiles/B6.json'")
    source=source.replace("('native_attachments.lua','native_attachment_profile.lua','physbone_runtime.lua')","('native_attachments.lua','physbone_runtime.lua')")
    source=source.replace("type(a.hooks.render)=='function'", "type(a.hooks.update)=='function' and a.hooks.render==nil")
    source=source.replace('p.armSync==false and p.armGripSync==false','p.armSync==true and p.armGripSync==true')
    source=source.replace('a.hooks.render()','a.hooks.update()').replace('renderFrames=state.frame','updateFrames=state.frame')
    (ROOT/'tools/audit_native_v15_chef.py').write_text(source,encoding='utf-8')
    print('B6 packaged: only Chef callback phase and revision differ from B5.')

if __name__=='__main__':main()
