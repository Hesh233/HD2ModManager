"""Exercise attachment Lua using actual packaged model and avatar layouts."""
import argparse, copy, json, os, struct, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,os.environ.get('HD2_LUA_TEST_RUNTIME',str(ROOT/'outputs/native-fix-20261103/test-runtime')))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import bone_name_hash
from native_attachment_layouts import build_model_layouts


def units(path):
    result={}
    with path.open('rb') as f:
        h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+32*nt)
        rows=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
        for row in rows:
            if row[1]!=UNIT_TYPE_ID:continue
            f.seek(row[2]);result[f'{row[0]:016x}']=UnitData.parse(f.read(row[7]))
    return result


def shape(unit):
    return dict(hashes=unit.name_hashes,parents=[0 if p is None else p+1 for p in unit.parents],
                localPoses=[dict(p=list(t.position),q=list(t.rotation)) for t in unit.transforms])


def plain(value):
    return {k:plain(v) for k,v in value.items()} if hasattr(value,'items') else value


def run(profile,fixture,source,harness):
    vm=LuaRuntime(unpack_returned_tuples=True)
    vm.globals().adapter=vm.execute(source)
    vm.globals().profile=vm.table_from(profile,recursive=True)
    vm.globals().fixture=vm.table_from(fixture,recursive=True)
    vm.globals().hash_name=bone_name_hash
    return plain(vm.execute(harness))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True,type=Path)
    parser.add_argument('--model-patch',required=True,action='append',type=Path)
    avatar_input=parser.add_mutually_exclusive_group(required=True)
    avatar_input.add_argument('--avatar-patch',type=Path)
    avatar_input.add_argument('--avatar-unit',type=Path,help='A serialized standalone Unit payload, for checks before full animation build')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--consumer-unit',action='append',default=[],help='Actual serialized consumer Unit, resource_hex=path')
    parser.add_argument('--legacy-source',type=Path,help='Verify that an older adapter fails the weapon-component regression')
    args=parser.parse_args()
    profile=json.loads(args.profile.read_text(encoding='utf-8-sig'))
    expected=build_model_layouts(args.model_patch,profile)
    assert profile['modelLayouts']==expected,'Profile differs from final serialized model layout'
    model={}
    for path in args.model_patch:model.update(units(path))
    avatar=UnitData.parse(args.avatar_unit.read_bytes()) if args.avatar_unit else next(iter(units(args.avatar_patch).values()))
    assert len(avatar.transforms)==profile['expectedAvatarNodes']
    fixture=dict(avatar=shape(avatar),models={resource:shape(model[resource]) for resource in expected})
    if args.consumer_unit:
        fixture['consumers']={}
        for value in args.consumer_unit:
            resource,path=value.split('=',1)
            assert len(resource)==16 and int(resource,16)>0
            fixture['consumers'][resource]=shape(UnitData.parse(Path(path).read_bytes()))
    source=(ROOT/'HD2PhysBoneCompat/src/native_attachments.lua').read_text(encoding='utf-8')
    harness=(ROOT/'HD2PhysBoneCompat/test/attachments_layout_harness.lua').read_text(encoding='utf-8')
    result=run(profile,fixture,source,harness)
    if args.legacy_source:
        assert len(fixture.get('consumers',{}))>=6,'Weapon components required for legacy regression'
        try:run(profile,fixture,args.legacy_source.read_text(encoding='utf-8-sig'),harness)
        except Exception as error:
            assert 'independent equipment graphs not refreshed' in str(error),str(error)
        else:raise AssertionError('Older adapter unexpectedly refreshed weapon components')
        result['legacyComponentOmissionReproduced']=True
    wrong=copy.deepcopy(profile)
    wrong['modelLayouts'][wrong['targets']['body'][0]]['nodeCount']-=7
    prefix=harness.split("check(armor.nodes~=A.nodes",1)[0]
    regression=run(wrong,fixture,source,prefix+'tick(3);return {active=runtime.stats.active,matching=#runtime.armor}')
    assert regression=={'active':0,'matching':0},regression
    # A new target missing a signature bone must fail generation, rather than
    # silently falling back to a guessed node count or a partial signature.
    missing=copy.deepcopy(profile);missing['signature'][0]['name']='absent_signature_bone'
    try:build_model_layouts(args.model_patch,missing)
    except ValueError:missing_rejected=True
    else:raise AssertionError('Missing model signature was accepted')
    result.update(status='PASS',gameTested=False,missingSignatureRejected=missing_rejected,
                  wrongCountRegression=regression,layouts=len(expected),profileMatchesModelBytes=True,
                  independentConsumerLayouts=len(fixture.get('consumers',{})))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
