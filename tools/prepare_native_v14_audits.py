"""Prepare v14-specific retained regression fixtures and record completed tests."""
from pathlib import Path
from package_native_v12 import save_json, digest

ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'outputs/native-v14-20261104'

def main():
    for name in ('chef','runtime'):
        source=(ROOT/f'tools/audit_native_v13_{name}.py').read_text(encoding='utf-8')
        source=source.replace('native-v13-20261104','native-v14-20261104').replace('v13Baseline','v14Baseline')
        if name=='chef':
            source=source.replace("a.version=='2.1.8'", "a.version=='2.1.9'")
            source=source.replace('p.armSync==false and #p.armChains==2', 'p.armSync==false and p.armGripSync==false and #p.armChains==2')
        (ROOT/f'tools/audit_native_v14_{name}.py').write_text(source,encoding='utf-8')
    text=(W/'python-regression.log').read_text(encoding='utf-8-sig')
    assert 'Ran 117 tests' in text and 'OK (skipped=1)' in text
    save_json(W/'python-regression.json',dict(status='PASS',tests=117,skipped=1,log='python-regression.log',sha256=digest(W/'python-regression.log')))
    text=(W/'exporter-tests.log').read_text(encoding='utf-8-sig')
    assert '测试运行成功' in text and '通过数: 8' in text
    save_json(W/'exporter-audit.json',dict(status='PASS',tests=8,publishedAssembly=str(W/'manager/HD2ModCore.dll'),
        assemblySha256=digest(W/'manager/HD2ModCore.dll'),exportedVia='NativeReleaseTools: published PhysBoneLuaPackageExport.Export',
        luaSha256=digest(W/'physics-export-delivery/lua版/hd2physbone.lua'),log='exporter-tests.log'))

if __name__=='__main__':main()
