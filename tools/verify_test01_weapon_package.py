"""Verify the actual Core-built package in Chef and unchanged FP gate suites."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from verify_test04_lua_entry import exercise
import audit_native_v31_b23_chef as chef
from audit_test07_sidearm_111 import build_111_harness
from audit_native_v31_b23 import run_harness
from audit_native_b23_107_issues import plain
TARGET=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';PREFIX='test01-武器握持修正-1.0.17'
class Aliases:
 def __init__(self,relative=''):self.relative=relative
 def __truediv__(self,name):
  key=(self.relative+'/'+str(name)).lstrip('/')
  if key in aliases:return aliases[key]
  return Aliases(key)
aliases={
 'hd2attachmentfix-B23.lua':TARGET/(PREFIX+'.lua'),
 'runtime/9ba626afa44a3aa3.patch_4':TARGET/(PREFIX+'.patch'),
 'physics-companion/9ba626afa44a3aa3.patch_3':TARGET/'物理日志缩减-2.2.1.patch',
 'native-parenting/9ba626afa44a3aa3.patch_5':TARGET/'test-library/[骨骼挂点修正]test01/9ba626afa44a3aa3.patch_1',
 'chef-audit.json':TARGET/'日志缩减-1.0.17-Chef验证.json',
 'chef-fixture.log':TARGET/'日志缩减-1.0.17-Chef测试.log',
}
def main():
 source=(TARGET/(PREFIX+'.lua')).read_text(encoding='utf8');r=exercise(source)
 assert r['started'] and r['version']=='1.0.17' and r['writes']==0 and r['closed']==1
 (TARGET/'日志缩减-1.0.17-入口验证.json').write_text(json.dumps(r,indent=2),encoding='utf8')
 chef.W=Aliases();chef.main(version='1.0.17')
 if '--chef-only' in sys.argv:return
 p,f,h=build_111_harness();h=h[:h.rindex('\nreturn {status=')]
 guard=(ROOT/'HD2PhysBoneCompat/src/native_first_person_guard.lua').read_text(encoding='utf8')
 extra=(ROOT/'HD2PhysBoneCompat/test/native_grip_first_person_harness.lua').read_text(encoding='utf-8-sig').replace('local fpGuardModule=fp_guard_module','local fpGuardModule=__fp_guard_module')
 h+='\n__fp_guard_module=(function()\n'+guard+'\nend)()\nreturn (function()\n'+extra+'\nend)()'
 r=plain(run_harness(p,f,h));logs=r.pop('logs');r.update(luaVersion='1.0.17',gameTested=False)
 (TARGET/'日志缩减-1.0.17-FP验证.json').write_text(json.dumps(r,indent=2),encoding='utf8')
 (TARGET/'日志缩减-1.0.17-FP测试.log').write_text('\n'.join(logs),encoding='utf8');print(json.dumps(r))
if __name__=='__main__':main()
