"""Read-only latest test07 native-vs-Lua sidearm log comparison. Never deploys."""
import collections,hashlib,json,math,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
OUT=ROOT/'outputs/test07-sidearm-followup-20261106'

def stat(values):
    if not values:return {'n':0}
    return {'n':len(values),'min':min(values),'median':statistics.median(values),'max':max(values)}

def main():
    log=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2';p=log/'hd2_grip_b23.log'
    # Log is >500MB. The current short session is in the tail; never parse all.
    with p.open('rb') as f:
        f.seek(max(0,p.stat().st_size-32*1024*1024));data=f.read()
    lines=data.decode('utf-8',errors='replace').splitlines()
    starts=[i for i,l in enumerate(lines) if '"event":"loaded"' in l]
    if not starts:raise RuntimeError('Latest loaded marker not in bounded tail; choose a larger explicit capture')
    lines=lines[starts[-1]:];events=[]
    for line in lines:
        if '{' not in line:continue
        try:row=json.loads(line[line.index('{'):])
        except json.JSONDecodeError:continue
        row['stamp']=line[:19];events.append(row)
    OUT.mkdir(exist_ok=True);(OUT/'latest-grip-session.log').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'latest-loader-tail.log').write_text('\n'.join((log/'chef_loader.log').read_text(encoding='utf-8',errors='replace').splitlines()[-90:])+'\n',encoding='utf-8')
    left={e['frame']:e for e in events if e['event'] in ('left_applied','left_skipped')}
    groups={}
    for e in events:
        if e['event']!='applied':continue
        hand=left.get(e['frame'],{});rid=e.get('weaponResource') or hand.get('weaponResource') or hand.get('intent',{}).get('resource')
        if not rid:continue
        held=hand.get('intent',{}).get('held',False)
        key=rid+('::two_hand_pose_proxy' if held else '::free_pose_proxy')
        g=groups.setdefault(key,{'wristDistance':[],'nativeMinusSourceZ':[],'rootShiftZ':[],'leftReachResidual':[],'samples':[]})
        g['wristDistance'].append(math.dist(e['nativeRight'][9:12],e['equivalentRight'][9:12]))
        g['nativeMinusSourceZ'].append(e['nativeRight'][11]-e['equivalentRight'][11])
        g['rootShiftZ'].append(e['desiredWorld'][11]-e['beforeWorld'][11])
        if hand.get('reachResidual') is not None:g['leftReachResidual'].append(hand['reachResidual'])
        g['samples'].append({'stamp':e['stamp'],'frame':e['frame'],'nativeRight':e['nativeRight'][9:12],
           'sourceRight':e['equivalentRight'][9:12],'rootBefore':e['beforeWorld'][9:12],'rootAfter':e['desiredWorld'][9:12],
           'mountReadbackError':e.get('worldReadbackError',e.get('localReadbackError'))})
    summary={k:{name:stat(values) for name,values in group.items() if name!='samples'} for k,group in groups.items()}
    scans=[e for e in events if e['event']=='scan'];changes=[]
    for i,e in enumerate(scans):
        if not i or (e['actors'],e['models'])!=(scans[i-1]['actors'],scans[i-1]['models']):
            changes.append({k:e[k] for k in ('stamp','actors','models','consumers')})
    report={'sessionStart':lines[0][:19],'sessionEnd':lines[-1][:19],'version':events[0]['version'],
            'eventCounts':dict(collections.Counter(e['event'] for e in events)),'sceneChanges':changes,
            'summary':summary,'complete':next((e for e in reversed(events) if e['event']=='complete'),None),
            'nativeOnlyPoseTelemetryAvailable':False,'p4CylinderPoseTelemetryAvailable':False,
            'poseLabelsAreProxiesNotEngineADSFlags':True,'gameOrLibraryModified':False}
    (OUT/'pose-comparison.json').write_text(json.dumps({'summary':summary,'samples':groups},indent=2),encoding='utf-8')
    (OUT/'latest-session-evidence.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Serialized P-4 graph, not a claim of the renderer's current skinning state.
    from survey_native_weapon_grips import Survey
    from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
    from anim_batch_mod.formats import UnitData,BonesData
    survey=Survey()
    try:
        a=survey.archive('94b554570b12c088');unit=UnitData.parse(a.entries[(0x8d3d52a3b2f19402,UNIT_TYPE_ID)].toc_data)
        names=dict(survey.bone_names);bones=BonesData.parse(a.entries[(unit.bones_ref,BONE_TYPE_ID)].toc_data)
        names.update(zip(bones.hashes,bones.names))
        graph={'resource':'8d3d52a3b2f19402','nodeCount':len(unit.parents),'indexBase':0,'runtimeIndexBase':1,
               'nodes':[{'index':i,'runtimeIndex':i+1,'name':names.get(h),'hash':h,'parent':unit.parents[i]} for i,h in enumerate(unit.name_hashes)],
               'animationChannelNames':bones.names,'gameTested':False}
        (OUT/'p4-serialized-graph.json').write_text(json.dumps(graph,indent=2),encoding='utf-8')
    finally:survey.db.close()
    print(json.dumps({'sessionStart':report['sessionStart'],'sessionEnd':report['sessionEnd'],
        'version':report['version'],'sceneChanges':changes,'p4':summary.get('8d3d52a3b2f19402::two_hand_pose_proxy'),
        'nativeOnlyPoseTelemetryAvailable':False,'p4CylinderPoseTelemetryAvailable':False,'gameOrLibraryModified':False}))
    return report
if __name__=='__main__':main()
