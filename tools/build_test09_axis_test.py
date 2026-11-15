"""Build a test09-only source-frame compat copy. No model/installation/game writes."""
from __future__ import annotations
import argparse,copy,hashlib,json,math,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
import numpy as np
from lupa.lua51 import LuaRuntime
import audit_test06_vrd_skirt as a
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.math3d import quat_rotate,quat_conjugate
OUT=ROOT/'outputs/test09-chr654-axis-fix-20261110'
EVIDENCE=ROOT/'outputs/test09-chr654-front-skirt-analysis-20261110'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
MODEL=INSTALL/'test-library/[单骨架模型]test09_chr654'
COMPAT_VERSION='1.3.2-test09-axis1'
RUNTIME_VERSION='2.3.2-test09-axis1'
PROFILE='test09-chr654-source-frame-v1'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def save(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')

def literal(v):
    if isinstance(v,dict):return '{'+','.join('['+json.dumps(k,ensure_ascii=False)+']='+literal(x) for k,x in sorted(v.items()))+'}'
    if isinstance(v,(list,tuple)):return '{'+','.join(literal(x) for x in v)+'}'
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,bool):return 'true' if v else 'false'
    if v is None:return 'nil'
    assert math.isfinite(v)
    return format(v,'.17g') if isinstance(v,float) else str(v)

