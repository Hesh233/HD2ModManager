"""Single-front-skirt semantic gate, real test07 attach and moving-anchor regression.
No game, library or generated-model writes. --model points at an existing test07 v3 model.
"""
from pathlib import Path
import argparse,copy,json,math,struct,sys
from lupa.lua51 import LuaRuntime
ROOT=Path(__file__).resolve().parents[2]
PROJECT=ROOT.parent if ROOT.name=='HD2ModManager_main' else ROOT
INSTALL=PROJECT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
sys.path.insert(0,str(INSTALL));sys.path.insert(1,r'I:\HD2SDK-CommunityEdition')
from anim_batch_mod.formats import UnitData
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.math3d import quat_multiply,quat_rotate
from anim_batch_mod.processor import _calculate_world_transforms
ap=argparse.ArgumentParser();ap.add_argument('--model',type=Path,default=INSTALL/'test-library/[单骨架模型]test07/vpk2patch');ap.add_argument('--native-model',type=Path,action='append',default=[]);ap.add_argument('--report',type=Path);args=ap.parse_args()
checks=0

def check(ok,message):
 global checks
 checks+=1
 if not ok:raise AssertionError(message)

def table(lua,value):
 if isinstance(value,dict):return lua.table_from({k:table(lua,v) for k,v in value.items()})
 if isinstance(value,(list,tuple)):return lua.table_from([table(lua,v) for v in value])
 return value

def py(value):
 if not hasattr(value,'items'):return value
 d={k:py(v) for k,v in value.items()}
 if d and all(isinstance(k,int) for k in d) and set(d)==set(range(1,len(d)+1)):return [d[i] for i in range(1,len(d)+1)]
 return d

def module(path,previous_anchor=False):
 lua=LuaRuntime(unpack_returned_tuples=True)
 source=path.read_text(encoding='utf-8-sig')
 if previous_anchor:
  # Isolate the pre-fix policy without depending on an untracked local .bak.
  call='local anchorPolicy, anchorControl = M.front_skirt_anchor_policy(rig, chain)'
  check(source.count(call)==1,'baseline override no longer targets one attach decision')
  source=source.replace(call,'local anchorPolicy, anchorControl = nil, nil',1)
 return lua,lua.execute(source)

