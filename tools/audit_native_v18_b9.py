"""Actual-layout B7 equivalence, external-link semantics and read-only telemetry."""
import ast
import copy
import json
import os
from package_native_v12 import ROOT,load,save_json,digest
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from audit_native_attachment_layouts import units,shape,plain
from anim_batch_mod.native_skeleton import bone_name_hash
from lupa.lua51 import LuaRuntime
from analyze_native_b9_log import analyze

W=ROOT/'outputs/native-v18-20261104';P=ROOT/'outputs/native-manual-20261103/project'


def main():
    profile=load(W/'B9.json');control=load(P/'diagnostics/B7/B7.json')
    models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    fixture=dict(avatar=shape(avatar),models={r:shape(models[r])for r in profile['modelLayouts']})
    base=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    prefix=base.split('check(armor.nodes~=A.nodes',1)[0]
    current=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    before=(P/'diagnostics/B7/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    observer=(ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua').read_text(encoding='utf-8')
    forbidden=('set_local_pose','set_local_position','set_local_rotation','set_local_scale','link_unit','update_unit','unlink_unit')
    assert not any(word in observer for word in forbidden)
    assert 'sync_model_arm_locals' not in current and 'armLocalOwner' not in current
    coverage=load(ROOT/'outputs/native-v16-20261104/consumer-coverage.json')['rows']
    weighted={r['resource']:next(n['name']for n in r['armWeights']if n['name'].endswith('_hand'))
        for r in coverage if r['part'].startswith(('LeftArm/','RightArm/'))}
    def run(source,program,p=profile,standalone=False):
        vm=LuaRuntime(unpack_returned_tuples=True)
        vm.globals().adapter=vm.execute(source)
        vm.globals().observer=vm.execute(observer)
        vm.globals().profile=vm.table_from(p,recursive=True)
        vm.globals().fixture=vm.table_from(fixture,recursive=True)
        vm.globals().hash_name=bone_name_hash
        vm.globals().weighted_hand_resources=vm.table_from(weighted)
        return plain(vm.execute(program))
    split=(ROOT/'HD2PhysBoneCompat/test/split_model_refresh_harness.lua').read_text(encoding='utf-8')
    disabled=run(current,prefix+split,control)
    assert disabled==run(before,prefix+split,control)
    legacy=load(ROOT/'outputs/native-v12-20261104/project/attachment-profile.json');legacy['protectControllerParents']=False
    lifecycle=run(current,base,legacy)
    assert lifecycle==run(before,base,legacy)
    standalone=run(current,(ROOT/'HD2PhysBoneCompat/test/scene_observer_harness.lua').read_text(encoding='utf-8'))
    external_log=standalone.pop('externalLog')
    synthetic=analyze(external_log)
    encoded=[json.loads(line.split('[scene_probe] ',1)[1])for line in external_log.splitlines()]
    expected_hashes={r['name']:r['hash']for r in profile['sceneObservation']['layouts']['d154442f2e33fdee']}
    assert all(e['hash']==expected_hashes[e['name']]for e in encoded if e['event']=='node')
    assert synthetic['summary']['sameFrameNodePairs']==8
    for r in synthetic['observations']:
        assert r['parentVsAvatarSame']['positionMeters']<1e-10
        assert r['parentVsAvatarSame']['linearMaxAbs']<1e-10
        assert max(abs(a-b)for a,b in zip(r['localScale']['axisLengths'],[1.2,.8,1]))<1e-10
        assert max(abs(a-b)for a,b in zip(r['effectiveParentScale']['axisLengths'],[2,3,4]))<1e-10
    variants=analyze(standalone.pop('variantsLog'))
    assert {str(r['runtimeParent'])for r in variants['observations']}=={'0','-1','nil','1'}
    assert any('parentVsModelRuntimeParent' in r for r in variants['observations'])
    # Reuse the corrected external-link replay from the prior analysis, never
    # the old B8 stub that ignored the model's local attachment offset.
    tree=ast.parse((ROOT/'outputs/native-b8-analysis-20261104/analyze_evidence.py').read_text(encoding='utf-8'))
    replay=next(n.value.value for n in ast.walk(tree)if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='program'for t in n.targets))
    replay=replay.replace('profile.modelArmLocalLayouts','profile.sceneObservation.layouts').replace('for k=1,4 do','for k=1,8 do')
    replay=replay.replace('clock=clock+1/60','clock=clock+1')
    APIs='''
S.Unit.world_pose=function(u,n)return world(u,n)end
S.Unit.scene_graph_parent=function(u,n)if u.owner then return 0 end;return u.parents[n]end
S.Unit.local_scale=function(u,n)return {1,1,1}end
'''
    replay=replay.replace('local animationA=copy(A.locals)',APIs+'\nlocal animationA=copy(A.locals)')
    new=run(current,prefix+replay);old=run(before,prefix+replay)
    assert new['history']==old['history']
    assert all(r['modelLocalWrites']==0 and r['maxWorldError']<1e-8 for r in new['history'].values())
    log='\n'.join(new.pop('logs').values());old.pop('logs')
    telemetry=analyze(log)
    assert telemetry['summary']['sameFrameNodePairs']>=11*8
    assert all(r['parentVsAvatarSame']['positionMeters']<2e-7 for r in telemetry['observations'])
    assert all(r['parentVsAvatarSame']['linearMaxAbs']<2e-7 for r in telemetry['observations'])
    for r in telemetry['observations']:
        if 'sameFrameLocalChange' in r:assert r['sameFrameLocalChange']['linearMaxAbs']==0 and r['sameFrameLocalChange']['positionMeters']==0
    (W/'synthetic-external-link.log').write_text(log,encoding='utf-8')
    save_json(W/'synthetic-scene-analysis.json',telemetry)
    # Truncated/corrupt input must not silently become completed evidence.
    assert analyze(log.split('[scene_probe] ')[0])['summary']['sameFrameNodePairs']==0
    truncated='\n'.join(external_log.splitlines()[:-1])
    assert analyze(truncated)['summary']['sameFrameNodePairs']==0
    first=standalone
    save_json(W/'scene-observer-audit.json',dict(status='PASS',gameTested=False,readOnlyEngineApi=True,
        standalone=first,scaleParentReconstructionVerified=True,rawParentVariantsVerified=True,
        disabledB7Regression=disabled,legacyLifecycle=lifecycle,externalLinkB7Equivalence=new,
        completeSyntheticNodePairs=telemetry['summary']['sameFrameNodePairs'],
        sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'),
        observerSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_scene_observer.lua')))
    print('PASS: B7 behavior unchanged; zero model writes; actual external-link offsets, affine scale, sentinels, failures and bounded logging covered.')


if __name__=='__main__':main()
