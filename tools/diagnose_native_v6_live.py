"""Read-only deployed patch/log inspection; writes evidence only in workspace."""
import collections, hashlib, json, os, re, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID, ANIMATION_TYPE_ID, STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData
W = ROOT / 'outputs/native-v6-analysis-20261104'
W.mkdir(exist_ok=True)
P = ROOT / 'outputs/native-v6-20261104/project'
settings = json.loads((ROOT/'outputs/native-manual-20261103/test/settings.json').read_text(encoding='utf-8-sig'))
data = Path(settings['GameDataFolder']); lib = Path(settings['ModLibraryFolder'])
manifest = json.loads((P/'source-skeleton.json').read_text(encoding='utf-8'))
profile = json.loads((P/'attachment-profile.json').read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def entries(p):
    with p.open('rb') as f:
        h=f.read(72); nt,n=struct.unpack_from('<II',h,4); f.seek(72+32*nt)
        rows=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
    return rows
def payload(p,r):
    with p.open('rb') as f: f.seek(r[2]); return f.read(r[7])
types={UNIT_TYPE_ID:'Unit',BONE_TYPE_ID:'Bones',ANIMATION_TYPE_ID:'Animation',STATE_MACHINE_TYPE_ID:'StateMachine',0xa14e8dfa2cd117e2:'Lua'}
known=collections.defaultdict(list)
for base in [P,lib]:
    for p in base.rglob('*.patch_*'):
        if p.is_file(): known[(p.stat().st_size,sha(p))].append(str(p))
allrows={}; reports=[]; lua_files=[]
for p in sorted(data.glob('*.patch_*'),key=lambda p:(int(p.name.split('.patch_')[1].split('.')[0]),p.name)):
    digest=sha(p); item={'file':p.name,'size':p.stat().st_size,'sha256':digest,'matches':known.get((p.stat().st_size,digest),[])}
    if not p.name.rsplit('.',1)[-1].startswith('patch_'): reports.append(item); continue
    rows=entries(p); allrows[p.name]=rows
    item['types']=dict(collections.Counter(types.get(r[1],f'{r[1]:016x}') for r in rows))
    item['units']=[]
    for r in rows:
        if r[1]==UNIT_TYPE_ID:
            try:
                u=UnitData.parse(payload(p,r)); item['units'].append({'id':f'{r[0]:016x}','nodes':len(u.transforms),'sourceNames':sum(b['hash'] in u.name_hashes for b in manifest['bones']), 'sourceIndices':{str(b['sourceIndex']):u.name_hashes.index(b['hash']) for b in manifest['bones'] if b['hash'] in u.name_hashes},'hashes':u.name_hashes,'parents':u.parents})
            except Exception as e: item['units'].append({'id':f'{r[0]:016x}','error':str(e)})
        if r[1]==BONE_TYPE_ID:
            b=BonesData.parse(payload(p,r));item['bones']={'count':len(b.names),'names':b.names,'hashes':b.hashes}
        if types.get(r[1])=='Lua':
            raw=payload(p,r);out=W/(p.name+f'_{r[0]:016x}.lua-payload');out.write_bytes(raw)
            start=raw.find(b'--'); source=raw[start:] if start>=0 else raw
            lua_files.append({'patch':p.name,'id':f'{r[0]:016x}','sha256':hashlib.sha256(raw).hexdigest(),'file':str(out)})
    reports.append(item)
focus={(r[0],r[1]) for name,rows in allrows.items() if name.endswith('patch_9') for r in rows}
focus.update((int(t,16),UNIT_TYPE_ID) for ts in profile['targets'].values() for t in ts)
overlap=[]
for key in focus:
    found=[name for name,rows in allrows.items() if any((r[0],r[1])==key for r in rows)]
    if len(found)>1: overlap.append({'id':f'{key[0]:016x}','type':types.get(key[1],str(key[1])),'patches':found})
logs=Path(os.environ['APPDATA'])/'Arrowhead/Helldivers2'
log_text=(logs/'hd2physbone.log').read_text(encoding='utf-8-sig',errors='replace')
session_start=log_text.rfind('[physbone] 运行时 2.1.2 已安装')
session=log_text[session_start:]
interesting=[x for x in session.splitlines() if '[attachments]' in x or 'IDENTITY' in x or '绑定' in x and '心跳' not in x]
(W/'latest-runtime-evidence.txt').write_text('\n'.join(interesting),encoding='utf-8')
for name in ['chef_loader_health.txt','chef_loader_trace.txt']:
    (W/name).write_bytes((logs/name).read_bytes())
chef=(logs/'chef_loader.log').read_text(encoding='utf-8-sig');chef=chef[chef.rfind('==== Chef Shared Loader'):]
(W/'latest-chef-session.txt').write_text(chef,encoding='utf-8')
library=json.loads((lib/'library.json').read_text(encoding='utf-8-sig'))
report={'gameData':str(data),'settings':settings,'files':reports,'lua':lua_files,'overlaps':overlap,
        'targets':profile['targets'],'latestSession':{'attachmentLines':[x for x in session.splitlines() if '[attachments]' in x], 'readbackLines':session.count('回读 position_error'), 'activeNonzero':bool(re.search(r'\[attachments\] active=[1-9]',session))},
        'library':[{'id':k,'path':v['relativePath'],'name':v['metadata']['name']} for k,v in library['nodes'].items()]}
(W/'deployment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'gameData':report['gameData'],'files':[{'file':r['file'],'matches':r['matches'],'types':r.get('types'),'unitCounts':dict(collections.Counter(u.get('nodes') for u in r.get('units',[])))} for r in reports if '.gpu_' not in r['file'] and not r['file'].endswith('.stream')], 'overlaps':overlap,'latestSession':report['latestSession'],'targets':profile['targets']},ensure_ascii=False,indent=2))
