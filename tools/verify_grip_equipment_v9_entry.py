"""Validate V9 composed entries against the existing Chef parser/sandbox, with stub IO/worlds."""
from pathlib import Path
import sys,json,zipfile,inspect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
sys.path.insert(0,str(ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'))
import lz4
sys.modules['utils.lz4_311']=lz4
from verify_test04_lua_entry import exercise
import audit_native_v31_b23_chef as chef
from build_detailed_grip_test import VERSION,DEFAULT_OUTPUT
OUT=DEFAULT_OUTPUT

def main():
 rows=json.loads((OUT/'build-report.json').read_text(encoding='utf-8'));reports=[]
 # Reuse the original deterministic Chef runner. Only its legacy compact filename
 # assertion differs: V9 intentionally writes a separate, labelled test session.
 runner=inspect.getsource(chef.main)
 old="local path=api.log_directory..'/hd2_grip_b23_compact.log'"
 new="local path=opens[1].path;assert(path:find('/hd2_grip_TEST_PERF_',1,true) and path:find('_EQUIPMENT_PERF_V9_',1,true) and path:find('.part01.log',1,true),'V9 test log path missing')"
 assert old in runner;runner=runner.replace(old,new,1)
 for row in rows:
  name=row['model'];folder=OUT/name;source=(folder/'hd2attachmentfix-B23.lua').read_text(encoding='utf-8')
  entry=exercise(source)
  assert entry['started'] and entry['version']==VERSION and entry['closed']==1 and entry['writes']==0,entry
  assert any('[TEST_ONLY_PERF]' in line and '"event":"loaded"' in line for line in entry['logs'])
  with zipfile.ZipFile(row['package']) as z:
   for key in ('9ba626afa44a3aa3.patch_0','9ba626afa44a3aa3.patch_1'):(folder/('chef-readback-'+key)).write_bytes(z.read(key))
  mapping={
   'hd2attachmentfix-B23.lua':folder/'hd2attachmentfix-B23.lua',
   'runtime/9ba626afa44a3aa3.patch_4':folder/'chef-readback-9ba626afa44a3aa3.patch_0',
   'native-parenting/9ba626afa44a3aa3.patch_5':folder/'chef-readback-9ba626afa44a3aa3.patch_1',
   'physics-companion/9ba626afa44a3aa3.patch_3':ROOT/'outputs/native-v34-b23-integrated-20261105/physics-companion/9ba626afa44a3aa3.patch_3',
   'chef-audit.json':folder/'chef-entry-validation.json',
   'chef-fixture.log':folder/'chef-entry-validation.log',
  }
  class Alias:
   def __init__(self,key=''):self.key=key
   def __truediv__(self,key):
    path=(self.key+'/'+str(key)).lstrip('/')
    return mapping.get(path,Alias(path))
  env=dict(chef.__dict__);env['W']=Alias();exec(compile(runner,'<reused-chef-v9-test-entry>','exec'),env);env['main'](VERSION)
  report=json.loads((folder/'chef-entry-validation.json').read_text(encoding='utf-8'))
  report['model']=name;report['testOnly']=True;report['smoke']=entry;reports.append(report)
 (OUT/'entry-chef-validation.json').write_text(json.dumps(dict(status='PASS_PENDING_GAME_TEST',entries=reports,gameTested=False,gameDeployed=False),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(status='PASS_PENDING_GAME_TEST',entries=len(reports),version=VERSION,actualChefParser=True,actualChefSandbox=True,gameTested=False)))

if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');main()
