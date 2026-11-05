"""B12 actual-layout, lifecycle, transaction, and unchanged-solver regression."""
import ast
import os
from package_native_v12 import ROOT,load,save_json,digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units,shape,plain
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime
import audit_native_v18_b9 as b9
W=ROOT/'outputs/native-v20-b12-20261104';P=ROOT/'outputs/native-manual-20261103/project'


def raw(t):
    x,y,z,w=t.rotation;s=t.scale
    a=[1-2*y*y-2*z*z,2*x*y+2*z*w,2*x*z-2*y*w,
       2*x*y-2*z*w,1-2*x*x-2*z*z,2*y*z+2*x*w,
       2*x*z+2*y*w,2*y*z-2*x*w,1-2*x*x-2*y*y]
    return [v*s[i//3]for i,v in enumerate(a)]+t.position


def main():
    save_json(W/'B9.json',load(P/'diagnostics/B9/B9.json'));b9.W=W;b9.main()
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    module=(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    harness=(ROOT/'HD2PhysBoneCompat/test/attachment_probe_harness.lua').read_text(encoding='utf-8')
    fixture=dict(hashes=avatar.name_hashes,parents=[0 if p is None else p+1 for p in avatar.parents],matrices=[raw(t)for t in avatar.transforms])
    cases={}
    for variant in ('A','B','ALL'):
        vm=LuaRuntime(unpack_returned_tuples=True);vm.globals().probe=vm.execute(module)
        vm.globals().profile=vm.table_from(load(W/('B12-'+variant+'.json')),recursive=True)
        vm.globals().fixture=vm.table_from(fixture,recursive=True)
        result=plain(vm.execute(harness));log='\n'.join(result.pop('logs').values())
        assert 'event=applied'in log and 'event=rollback avatar=1 verified=true'in log
        (W/('probe-'+variant+'-synthetic.log')).write_text(log,encoding='utf-8');cases[variant]=result
    # Full adapter with actual split model hashes; explicit Avatar-only setters.
    models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    profile=load(W/'B12-A.json')
    fixture=dict(avatar=shape(avatar),models={r:shape(models[r])for r in profile['modelLayouts']})
    base=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8').split('check(armor.nodes~=A.nodes',1)[0]
    tree=ast.parse((ROOT/'outputs/native-b8-analysis-20261104/analyze_evidence.py').read_text(encoding='utf-8'))
    replay=next(n.value.value for n in ast.walk(tree)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='program'for t in n.targets))
    setup=replay.split('local animationA=copy(A.locals)',1)[0]
    program=r'''
S.Unit.world_pose=function(u,n)return world(u,n)end
S.Unit.scene_graph_parent=function(u,n)if u.owner then return nil end;return u.parents[n]end
S.Matrix4x4.from_elements=function(...)
 local m={...};local q=quat_from_matrix(m)
 return {q={q[1],q[2],q[3],q[4]},p={m[10],m[11],m[12]}}
end
local animationA=copy(A.locals);local animationB=copy(B.locals)
local first=profile.attachmentProbe.nodes[1].index+1
local nativeHandBefore=copy(A.locals[48]);local history={}
local originalSetter=S.Unit.set_local_pose
S.Unit.set_local_pose=function(u,n,p)
 check(u==A,'probe or solver wrote another Avatar/model');return originalSetter(u,n,p)
end
for k=1,18 do
 frame=frame+1;clock=clock+1
 A.locals=copy(animationA);B.locals=copy(animationB)
 for _,u in ipairs(parts)do refresh(u)end
 runtime:tick(frame)
 local d=world(A,first).p[3]-world(B,first).p[3]
 history[k]={active=runtime.stats.active,delta=d}
 check(adapter.close(A.locals[48],nativeHandBefore),'native hand modified')
 check(B.writes==0,'original armor Avatar modified')
 for _,u in ipairs(parts)do check(u.writes==0,'model local mutated')end
end
local hasApplied=false;for _,line in ipairs(logs)do if line:find('event=applied',1,true)then hasApplied=true end end
check(hasApplied,'no applied telemetry on real adapter')
-- Lose body selection while UP. Do not feed a new animation: this requires restore.
for _,u in ipairs(parts)do u.visible=false end
clock=clock+1;frame=frame+1;runtime:tick(frame)
check(runtime.stats.active==0,'hidden body remained active')
for _,r in ipairs(profile.attachmentProbe.nodes)do
 check(adapter.close(A.locals[r.index+1],animationA[r.index+1]),'switch away retained probe')
end
for _,u in ipairs(parts)do u.visible=true end
for k=1,6 do
 clock=clock+1;frame=frame+1;A.locals=copy(animationA);for _,u in ipairs(parts)do refresh(u)end;runtime:tick(frame)
 if k<=5 then check(math.abs(world(A,first).p[3]-world(B,first).p[3])<1e-6,'switch back did not restart BASE phase')end
end
runtime:release()
for _,r in ipairs(profile.attachmentProbe.nodes)do check(adapter.close(A.locals[r.index+1],animationA[r.index+1]),'release retained probe')end
return {checks=checks,history=history,logs=logs,otherAvatarWrites=B.writes}
'''
    from anim_batch_mod.math3d import matrix3_columns_to_quaternion
    vm=LuaRuntime(unpack_returned_tuples=True)
    def quat(m):return vm.table_from(matrix3_columns_to_quaternion([[m[i]for i in range(j,j+3)]for j in (1,4,7)]))
    vm.globals().quat_from_matrix=quat
    vm.globals().adapter=vm.execute((ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8'))
    vm.globals().profile=vm.table_from(profile,recursive=True);vm.globals().fixture=vm.table_from(fixture,recursive=True);vm.globals().hash_name=bone_name_hash
    integrated=plain(vm.execute(base+setup+program));log='\n'.join(integrated.pop('logs').values())
    assert 'event=disabled'not in log and 'event=rollback'not in log,log[-4000:]
    assert any(abs(r['delta']-.6)<1e-5 for r in integrated['history'].values()),integrated
    assert any(abs(r['delta'])<1e-5 for r in integrated['history'].values()),integrated
    (W/'probe-full-adapter-synthetic.log').write_text(log,encoding='utf-8')
    save_json(W/'attachment-probe-audit.json',dict(status='PASS',gameTested=False,cases=cases,fullAdapter=integrated,
        scope='Affine real-layout fixtures, parent-family closure, copied matrices, rollback, live-animation replacement, test01 gating, hidden body/release, zero model/other-avatar writes.',
        sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'),probeSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua')))
    print('PASS: all B12 variants, affine displacement/restore, faults, real adapter test01 gating, B9 regression.')


if __name__=='__main__':main()
