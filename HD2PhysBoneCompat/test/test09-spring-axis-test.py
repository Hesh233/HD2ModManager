"""Test the separate test09 source-frame build, never production/library/game writes."""
from __future__ import annotations
import argparse,copy,hashlib,json,math,runpy,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
import numpy as np
from lupa.lua51 import LuaRuntime
import audit_test06_vrd_skirt as a
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_rotate,quat_multiply,quat_conjugate
from anim_batch_mod.native_skeleton import bone_name_hash
OUT=ROOT/'outputs/test09-chr654-axis-fix-20261110'
EVIDENCE=ROOT/'outputs/test09-chr654-front-skirt-analysis-20261110'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
BASELINE=(OUT/'baseline-physbone_compat.lua').read_bytes()
SOURCE=(OUT/'physbone_compat-test09.lua').read_bytes()
checks=0

def check(ok,label):
    global checks
    checks+=1
    if not ok:raise AssertionError(label)

def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),'utf8')

def load_skin_fixture():
    # Reuse the already verified GPU decoder/skin math, but stop before the
    # old analysis loop (which would write historical results). Prefix is pure.
    path=EVIDENCE/'replay_gpu_skin.py';s=path.read_text('utf8')
    prefix=s[:s.index('results={};outputs=')]
    env={'__file__':str(path),'__name__':'test09_skin_fixture'}
    exec(compile(prefix,str(path),'exec'),env)
    return env


