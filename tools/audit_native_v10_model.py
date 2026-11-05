"""Verify that v8 only changes animation generation, preserving the v7 model."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'tools'))
from package_native_v10 import PROJECT as P,WORK as W,files,digest,records,payload
from anim_batch_mod.formats import UnitData
from anim_batch_mod.constants import UNIT_TYPE_ID,STATE_MACHINE_TYPE_ID
V7=ROOT/'outputs/native-v8-20261104/project'
rows=[];units=[]
for folder in ('models','models-o3'):
    for path,relative in files(P/folder):
        old=V7/folder/relative;assert old.is_file() and digest(path)==digest(old),(folder,str(relative))
        rows.append({'path':(Path(folder)/relative).as_posix(),'sha256':digest(path),'sameAsV8':True})
        if path.name=='9ba626afa44a3aa3.patch_0' and folder!='physics-runtime':
            rs=records(path);assert not any(r[1]==STATE_MACHINE_TYPE_ID for r in rs)
            for r in rs:
                if r[1]!=UNIT_TYPE_ID:continue
                u=UnitData.parse(payload(path,r));assert u.bones_ref==0
                units.append({'path':(Path(folder)/relative).as_posix(),'id':f'{r[0]:016x}','nodes':len(u.transforms),'bonesID':'0'})
manifest=json.loads((P/'source-skeleton.json').read_text());assert manifest['modelScale']==1.08 and manifest['scaleOrigin']=='source'
assert len(manifest['bones'])==89 and len(manifest['motionLayers'])==2
report={'status':'PASS','gameTested':False,'modelScale':1.08,'scaleOrigin':'source','modelStateMachineEntries':0,'v8ModelPhysicsSidecarsAndMaterialsUnchanged':True,'files':rows,'units':units,'scope':'Byte-for-byte v8 model/material/embedded physics preservation, plus current Unit references and hierarchy configuration. Waist correction is in generated animation translations.'}
(W/'model-final-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('PASS',len(rows),'files',len(units),'units')
