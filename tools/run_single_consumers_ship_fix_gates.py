"""Actual candidate ZIP + real game Lua/Chef bit regression. No game/FPS claim."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
import argparse
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--evidence-root',type=Path,default=ROOT/'outputs/physics-single-consumers-ship-11fps-20261117');ap.add_argument('--output',type=Path);ap.add_argument('--loader-size-fix',action='store_true');a=ap.parse_args()
LAB=a.evidence_root.resolve();OUT=a.output.resolve()if a.output else LAB/'release-candidate';SHIM=LAB/'actual-chef-bit-shim.lua'
assert LAB.is_relative_to(ROOT)and OUT.is_relative_to(LAB)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads((ROOT/'HD2PhysBoneCompat/src/production/single_remote_release_manifest.json').read_text('utf-8-sig'));inputs={'catalog':sha(ROOT/'HD2PhysBoneCompat/src/production/single_consumer_catalog.json'),'actualChefBit':sha(SHIM)}
for e in manifest['sources']:
 v=e['variant'];assert sha(OUT/(v+'-extracted/physbone_runtime.lua'))==e['runtimeSha256'];assert sha(OUT/(v+'-extracted/physbone_compat.lua'))==e['compatSha256'];inputs[v+'Runtime']=e['runtimeSha256'];inputs[v+'Compat']=e['compatSha256']
assert inputs['ACompat']==inputs['BCompat'];records=[];env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
def run(label,argv):
 cmd=[sys.executable,'-u','-B',str(ROOT/argv[0])]+[str(x)for x in argv[1:]]
 r=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=600);log=OUT/(label+'-runner.log');log.write_text(r.stdout+r.stderr,encoding='utf-8');records.append(dict(label=label,command=cmd,returncode=r.returncode,scriptSha256=sha(cmd[3]),log=str(log),logSha256=sha(log)))
 (OUT/'gate-run.json').write_text(json.dumps(dict(status='RUNNING_CORRECTION_CANDIDATE_GATES'if r.returncode==0 else'FAILED_CORRECTION_CANDIDATE_GATE',inputs=inputs,tests=records),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(label,'PASS'if r.returncode==0 else'FAIL',flush=True)
 if r.returncode:print((r.stdout+r.stderr)[-8000:]);raise SystemExit(r.returncode)
for v in ['A','B']:
 for profile,vm,chef in [('jit','luajit21',False),('plain','lua51',False),('chef','lua51',True)]+([('chef-patch','lua51',True)]if a.loader_size_fix else[]):
  label='runtime-'+v+'-'+profile;argv=['HD2PhysBoneCompat/test/single-consumer-runtime-test.py','--source',OUT/(v+'-extracted'),'--output',OUT/label,'--vm',vm]
  if chef:argv+=['--chef-bit',SHIM]
  if profile=='chef-patch':argv+=['--chef-patch',OUT/(v+'-export/physics-runtime.zip'),'--chef-core',LAB/'actual-chef-core-1.lua']
  run(label,argv)
 for vm in ['lua51','luajit21']:
  for kind in ['inventory','epoch']:
   label=kind+'-'+v+'-'+vm;run(label,['HD2PhysBoneCompat/test/single-consumer-'+kind+'-test.py','--source',OUT/(v+'-extracted'),'--output',OUT/label,'--vm',vm])
  for flag,baseline in [('--ship',None),(None,None),('--full-baseline','single-mainline-regression-test.lua'),('--full-baseline','multiplayer-skeleton-regression-test.lua')]:
   label=v+'-'+vm+'-'+('ship'if flag=='--ship'else baseline or'ads');argv=['tools/run_single_ship_formal_gates.py','--variant',v,'--vm',vm,'--output',OUT,'--extracted']
   if flag:argv.append(flag)
   if baseline:argv.append(baseline)
   run(label,argv)
for profile,vm,chef in [('jit','luajit21',False),('plain','lua51',False),('chef','lua51',True)]:
 for model in ['test01','cow','test13','test15']:
  label='palette-'+model+'-'+profile;argv=['HD2PhysBoneCompat/test/single-consumer-palette-test.py','--source',OUT/'A-extracted/physbone_compat.lua','--output',OUT/label,'--model',model,'--vm',vm]
  if chef:argv+=['--chef-bit',SHIM]
  run(label,argv)
for mutation in ['gpu','toc','higher','missing_gpu','bind']:
 label='negative-'+mutation+'-chef';run(label,['HD2PhysBoneCompat/test/single-consumer-palette-test.py','--source',OUT/'A-extracted/physbone_compat.lua','--output',OUT/label,'--vm','lua51','--chef-bit',SHIM,'--mutation',mutation])
expected=49 if a.loader_size_fix else 47
assert len(records)==expected
(OUT/'gate-run.json').write_text(json.dumps(dict(status='PASS_'+str(expected)+'_CORRECTION_CANDIDATE_GATES_NOT_GAME_FPS',inputs=inputs,tests=records),ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print('PASS',expected,'actual correction ZIP gate commands; game FPS unmeasured',flush=True)
