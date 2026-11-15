"""Re-run frozen Source2 harnesses against the version-only formal candidate."""
from pathlib import Path
import sys,shutil,json,subprocess,hashlib,struct,os
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'outputs/test1201-source2-live-rejection-20261111';OUT=ROOT/'outputs/test1201-source2-accepted-20261111'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (OUT/'formal-verification-summary.json').exists(),'Verification outputs are frozen'
for name in ['source-profile.json','parsed-rig.json','raw-source-bones.json','unit-fits.json','source_solver.lua']:
 shutil.copyfile(OLD/name,OUT/name)
for kind in ['compat','runtime']:
 shutil.copyfile(OUT/'formal'/f'physbone_{kind}.lua',OUT/f'physbone_{kind}-test1201.lua')
raw=(OLD/'hd2physbone-test1201.lua').read_bytes();code=raw.replace(b'1.3.3-test1201-source2',b'1.3.3').replace(b'2.3.3-test1201-source2',b'2.3.3');(OUT/'hd2physbone-test1201.lua').write_bytes(code)
package=OUT/'candidate-package'
if not package.exists():
 subprocess.run(['dotnet',str(ROOT/'tools/ManagerPackageSupport/bin/Release/net10.0/ManagerPackageSupport.dll'),'physics',str(OUT/'candidate'),str(package)],cwd=ROOT,check=True,stdout=(OUT/'candidate-package-console.json').open('w',encoding='utf8'))
(OUT/'patch').mkdir(exist_ok=True)
for name in ['manifest.json','9ba626afa44a3aa3.patch_0','9ba626afa44a3aa3.patch_0.stream','9ba626afa44a3aa3.patch_0.gpu_resources']:
 shutil.copyfile(package/'export'/name,OUT/'patch'/name)
patch=(OUT/'patch/9ba626afa44a3aa3.patch_0').read_bytes();offset=struct.unpack_from('<Q',patch,120)[0];size=struct.unpack_from('<I',patch,offset)[0];embedded=patch[offset+8:offset+8+size]
assert embedded.replace(b'\r\n',b'\n')==code.replace(b'\r\n',b'\n'),'Formal exporter differs beyond platform newlines'
(OUT/'hd2physbone-test1201.lua').write_bytes(embedded)
os.environ['PYTHONIOENCODING']='utf-8'
scripts=['verify.py','verify_identity.py','verify_edges.py','verify_locations_sprint.py','run_existing.py'];results=[]
for name in scripts:
 text=(OLD/name).read_text('utf8')
 if name=='run_existing.py':text=text.replace('1.3.3-test1201-source2','1.3.3').replace('2.3.3-test1201-source2','2.3.3').replace('chef-test1201-source2','chef-test1201-accepted')
 if name=='run_existing.py':text=text.replace("text=text.replace('physbone_compat-test09.lua'","text=text.replace(\"(OUT/'hd2physbone-test09.lua').read_text('utf8')\",\"(OUT/'hd2physbone-test09.lua').read_bytes().decode('utf8')\")\ntext=text.replace('physbone_compat-test09.lua'")
 (OUT/name).write_text(text,'utf8')
 print('START',name,flush=True)
 with (OUT/(name+'.console.log')).open('w',encoding='utf8') as log:
  result=subprocess.run([sys.executable,'-B',str(OUT/name)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
 if result.returncode:print((OUT/(name+'.console.log')).read_text('utf8'),flush=True);raise SystemExit(result.returncode)
 print('PASS',name,flush=True);results.append(dict(script=name,status='PASS'))
reports=['verification.json','identity-verification.json','edge-verification.json','location-sprint-verification.json','existing-suite.json'];rows={}
for n in reports:
 v=json.loads((OUT/n).read_text('utf8'));assert v['status'].startswith('PASS');rows[n]=dict(status=v['status'],checks=v.get('checks'),sha256=sha(OUT/n))
(OUT/'formal-verification-summary.json').write_text(json.dumps(dict(status='PASS_FORMAL_VERSION_ONLY_CANDIDATE_OFFLINE',candidateCompatSha256=sha(OUT/'formal/physbone_compat.lua'),candidateRuntimeSha256=sha(OUT/'formal/physbone_runtime.lua'),reports=rows,scripts=results),ensure_ascii=False,indent=2),'utf8')
print('ALL FORMAL OFFLINE TESTS PASS',flush=True)
