"""Build isolated correction candidates; no game/library/normal Core writes."""
from pathlib import Path
import base64,hashlib,json,math,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/physics-single-consumers-ship-11fps-20261117';PROD=ROOT/'HD2PhysBoneCompat/src/production';NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def byte_literal(data):return '"'+''.join('\\'+format(b,'03d')for b in data)+'"'
def lua(v):
 if v is None:return 'nil'
 if v is True:return 'true'
 if v is False:return 'false'
 if isinstance(v,(float,int)):
  assert math.isfinite(v);return repr(v)
 if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
 if isinstance(v,list):return '{'+','.join(lua(x)for x in v)+'}'
 if isinstance(v,dict):
  fields=[]
  for key,value in sorted(v.items()):
   if key.endswith('ExactBase64'):
    fields.append('['+lua(key[:-6])+']='+byte_literal(base64.b64decode(value,validate=True)))
   else:fields.append('['+lua(key)+']='+lua(value))
  return '{'+','.join(fields)+'}'
 raise TypeError(type(v))
models=[];units=[];rejected=[];seen={}
for key,name in [('test01','[单骨架模型]test01'),('cow','[单骨架模型]Cow_QiPao_Milltina_Nick'),('test13','[单骨架模型]test13'),('test15','[单骨架模型]test15')]:
 facts=OUT/(key+'-facts.json')
 subprocess.run(['dotnet',str(OUT/'producer/PhysicsConsumerAudit.dll'),str(NORMAL/'test-library'/name),str(facts)],check=True)
 data=json.loads(facts.read_text('utf-8-sig'))
 assert data['revision']=='single-toc-palette-consumers-v2'
 models.append({k:data[k]for k in ['modelName','rigSha256','driverRigSha256','configSha256','bindSha256','rigExactBase64','driverExactBase64']})
 for row in data['units']:
  row={k:v for k,v in row.items()if k not in ['domain','sourcePatch']};row.update(model=name,rigSha256=data['rigSha256'],driverRigSha256=data['driverRigSha256'])
  assert set(row['weightedNodes'])<=set(row['skinPaletteNodes'])
  assert hashlib.sha256(base64.b64decode(row['tocExactBase64'],validate=True)).hexdigest()==row['tocSha256']
  k=(name,row['resource'],row['tocSha256'],row['gpuSha256'],row['streamSha256'])
  if k in seen:assert seen[k]==row;continue
  seen[k]=row;units.append(row)
 rejected.extend(dict(x,model=name)for x in data['rejected'])
catalog=dict(schema='hd2-physics-consumers/2',revision='single-toc-palette-consumers-v2',proofMode='toc-exact-palette-v2',models=models,units=units,unknownOrMismatch='full-original-solver',notVisibilityBased=True,allLegalGpuPaletteConsumersPreserved=True)
blob=(json.dumps(catalog,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8');(OUT/'consumer-catalog.json').write_bytes(blob);(PROD/'single_consumer_catalog.json').write_bytes(blob)
(OUT/'consumer-rejected.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
base=(OUT/'before-source/single_remote_compat.lua').read_text('utf-8-sig');marker='-- Streaming SHA-256. Bounded verification work; no shell/helper process.';assert base.count(marker)==1
prefix=base[:base.index(marker)];assert prefix.count('M.version = "1.3.11"')==1;prefix=prefix.replace('M.version = "1.3.11"','M.version = "1.3.12"',1)
hashCode=(PROD/'single_consumer_sha256.lua.in').read_text('utf-8-sig');tpl=(PROD/'single_consumers_compat.lua.in').read_text('utf-8-sig');assert tpl.count('@CATALOG@')==1
compat=prefix+hashCode+'\n'+tpl.replace('@CATALOG@',lua(catalog))+'\nreturn M\n';(PROD/'single_remote_compat.lua').write_text(compat,encoding='utf-8',newline='\n')
rtTemplate=(PROD/'single_consumers_runtime.lua.in').read_text('utf-8-sig');sources=[]
for variant,oldVersion,version in [('A','2.3.15','2.3.17'),('B','2.3.16','2.3.18')]:
 rt=(OUT/'before-source'/('single_remote_'+variant+'_runtime.lua')).read_text('utf-8-sig')
 old=(OUT/'before-source/single_consumers_runtime.lua.in').read_text('utf-8-sig');assert rt.count(old)==1;rt=rt.replace(old,rtTemplate,1)
 assert rt.count('pcall(Compat.single_scene_policy_transition,')==1;rt=rt.replace('pcall(Compat.single_scene_policy_transition,','pcall(Compat.single_remote_policy_transition,',1)
 assert rt.count('M.VERSION = "'+oldVersion+'"')==1;rt=rt.replace('M.VERSION = "'+oldVersion+'"','M.VERSION = "'+version+'"',1)
 source=PROD/('single_remote_'+variant+'_runtime.lua');source.write_text(rt,encoding='utf-8',newline='\n');stage=OUT/(variant+'-source');stage.mkdir(exist_ok=True);(stage/'physbone_runtime.lua').write_bytes(source.read_bytes());(stage/'physbone_compat.lua').write_bytes((PROD/'single_remote_compat.lua').read_bytes())
 sources.append(dict(variant=variant,runtimeVersion=version,compatVersion='1.3.12',policy='self-only'if variant=='A'else'remote-no-vrd',runtimePath=str(source),runtimeSha256=sha(source),compatSha256=sha(PROD/'single_remote_compat.lua')))
old=json.loads((OUT/'before-source/single_remote_release_manifest.json').read_text('utf-8-sig'))
metadata={**old,'sources':sources,'consumerRevision':catalog['revision'],'consumerProof':'complete winning TOC exact bytes + ALL TOC skin palette upper bound; raw rig/driver exact; sidecar range; no render SHA','consumerModels':[{k:m[k]for k in ['modelName','rigSha256','driverRigSha256','configSha256','bindSha256']}for m in models],'consumerProfiles':len(units),'consumerDistinctResources':len({p['resource']for p in units}),'consumerCatalogSha256':sha(PROD/'single_consumer_catalog.json'),'realGameAcceptanceStatus':'correction-candidate-pending-ship-FPS','supersedesRejectedVersions':['2.3.15','2.3.16'],'renderGpuHashing':False}
metadata['templateSha256']={**old['templateSha256'],'policy':sha(PROD/'single_remote_policy.lua.in'),'consumerCompat':sha(PROD/'single_consumers_compat.lua.in'),'consumerRuntime':sha(PROD/'single_consumers_runtime.lua.in'),'consumerSha256':sha(PROD/'single_consumer_sha256.lua.in'),'consumerProducer':sha(ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs'),'consumerFixBuilder':sha(Path(__file__))};metadata['templateSha256'].pop('consumerRuntimeRecipe',None)
(PROD/'single_remote_release_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(OUT/'source-build.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='CORRECTION_CANDIDATE_SOURCES_NOT_GAME_ACCEPTED',sources=sources,profiles=len(units),resources=metadata['consumerDistinctResources'],compatBytes=len(compat.encode('utf-8'))),ensure_ascii=False,indent=2))
