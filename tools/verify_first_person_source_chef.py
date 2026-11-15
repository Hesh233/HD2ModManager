"""Reuse actual Chef parser/sandbox for the model-specific FP Source prototype."""
from pathlib import Path
import argparse,inspect,json,sys,zipfile
import build_detailed_grip_test as b
import audit_native_v31_b23_chef as chef
from build_first_person_source_test import OUT,ROOT,VERSION,SOURCE_NAME,TAG

def main(argv=None):
 global OUT
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,default=OUT);OUT=parser.parse_args(argv).out.resolve()
 row=b.load(OUT/'build-report.json')
 with zipfile.ZipFile(row['package'])as z:
  (OUT/'chef-fp-lua.patch').write_bytes(z.read('9ba626afa44a3aa3.patch_0'))
  (OUT/'chef-tp-parent.patch').write_bytes(z.read('9ba626afa44a3aa3.patch_1'))
 mapping={'hd2attachmentfix-B23.lua':OUT/SOURCE_NAME,'runtime/9ba626afa44a3aa3.patch_4':OUT/'chef-fp-lua.patch','native-parenting/9ba626afa44a3aa3.patch_5':OUT/'chef-tp-parent.patch','physics-companion/9ba626afa44a3aa3.patch_3':ROOT/'outputs/native-v34-b23-integrated-20261105/physics-companion/9ba626afa44a3aa3.patch_3','chef-audit.json':OUT/'chef-fp-source-validation.json','chef-fixture.log':OUT/'chef-fp-source-validation.log'}
 class Alias:
  def __init__(self,k=''):self.k=k
  def __truediv__(self,k):key=(self.k+'/'+str(k)).lstrip('/');return mapping.get(key,Alias(key))
 fn=inspect.getsource(chef.main);old="local path=api.log_directory..'/hd2_grip_b23_compact.log'";new=f"local path=opens[1].path;assert(path:find('_{TAG}_',1,true),'FP source log not isolated')";assert old in fn;fn=fn.replace(old,new,1)
 env=dict(chef.__dict__);env['W']=Alias();exec(compile(fn,'<fp-source-actual-chef>','exec'),env);env['main'](VERSION)
 r=b.load(OUT/'chef-fp-source-validation.json');assert r['status']=='PASS'and r['sourceSha256']==row['luaSha256'] and r['emptyWorldWrites']==0;print('FP Source actual Chef parse/sandbox/module-selection PASS; no empty-world writers.')
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
