"""Run original 21 physical regression harnesses against the separate probe."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import verify_test09_axis_test as tests
import build_test09_vrd_probe as build
if __name__=='__main__':
    tests.OUT=build.OUT
    tests.COMPAT=build.OUT/'physbone_compat-test09.lua'
    tests.RUNTIME=build.OUT/'physbone_runtime-test09.lua'
    tests.COMPAT_VERSION=build.COMPAT_VERSION
    tests.RUNTIME_VERSION=build.RUNTIME_VERSION
    tests.main()
