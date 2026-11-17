from pathlib import Path
import argparse,importlib,json,os,re
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--ship',action='store_true');ap.add_argument('--output',type=Path);ap.add_argument('--variant',choices=['A','B'],required=True);ap.add_argument('--vm',choices=['lua51','luajit21'],default='lua51');ap.add_argument('--extracted',action='store_true');ap.add_argument('--full-baseline',choices=['single-mainline-regression-test.lua','multiplayer-skeleton-regression-test.lua']);a=ap.parse_args()
OUT=(a.output.resolve() if a.output else ROOT/'outputs/physics-single-ship-vrd-formal-20261117');assert OUT.is_relative_to(ROOT.resolve());work=OUT/(a.variant+'-offline-'+a.vm);work.mkdir(exist_ok=True);os.chdir(ROOT);os.environ['LOCALAPPDATA']=str(work);os.environ['APPDATA']=str(work)
L=importlib.import_module('lupa.'+a.vm).LuaRuntime;lua=L(unpack_returned_tuples=True);lines=[];lua.globals().print=lambda *v:lines.append('\t'.join(map(str,v)))
name=a.full_baseline or ('single-ship-formal-test.lua' if a.ship else 'single-ads-formal-test.lua');test=ROOT/'HD2PhysBoneCompat/test'/name;folder=OUT/(a.variant+('-extracted' if a.extracted else '-source'))
lua.globals().arg=lua.table_from({0:str(test),1:str(folder/'physbone_runtime.lua'),2:str(folder/'physbone_compat.lua')})
s=test.read_text('utf-8-sig').replace('os.exit(1)','error("HARNESS_EXIT_1")')
if a.full_baseline:s=s.replace('local options={compat=C,','local options={singleFormalPolicy=false,compat=C,');assert 'singleFormalPolicy=false' in s
error=None
try:lua.execute(s,name=str(test))
except Exception as e:error=str(e);lines.append('ERROR '+error)
text='\n'.join(lines)+'\n';tag=a.variant+'-'+a.vm+'-'+name+('-full-baseline' if a.full_baseline else '')+('-actual-zip' if a.extracted else '')
(OUT/(tag+'.log')).write_text(text,encoding='utf8');failed=len(re.findall(r'^\s*FAIL\s',text,re.M));passed=len(re.findall(r'^\s*PASS\s',text,re.M))
print(json.dumps({'variant':a.variant,'vm':a.vm,'test':name,'fullBaselineOverride':bool(a.full_baseline),'actualZipSource':a.extracted,'pass':passed,'fail':failed,'error':error}))
if failed or error:print(text[-7500:]);raise SystemExit(1)
