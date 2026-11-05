"""Preflight the final all-key lower-body regression on serialized candidates."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
from audit_native_v8_animations import check_clip
from package_native_v8 import records,payload
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import append_unit,append_bones,load_manifest
W=ROOT/'outputs/native-v8-20261104';P=W/'project';B=ROOT/'outputs/native-fix-20261103'
m=load_manifest(P/'source-skeleton.json');u=UnitData.parse((B/'avatar.toc').read_bytes());b=BonesData.parse((B/'bones.toc').read_bytes())
eu=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));eb=BonesData.parse(append_bones((B/'bones.toc').read_bytes(),m))
hip=len(u.transforms)+next(i for i,n in enumerate(m['bones']) if n['driver']=='hips');lower=set()
for i in range(len(m['bones'])):
    cursor=len(u.transforms)+i
    while cursor is not None and cursor!=hip:cursor=eu.parents[cursor]
    if cursor==hip:lower.add(len(b.names)+i)
lower.update(range(len(b.names)+len(m['bones']),len(b.names)+len(m['bones'])+len(m['motionLayers'])))
old=ROOT/'outputs/native-v7-20261104/project/animations/runtime/9ba626afa44a3aa3.patch_2';rs={r[0]:r for r in records(old) if r[1]==ANIMATION_TYPE_ID}
arc=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636');results=[]
for path in sorted((W/'candidate-clips').glob('*.toc')):
    fid=int(path.stem)
    result=check_clip(path.read_bytes(),arc.entries[fid,ANIMATION_TYPE_ID].toc_data,len(eb.names),len(b.names),m['attachmentShadows'],eb.names.index(m['attachmentShadows'][0]['name']),[(t.position,t.rotation,t.scale) for t in u.transforms],payload(old,rs[fid]),lower)
    results.append({'id':str(fid),**result})
report={'status':'PASS','lowerBodyAndMotionChannels':len(lower),'samples':results,'scope':'Exact initial states and every position/rotation/scale key versus v7 for all lower-body and root/boss motion channels'}
(W/'candidate-lower-body-keys.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('PASS',len(results),'candidates',len(lower),'lower-body/motion channels')
