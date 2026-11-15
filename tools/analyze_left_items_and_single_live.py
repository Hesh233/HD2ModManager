"""Read-only V10/S1 live evidence and exact deployed single-model alias audit."""
from pathlib import Path
import collections, hashlib, json, os, sys
import build_detailed_grip_test as b
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/grip-left-items-analysis-20261109'
BASE=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
LOGS=Path(os.environ['APPDATA'])/'Arrowhead/Helldivers2'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def records(path):
    for number,line in enumerate(path.open(encoding='utf-8-sig'),1):
        at=line.find('{')
        if at<0: continue
        yield line[:19],number,json.loads(line[at:])

def layout_signature(unit):
    return hashlib.sha256(json.dumps([unit.name_hashes,unit.parents,b.matrices(unit)],separators=(',',':')).encode()).hexdigest()

def deployed_aliases(source_paths, game_data):
    layouts={}
    for path in source_paths:
        for rid,t,raw in b.resources(path):
            if t!=b.UNIT_TYPE_ID: continue
            u=b.UnitData.parse(raw)
            layouts.setdefault(layout_signature(u),[]).append(f'{rid:016x}')
    aliases={}; provenance={}
    for path in sorted(game_data.glob('9ba626afa44a3aa3.patch_*')):
        if not path.suffix.rsplit('_',1)[-1].isdigit(): continue
        rows=b.resources(path)
        for rid,t,raw in rows:
            if t!=b.UNIT_TYPE_ID: continue
            unit=b.UnitData.parse(raw);sig=layout_signature(unit);sources=layouts.get(sig)
            if not sources: continue
            assert len(set(sources))==1,'Ambiguous source model bind/layout'
            resource=f'{rid:016x}';aliases[resource]=sources[0]
            provenance[resource]=dict(sourceResource=sources[0],patch=str(path),unitSha256=hashlib.sha256(raw).hexdigest(),layoutSha256=sig,count=len(unit.parents))
    return aliases,provenance

def main():
    grip_path=LOGS/'hd2_grip_TEST_PERF_test06_LEFT_ITEMS_V10_20261109_083154.part01.log'
    single_path=LOGS/'hd2_single_TEST_DETAILED_test01_RAGDOLL_S1_20261109_091013.log'
    model=BASE/'test-library/[单骨架模型]test01/vpk2patch'
    source_paths=[p for p in model.glob('*.patch_*') if p.suffix.rsplit('_',1)[-1].isdigit()]
    aliases,alias_provenance=deployed_aliases(source_paths,Path('E:/Steam/steamapps/common/Helldivers 2/data'))
    profile=b.load(ROOT/'outputs/single-test01-ragdoll-probe-20261109/single-observer-profile.json')
    events=collections.Counter();groups={};complete=None;first=last=None
    for stamp,line,r in records(grip_path):
        first=first or stamp;last=stamp;events[r['event']]+=1
        if r['event'] in ('left_applied','left_skipped'):
            k=(r['event'],r.get('weaponResource') or (r.get('intent') or {}).get('resource'),r.get('gripResource'),r.get('reason'))
            row=groups.setdefault(k,dict(event=k[0],weapon=k[1],grip=k[2],reason=k[3],count=0,first=stamp,last=stamp));row['count']+=1;row['last']=stamp
        if r['event']=='complete': complete=r
    grip=dict(path=str(grip_path),sha256=digest(grip_path),bytes=grip_path.stat().st_size,first=first,last=last,events=dict(events),groups=list(groups.values()),complete=complete)
    events=collections.Counter();instances={};fk=0;scale_delta=0;modes=collections.Counter();model_samples=0;first=last=None
    for stamp,line,r in records(single_path):
        first=first or stamp;last=stamp;events[r['event']]+=1
        if r['event']!='single_ragdoll_pose': continue
        model_samples+=r['kind']=='single_model'
        k=r['instance'];row=instances.setdefault(k,dict(instance=k,resource=r['resource'],kind=r['kind'],count=r['actualCount'],samples=0,first=stamp,last=stamp));row['samples']+=1;row['last']=stamp
        modes[(r['animationState'].get('value'),r['boneMode'].get('value'))]+=1
        for pose in r['poses']:
            if not pose.get('available'): continue
            fk=max(fk,pose.get('worldVsLocalParentFK',0))
            if pose.get('name') in {'hips','spine1','spine2','chest','neck','head','l_clavicle','r_clavicle','l_shoulder','r_shoulder','l_elbow','r_elbow','l_hand','r_hand','l_thigh','r_thigh','l_knee','r_knee','l_foot','r_foot'}:
                for value in pose.get('worldScale',[])+pose.get('localScale',[]): scale_delta=max(scale_delta,abs(value-1))
    single=dict(path=str(single_path),sha256=digest(single_path),bytes=single_path.stat().st_size,first=first,last=last,events=dict(events),instances=list(instances.values()),singleModelPoseSamples=model_samples,nativeReferenceMaxParentFKMetres=fk,nativeDeformBoneMaxScaleDeviation=scale_delta,modes=[dict(fsm=k[0],boneMode=k[1],samples=v) for k,v in modes.items()],targetCoverage='FAIL_NO_SINGLE_MODEL_SAMPLES',ragdollRootCauseProven=False)
    report=dict(status='ANALYZED_NOT_GAME_FIX_VERIFICATION',gripV10=grip,singleS1=single,deployedSingleAliases=aliases,aliasProvenance=alias_provenance,s1RecognizesDeployedAliases=sorted(set(aliases)&set(profile['resources'])),notes=['V10 compact output has no per-item link matrices; reload recognition failure is observed, offset cause remains a candidate.','S1 recorded only native Avatar references, not the single model.','Deployed aliases match source name hashes, parents and every local bind matrix exactly.','No model, animation, physics, config, library or game files written.'])
    OUT.mkdir(exist_ok=True);(OUT/'live-v10-and-s1-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(gripEvents=grip['events'],gripRefreshErrors=complete['stats']['refreshErrors'],gripDisabled=complete['disabled'],singleEvents=single['events'],singleModelPoseSamples=model_samples,deployedSingleAliases=len(aliases),recognizedByS1=report['s1RecognizesDeployedAliases'],nativeReferenceMaxFKMetres=fk,nativeReferenceMaxScaleDeviation=scale_delta),ensure_ascii=False,indent=2))
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
