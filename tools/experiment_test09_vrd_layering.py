"""Offline controlled experiment: accepted axis1 vs pre-VRD flex frame.
No release or production edits. Only affects in-memory fake-engine reads.
"""
from pathlib import Path
import json,math,sys,copy
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
import numpy as np
import audit_test06_vrd_skirt as a
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_rotate,quat_conjugate,quat_multiply
from anim_batch_mod.native_skeleton import bone_name_hash
OUT=ROOT/'outputs/test09-chr654-hips-probe2-20261110/live-probe2-2300'
AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110';E=ROOT/'outputs/test09-chr654-front-skirt-analysis-20261110'
LIVE1=ROOT/'outputs/test09-chr654-vrd-followup-20261110/live-probe1-2230'

def main():
 p=E/'replay_gpu_skin.py';text=p.read_text('utf8');env={'__file__':str(p),'__name__':'layer_control_fixture'}
 exec(compile(text[:text.index('results={};outputs=')],str(p),'exec'),env)
 L=env['lua'];M=L.execute((AXIS/'physbone_compat-test09.lua').read_bytes());env['M']=M
 units=a.units(env['MODEL']/'Overwrite/9ba626afa44a3aa3.patch_0');u=units['34a40a5ae7a392ba'];env['unit']=u;env['doc']=dict(env['doc'],resource='34a40a5ae7a392ba')
 profile=json.loads((AXIS/'test09-source-frame-profile.json').read_text('utf8'));frames={r['name']:r for r in profile['frames']};raw=json.loads((OUT/'hips-analysis.json').read_text('utf8'))['rawBundles']
 live_samples=[1,11,14];oldhip=u.name_hashes.index(bone_name_hash('hips'));bodyroot=u.parents[oldhip]
 # The scene input uses real Hips bone layout, but these are fixed synthetic
 # controls reconstructed from recorded D; no interpolation pretends to be live.
 conditions=[('neutral',None),('recorded-control-sample1',1),('recorded-control-sample11',11),('recorded-control-sample14',14)]
 results=[];outputs={};springQ={}
 for label,si in conditions:
  for variant in ['axis1','separated-reference-experiment']:
   session,local,world,calls,logs=env['fixture']();M._fastWrite=True
   if si is not None:
    for name,rows in raw['drivers'].items():
     b=next(b for b in profile['driverBones'] if b['name']==name);row=rows[str(si)]
     delta=np.array([float(v) for v in row['ctrlD'].split(',')]);delta=(delta/np.linalg.norm(delta)).tolist()
     control=u.name_hashes.index(bone_name_hash(b['controlName']))
     local[control].rotation=quat_multiply(delta,b['controlBindQ'])
    # retain bind hip/body orientation so only controls differ: separates
    # VRD intent from whole-body lean and locomotion acceleration.
    session.S.World.update_unit(session.world,session.unit)
   helper_nodes={int(r.node):int(r.parentNode) for _,r in session.drivers.items()}
   if variant!='axis1':
    read=session.S.Unit.world_rotation;wrap=L.eval('function(f)return function(...)return f(...)end end')
    def controlled(unit,node):
     # test09 canonical helper bind rotation is identity. Read the hips world
     # frame instead of helper's already-driven frame ONLY for spring anchor.
     # The fake engine's stored/helper pose and rendered hierarchy are untouched.
     return read(unit,helper_nodes.get(int(node),int(node)))
    session.S.Unit.world_rotation=wrap(controlled)
   for frame in range(600):M.update_tip(session,1/60)
   w=world();trans={}
   for _,item in session.sessions.items():
    n=item.chain[1].name
    if n not in env['front_names']:continue
    parent=w[int(item.anchorNode)];node=w[int(item.nodes[1])]
    helperRelative=quat_multiply(quat_conjugate(w[oldhip].rotation),parent.rotation)
    finalRelative=quat_multiply(quat_conjugate(w[oldhip].rotation),node.rotation)
    trans[n]=dict(helperDeg=a.angle(helperRelative),springLocalDeg=a.angle(local[int(item.nodes[1])].rotation),
     finalHipRelativeDeg=a.angle(finalRelative),springLocalQ=local[int(item.nodes[1])].rotation[:],finalHipRelativeQ=finalRelative,
     visibleDir=quat_rotate(node.rotation,frames[n]['forward']))
   springQ[(label,variant)]=trans
   results.append(dict(condition=label,variant=variant,frontBones=trans,engineWrites=calls,scope='fixed synthetic controls; not live animation'))
 # A layered frame should keep identical idle and full physical local flex at
 # fixed controls while helper intent remains a separate parent articulation.
 neutralA=springQ[('neutral','axis1')];neutralB=springQ[('neutral','separated-reference-experiment')]
 idleErr=max(a.angle(neutralA[n]['springLocalQ'],neutralB[n]['springLocalQ']) for n in neutralA)
 checks=[]
 assert idleErr<.001
 for label,si in conditions[1:]:
  b=springQ[(label,'separated-reference-experiment')]
  same=max(a.angle(neutralB[n]['springLocalQ'],b[n]['springLocalQ']) for n in neutralB)
  assert same<.001
  before=springQ[(label,'axis1')]
  checks.append(dict(condition=label,maxLocalFlexChangeVsNeutralDeg=same,
   centralBefore=dict(helperDeg=before['skirt_a_c']['helperDeg'],localFlexDeg=before['skirt_a_c']['springLocalDeg'],finalHipDeg=before['skirt_a_c']['finalHipRelativeDeg']),
   centralAfter=dict(helperDeg=b['skirt_a_c']['helperDeg'],localFlexDeg=b['skirt_a_c']['springLocalDeg'],finalHipDeg=b['skirt_a_c']['finalHipRelativeDeg'])))
 report=dict(status='OFFLINE_EXPERIMENT_NOT_RELEASED_OR_GAME_ACCEPTED',zeroControlIdleMaxDifferenceDeg=idleErr,conditions=results,
  checks=checks,diagnosis='Current spring flex reacts to intentional VRD anchor rotation and gravity pulls it back; neutral flex reference decouples intent without retuning gains.',
  caveat='Experiment intercepts helper anchor reads in a fake engine. Production implementation requires scoped frame data, identity/missing-node guards, binding and dynamics regression. No source file, model or game runtime changed.')
 (OUT/'layer-separation-experiment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
 print('Controlled layer experiment',checks,'idle diff',idleErr)

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
