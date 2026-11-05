"""B10 transaction faults plus the unchanged B9 disabled path."""
import ast
import os
from package_native_v12 import ROOT,load,save_json,digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import plain,units,shape
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime
import audit_native_v18_b9 as b9
from analyze_native_b10_log import analyze
W=ROOT/'outputs/native-v19-20261104'


def main():
    profile=load(W/'B10.json')
    control=load(ROOT/'outputs/native-manual-20261103/project/diagnostics/B9/B9.json')
    save_json(W/'B9.json',control) # Explicit disabled-path control for inherited B9 suite.
    b9.W=W;b9.main()
    module=ROOT/'HD2PhysBoneCompat/src/native_scene_roundtrip.lua'
    vm=LuaRuntime(unpack_returned_tuples=True)
    vm.globals().roundtrip=vm.execute(module.read_text(encoding='utf-8'))
    vm.globals().profile=vm.table_from(profile,recursive=True)
    result=plain(vm.execute((ROOT/'HD2PhysBoneCompat/test/scene_roundtrip_harness.lua').read_text(encoding='utf-8')))
    details={}
    for name,case in result['cases'].items():
        text='\n'.join(case.pop('logs').values())
        parsed=analyze(text)
        if name in ('normal','scaled_rotated'):
            assert len(parsed['passedTrials'])==2 and not parsed['incomplete']
            assert not analyze('\n'.join(text.splitlines()[:-1]))['passedTrials'][1:]
        if name in ('throw_after_mutation','readback_mismatch','shared_refresh'):
            assert len(parsed['failedTrials'])==1 and parsed['failedTrials'][0]['result']['rollback']=='verified'
        (W/(name+'-synthetic-roundtrip.log')).write_text(text,encoding='utf-8')
        details[name]=case
    # Full adapter/render path on the real layouts and the corrected external
    # attachment simulation. Actual B9 game locals are exactly identity.
    p=ROOT/'outputs/native-manual-20261103/project'
    models=units(p/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    avatar=next(iter(units(p/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    fixture=dict(avatar=shape(avatar),models={r:shape(models[r])for r in profile['modelLayouts']})
    base=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    prefix=base.split('check(armor.nodes~=A.nodes',1)[0]
    tree=ast.parse((ROOT/'outputs/native-b8-analysis-20261104/analyze_evidence.py').read_text(encoding='utf-8'))
    replay=next(n.value.value for n in ast.walk(tree)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='program'for t in n.targets))
    replay=replay.replace('profile.modelArmLocalLayouts','profile.sceneRoundtrip.layouts').replace('for k=1,4 do','for k=1,8 do').replace('clock=clock+1/60','clock=clock+1')
    api='''
S.Unit.world_pose=function(u,n)return world(u,n)end
S.Unit.scene_graph_parent=function(u,n)if u.owner then return nil end;return u.parents[n]end
S.Unit.local_scale=function(u,n)return {1,1,1}end
S.Matrix4x4.from_elements=function(...)
 local m={...};local identity={1,0,0,0,1,0,0,0,1}
 for i=1,9 do assert(math.abs(m[i]-identity[i])<1e-8,'actual-game-local expected identity')end
 return {p={m[10],m[11],m[12]},q={0,0,0,1}}
end
'''
    replay=replay.replace('local animationA=copy(A.locals)',api+'\nlocal animationA=copy(A.locals)')
    vm=LuaRuntime(unpack_returned_tuples=True)
    vm.globals().adapter=vm.execute((ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8'))
    vm.globals().profile=vm.table_from(profile,recursive=True);vm.globals().fixture=vm.table_from(fixture,recursive=True);vm.globals().hash_name=bone_name_hash
    integration=plain(vm.execute(prefix+replay));log='\n'.join(integration.pop('logs').values())
    parsed=analyze(log)
    assert len(parsed['passedTrials'])==3 and not parsed['failedTrials']and not parsed['rejected']and not parsed['incomplete'],parsed
    assert all(r['maxWorldError']<1e-8 for r in integration['history'].values())
    assert integration['history'][8]['active']==1 and integration['history'][8]['modelLocalWrites']==264
    (W/'full-adapter-synthetic-roundtrip.log').write_text(log,encoding='utf-8')
    result.update(status='PASS',gameTested=False,cases=details,
        scope='Affine external-parent fixtures, fault injection, and B9 disabled-path regression; not in-game setter evidence.',
        fullAdapterIntegration=integration,fullAdapterPassedTrials=3,parserChecks=True,
        sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'),roundtripSha256=digest(module))
    save_json(W/'scene-roundtrip-audit.json',result)
    print('PASS: 14 roundtrip cases, scaled/rotated full matrices, partial writes and shared-refresh rollback, destroyed/replaced instances, Avatar side effects, B9 disabled path.')


if __name__=='__main__':main()