def replace_once(source,old,new):
    assert source.count(old)==1,'Source anchor missing/nonunique: '+old[:70]
    return source.replace(old,new,1)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/'package-report.json').exists(),'preserve published test release'
    parser=argparse.ArgumentParser();parser.add_argument('--rebuild-draft',action='store_true');args=parser.parse_args()
    assert args.rebuild_draft or not (OUT/'build-report.json').exists(),'use --rebuild-draft only for an unpublished generated draft'
    history=json.loads((EVIDENCE/'snapshot-audit.json').read_text('utf8'))
    for p,h in history['protectedHashes'].items():assert sha(p)==h,'source changed since test09 audit: '+p
    paths=[Path(p) for p in history['protectedHashes']]
    paths += [INSTALL/n for n in ['HD2ModCore.dll','HD2ModManager.dll','settings.json','config.toml','test-library/library.json','test-library/profiles.json'] if (INSTALL/n).is_file()]
    for rel in ['[单骨架模型]test10_chr651','[单骨架动画](test10_chr651)','物理运行时-test06-VRD1.3.1-Arsenal直接导入-20261110']:
        paths += list(p for p in (INSTALL/'test-library'/rel).rglob('*') if p.is_file())
    activation=Path(r'E:\Steam\steamapps\common\Helldivers 2\data\activation-state.json')
    if activation.is_file():
        paths.append(activation)
        current=json.loads(activation.read_text('utf8'))
        paths += [Path(x['targetPath']) for x in current['files'] if Path(x['targetPath']).is_file()]
    before={str(p):sha(p) for p in sorted(set(paths))}
    save(OUT/'protected-before.json',before)
    raw_compat=(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua').read_bytes().replace(b'\r\n',b'\n')
    raw_runtime=(ROOT/'HD2PhysBoneCompat/src/physbone_runtime.lua').read_bytes().replace(b'\r\n',b'\n')
    (OUT/'baseline-physbone_compat.lua').write_bytes(raw_compat)
    (OUT/'baseline-physbone_runtime.lua').write_bytes(raw_runtime)
    L=LuaRuntime(unpack_returned_tuples=True);M=L.execute(raw_compat)
    rig=a.py(M.parse_rig((MODEL/'vpk2patch/physbone-rig.bin').read_bytes()))
    driver=a.py(M.parse_driver_rig((MODEL/'vpk2patch/physbone-driver-rig.bin').read_bytes()))
    assert rig['version']==2 and len(rig['bones'])==34 and driver['version']==3 and len(driver['bones'])==6
    skirts=[b for b in rig['bones'] if b['name'].startswith('skirt_')];assert len(skirts)==22
    mdl=(EVIDENCE/'evidence/survivor_producer.mdl').read_bytes();n,start=struct.unpack_from('<ii',mdl,156);sources={}
    for i in range(n):
        at=start+i*216;offset=at+struct.unpack_from('<i',mdl,at)[0];name=mdl[offset:mdl.index(0,offset)].decode('utf8')
        inv=np.eye(4);inv[:3,:]=np.array(struct.unpack_from('<12f',mdl,at+96)).reshape(3,4);sources[name]=np.linalg.inv(inv)
    units=a.units(MODEL/'vpk2patch/9ba626afa44a3aa3.patch_0');assert len(units)==7
    frames_by_unit={};fits=[]
    for rid,unit in units.items():
        world=_calculate_world_transforms(unit.transforms,unit.parents);indices={h:i for i,h in enumerate(unit.name_hashes)}
        names=[b['name'] for b in rig['bones']]
        X=np.array([sources[n][:3,3] for n in names]);Y=np.array([world[indices[bone_name_hash(n)]].position for n in names])
        affine=np.linalg.lstsq(np.column_stack([X,np.ones(len(X))]),Y,rcond=None)[0].T
        error=float(np.max(np.linalg.norm(np.column_stack([X,np.ones(len(X))])@affine.T-Y,axis=1)))
        U,S,V=np.linalg.svd(affine[:,:3]/.01905);T=U@V
        assert error<2e-6 and np.max(np.abs(S/np.mean(S)-1))<1e-5 and np.linalg.det(T)>.99999
        frames=[]
        for bone in skirts:
            node=indices[bone_name_hash(bone['name'])];parent=indices[bone_name_hash(bone['parentName'])]
            assert unit.parents[node]==parent
            own=T@sources[bone['name']][:3,:3]
            au,as_,av=np.linalg.svd(own);assert np.max(np.abs(as_-1))<1e-5 and np.linalg.det(au@av)>.99999
            own=au@av;q=quat_conjugate(world[parent].rotation)
            axes=[quat_rotate(q,own[:,i].tolist()) for i in range(3)]
            assert np.max(np.abs(np.array(axes)@np.array(axes).T-np.eye(3)))<1e-7
            frames.append(dict(name=bone['name'],parentName=bone['parentName'],left=axes[0],up=axes[1],forward=axes[2],
                bindOffset=unit.transforms[node].position,bindQ=unit.transforms[node].rotation))
        frames_by_unit[rid]=frames;fits.append(dict(resource=rid,maxFitErrorM=error,sourceToPublishedAffine=affine.tolist(),publishedMetersPerSourceUnit=float(np.mean(S)*.01905)))
    chosen=frames_by_unit['3b1b0b47bd4f0004']
    for rid,frames in frames_by_unit.items():
        for x,y in zip(chosen,frames):
            assert x['name']==y['name']
            for k in ['forward','left','up','bindOffset','bindQ']:assert np.max(np.abs(np.array(x[k])-y[k]))<1e-7,(rid,k)
    profile=dict(profile=PROFILE,springVersion=2,driverVersion=3,springBones=rig['bones'],driverBones=driver['bones'],frames=chosen)
    save(OUT/'test09-source-frame-profile.json',profile)
    save(OUT/'source-frame-provenance.json',dict(sourceMdlSha256=sha(EVIDENCE/'evidence/survivor_producer.mdl'),
        springRigSha256=sha(MODEL/'vpk2patch/physbone-rig.bin'),driverRigSha256=sha(MODEL/'vpk2patch/physbone-driver-rig.bin'),
        units=fits,framesEqualAcrossSevenUnits=True,sourceRigNotRestored=True))
    template=(ROOT/'HD2PhysBoneCompat/src/experimental/test09_spring_frame.lua.in').read_text('utf-8-sig')
    injected=replace_once(template,'__PROFILE_LITERAL__',literal(profile))
    compat=raw_compat.decode('utf8')
    compat=replace_once(compat,'M.version = "1.3.1"','M.version = "'+COMPAT_VERSION+'"')
    compat=replace_once(compat,'function M.attach(S, unit, rig, options)',injected+'\nfunction M.attach(S, unit, rig, options)')
    preflight='''\tlocal test09Frames = M.test09_axis_profile(rig)
    local test09Matched = test09Frames ~= nil
    local test09Applied, test09Rejected, test09Reason = 0, 0, "none"
    if test09Matched then
        local accepted, reason = test09_preflight(S, unit, resolveNode, test09Frames)
        if not accepted then test09Rejected, test09Reason, test09Frames = 22, reason or "unknown", nil end
    end

'''
    compat=replace_once(compat,'\tlocal cacheKey, attachCache = M.attach_cache_key(S, unit, nodeCount)',preflight+'\tlocal cacheKey, attachCache = M.attach_cache_key(S, unit, nodeCount)')
    marker='\t\t\t\t\t\t-- 世界朝向锚定：源数据里同时带 **yaw 约束(0x04) + pitch 约束(0x08)** 的骨，'
    apply='''                        if test09Frames ~= nil and test09_apply_frame(chain, bonesNew, segDirLocal, test09Frames) then
                            test09Applied = test09Applied + 1
                        end
'''
    compat=replace_once(compat,marker,apply+marker)
    log='''    if test09Matched then
        logger("[physbone][test09-axis] profile=test09-chr654-source-frame-v1 sourceFrames=22 springs=%d rejected=%d reason=%s", test09Applied, test09Rejected, test09Reason)
    end

'''
    compat=replace_once(compat,'\tlogger(string.format("[physbone] attach：可用链 %d 条（缺节点 %d、缺锚点 %d）",',log+'\tlogger(string.format("[physbone] attach：可用链 %d 条（缺节点 %d、缺锚点 %d）",')
    runtime=replace_once(raw_runtime.decode('utf8'),'M.VERSION = "2.3.1"','M.VERSION = "'+RUNTIME_VERSION+'"')
    (OUT/'physbone_compat-test09.lua').write_bytes(compat.encode('utf8'))
    (OUT/'physbone_runtime-test09.lua').write_bytes(runtime.encode('utf8'))
    compiled=L.execute(compat);assert compiled.version==COMPAT_VERSION
    assert len(compiled.test09_axis_profile(a.table(L,dict(rig,drivers=driver))))==22
    package_source=INSTALL/'test-library/物理运行时-test06-VRD1.3.1-Arsenal直接导入-20261110/9ba626afa44a3aa3.patch_0'
    raw=package_source.read_bytes();nt,n=struct.unpack_from('<II',raw,4);assert nt==1 and n==1
    row=struct.unpack_from('<QQQQQQQIIIIII',raw,72+32*nt);body=raw[row[2]:row[2]+row[7]]
    assert struct.unpack_from('<II',body)==(len(body)-8,2)
    standalone=body[8:].replace(b'\r\n',b'\n').decode('utf8')
    standalone=replace_once(standalone,raw_compat.decode('utf8'),compat)
    standalone=replace_once(standalone,raw_runtime.decode('utf8'),runtime)
    assert standalone.startswith('-- HD2-Addon: mods/hd2modmanager/physbone\n')
    L.eval('function(s)local f,e=loadstring(s);assert(f,e);return true end')(standalone)
    (OUT/'hd2physbone-test09.lua').write_bytes(standalone.encode('utf8'))
    before_after={p:sha(p) for p in before};assert before_after==before
    save(OUT/'build-report.json',dict(status='BUILT_TEST_ONLY_PENDING_REGRESSION',profile=PROFILE,compatVersion=COMPAT_VERSION,runtimeVersion=RUNTIME_VERSION,
        sourceFrames=22,sourceUnits=7,fullRigContract=True,bindPreflightAtomic=True,productionRuntimeModified=False,modelsModified=False,
        gameDeployed=False,gameTested=False,baselinePackage=str(package_source),baselinePackageSha256=sha(package_source),
        protectedFiles=len(before),compatSha256=sha(OUT/'physbone_compat-test09.lua'),runtimeSha256=sha(OUT/'physbone_runtime-test09.lua'),
        standaloneSha256=sha(OUT/'hd2physbone-test09.lua')))
    print('Built TEST-only test09 source-frame copy:',OUT,'protected',len(before))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf8');main()




