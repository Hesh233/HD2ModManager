"""Byte-exact pool roundtrip and actual Chef scan negative/boundary regressions."""
from pathlib import Path
import argparse,base64,hashlib,json,struct,sys,zipfile
sys.dont_write_bytecode=True
from physics_consumer_lua_catalog import emit_catalog,DECODE
from chef_physics_patch_harness import scan_patch
import importlib
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--evidence-root',type=Path,default=ROOT/'outputs/physics-single-loader-size-fix-20261117');a=ap.parse_args();LAB=a.evidence_root.resolve();assert LAB.is_relative_to(ROOT)
OUT=LAB/'release-candidate';catalog=json.loads((ROOT/'HD2PhysBoneCompat/src/production/single_consumer_catalog.json').read_text('utf-8-sig'))
text,stats=emit_catalog(catalog);checks=0

def compare(value,wanted):
 global checks
 checks+=1
 if isinstance(wanted,dict):
  expected={k[:-6]if k.endswith('ExactBase64')else k:(base64.b64decode(v,validate=True)if k.endswith('ExactBase64')else v)for k,v in wanted.items()if v is not None}
  assert set(value.keys())=={k.encode()for k in expected}
  for k,v in expected.items():compare(value[k.encode()],v)
 elif isinstance(wanted,list):
  assert len(value)==len(wanted)
  for i,v in enumerate(wanted,1):compare(value[i],v)
 else:assert value==(wanted.encode()if isinstance(wanted,str)else wanted)

roundtrips=[]
for vm in ['lua51','luajit21']:
 L=importlib.import_module('lupa.'+vm).LuaRuntime
 lua=L(unpack_returned_tuples=True,encoding=None);lua.execute(b'bit=nil;ffi=nil;jit=nil;require=function()error("decode dependency forbidden")end')
 compare(lua.execute(('return '+text).encode()),catalog)
 decode=lua.execute((DECODE+'\nreturn decode').encode())
 for n in [0,1,2,3,255,256,257,8192]:
  raw=bytes(i%256 for i in range(n));assert decode(base64.b64encode(raw))==raw;checks+=1
 for bad in [b'A',b'!!!!',b'AA=A',b'AB==',b'AAB=',b'AA==AAAA',b'====']:
  try:decode(bad)
  except Exception:checks+=1
  else:raise AssertionError('Malformed base64 accepted: '+repr(bad))
 roundtrips.append(dict(vm=vm,allCatalogFieldsExact=True,decodesWithoutBitFfiJit=True))
# An exact, small duplicate must be interned, not repeated decimal-escaped bytes.
_,tiny=emit_catalog({'a':{'tocExactBase64':'AAE='},'b':{'tocExactBase64':'AAE='}});assert tiny['uniqueBlobs']==1;checks+=1
negative=[]
for variant in ['A','B']:
 old=ROOT/'outputs/physics-single-consumers-ship-11fps-20261117/release-candidate'/(variant+'-export/physics-runtime.zip')
 with zipfile.ZipFile(old)as z:blob=z.read('9ba626afa44a3aa3.patch_0')
 lua=importlib.import_module('lupa.lua51').LuaRuntime(unpack_returned_tuples=True)
 _,r=scan_patch(lua,LAB/'actual-chef-core-1.lua',blob)
 assert r['big']==1 and r['found']==0 and r['bad']==0;negative.append(dict(variant=variant,oldZipSha256=hashlib.sha256(old.read_bytes()).hexdigest(),**r));checks+=1
with zipfile.ZipFile(OUT/'A-export/physics-runtime.zip')as z:original=z.read('9ba626afa44a3aa3.patch_0')
offset=struct.unpack_from('<Q',original,120)[0];header=original[:offset]
boundaries=[]
for size in [4*1024*1024,4*1024*1024+1]:
 marker=b'-- HD2-Addon: mods/hd2modmanager/physbone\nreturn{}\n';body=marker+b' '*(size-8-len(marker))
 blob=bytearray(header+struct.pack('<II',len(body),2)+body);struct.pack_into('<I',blob,160,size)
 lua=importlib.import_module('lupa.lua51').LuaRuntime(unpack_returned_tuples=True);_,r=scan_patch(lua,LAB/'actual-chef-core-1.lua',bytes(blob))
 assert r['found']==int(size==4*1024*1024) and r['big']==int(size>4*1024*1024);checks+=1;boundaries.append(dict(resourceBytes=size,**r))
result=dict(status='PASS_BYTE_EXACT_ENCODING_AND_ACTUAL_CHEF_SIZE_NEGATIVES',checks=checks,encodingStats=stats,roundtrips=roundtrips,oldPackagesSkipped=negative,inclusiveChefResourceBoundaries=boundaries,catalogSha256=hashlib.sha256((ROOT/'HD2PhysBoneCompat/src/production/single_consumer_catalog.json').read_bytes()).hexdigest())
(OUT/'catalog-and-chef-size-tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
