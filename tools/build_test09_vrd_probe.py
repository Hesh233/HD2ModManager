"""Keep accepted axis1 exactly, add READ-ONLY bounded VRD/body probe only."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from build_test09_axis_test import sha,save
OUT=ROOT/'outputs/test09-chr654-vrd-followup-20261110'
AXIS=ROOT/'outputs/test09-chr654-axis-fix-20261110'
COMPAT_VERSION='1.3.3-test09-vrdprobe1';RUNTIME_VERSION='2.3.3-test09-vrdprobe1'

def main():
    assert not (OUT/'package-report.json').exists(),'preserve completed probe release'
    report=json.loads((AXIS/'package-report.json').read_text('utf8'));assert sha(report['package'])==report['sha256']
    source=(AXIS/'physbone_compat-test09.lua').read_text('utf8');baseline=source
    template=(ROOT/'HD2PhysBoneCompat/src/experimental/test09_vrd_probe.lua').read_text('utf-8-sig')
    marker='return M';end=source.rfind(marker);assert end>=0
    compat=source[:end]+template+'\n'+source[end:]
    assert source.count('M.version = "1.3.2-test09-axis1"')==1
    compat=compat.replace('M.version = "1.3.2-test09-axis1"','M.version = "'+COMPAT_VERSION+'"',1)
    runtime=(AXIS/'physbone_runtime-test09.lua').read_text('utf8').replace('M.VERSION = "2.3.2-test09-axis1"','M.VERSION = "'+RUNTIME_VERSION+'"',1)
    standalone=(AXIS/'hd2physbone-test09.lua').read_text('utf8');assert standalone.count(baseline)==1
    standalone=standalone.replace(baseline,compat,1).replace((AXIS/'physbone_runtime-test09.lua').read_text('utf8'),runtime,1)
    for name,text in [('baseline-axis1-compat.lua',baseline),('physbone_compat-test09.lua',compat),('physbone_runtime-test09.lua',runtime),('hd2physbone-test09.lua',standalone)]:
        (OUT/name).write_bytes(text.encode('utf8'))
    from lupa.lua51 import LuaRuntime
    vm=LuaRuntime(unpack_returned_tuples=True);vm.execute(compat);vm.eval('function(s)local f,e=loadstring(s);assert(f,e);return true end')(standalone)
    save(OUT/'build-report.json',dict(status='BUILT_READ_ONLY_PROBE_PENDING_TESTS',compatVersion=COMPAT_VERSION,runtimeVersion=RUNTIME_VERSION,
        acceptedAxis1Sha256=report['sha256'],axisSolverCodePreserved=True,intervalSeconds=2,maxSamples=20,sessionCountLimit=1,
        source=(str(ROOT/'HD2PhysBoneCompat/src/experimental/test09_vrd_probe.lua')),gameDeployed=False,gameTested=False))
    print('Built READ-ONLY test09 VRD probe; accepted axis1 body preserved')

if __name__=='__main__':sys.stdout.reconfigure(encoding='utf8');main()
