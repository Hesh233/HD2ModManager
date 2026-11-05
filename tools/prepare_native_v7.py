"""Prepare v7 from the verified v6 model without changing mesh or physics bytes."""
import copy,hashlib,json,shutil,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import load_manifest,bone_name_hash,row_pose
from anim_batch_mod.motion_skeleton import apply_unit_layers,relative,matrix
from anim_batch_mod.processor import _calculate_world_transforms
W=ROOT/'outputs/native-v7-20261104';P=W/'project';OLD=ROOT/'outputs/native-v6-20261104';B=ROOT/'outputs/native-fix-20261103'
refresh='--refresh' in sys.argv
if P.exists() and not refresh:raise FileExistsError(P)
saved_profile=json.loads((P/'attachment-profile.json').read_text()) if refresh else None
P.mkdir(parents=True,exist_ok=True)
for folder in ('models','models-o3','source'):
    shutil.copytree(OLD/'project'/folder,P/folder,dirs_exist_ok=refresh)
shutil.copy2(OLD/'project/config.toml',P/'config.toml')
for filename in ('conversion.json','o3-mapping.json','avatar-reference.toc'):
    shutil.copy2(OLD/filename,W/filename)
m=load_manifest(OLD/'project/source-skeleton.json');u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes())
world=_calculate_world_transforms(u.transforms,u.parents);byname={n:u.name_hashes.index(h) for n,h in zip(b.names,b.hashes)}
rows=[]
for driver in ('root','boss'):
    i=byname[driver];parent=u.parents[i]
    name='__hd2_motion__'+m['boneNamespace']+'_'+driver
    rows.append(dict(name=name,hash=bone_name_hash(name),driver=driver,driverHash=u.name_hashes[i],driverUnitIndex=i,
        parentHash=rows[0]['hash'] if driver=='boss' else u.name_hashes[parent],animationChannel=b.names.index(driver),maskChannel=b.names.index(driver)))
m['motionLayers']=rows;m['motionParentOverrides']={};m['motionLocalOverrides']={}
for i,node in enumerate(m['bones']):
    if node['driver'] not in ('hips','spine1'):continue
    local=relative(world[byname['boss']],row_pose(node['world']));values=matrix(local)
    m['motionParentOverrides'][str(i)]=1
    m['motionLocalOverrides'][str(i)]={'rotation':values[:9],'position':values[9:12],'scale':[1,1,1],'padding':0}
m['retargetHierarchy']='native-root-boss-layers-v7'
for path in (P/'source-skeleton.json',P/'models/test01/source-skeleton.json',P/'models-o3/test01-O3/source-skeleton.json'):
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
changes=[]
for folder in ('models/test01','models-o3/test01-O3'):
    path=P/folder/'9ba626afa44a3aa3.patch_0';data=bytearray(path.read_bytes());nt,n=struct.unpack_from('<II',data,4)
    for ri in range(n):
        at=72+32*nt+80*ri;r=list(struct.unpack_from('<QQQQQQQIIIIII',data,at))
        if r[1]!=UNIT_TYPE_ID:continue
        raw=data[r[2]:r[2]+r[7]];unit=UnitData.parse(raw)
        if not all(node['hash'] in unit.name_hashes for node in m['bones']):continue
        revised=apply_unit_layers(raw,m);new=UnitData.parse(revised)
        data.extend(b'\0'*(-len(data)%16));r[2]=len(data);r[7]=len(revised);data.extend(revised)
        struct.pack_into('<QQQQQQQIIIIII',data,at,*r)
        changes.append(dict(folder=folder,id=f'{r[0]:016x}',before=len(unit.transforms),after=len(new.transforms)))
    path.write_bytes(data)
    for suffix in ('.gpu_resources','.stream'):
        assert Path(str(path)+suffix).read_bytes()==(OLD/'project'/folder/(path.name+suffix)).read_bytes()
profile=json.loads((OLD/'project/attachment-profile.json').read_text())
for row in profile['vpk']:
    row['referenceIndex']+=len(rows)
    if 'sourceReferenceIndex' in row:row['sourceReferenceIndex']+=len(rows)
profile['version']=4;profile['expectedAvatarNodes']+=len(rows);profile.pop('expectedModelNodes',None)
profile['phaseRequirement']='Render applies attachment poses; engine weapon consumption order is unverified and must be measured in game.'
(P/'attachment-profile.json').write_text(json.dumps(saved_profile or profile,ensure_ascii=False,indent=2),encoding='utf-8')
(W/'model-hierarchy-audit.json').write_text(json.dumps({'status':'PASS','changes':changes,'meshGpuAndPhysicsBytesUnchanged':True,'modelScale':1.08,'sourceOriginPreserved':True},indent=2),encoding='utf-8')
print('Prepared',len(changes),'source/O3 model Units; actor',profile['expectedAvatarNodes'],'nodes; 2 independent motion layers.')
from prepare_native_v7_references import prepare
prepare()
