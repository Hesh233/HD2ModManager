"""Resource-only frozen normal Core candidates and actual application exporter."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,os
ROOT=Path(__file__).resolve().parents[1];LAB=ROOT/'outputs/physics-single-consumers-formal-20261117';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
sys.dont_write_bytecode=True
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=LAB);ap.add_argument('--source-root',type=Path,default=LAB);a=ap.parse_args();OUT=a.output.resolve();SOURCE=a.source_root.resolve();assert SOURCE.is_relative_to(ROOT)
assert OUT.is_relative_to(ROOT) and not OUT.is_relative_to(NORMAL)
OUT.mkdir(parents=True,exist_ok=True)
for variant in ['A','B']:
 source=SOURCE/(variant+'-source');candidate=OUT/(variant+'-candidate')
 manifest=json.loads((ROOT/'HD2PhysBoneCompat/src/production/single_remote_release_manifest.json').read_text('utf-8-sig'));entry=next(e for e in manifest['sources']if e['variant']==variant)
 assert hashlib.sha256((source/'physbone_runtime.lua').read_bytes()).hexdigest()==entry['runtimeSha256'] and hashlib.sha256((source/'physbone_compat.lua').read_bytes()).hexdigest()==entry['compatSha256'], 'Refusing stale source directory'
 if candidate.exists():raise RuntimeError('Use a new export stage; do not overwrite a previously exported candidate')
 subprocess.run(['dotnet',str(ROOT/'tools/PhysicsResourceUpdate/bin/Release/net10.0/PhysicsResourceUpdate.dll'),'update',str(NORMAL/'HD2ModCore.dll'),str(source),str(candidate)],check=True)
 for name in ['HD2GameItemAssets.dll','HD2ModAdaptation.dll','HD2SourceModel.dll','HD2SourceMigration.dll']:
  if(NORMAL/name).is_file():shutil.copyfile(NORMAL/name,candidate/name)
 subprocess.run(['dotnet',str(ROOT/'tools/ManagedPackageAudit/bin/Release/net10.0/ManagedPackageAudit.dll'),str(NORMAL/'HD2ModCore.dll'),str(candidate/'HD2ModCore.dll'),str(OUT/(variant+'-core-audit.json'))],check=True)
 audit=json.loads((OUT/(variant+'-core-audit.json')).read_text('utf-8-sig'))
 assert audit['identityUnchanged']and not audit['changedMethods']and not audit['changedConstants']and not audit['changedReferences']
 assert audit['methodsBefore']==audit['methodsAfter']==19802
 assert audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']
 env=os.environ.copy();env['APPDATA']=str(OUT/(variant+'-export-roaming'));env['LOCALAPPDATA']=str(OUT/(variant+'-export-local'))
 subprocess.run(['dotnet',str(ROOT/'tools/ManagerPackageSupport/bin/Release/net10.0/ManagerPackageSupport.dll'),'physics',str(candidate),str(OUT/(variant+'-export'))],check=True,env=env)
 print(variant,'actual exporter PASS',flush=True)
