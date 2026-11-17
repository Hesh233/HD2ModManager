"""Real loadCarriers inventory: TOC-only higher overrides cannot use an older mask.
Uses isolated copies of real Unit/GPU payloads and the actual exported Lua.
No library writes, runtime shell helpers, game or FPS inference.
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, struct, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
NORMAL = ROOT / 'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
ap = argparse.ArgumentParser()
ap.add_argument('--source', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
ap.add_argument('--vm', choices=['lua51', 'luajit21'], default='luajit21')
a = ap.parse_args()
a.source = a.source.resolve()
OUT = a.output.resolve()
assert OUT.is_relative_to(ROOT) and not OUT.is_relative_to(NORMAL)
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT/'outputs/fp-physics-consumer-analysis-20261117'))
from analysis_common import make, units
os.environ['APPDATA']=str(OUT);os.environ['LOCALAPPDATA']=str(OUT)
folder = NORMAL/'test-library/[单骨架模型]test01/sectional'
models = units(folder/'9ba626afa44a3aa3.patch_0')
rid = next(iter(models))
rt = (a.source/'physbone_runtime.lua').read_text('utf-8-sig')
compat = (a.source/'physbone_compat.lua').read_text('utf-8-sig')
start = rt.index('local function loadCarriers(')
stop = rt.index('\n-- ---------------------------------------------------------------------------', start)
load_code = rt[start:stop] + '\nreturn loadCarriers'
checks, rows = 0, []
def check(ok, message):
    global checks
    checks += 1
    if not ok: raise AssertionError(message)
for case in ['healthy', 'higher_toc_only', 'orphan_gpu']:
    work = OUT/case
    data = work/'data'
    data.mkdir(parents=True, exist_ok=True)
    for index, domain in enumerate(['sectional', 'Overwrite']):
        src = folder.parent/domain/'9ba626afa44a3aa3.patch_0'
        dest = data/('9ba626afa44a3aa3.patch_'+str(index))
        for suffix in ['', '.gpu_resources', '.stream']:
            source, target = Path(str(src)+suffix), Path(str(dest)+suffix)
            if source.is_file(): shutil.copyfile(source, target)
            else: target.write_bytes(b'')
    if case == 'higher_toc_only':
        blob = bytearray((data/'9ba626afa44a3aa3.patch_1').read_bytes())
        nt, count = struct.unpack_from('<II', blob, 4)
        for i in range(count):
            t = struct.unpack_from('<QQQQQQQIIIIII', blob, 72+32*nt+i*80)
            if t[1] == 0xe0a48d0be9a7453f and f'{t[0]:016x}' == rid:
                blob[t[2]+t[7]-1] ^= 1
                break
        else: raise AssertionError('Real winning Unit not found')
        (data/'9ba626afa44a3aa3.patch_2').write_bytes(blob)
    elif case == 'orphan_gpu':
        shutil.copyfile(data/'9ba626afa44a3aa3.patch_1.gpu_resources', data/'9ba626afa44a3aa3.patch_2.gpu_resources')
    os.chdir(work)
    x = make(a.vm, models[rid], rid, folder, compat)
    C, lua, session = x['C'], x['lua'], x['session']
    lua.globals().Compat = C
    load = lua.execute(load_code)
    cache = lua.table()
    carriers = load(x['engine'][0], cache, lua.table(), lua.eval('function()end'))
    check(len(carriers) > 0, 'Real disk scan did not load a physics carrier')
    files = cache.consumerFiles
    ctx = C.consumer_api.new(files, None)
    before = (len(session.sessions), len(session.drivers))
    C.consumer_api.bind(ctx, session)
    for frame in range(1, 200001):
        C.begin_frame(frame)
        C.consumer_api.tick(ctx, 8192)
        if session.consumerPending: C.consumer_api.bind(ctx, session)
        if not session.consumerPending: break
    else: raise AssertionError('Real inventory proof did not terminate')
    row = dict(case=case, files=len(files), mode=session.consumerMode, reason=session.consumerReason, proofCallbacks=frame)
    print(json.dumps(row), flush=True)
    if case == 'healthy':
        check(session.consumerMode == 'active' and len(session.sessions) == 5, 'Healthy exact payload did not activate its head closure')
        check(len(files) == 2, 'Healthy inventory aliases were duplicated')
    else:
        check(session.consumerMode is None and (len(session.sessions), len(session.drivers)) == before, 'Higher/incomplete inventory incorrectly used an older consumer mask: '+case)
        check(len(files) == 3, 'TOC-only/orphan patch is missing from the proof inventory: '+case)
    C.consumer_api.close(ctx)
    check(all(j.handle is None for j in ctx.jobs.values()), 'Proof left an open file handle')
    rows.append(row)
result = dict(status='PASS_REAL_LOADER_CONSUMER_INVENTORY_NOT_FPS', vm=a.vm, checks=checks, cases=rows,
              runtimeSha256=hashlib.sha256((a.source/'physbone_runtime.lua').read_bytes()).hexdigest(),
              compatSha256=hashlib.sha256((a.source/'physbone_compat.lua').read_bytes()).hexdigest(), actualGameFps=False)
(OUT/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result), flush=True)
