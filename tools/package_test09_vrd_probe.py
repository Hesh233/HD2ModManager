"""Flat Arsenal READ-ONLY probe; accepted axis1 solver remains embedded unchanged."""
from pathlib import Path
import json,struct,sys,zipfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from build_test09_axis_test import sha,save
from build_test09_vrd_probe import OUT,AXIS,COMPAT_VERSION,RUNTIME_VERSION
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
NAME='物理运行时-test09_chr654-axis1保留-VRD与前倾取证-probe1'
PACKAGE=INSTALL/'非运行文件/测试包'/(NAME+'.zip')

def prepare():
 build=json.loads((AXIS/'package-report.json').read_text('utf8'));accepted=Path(build['package']);assert sha(accepted)==build['sha256']
 with zipfile.ZipFile(accepted) as z:raw=z.read('9ba626afa44a3aa3.patch_0');manifest=json.loads(z.read('manifest.json'))
 nt,n=struct.unpack_from('<II',raw,4);assert nt==n==1;at=72+nt*32;row=struct.unpack_from('<QQQQQQQIIIIII',raw,at)
 code=(OUT/'hd2physbone-test09.lua').read_bytes();assert code.startswith(b'-- HD2-Addon: mods/hd2modmanager/physbone\n')
 body=struct.pack('<II',len(code),2)+code;result=bytearray(raw[:row[2]]);struct.pack_into('<I',result,at+56,len(body));result+=body;result+=bytes((-len(result))%16)
 target=OUT/'patch';target.mkdir(exist_ok=True);(target/'9ba626afa44a3aa3.patch_0').write_bytes(result)
 for suffix in ['stream','gpu_resources']:(target/('9ba626afa44a3aa3.patch_0.'+suffix)).write_bytes(b'')
 manifest.update(Name=NAME,Description=f'READ-ONLY test09 VRD and body tilt probe; axis1 retained; {RUNTIME_VERSION}; not a VRD fix.')
 save(target/'manifest.json',manifest)
 print('Prepared flat probe patch')

def publish():
 import verify_test09_axis_test as tests
 regression=json.loads((OUT/'probe-regression.json').read_text('utf8'));suite=json.loads((OUT/'test09-axis-suite.json').read_text('utf8'))
 assert regression['writerTraceEqualsAcceptedAxis1'] and suite['status']=='PASS_OFFLINE_NOT_GAME_ACCEPTANCE'
 assert suite['candidateCompatSha256']==sha(OUT/'physbone_compat-test09.lua') and suite['candidateRuntimeSha256']==sha(OUT/'physbone_runtime-test09.lua')
 old=json.loads((OUT/'protected-before.json').read_text('utf8'));assert {p:sha(p) for p in old}==old
 assert not PACKAGE.exists(),'preserve previous release'
 prepare();members=list((OUT/'patch').iterdir());assert len(members)==4
 with zipfile.ZipFile(PACKAGE,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in members:z.write(p,p.name)
 with zipfile.ZipFile(PACKAGE) as z:
  assert z.testzip() is None and len(z.infolist())==4
  for p in members:assert z.read(p.name)==p.read_bytes()
 save(OUT/'package-report.json',dict(status='PASS_OFFLINE_READ_ONLY_PROBE_NOT_GAME_ACCEPTANCE',package=str(PACKAGE),sha256=sha(PACKAGE),bytes=PACKAGE.stat().st_size,
  compatVersion=COMPAT_VERSION,runtimeVersion=RUNTIME_VERSION,axis1SolverPreserved=True,writerTraceExact=True,zipCrc=True,flatRootManifestAndThreePatchFiles=True,
  test09Only=True,sampleIntervalSeconds=2,maxSamples=20,maxProbeSessions=1,probeIsReadOnly=True,protectedFilesUnchanged=len(old),
  memberSha256={p.name:sha(p) for p in members},gameDeployed=False,gameTested=False))
 print('PACKAGE',str(PACKAGE),'bytes',PACKAGE.stat().st_size,'SHA',sha(PACKAGE))

if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf8');publish() if '--publish' in sys.argv else prepare()
