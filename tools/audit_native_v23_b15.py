"""Verify both subsets against independent solved controls and real topology."""
import ast
import copy
import os
from package_native_v12 import ROOT,load,save_json,digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units,shape,plain
from audit_native_v20_b12 import raw
from anim_batch_mod.native_skeleton import bone_name_hash
from anim_batch_mod.math3d import matrix3_columns_to_quaternion
from lupa.lua51 import LuaRuntime

W=ROOT/'outputs/native-v23-b15-20261105';P=ROOT/'outputs/native-manual-20261103/project'


def main():
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    source=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
    module=(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua').read_text(encoding='utf-8')
    strict=(ROOT/'HD2PhysBoneCompat/test/strict_id32_fixture.lua').read_text(encoding='utf-8')
    harness=(ROOT/'HD2PhysBoneCompat/test/attachment_probe_harness.lua').read_text(encoding='utf-8')
    harness=harness.replace('local function make(p)',strict+'\nlocal function make(p)')
    wrap="local originalMake=make\nmake=function(p)local instance=originalMake(p);if instance then local apply=instance.apply;instance.apply=function(self,...)strictIdStats.advanceFrame();return apply(self,...)end end;return instance end\nlocal base=copy(avatar.locals)"
    harness=harness.replace('local base=copy(avatar.locals)',wrap)
    harness=harness.replace('return {checks=checks',"check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'invalid or expired ID');return {checks=checks")
    cases={}
    for variant in ('A1','A2'):
        profile=load(W/('B15-'+variant+'.json'))
        vm=LuaRuntime(unpack_returned_tuples=True);vm.globals().probe=vm.execute(module)
        vm.globals().profile=vm.table_from(profile,recursive=True);vm.globals().hash_name=bone_name_hash
        vm.globals().fixture=vm.table_from(dict(hashes=avatar.name_hashes,parents=[0 if p is None else p+1 for p in avatar.parents],matrices=[raw(t)for t in avatar.transforms]),recursive=True)
        result=plain(vm.execute(harness));log='\n'.join(result.pop('logs').values())
        assert 'event=applied'in log and 'event=rollback avatar=1 verified=true'in log
        (W/f'probe-{variant}-synthetic.log').write_text(log,encoding='utf-8');cases[variant]=result
    base=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8').split('check(armor.nodes~=A.nodes',1)[0]
    base=base.replace('local runtime=adapter.new',strict+'\nlocal runtime=adapter.new')
    tree=ast.parse((ROOT/'outputs/native-b8-analysis-20261104/analyze_evidence.py').read_text(encoding='utf-8'))
    replay=next(n.value.value for n in ast.walk(tree)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='program'for t in n.targets))
    setup=replay.split('local animationA=copy(A.locals)',1)[0]
    program=r'''
S.Unit.world_pose=function(u,n)return world(u,n)end
S.Unit.scene_graph_parent=function(u,n)if u.owner then return nil end;return u.parents[n]end
S.Matrix4x4.from_elements=function(...)
 local m={...};local q=quat_from_matrix(m);return {q={q[1],q[2],q[3],q[4]},p={m[10],m[11],m[12]}}
end
local animationA=copy(A.locals);local animationB=copy(B.locals)
local nativeLeft,nativeRight=copy(A.locals[48]),copy(A.locals[72])
local history,switchback={},{}
local originalSetter=S.Unit.set_local_pose
S.Unit.set_local_pose=function(u,n,p)check(u==A,'other Avatar/model written');return originalSetter(u,n,p)end
local function sample()
 local rows={};for _,r in ipairs(profile.attachmentProbe.nodes)do rows[r.name]=copy(world(A,r.index+1).p)end
 return rows
end
local function runTick()
 strictIdStats.advanceFrame();runtime:tick(frame)
 check(adapter.close(A.locals[48],nativeLeft)and adapter.close(A.locals[72],nativeRight),'native hand modified')
 check(B.writes==0,'other Avatar written');for _,u in ipairs(parts)do check(u.writes==0,'model local written')end
end
for k=1,18 do
 frame=frame+1;clock=clock+1;A.locals=copy(animationA);B.locals=copy(animationB)
 for _,u in ipairs(parts)do refresh(u)end;runTick();history[k]=sample()
end
local hasApplied=false;for _,line in ipairs(logs)do if line:find('event=applied',1,true)then hasApplied=true end end
check(hasApplied==profile.attachmentProbe.enabled,'incorrect probe activation')
for _,u in ipairs(parts)do u.visible=false end
clock=clock+1;frame=frame+1;runTick();check(runtime.stats.active==0,'hidden body active')
for _,r in ipairs(profile.attachmentProbe.nodes)do check(adapter.close(A.locals[r.index+1],animationA[r.index+1]),'switch-away retained probe')end
for _,u in ipairs(parts)do u.visible=true end
for k=1,6 do
 clock=clock+1;frame=frame+1;A.locals=copy(animationA);for _,u in ipairs(parts)do refresh(u)end;runTick();switchback[k]=sample()
end
strictIdStats.advanceFrame();runtime:release()
for _,r in ipairs(profile.attachmentProbe.nodes)do check(adapter.close(A.locals[r.index+1],animationA[r.index+1]),'release retained probe')end
check(strictIdStats.invalidArgumentCalls==0 and strictIdStats.expiredArgumentCalls==0,'ID contract/lifetime failed')
return {checks=checks,history=history,switchback=switchback,logs=logs,otherAvatarWrites=B.writes,expiredIdCalls=strictIdStats.expiredArgumentCalls}
'''
    full={}
    for variant in ('A1','A2'):
        profile=load(W/('B15-'+variant+'.json'))
        fixture=dict(avatar=shape(avatar),models={r:shape(models[r])for r in profile['modelLayouts']})
        def run(enabled):
            p=copy.deepcopy(profile);p['attachmentProbe']['enabled']=enabled
            vm=LuaRuntime(unpack_returned_tuples=True)
            def quat(m):return vm.table_from(matrix3_columns_to_quaternion([[m[i]for i in range(j,j+3)]for j in (1,4,7)]))
            vm.globals().quat_from_matrix=quat;vm.globals().adapter=vm.execute(source)
            vm.globals().profile=vm.table_from(p,recursive=True);vm.globals().fixture=vm.table_from(fixture,recursive=True);vm.globals().hash_name=bone_name_hash
            result=plain(vm.execute(base+setup+program));log='\n'.join(result.pop('logs').values())
            assert not any('event='+e in log for e in ('disabled','rollback','validation_mismatch','restore_failed'))
            (W/f'full-{variant}-{enabled}.log').write_text('\n'.join(r for r in log.splitlines()if '[attach_probe]'in r),encoding='utf-8')
            return result
        enabled,control=run(True),run(False)
        deltas={};up=base_count=0
        for k,snapshot in enabled['history'].items():
            delta=[]
            for name,p in snapshot.items():
                q=control['history'][k][name];d=[p[i]-q[i]for i in (1,2,3)]
                assert abs(d[0])<1e-6 and abs(d[1])<1e-6
                assert min(abs(d[2]),abs(d[2]-.6))<1e-6
                delta.append(d[2])
            assert max(delta)-min(delta)<1e-6
            deltas[k]=delta[0];up+=abs(delta[0]-.6)<1e-6;base_count+=abs(delta[0])<1e-6
        assert up and base_count
        for k in range(1,6):
            for name,p in enabled['switchback'][k].items():
                assert max(abs(p[i]-control['switchback'][k][name][i])for i in (1,2,3))<1e-6,'switch-back failed BASE reset'
        full[variant]=dict(enabledChecks=enabled['checks'],controlChecks=control['checks'],worldDeltaByFrame=deltas,
            shiftedFrames=up,baseFrames=base_count,otherAvatarWrites=enabled['otherAvatarWrites'],expiredIdCalls=enabled['expiredIdCalls'])
    save_json(W/'attachment-probe-audit.json',dict(status='PASS',cases=cases,fullAdapter=full,
        sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'),probeSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachment_probe.lua'),
        gameTested=False,scope='Subset affine/lifecycle/fault cases and independent solved-control comparisons for every selected node; fresh IDs per frame; zero model/other-Avatar writes.'))
    print('PASS: A1/A2 subsets, affine/rollback/lifetime cases, paired solved controls, all selected-node deltas, switch-away/back and release.')


if __name__=='__main__':main()
