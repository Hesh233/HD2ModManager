"""Run each existing Lua physics harness in its own Lua 5.1 process (os.exit safe)."""
import argparse,json,os,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
TESTS=['p1-regression-test.lua','p2-solver-test.lua','bind-shape-test.lua','attach-cache-test.lua',
 'attach-loop-test.lua','axis-limit-behaviour-test.lua','axis-limit-frame-test.lua','limit-source-test.lua',
 'fast-write-test.lua','lifecycle-test.lua','motion-gate-test.lua','rig-select-test.lua','runtime-harness-test.lua']
ap=argparse.ArgumentParser();ap.add_argument('--child');ap.add_argument('--report',type=Path);ap.add_argument('--include-linear',action='store_true');args=ap.parse_args()
if args.child:
 from lupa.lua51 import LuaRuntime
 lua=LuaRuntime(unpack_returned_tuples=True)
 path=ROOT/'HD2PhysBoneCompat/test'/args.child
 module='physbone_runtime.lua' if args.child=='runtime-harness-test.lua' else 'physbone_compat.lua'
 lua.globals().arg=lua.table_from({0:str(path),1:str(ROOT/'HD2PhysBoneCompat/src'/module),2:str(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua.before-spring-dof-130-20261108.bak')})
 lua.execute(path.read_text('utf-8-sig'))
 raise SystemExit(0)
if args.include_linear:TESTS+=['spring-dof-test.lua']
log_root=(ROOT/'tmp/lua-boot').resolve()
assert log_root.is_relative_to(ROOT.resolve()) and log_root.is_dir()
rows=[];logs=[]
for name in TESTS:
 result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',name],cwd=ROOT,
  env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',LOCALAPPDATA=str(log_root)),capture_output=True)
 out=result.stdout.decode('utf-8',errors='replace');err=result.stderr.decode('utf-8',errors='replace')
 failed=bool(re.search(r'^\s*FAIL\s',out,re.MULTILINE))
 passed=result.returncode==0 and not failed
 row=dict(test=name,status='PASS' if passed else 'FAIL',exitCode=result.returncode,
  passLines=len(re.findall(r'^\s*PASS\s',out,re.MULTILINE)),stderr=err[-2000:])
 rows.append(row);logs.append('==== '+name+' ====\n'+out+'\n'+err)
 print(name,row['status'],row['passLines'])
 if not passed:print((out+'\n'+err)[-5000:])
if args.report:
 args.report.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 args.report.with_suffix('.log').write_text('\n'.join(logs),encoding='utf-8')
raise SystemExit(0 if all(r['status']=='PASS' for r in rows) else 1)
