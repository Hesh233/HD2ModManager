"""Rebuild the read-only producer and verify current facts/stale input rejection."""
from pathlib import Path
import hashlib, json, os, shutil, stat, subprocess, sys
ROOT = Path(__file__).resolve().parents[1]
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--evidence-root',type=Path,default=ROOT/'outputs/physics-single-consumers-ship-11fps-20261117');a=ap.parse_args()
LAB = a.evidence_root.resolve();assert LAB.is_relative_to(ROOT)
NORMAL = ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text('utf-8-sig'))
env = os.environ.copy(); env['DOTNET_CLI_TELEMETRY_OPTOUT']='1'
binary = LAB/'producer-finish/PhysicsConsumerAudit.dll'
cmd = ['dotnet','build','tools/PhysicsConsumerAudit/PhysicsConsumerAudit.csproj','-c','Release','--no-restore','-o',str(binary.parent)]
build = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
(LAB/'producer-finish-build.log').write_text(build.stdout+build.stderr, encoding='utf-8')
assert build.returncode == 0, build.stdout+build.stderr
rows=[]
for key, name in [('test01','[单骨架模型]test01'),('cow','[单骨架模型]Cow_QiPao_Milltina_Nick'),('test13','[单骨架模型]test13'),('test15','[单骨架模型]test15')]:
    output=LAB/'producer-finish'/('verified-'+key+'-facts.json')
    r=subprocess.run(['dotnet',str(binary),str(NORMAL/'test-library'/name),str(output)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    assert r.returncode==0,r.stdout+r.stderr
    assert read(output)==read(LAB/(key+'-facts.json')), 'Fresh producer does not reproduce '+key
    facts=read(output)
    rows.append(dict(model=name,eligibleUnits=len(facts['units']),rejectedUnits=len(facts['rejected']),factsSha256=sha(output)))
negative=[]
for case in ['config','bind','model-payload']:
    model=LAB/'producer-negative-r2'/case
    sectional=model/'sectional'
    assert not model.exists(), 'Use a fresh negative output directory'
    shutil.copytree(NORMAL/'test-library/[单骨架模型]test01/sectional',sectional)
    name={'config':'single-config.toml','bind':'single-hd2-bind.json','model-payload':'9ba626afa44a3aa3.patch_0'}[case]
    path=sectional/name
    assert path.resolve().is_relative_to((LAB/'producer-negative-r2').resolve())
    path.chmod(stat.S_IREAD|stat.S_IWRITE)
    data=path.read_bytes()
    path.write_bytes(data+b'\n' if case in ['config','bind'] else data[:-1]+bytes([data[-1]^1]))
    output=LAB/'producer-finish'/('negative-'+case+'.json')
    r=subprocess.run(['dotnet',str(binary),str(model),str(output)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (LAB/'producer-finish'/('negative-'+case+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
    assert r.returncode!=0 and not output.exists(), 'Stale input produced an eligible manifest: '+case
    reason=json.loads(r.stderr.strip())
    assert reason['status']=='REJECTED_READ_ONLY_CONSUMER_FACTS',reason
    negative.append(dict(case=case,status=reason['status'],reason=reason['reason']))
result=dict(status='PASS_FRESH_PRODUCER_AND_STALE_CERTIFICATE_REJECTION',sourceSha256=sha(ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs'),auditProgramSha256=sha(ROOT/'tools/PhysicsConsumerAudit/Program.cs'),assemblySha256=sha(binary),buildReturncode=build.returncode,buildLogSha256=sha(LAB/'producer-finish-build.log'),models=rows,negativeCases=negative,libraryInputsWritten=False)
(LAB/'producer-finish-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
