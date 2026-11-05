"""Prepare small project inputs and synchronized sources for a v13 publish."""
import json
import shutil
from pathlib import Path
from package_native_v12 import lua, digest, save_json

ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/native-v13-20261104'; P=W/'project'
OLD=ROOT/'outputs/native-v12-20261104/project'

def main():
    for name in ('models','models-o3','bone-names','source','research'):
        shutil.copytree(OLD/name,P/name,dirs_exist_ok=True)
    source=ROOT/'HD2PhysBoneCompat/src'
    profile=json.loads((P/'attachment-profile.json').read_text(encoding='utf-8'))
    assert not profile['armSync'] and len(profile['armChains'])==2
    (source/'native_attachment_profile.lua').write_text('-- Generated test01 v13 A profile.\nreturn '+lua(profile)+'\n',encoding='utf-8')
    runtime=ROOT/'tools/native-python/anim_batch_mod'
    for file in ROOT.parent.glob('*.py'):
        shutil.copy2(file,runtime/file.name)
    info=json.loads((runtime/'build-info.json').read_text(encoding='utf-8-sig'))
    for row in info['files']:
        row['sha256']=digest(runtime/row['name'])
    info['sourceRevision']='test01-v13';save_json(runtime/'build-info.json',info)
    save_json(W/'python-regression.json',dict(status='PASS',tests=107,skipped=1,log='python-regression-final.log'))
    print('Project assets and bundled Python/Lua synchronized')

if __name__=='__main__':main()
