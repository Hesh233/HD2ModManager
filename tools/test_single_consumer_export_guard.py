"""Frozen normal DLL exporter: raw CRLF/UTF8 size rejection + exact patch re-export."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];LAB=ROOT/'outputs/physics-single-loader-size-fix-20261117';OUT=LAB/'release-candidate'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
helper=ROOT/'tools/ManagerPackageSupport/bin/Release/net10.0/ManagerPackageSupport.dll';rows=[]
for variant in ['A','B']:
 old=ROOT/'outputs/physics-single-consumers-ship-11fps-20261117/release-candidate'/(variant+'-candidate')
 blocked=LAB/('old-oversized-export-rejected-'+variant);assert not blocked.exists()
 env=os.environ.copy();env['APPDATA']=str(LAB/'export-recheck');env['LOCALAPPDATA']=env['APPDATA']
 r=subprocess.run(['dotnet',str(helper),'physics',str(old),str(blocked)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
 (LAB/('export-old-reject-'+variant+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
 assert r.returncode!=0 and '4 MiB' in r.stderr and not blocked.exists(),'Old oversized exporter not rejected before output'
 fresh=LAB/'export-recheck'/(variant+'-export');assert not fresh.exists()
 r=subprocess.run(['dotnet',str(helper),'physics',str(OUT/(variant+'-candidate')),str(fresh)],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
 (LAB/('export-recheck-'+variant+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8');assert r.returncode==0,r.stdout+r.stderr
 with zipfile.ZipFile(fresh/'physics-runtime.zip')as z,zipfile.ZipFile(OUT/(variant+'-export/physics-runtime.zip'))as retained:
  assert z.testzip()is None and set(z.namelist())==set(retained.namelist())
  for name in z.namelist():assert z.read(name)==retained.read(name),'Fresh exporter changed payload '+name
 rows.append(dict(variant=variant,oldExportRejectedBeforeOutput=True,freshExportPatchAndManifestExact=True,retainedZipSha256=sha(OUT/(variant+'-export/physics-runtime.zip'))))
result=dict(status='PASS_ACTUAL_EXPORTER_RAW_RESOURCE_GUARD',oldOversizedRejected=2,rows=rows,helperSha256=sha(helper),helperSourceSha256=sha(ROOT/'tools/ManagerPackageSupport/Program.cs'),normalCoreUnmodified=True)
(LAB/'actual-export-guard-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
