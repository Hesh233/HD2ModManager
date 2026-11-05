import copy,json,math,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.native_skeleton import local_pose
W=ROOT/'outputs/native-v11-20261104';P=W/'project'
base=ROOT/'outputs/native-manual-20261103/project'
m=json.loads((P/'source-skeleton.json').read_text())
p=json.loads((base/'attachment-profile.json').read_text())
nodes=m['bones'];source=json.loads((W/'source-procedures.json').read_text())
model=next(r for r in source if r['path']=='models/survivors/survivor_namvet.mdl')
lookup={n['sourceIndex']:i for i,n in enumerate(nodes)}
procedures=[]
for b in model['bones']:
    if b['type']!=2 or b['name'] not in ('ValveBiped.handl','ValveBiped.handr'):continue
    i=lookup[b['index']];ci=lookup[b['control']];pi=nodes[i]['parent']
    assert nodes[ci]['parent']==pi and not nodes[i]['physics']
    bind=local_pose(nodes[i]['local']);triggers=copy.deepcopy(b['triggers'])
    for t in triggers:
        t['position']=[v*.0254*m['modelScale'] for v in t['position']]
        assert math.dist(t['position'],bind.position)<2e-6
        for k in ('trigger','rotation'):
            norm=math.sqrt(sum(v*v for v in t[k]));assert abs(norm-1)<1e-5
            t[k]=[v/norm for v in t[k]]
    assert abs(sum(a*c for a,c in zip(bind.rotation,triggers[0]['rotation'])))>1-1e-7
    procedures.append(dict(index=107+i,name=nodes[i]['name'],parentIndex=107+pi,parentName=nodes[pi]['name'],
                           controlIndex=107+ci,controlName=nodes[ci]['name'],bind=dict(p=bind.position,q=bind.rotation),
                           triggers=triggers,source=b['name']))
assert len(procedures)==2
head=[]
for row in p['vpk']:
    if row['ownerSlot']=='head':
        row['policy']='original-world';row['anchorReason']='v11 trial: leave every native head child untouched, including aim and camera inputs.'
        head.append(row['index'])
    if row['standardName']=='sling':
        # The Source torso already provides its dimensions. The configured
        # native socket offset adds the same shape correction a second time.
        row['configuredAnchorIndex']=row['driverAnchorIndex']
        row['configuredAnchorName']=row['driverAnchorName']
        row['sourceReferenceIndex']=row['referenceIndex']
        row['sourceReferenceName']=row['referenceName']
        row['anchorReason']='Use the unmodified animated sling-to-spine2 pose; Source anchor already supplies the character proportions.'
p.update(jointProcedures=procedures,preserveHeadAttachments=True,revision='test01-v11')
(P/'attachment-profile.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
def lua(v):
    if v is None:return 'nil'
    if isinstance(v,bool):return 'true' if v else 'false'
    if isinstance(v,(int,float)):return repr(v)
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
    return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'
path=ROOT/'HD2PhysBoneCompat/src/native_attachment_profile.lua'
if not (W/'source-before'/path.name).exists():shutil.copy2(path,W/'source-before'/path.name)
path.write_text('-- Generated test01 v11 profile. Indices are zero-based.\nreturn '+lua(p)+'\n',encoding='utf-8')
(W/'profile-changes.json').write_text(json.dumps(dict(headNodesUntouched=head,sourceWristProcedures=[r['source'] for r in procedures],
    slingReference='original animated local offset; duplicate configured offset removed',gameTested=False),indent=2),encoding='utf-8')
print('Head nodes untouched:',head,'Wrist helpers:',len(procedures))
