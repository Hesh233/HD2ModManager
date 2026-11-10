"""Real current rigs: flag DOFs, preserved constrained branches, writes and restoration.
No model/library/game writes. Run with a Python that has lupa.lua51 and numpy.
"""
import argparse,copy,hashlib,json,math,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
sys.path.insert(0,str(INSTALL));sys.path.insert(1,r'I:\HD2SDK-CommunityEdition')
from lupa.lua51 import LuaRuntime
from anim_batch_mod.formats import UnitData
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.math3d import quat_rotate,quat_multiply
from anim_batch_mod.processor import _calculate_world_transforms
AP=argparse.ArgumentParser();AP.add_argument('--report',type=Path,required=True);args=AP.parse_args()
CASES=[('test01','[单骨架模型]test01',{4194694925}),('test06','[原比例模型]test06',{4107007688,215120276}),('test07','[单骨架模型]test07',{706588520,329975474})]
checks=0

def check(ok,message):
 global checks
 checks+=1
 if not ok:raise AssertionError(message)

def table(lua, v):
 if isinstance(v, dict): return lua.table_from({k:table(lua,x) for k,x in v.items()})
 if isinstance(v, (list,tuple)): return lua.table_from([table(lua,x) for x in v])
 return v

def py(v):
 if not hasattr(v,'items'): return v
 d={k:py(x) for k,x in v.items()}
 if d and set(d)==set(range(1,len(d)+1)): return [d[i] for i in range(1,len(d)+1)]
 return d

def units(path):
 d=path.read_bytes(); nt,n=struct.unpack_from('<II',d,4); result={}
 for i in range(n):
  r=struct.unpack_from('<QQQQQQQIIIIII',d,72+32*nt+80*i)
  if r[1]==UNIT_TYPE_ID: result[f'{r[0]:016x}']=UnitData.parse(d[r[2]:r[2]+r[7]])
 return result

def engine(lua,model,rid):
 world=_calculate_world_transforms(model.transforms,model.parents)
 p=[list(w.position) for w in world];q=[list(w.rotation) for w in world]
 local_p=[list(t.position) for t in model.transforms];local_q=[list(t.rotation) for t in model.transforms]
 stats={'writes':{},'translationChanges':{},'translationOffsets':{}};logs=[]
 S=table(lua,{k:{} for k in ['Application','Unit','World','Vector3','Quaternion','Matrix4x4']})
 wrap=lua.eval('function(fn) return function(...)return fn(...)end end')
 def fn(obj,name,f):obj[name]=wrap(f)
 def pose(node):return table(lua,dict(q=local_q[int(node)],p=local_p[int(node)]))
 def packed(v):
  qv=[v.q[i] for i in range(1,5)];pv=[v.p[i] for i in range(1,4)]
  return tuple(sum([quat_rotate(qv,a) for a in ([1,0,0],[0,1,0],[0,0,1])],[])+pv)
 def writeq(u,node,v):
  n=int(node);stats['writes'][n]=stats['writes'].get(n,0)+1;local_q[n]=[v[i] for i in range(1,5)]
 def writepose(u,node,v):
  n=int(node);writeq(u,node,v.q);nv=[v.p[i] for i in range(1,4)]
  offset=math.dist(nv,model.transforms[n].position);stats['translationOffsets'][n]=max(offset,stats['translationOffsets'].get(n,0))
  delta=math.dist(nv,local_p[n]);stats['translationChanges'][n]=max(delta,stats['translationChanges'].get(n,0));local_p[n]=nv
 fn(S.Application,'string_to_id32',bone_name_hash);fn(S.Application,'time_since_launch',lambda:0)
 fn(S.Unit,'alive',lambda u:True);fn(S.Unit,'num_scene_graph_items',lambda u:len(model.transforms))
 fn(S.Unit,'name_hash',lambda u:rid);fn(S.Unit,'debug_name',lambda u:'read-only-breast-fixture')
 fn(S.Unit,'has_node',lambda u,h:h in model.name_hashes);fn(S.Unit,'node',lambda u,h:model.name_hashes.index(h))
 fn(S.Unit,'local_pose',lambda u,n:pose(n));fn(S.Unit,'local_rotation',lambda u,n:table(lua,local_q[int(n)]))
 fn(S.Unit,'world_position',lambda u,n:table(lua,p[int(n)]));fn(S.Unit,'world_rotation',lambda u,n:table(lua,q[int(n)]))
 fn(S.Unit,'set_local_rotation',writeq);fn(S.Unit,'set_local_pose',writepose);fn(S.World,'update_unit',lambda *a:None)
 S.Vector3.to_elements=lua.eval('function(v)return v[1],v[2],v[3] end')
 S.Quaternion.to_elements=lua.eval('function(v)return v[1],v[2],v[3],v[4] end')
 S.Quaternion.from_elements=lua.eval('function(x,y,z,w)return {x,y,z,w} end')
 S.Quaternion.axis_angle=lua.eval('function(a,t)local s=math.sin(t/2);return {a[1]*s,a[2]*s,a[3]*s,math.cos(t/2)} end')
 fn(S.Matrix4x4,'to_elements',packed);fn(S.Matrix4x4,'is_valid',lambda v:True)
 S.Matrix4x4.from_quaternion_position=lua.eval('function(q,p)return {q=q,p=p} end')
 lua.eval('function(v)setmetatable(v,{__call=function(_,x,y,z)return {x,y,z} end})end')(S.Vector3)
 logger=wrap(lambda fmt,*a:logs.append(lua.eval('string.format')(fmt,*a)))
 return S,table(lua,{}),table(lua,dict(logger=logger,world={})),p,q,stats,logs
