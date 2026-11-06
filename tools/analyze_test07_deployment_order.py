"""Read-only: inspect real game patch precedence and the latest test07 Lua session."""
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import TOC_MAGIC,UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
OUT=ROOT/'outputs/test07-live-attachment-audit-20261106'
INSTALLED=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
RESOURCE=0x4d1c334d294dfa97


def selective(path):
    result={}
    with Path(path).open('rb') as f:
        header=f.read(72);magic,types,count,_=struct.unpack_from('<IIII',header)
        assert magic==TOC_MAGIC
        f.seek(72+types*32);rows=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(count)]
        for row in rows:
            if row[0]==RESOURCE and row[1] in (UNIT_TYPE_ID,BONE_TYPE_ID):
                f.seek(row[2]);result[row[1]]=f.read(row[7])
    return result


def summarize(path):
    data=selective(path);row={'path':str(Path(path).resolve()),'bytes':Path(path).stat().st_size}
    if UNIT_TYPE_ID in data:
        raw=data[UNIT_TYPE_ID];u=UnitData.parse(raw);row.update(avatarNodes=len(u.parents),unitSha256=hashlib.sha256(raw).hexdigest())
    if BONE_TYPE_ID in data:row.update(bonesChannels=len(BonesData.parse(data[BONE_TYPE_ID]).names),bonesSha256=hashlib.sha256(data[BONE_TYPE_ID]).hexdigest())
    return row


