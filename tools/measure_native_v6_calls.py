"""Count engine API calls in a fixed fake-engine scenario, not game FPS."""
import copy,json,types
from pathlib import Path
scope={'__file__':str(Path(__file__).with_name('audit_native_v6_runtime.py'))}
exec(Path(scope['__file__']).read_text(encoding='utf-8').split('result=lua.execute',1)[0],scope)
audit=types.SimpleNamespace(**scope)
from lupa.lua51 import LuaRuntime
W=audit.W;ROOT=audit.ROOT
prefix=(ROOT/'HD2PhysBoneCompat/test/attachments_harness.lua').read_text(encoding='utf-8').split('local original={}',1)[0]
fixture=dict(names=audit.names,parents=[0 if p is None else p+1 for p in audit.u.parents],localPoses=[dict(p=list(t.position),q=list(t.rotation)) for t in audit.local])
suffix='''
tick(3)
local counts={}
for _,name in ipairs({'world_position','world_rotation','local_pose','set_local_pose'}) do
 local method=S.Unit[name];counts[name]=0
 S.Unit[name]=function(...) counts[name]=counts[name]+1;return method(...) end
end
for i=1,100 do tick(1) end
return counts
'''
reports={}
for version in ('v5','v6'):
    profile=copy.deepcopy(audit.profile) if version=='v6' else json.loads((ROOT/'outputs/native-v5-20261103/project/attachment-profile.json').read_text(encoding='utf-8'))
    profile['expectedModelNodes']=196
    src=ROOT/'HD2PhysBoneCompat/src/native_attachments.lua' if version=='v6' else next((W/'source-before').rglob('native_attachments.lua'))
    vm=LuaRuntime(unpack_returned_tuples=True);vm.globals().adapter=vm.execute(src.read_text(encoding='utf-8-sig'))
    vm.globals().profile=vm.table_from(profile,recursive=True);vm.globals().fixture=vm.table_from(fixture,recursive=True)
    reports[version]=dict(vm.execute(prefix+suffix).items())
report=dict(status='PASS',frames=100,scenario='two avatars; one matched body armor; one unmodified native avatar; scan every frame for both versions',
    gameMeasured=False,counts=reports,note='API call counts only; excludes real animation evaluation, engine cost and GPU; not an FPS benchmark.')
assert reports['v6']['world_position']<reports['v5']['world_position']
(W/'lua-api-call-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
