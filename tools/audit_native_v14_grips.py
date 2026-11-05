"""Test palm contacts, reflected reference segments and runtime rollback."""
import ast
import copy
import json
import math
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'outputs/native-v14-20261104';P=W/'project'
sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(ROOT/'outputs/native-v11-20261104/test-runtime'))
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
from lupa.lua51 import LuaRuntime
from anim_batch_mod.formats import AnimationData,BonesData
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms,WorldTransform
from anim_batch_mod.math3d import quat_rotate,quat_multiply,vec_add,vec_sub
from anim_batch_mod import native_skeleton as native
from prepare_native_v13_arms import calibration
from audit_native_attachment_layouts import run,shape,units
from package_native_v12 import load,save_json

def main():
    profile=load(P/'ab-profiles/B5.json');chains=profile['armChains']
    _,avatar,rest=calibration(P)
    bones=BonesData.parse(native.append_bones((ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes(),native.load_manifest(P/'source-skeleton.json')))
    mapping=[avatar.name_hashes.index(h) for h in bones.hashes]
    source=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
    vm=LuaRuntime(unpack_returned_tuples=True);adapter=vm.execute(source)
    table=lambda x:vm.table_from(x,recursive=True)
    pose=lambda t:dict(p=t.position,q=t.rotation)
    count=0;max_length=0.;max_contact_invariant=0.;max_residual=0.;reachable=0
    def test(worlds,chain,s=None,target_override=None):
        nonlocal count,max_length,max_contact_invariant,max_residual,reachable
        grip=pose(worlds[chain['nativeGrip']]);parent=worlds[chain['parent']]
        s=parent.scale[0] if s is None else s
        parent=WorldTransform(parent.position,parent.rotation,[s,s,s])
        desired=adapter.grip_target(table(grip),table(chain),s)
        target=dict(p=[desired.p[i] for i in range(1,4)],q=worlds[chain['nativeHand']].rotation,
                    referencePosition=worlds[chain['nativeHand']].position)
        if target_override is not None:target['p']=target_override
        result,residual=adapter.solve_arm(table(pose(worlds[chain['root']])),table(pose(worlds[chain['nativeUpper']])),
            table(pose(worlds[chain['nativeForearm']])),table(target),table(pose(parent)),table(chain),vm.table(),1/60,s,desired.q)
        local=[WorldTransform([result[i].p[j] for j in range(1,4)],[result[i].q[j] for j in range(1,5)],[1,1,1]) for i in range(1,4)]
        out=_calculate_world_transforms([parent]+local,[None,0,1,2])
        expected=[s*math.sqrt(sum(v*v for v in chain[k])) for k in ('upperOffset','forearmOffset')]
        length_error=max(abs(math.dist(out[i+1].position,out[i+2].position)-expected[i]) for i in range(2))
        wrist_error=math.dist(out[3].position,target['p'])
        assert abs(wrist_error-residual)<1e-6 and length_error<1e-6,(count,chain['side'],wrist_error,residual,length_error,parent.scale,local)
        contact=vec_add(out[3].position,quat_rotate(out[3].rotation,[v*s for v in chain['sourceGripOffset']]))
        if target_override is None:
            error=abs(math.dist(contact,grip['p'])-residual)
            assert error<1e-6
            max_contact_invariant=max(max_contact_invariant,error)
        max_length=max(max_length,length_error);max_residual=max(max_residual,residual)
        if residual<1e-5:reachable+=1
        count+=1
    for path in sorted((W/'arm-candidates').glob('*.toc')):
        a=AnimationData.parse(path.read_bytes())
        if a.is_additive:continue
        tracks=_build_tracks(a)
        for frame in range(9):
            local=list(avatar.transforms)
            for ch,index in enumerate(mapping):local[index]=WorldTransform(*(t[ch].evaluate(a.animation_length*1000*frame/8) for t in tracks))
            worlds=_calculate_world_transforms(local,avatar.parents)
            for chain in chains:test(worlds,chain)
    worlds=_calculate_world_transforms(rest,avatar.parents)
    for chain in chains:
        root=worlds[chain['root']].position
        for s in (.8,1.,1.08):
            for i in range(81):
                ray=.7*i/80;angle=i*math.pi/20
                test(worlds,chain,s,vec_add(root,[ray*math.cos(angle),ray*math.sin(angle),0]))
    # Reuse the engine-shaped lifecycle contract (not its older hinge assertions).
    models=units(P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    fixture=dict(avatar=shape(avatar),models={k:shape(models[k]) for k in profile['modelLayouts']})
    harness=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    prefix=harness.split('check(armor.nodes~=A.nodes',1)[0]
    tree=ast.parse((ROOT/'tools/audit_native_v13_arms.py').read_text(encoding='utf-8'))
    checks=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str) and n.value.startswith('\nlocal saved={}'))
    checks=checks.replace("-- New animation input", "check(hasLog('palm_contact_error'),'palm contact log missing')\n-- New animation input")
    checks=checks.replace('-- New animation input', '''
check(hasLog('arm_consumer_readback phase=after_model_refresh'),'model consumer log missing')
local item=runtime.models[armor];local owner=runtime.avatars[A]
local writesBefore=A.writes+armor.writes
local report=runtime:arm_consumer_readback(owner,item,'test_equal')
check(report.nodes==6 and report.missing==0 and report.positionError<1e-6,'model hash mapping failed')
armor.poseNoise=.125
report=runtime:arm_consumer_readback(owner,item,'test_mismatch')
check(math.abs(report.positionError-.125)<1e-6,'model mismatch hidden by avatar readback')
armor.poseNoise=nil
check(A.writes+armor.writes==writesBefore,'read-only model diagnostic changed a pose')
-- New animation input''')
    lifecycle=run(profile,fixture,source,prefix+checks)
    report=dict(status='PASS',gameTested=False,samples=count,reachableSamples=reachable,
        maxBoneLengthErrorMetres=max_length,maxPalmResidualInvariantError=max_contact_invariant,
        maxUnreachableResidualMetres=max_residual,lifecycle=lifecycle,
        scope='same-avatar native grip target; Source-only writes; exact rotations/lengths/contact residual and rollback')
    save_json(W/'arm-sync-audit.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()