def main():
    OUT.mkdir(exist_ok=True)
    game=Path('E:/Steam/steamapps/common/Helldivers 2/data')
    log=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2'
    loader=(log/'chef_loader.log').read_bytes();lines=loader.decode('utf-8',errors='replace').splitlines()
    start=max(i for i,l in enumerate(lines) if '==== Chef Shared Loader' in l)
    session=lines[start:];(OUT/'latest-loader-session.log').write_text('\n'.join(session)+'\n',encoding='utf-8')
    current_start='2026-11-06 '+session[0][:8]
    start_stamp='2026-11-06 18:57:31' # Failed completed session reported at task start.
    p=log/'hd2_grip_b23.log';size=p.stat().st_size;tail_offset=max(0,size-16*1024*1024)
    with p.open('rb') as f:f.seek(tail_offset);tail=f.read()
    all_rows=tail.decode('utf-8',errors='replace').splitlines()[1:]
    rows=[l for l in all_rows if start_stamp<=l[:19]<='2026-11-06 19:00:28']
    current_rows=[l for l in all_rows if l[:19]>=current_start]
    (OUT/'failed-grip-session.log').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    (OUT/'current-grip-session.log').write_text('\n'.join(current_rows)+'\n',encoding='utf-8')
    events=[json.loads(l[l.index('{'):]) for l in rows if '{' in l]
    current_events=[json.loads(l[l.index('{'):]) for l in current_rows if '{' in l]
    current_scans=[e for e in current_events if e['event']=='scan']
    current_applied=[e for e in current_events if e['event'] in ('applied','left_applied','body_applied','attachments_applied')]
    loaded=next(e for e in events if e['event']=='loaded');complete=next(e for e in reversed(events) if e['event']=='complete')
    scans=[e for e in events if e['event']=='scan'];rejected=Counter()
    for e in scans:rejected.update(e.get('rejected',{}))
    deployed=[]
    for patch in sorted((p for p in game.glob('*.patch_*') if p.suffix.rsplit('_',1)[-1].isdigit()),key=lambda p:int(p.suffix.rsplit('_',1)[-1])):
        d=summarize(patch);d['gamePath']=str(patch);d['patchIndex']=int(patch.suffix.rsplit('_',1)[-1]);deployed.append(d)
    owners=[d for d in deployed if 'avatarNodes' in d];winner=owners[-1]
    assert loaded['rigExpectedNodes']==245
    assert complete['stats']['writes']==complete['stats']['attachmentWrites']==complete['stats']['bodyNodeWrites']==0
    assert all(e['actors']==0 for e in scans)
    lua_owner=next(d for d in owners if d['avatarNodes']==loaded['rigExpectedNodes'])
    # The user may reorder the live profile while this read-only audit runs.
    # Preserve the logged failure independently from the current patch order.
    animation_owner=next(d for d in owners if d['avatarNodes']==240)
    assert any('actual=240:expected=245' in k for k in rejected)
    profile=json.loads((INSTALLED/'test-library/[骨骼挂点修正]test07/attachment-profile.json').read_text(encoding='utf-8-sig'))
    lua_unit=UnitData.parse(selective(lua_owner['path'])[UNIT_TYPE_ID]);animation_unit=UnitData.parse(selective(animation_owner['path'])[UNIT_TYPE_ID])
    # Five old Source animation nodes are renamed into private references;
    # original names move to appended unanimated outputs. Both UNIT and BONES
    # must therefore come from the Lua parenting package, not animation last.
    renamed=[i for i,h in enumerate(animation_unit.name_hashes) if lua_unit.name_hashes[i]!=h]
    assert len(renamed)==5
    animation_bones=BonesData.parse(selective(animation_owner['path'])[BONE_TYPE_ID])
    lua_bones=BonesData.parse(selective(lua_owner['path'])[BONE_TYPE_ID])
    names={h:n for data in (animation_bones,lua_bones) for h,n in zip(data.hashes,data.names)}
    reference_changes=[{'index':i,'animationName':names.get(animation_unit.name_hashes[i]),'luaName':names.get(lua_unit.name_hashes[i])} for i in renamed]
    extra=[]
    for i in range(len(animation_unit.parents),len(lua_unit.parents)):
        candidates=[n['name'] for n in profile['avatar']['nodes'] if n['index']==i]
        extra.append({'index':i,'hash':lua_unit.name_hashes[i],'parent':lua_unit.parents[i],'names':candidates or [names.get(lua_unit.name_hashes[i])]})
    simulated=[]
    for i in range(1,9):
        name=f'test{i:02d}';case=ROOT/'outputs/manager-parent-entry-fix-20261106'/(name+'-rs89')/name
        cfg=json.loads(next((case/'attachment').rglob('attachment-profile.json')).read_text(encoding='utf-8-sig'))
        a=summarize(next((case/'animations/runtime').glob('*.patch_2')))
        lp=next(p for p in case.iterdir() if p.is_dir() and p.name.startswith('[骨骼挂点修正]'))
        l=next(summarize(q) for q in lp.glob('*.patch_*') if q.suffix.rsplit('_',1)[-1].isdigit() and UNIT_TYPE_ID in selective(q))
        simulated.append({'model':name,'expected':cfg['avatar']['count'],'animationAfterLuaActual':a['avatarNodes'],
                          'luaAfterAnimationActual':l['avatarNodes'],'currentOrderRejected':a['avatarNodes']!=cfg['avatar']['count'],
                          'correctedOrderCountMatches':l['avatarNodes']==cfg['avatar']['count'],
                          'bonesBytesIdentical':a.get('bonesSha256')==l.get('bonesSha256')})
        assert simulated[-1]['currentOrderRejected'] and simulated[-1]['correctedOrderCountMatches']
    report={'status':'CAUSE_CONFIRMED','failedSession':start_stamp,'currentSession':current_start,
            'currentRuntime':{'eventCounts':dict(Counter(e['event'] for e in current_events)),'lastScan':current_scans[-1] if current_scans else None,'actualWriteEventsObserved':len(current_applied)>0},'loaded':loaded,'complete':complete,
            'scans':len(scans),'eventCounts':dict(Counter(e['event'] for e in events)),'rejections':dict(rejected),
            'deployedPatches':deployed,'avatarOverrideChain':owners,'currentWinningAvatar':winner,'luaRequiredAvatar':lua_owner,'animationAvatar':animation_owner,
            'currentOrderCountMatches':winner['avatarNodes']==loaded['rigExpectedNodes'],
            'initialObservedOrder':{'luaSkeletonPatch':6,'animationPatch':7,'source':'Initial game symlink query in this task; subsequently reordered externally.'},
            'missingNodes':extra,'renamedReferenceNodes':reference_changes,'eightCaseOrderSimulation':simulated,'gameOrLibraryModified':False,
            'note':'Order simulation verifies resource count/byte precedence, not real game visual success.',
            'logProvenance':{'path':str(p),'bytesAtRead':size,'tailOffset':tail_offset,'tailSha256':hashlib.sha256(tail).hexdigest()}}
    (OUT/'evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'loadedVersion':loaded['version'],'loggedActual':240,'currentWinner':winner['avatarNodes'],
                      'expected':loaded['rigExpectedNodes'],'luaSkeletonPatch':lua_owner['patchIndex'],'currentAnimationPatch':animation_owner['patchIndex'],
                      'writes':complete['stats']['writes'],'attachmentWrites':complete['stats']['attachmentWrites'],'missingNodes':extra,
                      'eightCaseOrderSimulation':simulated},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