source=(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua').read_text('utf-8-sig')
baseline=(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua.before-spring-dof-130-20261108.bak').read_text('utf-8-sig')
reports=[];protected={}
for label,folder,wanted in CASES:
 modeldir=INSTALL/'test-library'/folder/'vpk2patch'
 for path in modeldir.glob('*'):
  if path.is_file() and not path.name.endswith('.bak'):protected[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 lua=LuaRuntime(unpack_returned_tuples=True);mod=lua.execute(source)
 oldlua=LuaRuntime(unpack_returned_tuples=True);old=oldlua.execute(baseline)
 rig=dict(py(mod.parse_rig((modeldir/'physbone-rig.bin').read_bytes())),drivers=py(mod.parse_driver_rig((modeldir/'physbone-driver-rig.bin').read_bytes())))
 models=units(modeldir/'9ba626afa44a3aa3.patch_0')
 check(len(models)==7,'expected seven original source Units')
 targets=[b for b in rig['bones'] if bone_name_hash(b['name']) in wanted]
 check({bone_name_hash(b['name']) for b in targets}==wanted,'target hashes absent')
 records=[];first=None
 for rid,model in models.items():
  a=engine(lua,model,rid);b=engine(oldlua,model,rid)
  current=mod.attach(a[0],a[1],table(lua,rig),a[2]);previous=old.attach(b[0],b[1],table(oldlua,rig),b[2])
  check(len(current.sessions)==len(previous.sessions),'chain count changed')
  check(len(current.drivers)==len(previous.drivers) and current.excludedWristDrivers==2,'accepted wrist policy changed')
  entries={x.chain[1].name:x for _,x in current.sessions.items()}
  check(all(x['name'] in entries for x in targets),'target chain not attached')
  count_base=count_free=0
  for item in entries.values():
   for i in range(1,len(item.chain)+1):
    flags=item.chain[i].flags;g=item.tip.bones[i].gains
    base=bool(int(flags)&0x40);free=bool(int(flags)&3) and not bool(int(flags)&0x20)
    check((g.baseSpring is not None)==base,'base flag not honored')
    check(bool(g.freeLength)==free,'length flag not honored')
    count_base+=int(base);count_free+=int(free)
  records.append(dict(resource=rid,chains=len(current.sessions),drivers=len(current.drivers),baseBones=count_base,freeLengthBones=count_free))
  if first is None:first=(rid,model,current,previous,a,b)
 rid,model,current,previous,a,b=first
 new_entries={x.chain[1].name:x for _,x in current.sessions.items()};old_entries={x.chain[1].name:x for _,x in previous.sessions.items()}
 # Replay all unchanged constrained/no-base chains against accepted source exactly.
 preserved=0
 for name,item in new_entries.items():
  if item.tip.hasLinearDofs:continue
  olditem=old_entries[name];node=int(item.anchorNode);ap=a[3][node];aq=a[4][node]
  for frame in range(241):
   wave=.02*math.sin(frame/31);position=[ap[0]+wave,ap[1],ap[2]]
   mod.step_tip(item.tip,1/240,*position,*aq);old.step_tip(olditem.tip,1/240,*position,*aq)
   for i in range(1,len(item.tip.tips)+1):
    for field in ['px','py','pz','vx','vy','vz']:
     check(item.tip.tips[i][field]==olditem.tip.tips[i][field],'accepted constrained numeric branch changed')
  preserved+=1
 bones=[]
 for fact in targets:
  env=engine(lua,model,rid)
  s=mod.attach(env[0],env[1],table(lua,rig),env[2]);entry=next(x for _,x in s.sessions.items() if x.chain[1].name==fact['name'])
  anchor=int(entry.anchorNode);node=int(entry.nodes[1]);ap=env[3][anchor][:];aq=env[4][anchor][:]
  initial=copy.deepcopy(py(entry.tip));forward=quat_rotate(aq,initial['segDirLocal'][0]);span_change=base_offset=0
  t=copy.deepcopy(initial)
  for bone in t['bones']:bone['gains']['g']=0 # diagnostic axial control only; does not alter real rig
  numeric=table(lua,t)
  for frame in range(721):
   wave=.03*math.sin(2*math.pi*frame/240);position=[x+wave*y for x,y in zip(ap,forward)]
   mod.step_tip(numeric,1/240,*position,*aq)
   tip0=numeric.tips[1]
   if tip0.span is not None:span_change=max(span_change,abs(tip0.span-numeric.bones[1].gains.L))
   base_offset=max(base_offset,numeric.maxBaseOffset or 0)
   check(all(math.isfinite(tip0[k]) for k in ['px','py','pz','vx','vy','vz']),'nonfinite real-rig state')
  if fact['flags']&0x20:check(span_change==0,'fixed real-rig length changed')
  else:check(span_change>1e-4,'free real-rig has no axial response')
  if fact['flags']&0x40:check(base_offset>1e-5,'real-rig base spring has no inertial response')
  # Real bind + real setters: local translation only belongs to base-flag bones.
  env=engine(lua,model,rid);s=mod.attach(env[0],env[1],table(lua,rig),env[2])
  entry=next(x for _,x in s.sessions.items() if x.chain[1].name==fact['name'])
  s.sessions=table(lua,[entry]);s.drivers=table(lua,[])
  left=quat_rotate(aq,py(entry.tip)['bones'][0]['frameLocal'][:3])
  env[5]['writes'].clear();env[5]['translationOffsets'].clear()
  for frame in range(180):
   wave=.03*math.sin(2*math.pi*frame/60);env[3][anchor]=[x+wave*y for x,y in zip(ap,left)]
   mod.update(s,1/60,1000)
  offset=env[5]['translationOffsets'].get(node,0);writes=env[5]['writes'].get(node,0)
  check(writes>0,'target had no writer calls')
  if fact['flags']&0x40:check(offset>1e-5,'base displacement did not reach the local pose')
  else:check(offset==0,'unflagged bone translation changed')
  mod.release(s);pose=env[0].Unit.local_pose(env[1],node)
  actual=[pose.p[i] for i in range(1,4)]
  check(math.dist(actual,model.transforms[node].position)<1e-10,'release did not restore original local position')
  check(entry.tip.tips[1].baseSpringState is None and not entry.tip.tips[1].ready,'linear state survived release')
  bones.append(dict(hash=bone_name_hash(fact['name']),name=fact['name'],flags=hex(fact['flags']),
   axialSpanChangeMetres=span_change,baseWorldOffsetMetres=base_offset,maximumWrittenLocalOffsetMetres=offset,writes=writes,releaseRestored=True))
 reports.append(dict(model=label,units=records,constrainedChainsBitwisePreserved=preserved,bones=bones))
for path,value in protected.items():check(hashlib.sha256(Path(path).read_bytes()).hexdigest()==value,'model changed during read-only tests')
result=dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',compatVersion='1.3.1',checks=checks,models=reports,
 sourceSha256=hashlib.sha256(source.encode()).hexdigest(),baselineSha256=hashlib.sha256(baseline.encode()).hexdigest(),protectedModelFiles=len(protected))
args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(status=result['status'],checks=checks,units=sum(len(r['units']) for r in reports),models=[dict(model=r['model'],preserved=r['constrainedChainsBitwisePreserved'],bones=r['bones']) for r in reports]),ensure_ascii=False,indent=2))
