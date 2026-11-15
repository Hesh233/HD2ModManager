"""Build exact currently visible Hips observation package; no model/game writes."""
from pathlib import Path
import json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from build_test09_axis_test import sha,save
OUT=ROOT/'outputs/test09-chr654-hips-probe2-20261110'
AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110'
COMPAT_VERSION='1.3.4-test09-hipsprobe2';RUNTIME_VERSION='2.3.4-test09-hipsprobe2'

def main():
 OUT.mkdir(exist_ok=True);assert not (OUT/'package-report.json').exists(),'preserve published probe2'
 baseline=(AXIS/'physbone_compat-test09.lua').read_text('utf8');template=(ROOT/'HD2PhysBoneCompat/src/experimental/test09_hips_vrd_probe.lua').read_text('utf-8-sig')
 marker=baseline.rfind('return M');assert marker>0
 compat=(baseline[:marker]+template+'\n'+baseline[marker:]).replace('M.version = "1.3.2-test09-axis1"','M.version = "'+COMPAT_VERSION+'"',1)
 runtime=(AXIS/'physbone_runtime-test09.lua').read_text('utf8').replace('M.VERSION = "2.3.2-test09-axis1"','M.VERSION = "'+RUNTIME_VERSION+'"',1)
 base_runtime=(AXIS/'physbone_runtime-test09.lua').read_text('utf8')
 standalone=(AXIS/'hd2physbone-test09.lua').read_text('utf8');assert standalone.count(baseline)==1 and standalone.count(base_runtime)==1
 standalone=standalone.replace(baseline,compat,1).replace(base_runtime,runtime,1)
 # A diagnostic-only budget override, applied once to the installed runtime,
 # not a solver/animation parameter. Leave general production limits intact.
 old="local options = { compat = PhysBoneCompat, mode = 'external' }"
 assert standalone.count(old)==1
 standalone=standalone.replace(old,"local options = { compat = PhysBoneCompat, mode = 'external', logMaxBytes = 262144 }",1)
 for n,s in [('baseline-axis1-compat.lua',baseline),('physbone_compat-test09.lua',compat),('physbone_runtime-test09.lua',runtime),('hd2physbone-test09.lua',standalone)]: (OUT/n).write_bytes(s.encode('utf8'))
 from lupa.lua51 import LuaRuntime
 vm=LuaRuntime(unpack_returned_tuples=True);vm.execute(compat);vm.eval('function(s)local f,e=loadstring(s);assert(f,e);return true end')(standalone)
 save(OUT/'build-report.json',dict(status='BUILT_READ_ONLY_HIPS_PROBE_PENDING_TESTS',compatVersion=COMPAT_VERSION,runtimeVersion=RUNTIME_VERSION,
 exactHipResource='34a40a5ae7a392ba',maxSamples=16,intervalSeconds=2,maxSessions=1,logByteBudget=262144,
 acceptedAxis1SolverUnchanged=True,productionModified=False,gameDeployed=False,gameTested=False))
 print('Built exact-Hips probe2; no solver modifications')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
