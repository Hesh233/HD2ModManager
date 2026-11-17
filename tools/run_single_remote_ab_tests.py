from pathlib import Path
import argparse, importlib, os, re, json
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--vm',choices=['lua51','luajit21'],default='lua51');ap.add_argument('--variant',choices=['A','B'],required=True);ap.add_argument('--test',default='single-remote-policy-test.lua');ap.add_argument('--full-policy-regression',action='store_true');ap.add_argument('--extracted',action='store_true');args=ap.parse_args()
out=args.output.resolve();assert out.is_relative_to(ROOT)
os.chdir(ROOT);work=out/(args.variant+'-harness-'+args.vm);work.mkdir(exist_ok=True)
os.environ['LOCALAPPDATA']=str(work);os.environ['APPDATA']=str(work)
L=importlib.import_module('lupa.'+args.vm).LuaRuntime
lua=L(unpack_returned_tuples=True);lines=[]
def record(*values): lines.append('\t'.join(map(str,values)))
lua.globals().print=record
folder=out/(args.variant+('-extracted' if args.extracted else '-source'));test=ROOT/'HD2PhysBoneCompat/test'/args.test
lua.globals().arg=lua.table_from({0:str(test),1:str(folder/'physbone_runtime.lua'),2:str(folder/'physbone_compat.lua')})
source=test.read_text('utf-8-sig').replace('os.exit(1)','error("HARNESS_EXIT_1")')
if args.full_policy_regression:
    assert args.test in ['single-mainline-regression-test.lua','multiplayer-skeleton-regression-test.lua']
    source=source.replace('local options={compat=C,','local options={singleRemoteTestPolicy="full",compat=C,')
    assert 'singleRemoteTestPolicy="full"' in source
    # This explicitly tests the UNCHANGED baseline path; it is not a default A/B pass.
try: lua.execute(source,name=str(test));error=None
except Exception as e: error=str(e);lines.append('ERROR '+error)
text='\n'.join(lines)+'\n';log=out/(args.variant+'-'+args.vm+'-'+args.test+('-full-policy' if args.full_policy_regression else '')+('-actual-extracted' if args.extracted else '')+'.log');log.write_text(text,encoding='utf-8')
failed=len(re.findall(r'^\s*FAIL\s',text,re.M));passed=len(re.findall(r'^\s*PASS\s',text,re.M))
print(json.dumps({'variant':args.variant,'vm':args.vm,'test':args.test,'actualExtractedZipSource':args.extracted,'fullPolicyOverrideForRegressionOnly':args.full_policy_regression,'pass':passed,'fail':failed,'error':error,'log':str(log)},ensure_ascii=False))
if error or failed:
    print(text[-6500:]);raise SystemExit(1)