def main():
    env=load_skin_fixture();L=env['lua'];old=L.execute(BASELINE);new=L.execute(SOURCE)
    rig=env['rig'];profile=json.loads((OUT/'test09-source-frame-profile.json').read_text('utf8'))
    check(len(new.test09_axis_profile(a.table(L,rig)))==22,'exact rig selected')
    negative=[]
    mutations=[('spring-version',lambda r:r.__setitem__('version',1)),('driver-v2',lambda r:r['drivers'].__setitem__('version',2)),
        ('missing-spring',lambda r:r['bones'].pop()),('missing-driver',lambda r:r['drivers']['bones'].pop()),
        ('duplicate-spring',lambda r:r['bones'].__setitem__(0,copy.deepcopy(r['bones'][1]))),
        ('spring-name',lambda r:r['bones'][0].__setitem__('name','other_model_hair')),
        ('spring-parent',lambda r:r['bones'][-1].__setitem__('parentName','hips')),
        ('spring-length',lambda r:r['bones'][-1]['params'].__setitem__('length',7.123)),
        ('spring-flags',lambda r:r['bones'][-1].__setitem__('flags',0)),
        ('driver-control',lambda r:r['drivers']['bones'][0].__setitem__('controlName','l_hand')),
        ('driver-rule',lambda r:r['drivers']['bones'][0]['rules'][0].__setitem__('invTolerance',.7)),
        ('missing-canonical-bind',lambda r:r['drivers']['bones'][0].pop('controlBindQ')),
        ('changed-canonical-bind',lambda r:r['drivers']['bones'][0]['controlBindQ'].__setitem__(0,.5)),
        ('nonfinite-param',lambda r:r['bones'][0]['params'].__setitem__('tipMass',float('nan')))]
    for name,mutate in mutations:
        r=copy.deepcopy(rig);mutate(r);check(new.test09_axis_profile(a.table(L,r)) is None,'negative '+name);negative.append(name)
    # All source Units and all same-character rewritten variants share one canonical frame.
    actual_models=[]
    for sub in ['vpk2patch','Overwrite']:
        for rid,u in a.units(env['MODEL']/sub/'9ba626afa44a3aa3.patch_0').items():
            if len(u.transforms)==154 and bone_name_hash('skirt_a_c') in u.name_hashes:actual_models.append((sub,rid,u))
    unit0=env['unit'];doc0=env['doc'];all_units=[]
    for sub,rid,u in actual_models:
        env['unit']=u;env['doc']=dict(doc0,resource=rid);env['M']=new
        session,local,getworld,calls,logs=env['fixture']()
        check(any('springs=22 rejected=0' in l for l in logs),'all source frames applied '+rid)
        expected={f['name']:f for f in profile['frames']}
        for _,entry in session.sessions.items():
            name=entry.chain[1].name
            if name not in expected:continue
            check(np.max(np.abs(np.array([entry.tip.segDirLocal[1][i] for i in range(1,4)])-expected[name]['forward']))<1e-10,'canonical frame '+name)
            check(entry.tip.goalQ is None,'helper follows current rotation '+name)
        for frame in range(60):new.update_tip(session,1/60)
        for t in local:check(all(math.isfinite(x) for x in t.position+t.rotation),'finite '+rid)
        new.release(session)
        for i,t in enumerate(local):check(a.angle(t.rotation,u.transforms[i].rotation)<1e-4 and np.linalg.norm(np.array(t.position)-u.transforms[i].position)<1e-6,'release exact '+rid)
        all_units.append(dict(kind=sub,resource=rid,sourceFrames=22,releaseRestored=True))
    env['unit']=unit0;env['doc']=doc0
    # Changed bind/first-pose: preflight rejects unknown local bind atomically;
    # world/root yaw (animated parent) must not change the canonical frame.
    first_poses=[]
    for deg in [0,30,90,180,-75]:
        u=copy.deepcopy(unit0);i=u.name_hashes.index(bone_name_hash('hips'))
        yaw=[0,0,math.sin(math.radians(deg)/2),math.cos(math.radians(deg)/2)]
        u.transforms[i].rotation=quat_multiply(yaw,u.transforms[i].rotation)
        env['unit']=u;env['M']=new
        session,local,getworld,calls,logs=env['fixture']()
        check(any('springs=22 rejected=0' in l for l in logs),'first yaw accepted')
        for _,entry in session.sessions.items():
            if entry.chain[1].name in {x['name'] for x in profile['frames']}:
                f=next(f for f in profile['frames'] if f['name']==entry.chain[1].name)
                check(np.linalg.norm(np.array(a.py(entry.tip.segDirLocal[1]))-f['forward'])<1e-10,'first pose invariant')
        first_poses.append(dict(hipsYawDeg=deg,canonicalFrameIndependent=True))
    bind_rejected=[]
    for name,field in [('skirt_a_c','position'),('skirt_b_l','rotation')]:
        u=copy.deepcopy(unit0);i=u.name_hashes.index(bone_name_hash(name))
        if field=='position':u.transforms[i].position[0]+=.001
        else:u.transforms[i].rotation=[0,0,math.sin(.1),math.cos(.1)]
        env['unit']=u;env['M']=new
        session,local,getworld,calls,logs=env['fixture']()
        check(any('springs=0 rejected=22' in l for l in logs),'changed local bind rejected atomically')
        env['M']=old;ref,_,_,_,_=env['fixture']()
        for i,item in session.sessions.items():
            check(a.py(item.tip.segDirLocal)==a.py(ref.sessions[i].tip.segDirLocal),'unknown bind keeps legacy frames')
        bind_rejected.append(name+':'+field)
    # A missing node must never receive pose access or a partial new frame.
    path=EVIDENCE/'replay_gpu_skin.py';prefix=path.read_text('utf8').split('results={};outputs=',1)[0]
    prefix=prefix.replace('assert len(session.sessions)==25 and len(session.drivers)==6','pass')
    ghost={'__file__':str(path),'__name__':'test09_missing_node_fixture'};exec(compile(prefix,str(path),'exec'),ghost)
    missing=copy.deepcopy(unit0);idx=missing.name_hashes.index(bone_name_hash('skirt_a_c'));missing.name_hashes[idx]=bone_name_hash('missing_test09_skirt')
    ghost['unit']=missing;ghost['M']=ghost['lua'].execute(SOURCE)
    missing_session,_,_,_,missing_logs=ghost['fixture']()
    check(any('springs=0 rejected=22' in l for l in missing_logs),'missing node atomic fallback')
    check(len(missing_session.sessions)==24,'missing node skipped without invalid read')
    # Gentle illustrative animated-thigh controls with numeric FK before the
    # driver pass. This is NOT captured ship animation or a visual acceptance.
    env['unit']=unit0;motion=[]
    for label,mod in [('baseline',old),('fixed',new)]:
        env['M']=mod;session,local,getworld,calls,logs=env['fixture']();mod._fastWrite=True
        worst=1.;peak=0.
        for frame in range(360):
            for bone,sign in [('l_thigh',1),('r_thigh',-1)]:
                index=unit0.name_hashes.index(bone_name_hash(bone));ang=sign*math.radians(20)*math.sin(frame*.035)
                local[index].rotation=quat_multiply([0,0,math.sin(ang/2),math.cos(ang/2)],unit0.transforms[index].rotation)
            session.S.World.update_unit(session.world,session.unit)
            mod.update_tip(session,1/60)
            if frame%12==0:
                p=env['skin'](getworld());check(np.isfinite(p).all(),'animated control finite')
                v=env['stats'](p);worst=max(worst,v['edgeStretchMax']);peak=max(peak,v['frontDisplacementMaxCm'])
        motion.append(dict(source=label,maxSampledEdgeRatio=worst,peakFrontDisplacementCm=peak,frames=360,scope='illustrative CPU controls, not recorded gameplay'))
    check(motion[1]['maxSampledEdgeRatio']<motion[0]['maxSampledEdgeRatio'],'animated controlled comparison improves')
    env['unit']=unit0
    # Fixed-bind GPU reconstruction, real production update/write path in mock engine.
    results={};positions={'bind':env['bind']};hair_traces={}
    for mode,mod in [('baseline',old),('fixed',new),('fixed-matrix',new),('fixed-144Hz',new),('fixed-30Hz',new),('fixed-repeat',new)]:
        env['M']=mod;session,local,getworld,calls,logs=env['fixture']()
        if mode=='fixed-matrix':session.S.Unit.set_local_rotation=None;mod._fastWrite=False
        else:mod._fastWrite=True
        fps=144 if mode=='fixed-144Hz' else 30 if mode=='fixed-30Hz' else 60
        for frame in range(10*fps):mod.update_tip(session,1/fps)
        p=env['skin'](getworld());positions[mode]=p
        hair_traces[mode]=[[t.position,t.rotation] for i,t in enumerate(local) if unit0.name_hashes[i] in {bone_name_hash(b['name']) for b in rig['bones'] if b['name'].startswith('hair_')}]
        results[mode]=dict(env['stats'](p),mockCalls=calls,frontAngles={n:a.angle(local[i].rotation,unit0.transforms[i].rotation) for n,i in env['name_to_index'].items() if n in env['front_names']})
        check(np.isfinite(p).all(),'GPU finite '+mode)
    check(hair_traces['baseline']==hair_traces['fixed'],'test09 hair output untouched')
    check(results['fixed']['edgeStretchMax']<1.21,'fixed GPU max edge ratio')
    check(results['fixed']['edgeStretchP95']<1.03,'fixed GPU P95 edge ratio')
    check(results['fixed']['areaBelow10Percent']==0,'fixed avoids severe collapse')
    check(np.max(np.abs(positions['fixed']-positions['fixed-matrix']))<1e-7,'matrix and fast write match')
    check(np.array_equal(positions['fixed'],positions['fixed-repeat']),'repeat deterministic')
    for mode in ['fixed-144Hz','fixed-30Hz']:check(results[mode]['edgeStretchMax']<1.22,'frame-rate stable '+mode)
    # Other models, including accepted test06 and currently deployed test10:
    # compare per-frame writes/quaternions/positions/release, NOT just selector status.
    helpers=(ROOT/'HD2PhysBoneCompat/test/spring-dof-model-test.py').read_text('utf8')
    helpers=helpers[:helpers.index("source=(ROOT/")]
    ns={'__file__':str(ROOT/'HD2PhysBoneCompat/test/spring-dof-model-test.py'),'__name__':'test09_legacy_fixture'}
    saved=sys.argv;sys.argv=['legacy-helper','--report',str(OUT/'unused-report.json')]
    try:exec(compile(helpers,ns['__file__'],'exec'),ns)
    finally:sys.argv=saved
    legacy=[]
    legacy_paths=[('test01-native',INSTALL/'test-library/[原比例模型]test01/vpk2patch'),('test01-single',INSTALL/'test-library/[单骨架模型]test01/vpk2patch'),('test06-native',INSTALL/'test-library/[原比例模型]test06/vpk2patch'),
        ('test07-single',INSTALL/'test-library/[单骨架模型]test07/vpk2patch'),('test10-single',INSTALL/'test-library/[单骨架模型]test10_chr651/vpk2patch')]
    for label,path in legacy_paths:
        r=a.py(old.parse_rig((path/'physbone-rig.bin').read_bytes()));r['drivers']=a.py(old.parse_driver_rig((path/'physbone-driver-rig.bin').read_bytes()))
        check(new.test09_axis_profile(a.table(L,r)) is None,'real other rig does not match '+label)
        models=a.units(path/'9ba626afa44a3aa3.patch_0')
        rid,model=next(iter(models.items()));world=_calculate_world_transforms(model.transforms,model.parents)
        runs=[]
        for mod in [old,new]:
            S,u,opts,p,q,stats,logs=ns['engine'](L,model,rid);session=mod.attach(S,u,a.table(L,r),opts);trace=[]
            check(not any('[test09-axis]' in l for l in logs),'unmatched rig no tag '+label)
            for frame in range(240):
                shift=.008*math.sin(frame*.07)
                for i,w in enumerate(world):
                    p[i]=[w.position[0]+shift,w.position[1],w.position[2]+.004*math.cos(frame*.09)]
                    angle=.1*math.sin(frame*.05);q[i]=quat_multiply([0,0,math.sin(angle/2),math.cos(angle/2)],w.rotation)
                mod.update_tip(session,1/60)
                trace.append(dict(springs=[a.py(x.lastWritten) for _,x in session.sessions.items()],drivers=[a.py(x.lastWritten) for _,x in session.drivers.items()],
                    writes=copy.deepcopy(stats['writes']),calls=session.engineCalls))
            mod.release(session);runs.append(dict(trace=trace,stats=stats))
        check(runs[0]==runs[1],'legacy numerical trace exact '+label)
        legacy.append(dict(model=label,resource=rid,driverVersion=r['drivers']['version'],frames=240,numericTraceExact=True))
    save(OUT/'test09-axis-regression.json',dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',checks=checks,profile='test09-chr654-source-frame-v1',
        fullContractNegativeControls=negative,actualUnitChecks=all_units,firstPoseChecks=first_poses,localBindRejectedAtomically=bind_rejected,missingNodeRejectedAtomically=True,illustrativeMotionChecks=motion,
        gpuBindMaxErrorM=env['err'],gpuResults=results,test09HairNumericallyUnchanged=True,legacyRigs=legacy,productionFilesNotWritten=True,gameTested=False))
    np.savez_compressed(OUT/'test09-axis-gpu-replay.npz',faces=env['frontfaces'],**positions)
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    fig,axs=plt.subplots(1,3,figsize=(12,5),layout='constrained')
    for ax,key in zip(axs,['bind','baseline','fixed']):
        surface=positions[key][env['frontfaces']];project=surface[:,:,[0,2]]*100;project[:,:,0]*=-1;order=np.argsort(surface[:,:,1].mean(axis=1))[::-1]
        ax.add_collection(PolyCollection(project[order],array=np.mean(env['fw'][env['frontfaces']],axis=1)[order],cmap='Blues',clim=(0,1),edgecolors='#294860',linewidths=.15))
        ax.set_xlim(-24,24);ax.set_ylim(60,94);ax.set_aspect('equal');ax.set_title(key);ax.set_xlabel('front X (cm)')
    fig.suptitle('test09 source-frame TEST fix: decoded GPU + Lua CPU replay, NOT game pixels')
    fig.savefig(OUT/'test09-axis-comparison.png',dpi=150);plt.close(fig)
    print('PASS test09 axis regression',checks,'checks','legacy',len(legacy),'Units',len(all_units),'max edge',results['fixed']['edgeStretchMax'])

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf8');main()




