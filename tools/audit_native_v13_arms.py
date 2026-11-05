"""Check arm IK math against real clip poses and serialized model lifecycle."""
import copy
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'outputs/native-v13-20261104'
P = W / 'project'
os.environ['HD2_LUA_TEST_RUNTIME'] = str(ROOT / 'outputs/native-v11-20261104/test-runtime')
sys.path.insert(0, str(ROOT.parents[1]))
from audit_native_attachment_layouts import run, shape, units
from prepare_native_v13_arms import calibration
from lupa.lua51 import LuaRuntime
from anim_batch_mod.formats import AnimationData, BonesData
from anim_batch_mod.processor import WorldTransform, _calculate_world_transforms, _build_tracks, _cross
from anim_batch_mod.math3d import quat_multiply, quat_rotate, quat_inverse_rotate, vec_add, vec_sub
from anim_batch_mod import native_skeleton as native


def pose(t):
    return dict(p=t.position, q=t.rotation)


def main():
    profile = json.loads((P / 'attachment-profile.json').read_text(encoding='utf-8'))
    chains, avatar, reference = calibration(P)
    assert profile['armChains'] == chains
    profile['armSync'] = True  # B4 is the experimental native-hand sync variant.
    source = (ROOT / 'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
    vm = LuaRuntime(unpack_returned_tuples=True)
    adapter = vm.execute(source)
    solve = adapter.solve_arm
    table = lambda value: vm.table_from(value, recursive=True)
    statistics = dict(samples=0, maxReadbackErrorMetres=0., maxBoneLengthErrorMetres=0.,
                      maxHingeErrorDegrees=0., maxPalmErrorDegrees=0., maxUnreachableResidualMetres=0., unreachable=0)
    records = []
    def test(worlds, chain, state, dt=1/30, target=None):
        hand = pose(worlds[chain['nativeHand']])
        if target is not None:
            hand['p'] = target
        result, residual = solve(table(pose(worlds[chain['root']])), table(pose(worlds[chain['nativeUpper']])),
                                 table(pose(worlds[chain['nativeForearm']])), table(hand),
                                 table(pose(worlds[chain['parent']])), table(chain), state, dt, worlds[chain['parent']].scale[0])
        locals_ = [WorldTransform([result[i]['p'][j] for j in range(1,4)],
                                 [result[i]['q'][j] for j in range(1,5)], [1.,1.,1.]) for i in range(1,4)]
        root_input = worlds[chain['root']]
        parent = worlds[chain['parent']]
        output = _calculate_world_transforms([parent]+locals_, [None,0,1,2])
        first, second = vec_sub(output[2].position,output[1].position), vec_sub(output[3].position,output[2].position)
        expected_hand_q = quat_multiply(hand['q'],chain['handCalibration'])
        palm = math.degrees(2*math.acos(min(1.,abs(sum(a*b for a,b in zip(expected_hand_q,output[3].rotation))))))
        hinge = quat_inverse_rotate(output[1].rotation, _cross(first,second))
        size = math.sqrt(sum(v*v for v in hinge))
        hinge_error = math.degrees(math.acos(max(-1.,min(1.,sum(a*b for a,b in zip(hinge,chain['hingeAxis']))/size)))) if size>1e-9 else 0.
        # FK with the ORIGINAL offsets must reproduce the solver's joint positions.
        fk_mid = vec_add(output[1].position, quat_rotate(output[1].rotation,[v*parent.scale[0] for v in chain['upperOffset']]))
        fk_hand = vec_add(fk_mid, quat_rotate(output[2].rotation,[v*parent.scale[0] for v in chain['forearmOffset']]))
        error = max(math.dist(fk_mid,output[2].position),math.dist(fk_hand,output[3].position),
                    abs(math.dist(output[3].position,hand['p'])-residual))
        length_error = max(abs(math.sqrt(sum(v*v for v in a))-parent.scale[0]*math.sqrt(sum(v*v for v in b)))
                           for a,b in zip((first,second),(chain['upperOffset'],chain['forearmOffset'])))
        assert all(math.isfinite(v) for t in locals_ for v in t.position+t.rotation)
        assert math.dist(output[1].position,root_input.position) < 1e-6, (math.dist(output[1].position,root_input.position),parent,root_input)
        assert error < 1e-6 and length_error < 1e-6, (error,length_error)
        assert hinge_error < .05 and palm < .05, (hinge_error,palm)
        statistics['samples'] += 1
        for key,value in [('maxReadbackErrorMetres',error),('maxBoneLengthErrorMetres',length_error),
                          ('maxHingeErrorDegrees',hinge_error),('maxPalmErrorDegrees',palm),('maxUnreachableResidualMetres',residual)]:
            statistics[key] = max(statistics[key],value)
        statistics['unreachable'] += residual > .005
        return residual

    manifest = native.load_manifest(P/'source-skeleton.json')
    bones = BonesData.parse(native.append_bones((ROOT/'outputs/native-fix-20261103/bones.toc').read_bytes(),manifest))
    mapping = [avatar.name_hashes.index(h) for h in bones.hashes]
    for path in sorted((W/'candidate-clips').glob('*.toc')):
        clip = AnimationData.parse(path.read_bytes())
        if clip.is_additive:
            continue
        tracks = _build_tracks(clip)
        states = [vm.table(),vm.table()];residuals=[]
        for frame in range(math.floor(clip.animation_length*30)+1):
            local = list(avatar.transforms)
            for channel,index in enumerate(mapping):
                local[index] = WorldTransform(*(t[channel].evaluate(frame*1000/30) for t in tracks))
            worlds = _calculate_world_transforms(local,avatar.parents)
            for chain,state in zip(chains,states):
                residuals.append(test(worlds,chain,state))
        records.append(dict(clip=path.stem,samples=len(residuals),maxResidualMetres=max(residuals),
                            beyond5mm=sum(v>.005 for v in residuals)))
    actual_stats = copy.deepcopy(statistics)
    worlds = _calculate_world_transforms(reference,avatar.parents)
    for chain in chains:
        root = worlds[chain['root']].position
        reach = sum(math.sqrt(sum(v*v for v in chain[k])) for k in ('upperOffset','forearmOffset'))
        state = vm.table()
        # Folded, near straight, unreachable, turnaround, zero delta-time.
        for i in range(241):
            radius = reach * (.02 + 1.2 * (i%80)/79)
            angle = i*math.pi/60
            target = vec_add(root,[radius*math.cos(angle),radius*math.sin(angle),0.])
            test(worlds,chain,state,0 if i%17==0 else 1/60,target)
        test(worlds,chain,state,1/60,list(root))

    models = units(ROOT/'outputs/native-v12-20261104/project/models-o3/test01-O3/9ba626afa44a3aa3.patch_0')
    fixture = dict(avatar=shape(avatar),models={k:shape(models[k]) for k in profile['modelLayouts']})
    harness = (ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    prefix = harness.split("check(armor.nodes~=A.nodes",1)[0]
    checks = r'''
local saved={};local native={}
for _,chain in ipairs(profile.armChains)do
 for _,n in ipairs({chain.root,chain.mid,chain.hand})do saved[n+1]=copy(A.locals[n+1])end
 for _,n in ipairs({chain.nativeUpper,chain.nativeForearm,chain.nativeHand})do native[n+1]=world(A,n+1)end
end
for _,r in ipairs(profile.vpk)do if r.policy=='original-world' or r.standardName=='attach_weapon' or r.standardName=='attach_hand_r' or r.standardName=='attach_hand_l' then native[r.index+1]=world(A,r.index+1)end end
tick(3)
check(runtime.stats.active==1 and runtime.avatars[A].armsActive,'arms not selected')
check(B.writes==0,'unowned avatar modified')
for n,p in pairs(native)do check(adapter.close(world(A,n),p),'native IK/controller/sling changed');check(not A.written[n],'native IK node written')end
for _,chain in ipairs(profile.armChains)do
 for _,n in ipairs({chain.root,chain.mid,chain.hand})do check(A.written[n+1],'Source arm not written')end
end
check(hasLog('native_hand_sync') and hasLog('readback_error='),'hand readback log missing')
-- New animation input is saved on the next frame; restore must not freeze the activation pose.
for n,p in pairs(saved)do A.locals[n]=copy(p)end
local n=profile.armChains[1].root+1
A.locals[n].q={0,0,math.sin(.1),math.cos(.1)};saved[n]=copy(A.locals[n]);tick(1)
armor.visible=false;tick(1)
for n,p in pairs(saved)do check(adapter.close(A.locals[n],p),'latest animation pose not restored')end
check(not runtime.avatars[A].armsActive,'arm state not released')
armor.visible=true;tick(3)
runtime:release()
for n,p in pairs(saved)do check(adapter.close(A.locals[n],p),'release did not restore arms')end
-- Validate both arms before writing either one, including scaled ancestors.
local a=runtime.avatars[A];local scaleNode=profile.armChains[2].parent+1
A.locals[scaleNode].scaled=true
local writes=A.writes
local ok,err=pcall(runtime.sync_arms,runtime,a)
check(not ok and tostring(err):find('scaled Source arm unsupported',1,true),'ancestor scale accepted')
check(A.writes==writes,'partial arm mutation on scale rejection')
A.locals[scaleNode].scaled=nil
runtime:release()
-- A real engine readback failure must leave a releasable active transaction.
local originalUpdate=S.World.update_unit
local corrupt=true
S.World.update_unit=function(w,u)
 originalUpdate(w,u)
 if corrupt and u==A then u.locals[profile.armChains[1].hand+1].p[1]=10 end
end
ok,err=pcall(runtime.sync_arms,runtime,a)
check(not ok and tostring(err):find('write/readback mismatch',1,true),'bad readback accepted')
check(a.active,'partial mutation is not releasable')
corrupt=false;runtime:release()
check(not a.active and not a.armsActive,'failure cleanup failed')
return {checks=checks,handReadback=true,latestInputRestored=true,ancestorScaleRejected=true,partialWriteRestored=true,nativePosePreserved=true}
'''
    lifecycle = run(profile,fixture,source,prefix+checks)
    report = dict(status='PASS',gameTested=False,actualClips=actual_stats,allSamples=statistics,clips=records,lifecycle=lifecycle)
    (W/'arm-sync-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
