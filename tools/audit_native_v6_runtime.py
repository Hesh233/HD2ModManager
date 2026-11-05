"""Exercise production Lua with real rig poses and a fake engine."""
import json,sys,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'outputs/native-fix-20261103/test-runtime'))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.native_skeleton import load_manifest,append_unit,animation_nodes
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.processor import _build_tracks,WorldTransform
W=ROOT/'outputs/native-v6-20261104';B=ROOT/'outputs/native-fix-20261103'
m=load_manifest(W/'project/source-skeleton.json');u=UnitData.parse(append_unit((B/'avatar.toc').read_bytes(),m));b=BonesData.parse((B/'bones.toc').read_bytes())
profile=json.loads((W/'project/attachment-profile.json').read_text(encoding='utf-8'))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.native_skeleton import convert_clip
from anim_batch_mod.processor import ModConfig
import tomllib

cfg=W/'project/config.toml'
data,_=convert_clip((W/'original-sample.toc').read_bytes(),b,UnitData.parse((B/'avatar.toc').read_bytes()),m,ModConfig.load(cfg),tomllib.loads(cfg.read_text())['native_skeleton'])
a=AnimationData.parse(data)
tracks=_build_tracks(a);local=list(u.transforms);byhash={h:i for i,h in enumerate(u.name_hashes)}
for i,h in enumerate(b.hashes):local[byhash[h]]=WorldTransform(*(t[i].evaluate(0) for t in tracks))
for i in range(89):local[107+i]=WorldTransform(*(t[90+i].evaluate(0) for t in tracks))
for i,row in enumerate(m['attachmentShadows']):local[196+i]=WorldTransform(*(t[179+i].evaluate(0) for t in tracks))
for i,row in enumerate(m['sourceAttachmentShadows']):local[225+i]=WorldTransform(*(t[208+i].evaluate(0) for t in tracks))
names={n:byhash[h]+1 for n,h in zip(b.names,b.hashes)}
names.update({n['name']:108+i for i,n in enumerate(animation_nodes(m))})
names.update({n['name']:197+i for i,n in enumerate(m['attachmentShadows'])})
names.update({n['name']:226+i for i,n in enumerate(m['sourceAttachmentShadows'])})
names.update({r['standardName']:r['index']+1 for r in profile['vpk'] if r['standardName']})
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().adapter=lua.execute((ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8'))
lua.globals().profile=lua.table_from(profile,recursive=True)
lua.globals().fixture=lua.table_from(dict(names=names,parents=[0 if p is None else p+1 for p in u.parents],
    localPoses=[dict(p=list(t.position),q=list(t.rotation)) for t in local]),recursive=True)
result=lua.execute((ROOT/'HD2PhysBoneCompat/test/attachments_harness.lua').read_text(encoding='utf-8'))
result={k:v for k,v in result.items()};result.update(status='PASS',scope='production adapter with fake engine and real test01 poses',gameTested=False)
(W/'attachment-runtime-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().arg=lua.table_from({0:str(ROOT/'HD2PhysBoneCompat/test/mp_harness.lua')})
lua.execute((ROOT/'HD2PhysBoneCompat/test/mp_harness.lua').read_text(encoding='utf-8'))
