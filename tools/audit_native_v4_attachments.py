"""Independent matrix checks of the offline Lua attachment prototype on real clips."""
import copy,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'outputs/native-v4-20261103'
sys.path.insert(0,str(ROOT/'outputs/native-fix-20261103/test-runtime'));sys.path.append(str(ROOT.parents[1]))
import numpy as np
from lupa.lua51 import LuaRuntime
from anim_batch_mod.formats import UnitData,BonesData,AnimationData
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID,ANIMATION_TYPE_ID
from anim_batch_mod.processor import WorldTransform,_build_tracks,_calculate_world_transforms,_compose_additive_local

profile=json.loads((WORK/'project/attachment-profile-research.json').read_text(encoding='utf-8'))
assert len(profile['native'])==len(profile['vpk'])==29
assert all(profile['targets'][k] for k in ('body','head'))
assert len({r['virtualHash'] for r in profile['vpk']})==29
lua=LuaRuntime(unpack_returned_tuples=True)
module=lua.execute((ROOT/'HD2PhysBoneCompat/research/attachment_profiles.lua').read_text(encoding='utf-8'))
lp=lua.table_from(profile,recursive=True)

def matrix(t):
    x,y,z,w=[t['rotation'][i] for i in (range(1,5) if not isinstance(t,dict) else range(4))]
    r=np.array([[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],
        [2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],
        [2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]])
    indices=range(1,4) if not isinstance(t,dict) else range(3)
    out=np.eye(4);out[:3,:3]=r@np.diag([t['scale'][i] for i in indices]);out[:3,3]=[t['position'][i] for i in indices]
    return out

def pose(t):return dict(position=t.position,rotation=t.rotation,scale=t.scale)
def evidence(snapshot):
    return {slot:dict(verified=True,method='equipment-owner',avatar=snapshot['avatar'],generation=snapshot['generation'],
        frame=snapshot['frame'],rigIdentity=profile['boneNamespace'],slot=slot,armorResource=profile['targets'][slot][0])
        for slot in ('body','head')}

path=WORK/'project/animations/runtime/9ba626afa44a3aa3.patch_2'
maximum=0.;compared=0;restored=0;max_delta=0.;max_case=None
with path.open('rb') as f:
    h=f.read(72);types,count=struct.unpack_from('<II',h,4);f.seek(72+32*types)
    records=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
    def payload(record):f.seek(record[2]);return f.read(record[7])
    u=UnitData.parse(payload(next(r for r in records if r[1]==UNIT_TYPE_ID)))
    b=BonesData.parse(payload(next(r for r in records if r[1]==BONE_TYPE_ID)))
    lookup={h:i for i,h in enumerate(u.name_hashes)};indices=[lookup[h] for h in b.hashes]
    chosen=json.loads((WORK/'published-generator-audit.json').read_text())['exactGeneratedClips']
    for clip in chosen:
        a=AnimationData.parse(payload(next(r for r in records if r[0]==int(clip['id']) and r[1]==ANIMATION_TYPE_ID)))
        tracks=_build_tracks(a)
        for frame in range(21):
            time=a.animation_length*1000*frame/20;local=list(u.transforms)
            for ai,ui in enumerate(indices):
                value=WorldTransform(*(track[ai].evaluate(time) for track in tracks))
                local[ui]=_compose_additive_local(u.transforms[ui],value) if a.is_additive else value
            world=_calculate_world_transforms(local,u.parents)
            snapshot=dict(avatar='A',generation=7,frame=frame,phase='post-animation-pre-attachments',
                original={i:pose(t) for i,t in enumerate(world[:107])},source={i:pose(t) for i,t in enumerate(world[107:])})
            ev=evidence(snapshot);ls=lua.table_from(snapshot,recursive=True)
            rows,selection=module.evaluate(lp,ls,lua.table_from(ev,recursive=True))
            assert selection['head']==selection['body']=='vpk'
            for i,entry in enumerate(profile['vpk'],1):
                native=matrix(snapshot['original'][entry['index']]);expected=native
                if entry['policy']=='source-anchor-relative-animation':
                    c=matrix(dict(position=[0,0,0],rotation=entry['axisCorrection'],scale=[1,1,1]))
                    expected=matrix(snapshot['source'][entry['sourceAnchorIndex']])@c@np.linalg.inv(matrix(snapshot['original'][entry['driverAnchorIndex']]))@native
                actual=matrix(rows[i]['target']);maximum=max(maximum,float(np.max(np.abs(actual-expected))));compared+=1
                delta=float(np.linalg.norm(actual[:3,3]-native[:3,3]))
                if delta>max_delta:
                    max_delta=delta;max_case=dict(clip=clip['id'],additive=a.is_additive,frame=frame,
                        name=entry['standardName'],index=entry['index'])
            restored_rows,selection=module.evaluate(lp,ls,None)
            assert selection['head']==selection['body']=='native'
            for i,entry in enumerate(profile['vpk'],1):
                assert np.array_equal(matrix(restored_rows[i]['target']),matrix(snapshot['original'][entry['index']]))
                restored+=1

# These are contract tests with injected evidence, not a game ownership test.
cases=[]
for change,value in [('verified',False),('method','nearest-player'),('avatar','B'),('generation',8),
    ('frame',-1),('rigIdentity','other-rig'),('armorResource','other-armor'),('slot','head')]:
    ev=evidence(snapshot);ev['body'][change]=value
    _,selected=module.evaluate(lp,ls,lua.table_from(ev,recursive=True))
    assert selected['body']=='native' and selected['head']=='vpk';cases.append(change)
for slot in ('body','head'):
    ev=evidence(snapshot);ev.pop(slot)
    _,selected=module.evaluate(lp,ls,lua.table_from(ev,recursive=True))
    assert selected[slot]=='native' and selected['head' if slot=='body' else 'body']=='vpk'
    cases.append('mixed-'+slot)
other=copy.deepcopy(snapshot);other['avatar']='B'
_,selected=module.evaluate(lp,lua.table_from(other,recursive=True),lua.table_from(evidence(snapshot),recursive=True))
assert selected['body']==selected['head']=='native';cases.append('second-player')
other=copy.deepcopy(snapshot);other['phase']='after-equipment'
_,selected=module.evaluate(lp,lua.table_from(other,recursive=True),lua.table_from(evidence(snapshot),recursive=True))
assert selected['body']==selected['head']=='native';cases.append('wrong-phase')
assert maximum<1e-5 and max_delta>0.01,(maximum,max_delta)
report=dict(status='PASS',scope='offline Lua 5.1 pose math and injected ownership contract only',runtimeEnabled=False,
    gameTested=False,sceneGraphModified=False,nativeEntries=29,vpkEntries=29,sourceAnchored=26,
    controllerSpaceFallbacks=3,clips=len(chosen),evaluatedPoses=compared,currentFrameRestores=restored,
    maxMatrixError=maximum,maxCandidateDisplacementMetres=max_delta,maxDisplacementCase=max_case,selectionCases=cases,
    limitations=profile['blockers'])
(WORK/'attachment-profile-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
