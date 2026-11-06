"""Exercise the actual model profile and composed Lua entry in a Lua 5.1 stub VM."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from lupa.lua51 import LuaRuntime
from anim_batch_mod.archive import TocArchive

STUB = '''
captured={};opened=0;closed=0;writes=0
io={open=function()
 opened=opened+1
 return {write=function(self,...)local a={...};local s='';for _,v in ipairs(a)do s=s..tostring(v)end;captured[#captured+1]=s end,
 flush=function()end,close=function()closed=closed+1 end}
end}
stingray={Unit={},Matrix4x4={to_elements=function()end,from_elements=function()end},
 World={units=function()return {}end,update_unit=function()end},
 Application={worlds=function()return {}end,string_to_id32=function()end,time_since_launch=function()return 1 end},
 IdString64={to_hex=function()end}}
for _,n in ipairs({'alive','resource_name','num_scene_graph_items','has_node','node','scene_graph_parent','local_pose','world_pose'})do stingray.Unit[n]=function()end end
stingray.Unit.set_local_pose=function()writes=writes+1 end
'''

def exercise(source):
    vm=LuaRuntime(unpack_returned_tuples=True);vm.execute(STUB)
    loader=vm.table_from({'loader':'Chef Shared Loader','log_directory':'stub-only-no-disk'})
    try:
        api=vm.execute(source,loader)
    except Exception as err:
        return {'started':False,'error':str(err),'opened':vm.globals().opened,'closed':vm.globals().closed,'writes':vm.globals().writes}
    api.update();api.render();api.shutdown()
    return {'started':True,'version':api.version,'opened':vm.globals().opened,'closed':vm.globals().closed,
            'writes':vm.globals().writes,'logs':list(vm.globals().captured.values())}

def main():
    out=ROOT/'outputs/test04-live-crash-audit-20261106/evidence'
    base=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/test-library/[骨骼挂点修正]test04'
    patch=TocArchive.parse_parts((base/'9ba626afa44a3aa3.patch_0').read_bytes(),load_external_data=False)
    entries=[bytes(e.toc_data) for e in patch.entries.values() if b'attachment_runtime_version_mismatch' in e.toc_data]
    assert len(entries)==1
    payload=entries[0];begin=payload.index(b'-- HD2-Addon:');old=payload[begin:].split(b'\0',1)[0].decode('utf-8')
    (out/'test04-entry-deployed.lua').write_text(old,encoding='utf-8')
    before=exercise(old);after=exercise((out/'test04-entry-candidate.lua').read_text(encoding='utf-8'))
    assert not before['started'] and 'attachment_runtime_version_mismatch' in before['error']
    assert before['closed']==1 and before['writes']==0
    assert after['started'] and after['version']=='1.0.9' and after['closed']==1 and after['writes']==0
    assert any('"event":"loaded"' in l and '"rigExpectedNodes":261' in l for l in after['logs'])
    assert any('"event":"complete"' in l for l in after['logs'])
    report={'status':'PASS','before':before,'after':after,'realDeployedProfile':True,'composedByRebuiltCore':True,
            'gameTested':False,'stubWorldsEmpty':True,'gameOrLibraryModified':False}
    (out/'lua-entry-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','beforeStarted':False,'afterStarted':True,'version':after['version'],
                     'gameTested':False,'loadedAndShutdownObserved':True}))

if __name__=='__main__':main()
