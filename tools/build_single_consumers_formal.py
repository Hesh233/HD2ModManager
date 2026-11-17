"""Build independent formal A/B sources with exact registered-model consumers.
Reads existing library/model/config bytes. Outputs only new sources and evidence.
Never imports/rebakes/deploys or rewrites the normal program.
"""
from pathlib import Path
import argparse,hashlib,json,math,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-consumers-formal-20261117';PROD=ROOT/'HD2PhysBoneCompat/src/production';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
sys.dont_write_bytecode=True
raise SystemExit("RETIRED: A2.3.15/B2.3.16 failed real ship FPS (11 FPS). Do not regenerate/recommend this archived SHA-in-render recipe. Use tools/build_single_consumers_ship_fix.py; correction candidates still require game acceptance.")
ap=argparse.ArgumentParser();ap.add_argument('--profiles-only',action='store_true');a=ap.parse_args()
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def lua(v):
 if v is None:return 'nil'
 if v is True:return 'true'
 if v is False:return 'false'
 if isinstance(v,(float,int)):
  if not math.isfinite(v):raise ValueError('nonfinite')
  return repr(v)
 if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
 if isinstance(v,list):return '{'+','.join(lua(x)for x in v)+'}'
 if isinstance(v,dict):return '{'+','.join('['+lua(k)+']='+lua(x)for k,x in sorted(v.items()))+'}'
 raise TypeError(type(v))
rows=[];models=[];rejected=[];bykey={}
for key,name in [('test01','[单骨架模型]test01'),('cow','[单骨架模型]Cow_QiPao_Milltina_Nick'),('test13','[单骨架模型]test13'),('test15','[单骨架模型]test15')]:
 facts=OUT/(key+'-facts.json')
 subprocess.run(['dotnet',str(OUT/'producer-v2/PhysicsConsumerAudit.dll'),str(NORMAL/'test-library'/name),str(facts)],check=True)
 j=json.loads(facts.read_text('utf-8-sig'));models.append({k:j[k]for k in ['modelName','rigSha256','driverRigSha256','configSha256','bindSha256']});rejected.extend(dict(x,model=name)for x in j['rejected'])
 for row in j['units']:
  row={k:v for k,v in row.items()if k not in ['sourcePatch','domain']};row.update(model=name,rigSha256=j['rigSha256'],driverRigSha256=j['driverRigSha256'])
  key=(row['resource'],row['rigSha256'],row['driverRigSha256'],row['tocSha256'],row['gpuSha256'],row['streamSha256'])
  if key in bykey:assert bykey[key]==row;continue
  bykey[key]=row;rows.append(row)
catalog={'schema':'hd2-physics-consumers/1','revision':'single-exact-consumers-v1','models':models,'units':rows,'unknownOrMismatch':'full-original-solver','proof':'winning-deployed-Unit-TOC+GPU+stream-SHA256; full-live-bind before mask','notVisibilityBased':True}
jsonbytes=(json.dumps(catalog,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8');(OUT/'consumer-catalog.json').write_bytes(jsonbytes)
(PROD/'single_consumer_catalog.json').write_bytes(jsonbytes)
(OUT/'consumer-rejected.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Eligible exact profiles:',len(rows),'different resources:',len({r['resource']for r in rows}),'models:',len(models),'rejected auxiliary/unsupported records:',len(rejected),flush=True)
if a.profiles_only:raise SystemExit(0)
previous=json.loads((OUT/'before/single_remote_release_manifest.json').read_text('utf-8-sig'))
base=(OUT/'before/single_remote_compat.lua').read_text('utf-8-sig');assert base.count('M.version = "1.3.10"')==1
hashcode=(PROD/'single_consumer_sha256.lua.in').read_text('utf-8-sig');consumer=(PROD/'single_consumers_compat.lua.in').read_text('utf-8-sig');assert consumer.count('@CATALOG@')==1;consumer=consumer.replace('@CATALOG@',lua(catalog))
assert base.rstrip().endswith('return M');compat=base.rsplit('return M',1)[0].replace('M.version = "1.3.10"','M.version = "1.3.11"',1)+hashcode+'\n'+consumer+'\nreturn M\n'
(PROD/'single_remote_compat.lua').write_text(compat,encoding='utf-8',newline='\n')
rtpatch=(PROD/'single_consumers_runtime.lua.in').read_text('utf-8-sig')
versions={'A':'2.3.15','B':'2.3.16'};sources=[]
for v in ['A','B']:
 old=next(x for x in previous['sources']if x['variant']==v);runtime=(OUT/'before'/('single_remote_'+v+'_runtime.lua')).read_text('utf-8-sig')
 assert runtime.count('M.VERSION = "'+old['runtimeVersion']+'"')==1
 runtime=runtime.replace('M.VERSION = "'+old['runtimeVersion']+'"','M.VERSION = "'+versions[v]+'"',1)
 patches=json.loads((OUT/'runtime-edits.json').read_text('utf-8-sig'))
 for p in patches:
  if runtime.count(p['old'])!=p.get('count',1):raise ValueError((v,p['label'],runtime.count(p['old'])))
  runtime=runtime.replace(p['old'],p['new'],p.get('count',1))
 runtime=runtime.replace('@CONSUMER_RUNTIME@',rtpatch)
 file=PROD/('single_remote_'+v+'_runtime.lua');file.write_text(runtime,encoding='utf-8',newline='\n')
 stage=OUT/(v+'-source');stage.mkdir(exist_ok=True);(stage/'physbone_runtime.lua').write_bytes(file.read_bytes());(stage/'physbone_compat.lua').write_bytes((PROD/'single_remote_compat.lua').read_bytes())
 sources.append(dict(variant=v,runtimeVersion=versions[v],compatVersion='1.3.11',policy=old['policy'],runtimePath=str(file),runtimeSha256=sha(file),compatSha256=sha(PROD/'single_remote_compat.lua')))
manifest={**previous,'sources':sources,'consumerRevision':'single-exact-consumers-v1','consumerProof':'streamed SHA256 of winning Unit/GPU/stream; nonmesh and full bind verified; unknown/mismatch full fallback','consumerModels':models,'consumerProfiles':len(rows),'consumerDistinctResources':len({r['resource']for r in rows}),'consumerCatalogSha256':sha(PROD/'single_consumer_catalog.json')}
manifest['templateSha256']={**previous['templateSha256'],'consumerCompat':sha(PROD/'single_consumers_compat.lua.in'),'consumerRuntime':sha(PROD/'single_consumers_runtime.lua.in'),'consumerSha256':sha(PROD/'single_consumer_sha256.lua.in'),'consumerProducer':sha(ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs'),'consumerRuntimeRecipe':sha(OUT/'runtime-edits.json')}
(PROD/'single_remote_release_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(OUT/'source-build.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'FORMAL_A_B_CONSUMER_SOURCES','sources':sources,'catalogSha256':manifest['consumerCatalogSha256']},ensure_ascii=False),flush=True)
