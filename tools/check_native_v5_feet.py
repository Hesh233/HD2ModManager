import copy,json,math,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.archive import PackageStore,TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform,ModConfig
from anim_batch_mod.native_skeleton import convert_clip,load_manifest
BASE=ROOT/'outputs/native-fix-20261103';V4=ROOT/'outputs/native-v4-20261103';WORK=ROOT/'outputs/native-v5-20261103'
u=UnitData.parse((BASE/'avatar.toc').read_bytes());b=BonesData.parse((BASE/'bones.toc').read_bytes())
m=load_manifest(V4/'project/models/test01/source-skeleton.json')
by_hash={h:i for i,h in enumerate(u.name_hashes)};indices=[by_hash[h] for h in b.hashes]
feet=[by_hash[b.hashes[b.names.index(n)]] for n in ('l_foot','r_foot')]
hips=by_hash[b.hashes[b.names.index('hips')]]
source_feet=[i for i,n in enumerate(m['bones']) if n['driver'] in ('l_foot','r_foot')]
archive=TocArchive.load_toc_only(PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data')),'18235e0c9ec0e636')
allowed={int(r['id']) for r in json.loads((V4/'project/animations/build-report.json').read_text())['animations']}
def poses(a,times,source=False):
    tracks=_build_tracks(a);rows=[]
    for time in times:
        if source:
            local=[WorldTransform(*(track[90+i].evaluate(time) for track in tracks)) for i in range(len(m['bones']))]
            world=_calculate_world_transforms(local,[n['parent'] for n in m['bones']]);rows.append([world[i] for i in source_feet])
        else:
            local=list(u.transforms)
            for ai,ui in enumerate(indices):local[ui]=WorldTransform(*(track[ai].evaluate(time) for track in tracks))
            world=_calculate_world_transforms(local,u.parents);rows.append([world[i] for i in feet]+[world[hips]])
    return rows
def movement(rows):return max(math.dist(row[i].position,rows[0][i].position) for row in rows for i in (0,1))
candidates=[]
cache=WORK/'feet-sample-audit.json'
if cache.exists():allowed={int(r['id']) for r in json.loads(cache.read_text())['clips']}
for e in archive.entries_of_type(ANIMATION_TYPE_ID):
    if e.file_id not in allowed:continue
    a=AnimationData.parse(e.toc_data)
    if a.is_additive or not 1<a.animation_length<30:continue
    times=[a.animation_length*1000*i/8 for i in range(9)];p=poses(a,times);motion=movement(p)
    if motion<.012:
        q=p[0][2].rotation;turn=max(1-abs(sum(x*y for x,y in zip(q,row[2].rotation))) for row in p)
        candidates.append((turn,e.file_id,motion))
candidates.sort(reverse=True);print('stationary-feet candidates',len(candidates),candidates[:5],flush=True)
cfg=V4/'project/config.toml';options=tomllib.loads(cfg.read_text(encoding='utf-8-sig'))['native_skeleton'];report=[]
for _,id,motion in candidates[:3]:
    raw=archive.entries[id,ANIMATION_TYPE_ID].toc_data;original=AnimationData.parse(raw)
    times=[original.animation_length*1000*i/60 for i in range(61)];original_rows=poses(original,times)
    row=dict(id=str(id),originalFootTravelMetres=movement(original_rows))
    for enabled in (False,True):
        data,metrics=convert_clip(raw,b,u,m,ModConfig.load(cfg),dict(options,align_standard_feet=enabled))
        actual=poses(AnimationData.parse(data),times,True)
        row['withIK' if enabled else 'withoutIK']=dict(footTravelMetres=movement(actual),maxTargetError=metrics['max_standard_foot_error'],pelvisDrop=metrics['max_pelvis_drop'])
    report.append(row);print(row,flush=True)
assert len(report)==3
(WORK/'feet-sample-audit.json').write_text(json.dumps(dict(status='measured',clips=report),indent=2),encoding='utf-8')
