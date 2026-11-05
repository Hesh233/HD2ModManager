"""Regression for omitted split models using independent cached scene graphs."""
import copy
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/native-v16-20261104'
P=ROOT/'outputs/native-manual-20261103/project'
os.environ['HD2_LUA_TEST_RUNTIME']=str(ROOT/'outputs/native-v11-20261104/test-runtime')
sys.path.insert(0,os.environ['HD2_LUA_TEST_RUNTIME'])
from lupa.lua51 import LuaRuntime
from audit_native_attachment_layouts import units,shape,plain
from native_attachment_layouts import build_model_layouts
from package_native_v12 import load,save_json,digest
from anim_batch_mod.native_skeleton import bone_name_hash


def main():
    profile=load(W/'B7.json')
    patches=[P/'models-o3/test01-O3/9ba626afa44a3aa3.patch_0']
    assert build_model_layouts(patches,profile)==profile['modelLayouts']
    models=units(patches[0])
    avatar=next(iter(units(P/'animations/runtime/9ba626afa44a3aa3.patch_2').values()))
    fixture=dict(avatar=shape(avatar),models={k:shape(models[k]) for k in profile['modelLayouts']})
    base=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    prefix=base.split('check(armor.nodes~=A.nodes',1)[0]
    probe=(ROOT/'HD2PhysBoneCompat/test/split_model_refresh_harness.lua').read_text(encoding='utf-8')
    coverage=load(W/'consumer-coverage.json')['rows']
    weighted={r['resource']:next(n['name'] for n in r['armWeights'] if n['name'].endswith('_hand'))
              for r in coverage if r['part'].startswith(('LeftArm/','RightArm/'))}
    def run(source,program,p=profile):
        vm=LuaRuntime(unpack_returned_tuples=True)
        vm.globals().adapter=vm.execute(source)
        vm.globals().profile=vm.table_from(p,recursive=True)
        vm.globals().fixture=vm.table_from(fixture,recursive=True)
        vm.globals().weighted_hand_resources=vm.table_from(weighted)
        vm.globals().hash_name=bone_name_hash
        return plain(vm.execute(program))
    current=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    original=(P/'source-code/HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8-sig')
    result=run(current,prefix+probe)
    stale_probe=prefix+probe.split('tick(4)',1)[0]+'''
tick(4)
local gaps={}
for _,part in ipairs(parts)do
 local name=weighted_hand_resources[part.resource]
 if name then
  local h=hash_name(name)
  local expected=world(A,A.names[h]);local actual=world(part,part.names[h]);local d=0
  for i=1,3 do d=d+(expected.p[i]-actual.p[i])^2 end
  gaps[part.resource]=math.sqrt(d)
 end
end
return gaps
'''
    old_gaps=run(original,stale_probe)
    assert len(old_gaps)==2 and max(old_gaps.values())>.01,'fixture failed to expose stale drawn hand nodes'
    result['oldCachedHandGapsMetres']=old_gaps
    try:run(original,prefix+probe)
    except Exception as e:
        assert 'split part not refreshed:' in str(e),str(e)
        result['oldMissingSplitRefreshReproduced']=True
    else:raise AssertionError('Original adapter unexpectedly refreshed split models')
    # Existing profiles without the new consumer list retain their prior
    # discovery and ownership behavior. Run the established layout lifecycle.
    control=load(ROOT/'outputs/native-v12-20261104/project/attachment-profile.json')
    control['protectControllerParents']=False
    baseline=run(current,base,control)
    assert baseline==run(original,base,control),'legacy profile lifecycle changed'
    current_control=load(P/'ab-profiles/A.json')
    summary=prefix+"tick(3);return {active=runtime.stats.active,writes=A.writes,gun=A.written[33]==true,sling=A.written[28]==true}"
    assert run(current,summary,current_control)==run(original,summary,current_control),'A14 control changed'
    result.update(status='PASS',gameTested=False,legacyProfileLifecycle=baseline,
                  layoutsMatchPackagedUnits=True,sourceSha256=digest(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua'))
    save_json(W/'split-model-audit.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
