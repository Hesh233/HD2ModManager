"""Run the pure reader against actual native/hybrid layouts and hostile API fixtures."""
import os
import re
import sys
from package_native_v12 import ROOT, load, save_json, digest
sys.path.insert(0,str(ROOT / 'outputs/native-v11-20261104/test-runtime'))
sys.path.insert(0,str(ROOT / 'outputs/native-fix-20261103/test-runtime'))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.native_skeleton import bone_name_hash

W=ROOT / 'outputs/native-v29-b21-20261105'
SRC=ROOT / 'HD2PhysBoneCompat/src'
TEST=ROOT / 'HD2PhysBoneCompat/test'


def main():
    config=load(W / 'capture-profile.json')
    assets=load(W / 'native-capture-layouts.json')
    source=(SRC / 'native_reference_capture.lua').read_text(encoding='utf-8')
    entry=(W / 'native-grip-capture.lua').read_text(encoding='utf-8')
    assert not re.search(r'\b(?:U|Unit|World|S\.World)\.(?:set_\w+|update_unit|link\w*|unlink\w*)\s*\(',source)

    def fixture(row,kind,visible=True):
        return dict(resource=row['resource'],kind=kind,count=row['nodeCount'],visible=visible,
            hashes=[n['hash'] for n in row['nodes']],parents=[0 if n['parentIndex'] is None else n['parentIndex']+1 for n in row['nodes']],
            locals=[n['localMatrix'] for n in row['nodes']],worlds=[n['worldBindMatrix'] for n in row['nodes']])

    fixtures=[fixture(assets['nativeAvatar'],'avatar')]
    for resource,spec in config['resources'].items():
        if spec['kind']=='avatar':
            continue
        source_row=assets['test01Models'][resource] if spec['kind']=='test01_model' else assets['resources'][resource]
        fixtures.append(fixture(source_row,spec['kind'],spec['kind']!='test01_model'))
    strict=(TEST / 'strict_id32_fixture.lua').read_text(encoding='utf-8')
    program=(TEST / 'native_reference_capture_harness.lua').read_text(encoding='utf-8').replace('-- STRICT_ID_FIXTURE',strict)
    vm=LuaRuntime(unpack_returned_tuples=True)
    vm.globals().module=vm.execute(source)
    vm.globals().profile=vm.table_from(config,recursive=True)
    vm.globals().fixture=vm.table_from(fixtures,recursive=True)
    vm.globals().fixtureHybrid=vm.table_from(fixture(assets['test01Avatar'],'avatar'),recursive=True)
    vm.globals().hash_name=bone_name_hash
    assert vm.eval('function(s)return loadstring(s)~=nil end')(entry)
    result=vm.execute(program)
    sample_logs=list(result['sampleLogs'].values())
    all_logs=list(result['allLogs'].values())
    (W / 'fixture-native-capture.log').write_text('\n'.join('2000-01-01 00:00:00 [native_capture] '+s for s in sample_logs)+'\n',encoding='utf-8')
    (W / 'collector-regression.log').write_text('\n'.join(all_logs),encoding='utf-8')
    summary={k:v for k,v in result.items() if k not in ('sampleLogs','allLogs')}
    save_json(W / 'capture-runtime-audit.json',dict(status='PASS',**summary,
        sourceSha256={name:digest(SRC / name) for name in ('native_reference_capture.lua','native_reference_capture_entry.lua')},
        testSha256=digest(TEST / 'native_reference_capture_harness.lua'),sourceEmbedsCurrent=source in entry,
        gamePoseCaptured=False,scope='Actual file layouts, simulated engine animation and independent cached graphs; no game process used.'))
    print('PASS: native/hybrid layouts, paired callbacks, unchanged graphs, zero mutators, recycled matrices, IDs, lifecycle and limits.')


if __name__=='__main__':
    main()
