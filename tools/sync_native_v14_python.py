import shutil
from pathlib import Path
from package_native_v12 import load,save_json,digest
ROOT=Path(__file__).resolve().parents[1]

def main():
    directory=ROOT/'tools/native-python/anim_batch_mod'
    for file in ROOT.parent.glob('*.py'):shutil.copy2(file,directory/file.name)
    info=load(directory/'build-info.json')
    if not any(r['name']=='native_arm_reference.py' for r in info['files']):info['files'].append(dict(name='native_arm_reference.py'))
    for row in info['files']:row['sha256']=digest(directory/row['name'])
    info['sourceRevision']='test01-v14-reference-arms';save_json(directory/'build-info.json',info)
    print('v14 rebuild sources synchronized')

if __name__=='__main__':main()