lua,current=module(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua')
oldlua,old=module(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua',previous_anchor=True)
check(current.version=='1.3.1','wrong compat version')
spring=py(current.parse_rig((args.model/'physbone-rig.bin').read_bytes()))
drivers=py(current.parse_driver_rig((args.model/'physbone-driver-rig.bin').read_bytes()))
rig=dict(spring,drivers=drivers)
chain_table,_=current.build_chains(table(lua,rig['bones']))
chains=[[py(c[i]) for i in range(1,len(c)+1)] for _,c in chain_table.items()]
front=[c for c in chains if c[0]['name'] in ('skirt_0_0','skirt_0_3')]
check(len(front)==2 and drivers['version']==3,'not the intended real single model fixture')
for c in chains:
 got=current.single_front_skirt_anchor_policy(table(lua,rig),table(lua,c))
 expected=c in front
 check((got is not None)==expected,'policy escaped the exact two front chains')
for c in front:
 for version in (1,2,None):
  r=copy.deepcopy(rig);r['drivers']['version']=version
  check(current.single_front_skirt_anchor_policy(table(lua,r),table(lua,c)) is None,'legacy or missing version changed')
 for field,bad in [('parentName','chest'),('controlName','l_hand'),('name','unrelated_helper')]:
  r=copy.deepcopy(rig)
  for d in r['drivers']['bones']:
   if d['name']==c[0]['parentName']:d[field]=bad
  check(current.single_front_skirt_anchor_policy(table(lua,r),table(lua,c)) is None,'wrong driver semantic accepted')
 r=copy.deepcopy(rig);r['drivers']['bones']=[d for d in r['drivers']['bones'] if d['name']!=c[0]['parentName']]
 check(current.single_front_skirt_anchor_policy(table(lua,r),table(lua,c)) is None,'absent driver accepted')
 r=copy.deepcopy(rig);r['drivers']['bones'] += [copy.deepcopy(next(d for d in r['drivers']['bones'] if d['name']==c[0]['parentName']))]
 check(current.single_front_skirt_anchor_policy(table(lua,r),table(lua,c)) is None,'ambiguous driver accepted')
 for mutated in ([c[0]],c+[copy.deepcopy(c[1])],[dict(c[0],parentName='wrong'),c[1]],[c[0],dict(c[1],parentName='wrong')]):
  check(current.single_front_skirt_anchor_policy(table(lua,rig),table(lua,mutated)) is None,'wrong topology accepted')

# True final Unit tables, not a synthetic identity bind. Each Unit may reorder its nodes.
p=args.model/'9ba626afa44a3aa3.patch_0';data=p.read_bytes();nt,n=struct.unpack_from('<II',data,4);models=[]
for i in range(n):
 r=struct.unpack_from('<QQQQQQQIIIIII',data,72+32*nt+i*80)
 if r[1]==UNIT_TYPE_ID:models.append((r[0],UnitData.parse(data[r[2]:r[2]+r[7]])))
check(len(models)==7,'all seven real source Units are required')

def engine(lua,model,rid):
 world=_calculate_world_transforms(model.transforms,model.parents);calls={'set':0,'refresh':0};logs=[]
 S=table(lua,{k:{} for k in ['Application','Unit','World','Vector3','Quaternion','Matrix4x4']})
 wrap=lua.eval('function(f) return function(...) return f(...) end end')
 def func(obj,name,f):obj[name]=wrap(f)
 def q(node):return table(lua,model.transforms[int(node)].rotation)
 def pose(node):
  t=model.transforms[int(node)];return table(lua,dict(q=t.rotation,p=t.position))
 def setq(unit,node,value):calls['set']+=1
 def packed(value):
  qv=[value.q[i] for i in range(1,5)];pv=[value.p[i] for i in range(1,4)]
  return tuple(sum([quat_rotate(qv,a) for a in ([1,0,0],[0,1,0],[0,0,1])],[])+pv)
 func(S.Application,'string_to_id32',bone_name_hash);func(S.Application,'time_since_launch',lambda:0)
 func(S.Unit,'alive',lambda u:True)
 func(S.Unit,'num_scene_graph_items',lambda u:len(model.transforms))
 func(S.Unit,'name_hash',lambda u:f'{rid:016x}');func(S.Unit,'debug_name',lambda u:'real-test07-fixture')
 func(S.Unit,'has_node',lambda u,h:h in model.name_hashes);func(S.Unit,'node',lambda u,h:model.name_hashes.index(h))
 func(S.Unit,'local_pose',lambda u,node:pose(node));func(S.Unit,'local_rotation',lambda u,node:q(node))
 func(S.Unit,'world_position',lambda u,node:table(lua,world[int(node)].position));func(S.Unit,'world_rotation',lambda u,node:table(lua,world[int(node)].rotation))
 func(S.Unit,'set_local_rotation',setq);func(S.Unit,'set_local_pose',lambda *a:None)
 func(S.World,'update_unit',lambda *a:calls.__setitem__('refresh',calls['refresh']+1))
 S.Vector3.to_elements=lua.eval('function(v) return v[1],v[2],v[3] end')
 S.Quaternion.to_elements=lua.eval('function(v) return v[1],v[2],v[3],v[4] end')
 S.Quaternion.from_elements=lua.eval('function(x,y,z,w) return {x,y,z,w} end')
 S.Quaternion.axis_angle=lua.eval('function(a,t) local s=math.sin(t/2);return {a[1]*s,a[2]*s,a[3]*s,math.cos(t/2)} end')
 func(S.Matrix4x4,'to_elements',packed);func(S.Matrix4x4,'is_valid',lambda p:True)
 S.Matrix4x4.from_quaternion_position=lua.eval('function(q,p) return {q=q,p=p} end')
 lua.eval('function(v) setmetatable(v,{__call=function(_,x,y,z)return {x,y,z} end}) end')(S.Vector3)
 logger=wrap(lambda fmt,*a:logs.append(lua.eval('string.format')(fmt,*a)))
 return S,table(lua,{}),table(lua,dict(logger=logger,world={})),world,calls,logs

def measure_anchor(mod,entry,world):
 item=entry.tip;anchor=world[int(entry.anchorNode)];maxdev=0;maxlocal=0
 for frame in range(721):
  # Ramp up, hold, return; time-dependent helper rotation + mild translation.
  t=frame/240;deg=90*min(1,max(0,t/.8)) if t<1.5 else 90*max(0,1-(t-1.5)/.8)
  q=quat_multiply([math.sin(math.radians(deg)/2),0,0,math.cos(math.radians(deg)/2)],anchor.rotation)
  mod.step_tip(item,1/240,anchor.position[0]+.01*math.sin(2*t),anchor.position[1],anchor.position[2],*q)
  rotations=mod.local_rotations(item,*q);direction=[item.dirs[1][i] for i in range(1,4)];goal=quat_rotate(q,[item.segDirLocal[1][i] for i in range(1,4)])
  dot=sum(x*y for x,y in zip(direction,goal));dev=math.degrees(math.acos(max(-1,min(1,dot))))
  maxdev=max(maxdev,dev);maxlocal=max(maxlocal,rotations[1][4]*180/math.pi)
  check(all(math.isfinite(v) for v in direction),'non-finite moving-anchor output')
 return dict(maxDeviationFromDrivenHelperDegrees=maxdev,maxRootLocalCorrectionDegrees=maxlocal)

units=[];motion=[]
for rid,model in models:
 a=engine(lua,model,rid);b=engine(oldlua,model,rid)
 result=current.attach(a[0],a[1],table(lua,rig),a[2]);baseline=old.attach(b[0],b[1],table(oldlua,rig),b[2])
 check(len(result.sessions)==37 and len(baseline.sessions)==37,'real chain count changed')
 check(len(result.drivers)==6 and len(baseline.drivers)==6 and result.excludedWristDrivers==2,'real wrist exclusion changed')
 rb={x.chain[1].name:x for _,x in result.sessions.items()};ob={x.chain[1].name:x for _,x in baseline.sessions.items()}
 for name,item in rb.items():
  if name in ('skirt_0_0','skirt_0_3'):
   check(item.tip.goalQ is None and item.tip.anchorPolicy=='single-front-skirt-driver-v1','real front attach still world anchored')
   check(ob[name].tip.goalQ is not None,'old fixture no longer reproduces the defect')
  else:
   check(py(item.tip)==py(ob[name].tip),'non-front spring bind/gains changed')
 units.append(dict(resource=f'{rid:016x}',chains=len(result.sessions),drivers=len(result.drivers),policyChains=2))
 if rid!=models[0][0]:continue
 for name in ('skirt_0_0','skirt_0_3'):
  values=[]
  for mod,lua0,entry,world in [(current,lua,rb[name],a[3]),(old,oldlua,ob[name],b[3])]:
   values.append(measure_anchor(mod,entry,world))
  check(values[0]['maxDeviationFromDrivenHelperDegrees']<=15.01,'new root escapes its authored cone')
  check(values[1]['maxDeviationFromDrivenHelperDegrees']>70,'old runtime did not reproduce helper cancellation')
  motion.append(dict(chain=name,after=values[0],before=values[1]))
# Both legacy container versions keep every real test07 tip/bind/gain unchanged.
legacy=[]
for version in (1,2):
    r=copy.deepcopy(rig);r['drivers']['version']=version
    rid,model=models[0]
    a=engine(lua,model,rid+version);b=engine(oldlua,model,rid+version)
    new=current.attach(a[0],a[1],table(lua,r),a[2]);previous=old.attach(b[0],b[1],table(oldlua,r),b[2])
    check(len(new.sessions)==len(previous.sessions),'legacy session count changed')
    for i in range(1,len(new.sessions)+1):
        check(py(new.sessions[i].tip)==py(previous.sessions[i].tip),'legacy v1/v2 spring state changed')
    legacy.append(dict(version=version,chains=len(new.sessions),tipStateExact=True))
# The accepted test01 VRD names must not inherit the test07 policy.
fixture=PROJECT/'outputs/vrd-analysis-20261107/e2e-test01-single/test01'
if fixture.is_dir():
    r=py(current.parse_rig((fixture/'physbone-rig.bin').read_bytes()))
    r['drivers']=py(current.parse_driver_rig((fixture/'physbone-driver-rig.bin').read_bytes()))
    ct,_=current.build_chains(table(lua,r['bones']))
    for _,c in ct.items():
        check(current.single_front_skirt_anchor_policy(table(lua,r),c) is None,'accepted test01 policy changed')
    legacy.append(dict(fixture='test01-single-v3',chains=len(ct),allOldAnchorPolicies=True))
# Native/dual fixtures exercise the same production attach and numerical solver.
native=[]
for directory in args.native_model:
    r=py(current.parse_rig((directory/'physbone-rig.bin').read_bytes()))
    r['drivers']=py(current.parse_driver_rig((directory/'physbone-driver-rig.bin').read_bytes()))
    version=r['drivers']['version']
    check(version in (1,2),'native fixture version must be v1/v2')
    ct,_=current.build_chains(table(lua,r['bones']))
    cc=[[py(c[i]) for i in range(1,len(c)+1)] for _,c in ct.items()]
    fronts=[c for c in cc if c[0]['name'].endswith(('_skirt_0_0','_skirt_0_3'))]
    check(len(fronts)==2,'native fixture must contain the two known front chains')
    for c in cc:
        got=current.front_skirt_anchor_policy(table(lua,r),table(lua,c))
        check((got is not None)==(c in fronts),'native gate escaped the exact front chains')
    for c in fronts:
        for field in ('name','parentName','controlName'):
            for bad in ('wrong_name',c[0]['parentName'].replace(c[0]['name'].split('_phys_')[0],'hd2n_ffffffffffff')):
                rr=copy.deepcopy(r)
                for d in rr['drivers']['bones']:
                    if d['name']==c[0]['parentName']:d[field]=bad
                check(current.front_skirt_anchor_policy(table(lua,rr),table(lua,c)) is None,'wrong/foreign namespace driver accepted')
        rr=copy.deepcopy(r);rr['drivers']['bones'].append(copy.deepcopy(next(d for d in rr['drivers']['bones'] if d['name']==c[0]['parentName'])))
        check(current.front_skirt_anchor_policy(table(lua,rr),table(lua,c)) is None,'ambiguous native helper accepted')
        rr=copy.deepcopy(r);rr['drivers']['version']=3
        check(current.front_skirt_anchor_policy(table(lua,rr),table(lua,c)) is None,'namespaced v3 misclassified')
        for wrong in ([c[0]],c+[c[1]],[c[0],dict(c[1],parentName='wrong')],[dict(c[0],flags=0x31),c[1]],
                      [dict(c[0],name=c[0]['name'].replace('_phys_','_aux_')),c[1]],
                      [c[0],dict(c[1],name=c[1]['name'].replace(c[0]['name'].split('_phys_')[0],'hd2n_ffffffffffff'))]):
            check(current.front_skirt_anchor_policy(table(lua,r),table(lua,wrong)) is None,'malformed native chain accepted')
    data=(directory/'9ba626afa44a3aa3.patch_0').read_bytes();nt,n=struct.unpack_from('<II',data,4);source_units=[]
    for i in range(n):
        row=struct.unpack_from('<QQQQQQQIIIIII',data,72+32*nt+i*80)
        if row[1]==UNIT_TYPE_ID:source_units.append((row[0],UnitData.parse(data[row[2]:row[2]+row[7]])))
    check(len(source_units)==7,'native fixture requires all seven real source Units')
    item_motion=[];bound=[]
    for rid,model in source_units:
        current.clear_attach_cache();old.clear_attach_cache()
        a=engine(lua,model,rid);b=engine(oldlua,model,rid)
        result=current.attach(a[0],a[1],table(lua,r),a[2]);baseline=old.attach(b[0],b[1],table(oldlua,r),b[2])
        check(len(result.sessions)==37 and len(baseline.sessions)==37,'native spring count changed')
        check(len(result.drivers)==6 and len(baseline.drivers)==6 and result.excludedWristDrivers==2,'native wrist exclusion changed')
        rb={x.chain[1].name:x for _,x in result.sessions.items()};ob={x.chain[1].name:x for _,x in baseline.sessions.items()}
        for name,item in rb.items():
            if name.endswith(('_skirt_0_0','_skirt_0_3')):
                check(item.tip.goalQ is None and item.tip.anchorPolicy=='native-front-skirt-driver-v1','native attach did not follow the helper')
                check(ob[name].tip.goalQ is not None,'old native world-anchor defect not reproduced')
                if rid==source_units[0][0]:
                    after=measure_anchor(current,item,a[3]);before=measure_anchor(old,ob[name],b[3])
                    check(after['maxDeviationFromDrivenHelperDegrees']<=15.01,'native authored cone violated')
                    check(before['maxDeviationFromDrivenHelperDegrees']>70,'native old helper cancellation not reproduced')
                    item_motion.append(dict(chain=name,before=before,after=after))
            else:
                check(py(item.tip)==py(ob[name].tip),'non-front native spring state changed')
        bound.append(dict(resource=f'{rid:016x}',nodes=len(model.transforms),chains=37,drivers=6,excludedWrists=2))
    native.append(dict(directory=str(directory),driverVersion=version,units=bound,movingAnchor=item_motion))
# Actual test01 native fixtures do not have the 0x1d world-anchor path.
for directory in [INSTALL/'test-library/[原比例模型]test01/vpk2patch',PROJECT/'outputs/vrd-analysis-20261107/e2e-diag/test01']:
    if not (directory/'physbone-driver-rig.bin').exists():continue
    rr=py(current.parse_rig((directory/'physbone-rig.bin').read_bytes()));rr['drivers']=py(current.parse_driver_rig((directory/'physbone-driver-rig.bin').read_bytes()))
    ct,_=current.build_chains(table(lua,rr['bones']))
    for _,c in ct.items():check(current.front_skirt_anchor_policy(table(lua,rr),c) is None,'test01 native old policy changed')
    legacy.append(dict(fixture=str(directory),version=rr['drivers']['version'],allOldAnchorPolicies=True))
report=dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',checks=checks,units=units,movingAnchor=motion,changedPolicy='two verified front chains per test07 single/native fixture',legacySemanticNegativeTests=True,legacy=legacy,native=native,parametersUnchanged=True,baseline='pre-fix world-anchor policy isolated in memory')
if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
