"""Build isolated loadable A/B successors; keep all solver/evidence bytes intact."""
from pathlib import Path
import hashlib,json,sys
from physics_consumer_lua_catalog import emit_catalog
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/physics-single-loader-size-fix-20261117'
PROD=ROOT/'HD2PhysBoneCompat/src/production'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
catalogPath=PROD/'single_consumer_catalog.json'
catalog=json.loads(catalogPath.read_text('utf-8-sig'))
base=(OUT/'before/HD2PhysBoneCompat/src/production/single_remote_compat.lua').read_text('utf-8-sig')
marker='-- Streaming SHA-256. Bounded verification work; no shell/helper process.'
assert base.count(marker)==1
prefix=base[:base.index(marker)]
assert prefix.count('M.version = "1.3.12"')==1
prefix=prefix.replace('M.version = "1.3.12"','M.version = "1.3.13"',1)
embedded,stats=emit_catalog(catalog)
template=(PROD/'single_consumers_compat.lua.in').read_text('utf-8-sig')
assert template.count('@CATALOG@')==1
compat=prefix+(PROD/'single_consumer_sha256.lua.in').read_text('utf-8-sig')+'\n'+template.replace('@CATALOG@',embedded)+'\nreturn M\n'
# Fail before changing production sources; final aggregated resource checked by exporter.
assert len(compat.encode('utf-8'))+8<4*1024*1024
(PROD/'single_remote_compat.lua').write_text(compat,encoding='utf-8',newline='\n')
sources=[]
for v,old,new in [('A','2.3.17','2.3.19'),('B','2.3.18','2.3.20')]:
 p=PROD/('single_remote_'+v+'_runtime.lua')
 rt=(OUT/'before/HD2PhysBoneCompat/src/production'/p.name).read_text('utf-8-sig')
 assert rt.count('M.VERSION = "'+old+'"')==1
 rt=rt.replace('M.VERSION = "'+old+'"','M.VERSION = "'+new+'"',1)
 p.write_text(rt,encoding='utf-8',newline='\n')
 stage=OUT/(v+'-source');stage.mkdir(exist_ok=True)
 (stage/'physbone_runtime.lua').write_bytes(p.read_bytes())
 (stage/'physbone_compat.lua').write_bytes((PROD/'single_remote_compat.lua').read_bytes())
 sources.append(dict(variant=v,runtimeVersion=new,compatVersion='1.3.13',policy='self-only'if v=='A'else'remote-no-vrd',runtimePath=str(p),runtimeSha256=sha(p),compatSha256=sha(PROD/'single_remote_compat.lua')))
m=json.loads((OUT/'before/HD2PhysBoneCompat/src/production/single_remote_release_manifest.json').read_text('utf-8-sig'))
m.update(sources=sources,realGameAcceptanceStatus='loader-size-candidate-pending-physics-and-FPS',supersedesRejectedVersions=['2.3.15','2.3.16','2.3.17','2.3.18'],catalogEncoding='interned-base64-once-v1',catalogEncodingStats=stats,consumerCatalogSha256=sha(catalogPath),chefMaxLuaResourceBytes=4*1024*1024)
m['templateSha256'].update(consumerLoaderFixBuilder=sha(Path(__file__)),consumerCatalogEmitter=sha(ROOT/'tools/physics_consumer_lua_catalog.py'))
(PROD/'single_remote_release_manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'source-build.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status='LOADER_SIZE_FIX_CANDIDATES_NOT_GAME_ACCEPTED',compatBytes=len(compat.encode('utf-8')),encodingStats=stats,sources=sources),ensure_ascii=False,indent=2))
