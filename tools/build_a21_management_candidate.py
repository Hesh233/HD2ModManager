"""Build isolated A21 management-hotpath candidate. Never edit production or deploy."""
from pathlib import Path
import argparse, hashlib, json, sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import candidate as prior_candidate, replace_once, protected_files
OUT = ROOT / 'outputs/physics-A21-management-candidate-20261117'
PROD = ROOT / 'HD2PhysBoneCompat/src/production'

def build_runtime(original, projection=True):
    text = prior_candidate(original, 'active-dispatch')
    text = text.replace('experimentalDispatch', 'activeDispatch')
    text = text.replace('-- EXPERIMENT ONLY: rebuild after proof/policy/preview updates each callback.',
                        '-- Rebuild after proof/policy/preview updates EVERY callback; not an epoch cache.')
    if projection:
        text = replace_once(text, 'local function project(runtime, avatars)\n', '''local function clear_projection_table(t)
	for key in pairs(t) do t[key] = nil end
end

-- Only private projection storage is reused. Never reuse engine inventory,
-- source sessions, avatar clones, or wrapper identity across different owners.
function api.clear_projection(runtime)
	local single = runtime.singleState
	if single then
		single.projectionBuffers, single.projectionScratch, single.projectionSlot = nil, nil, nil
	end
end

local function project(runtime, avatars)
''')
        text = replace_once(text, '\tlocal current = {}\n\tfor _, avatar in ipairs(avatars or runtime.avatars or {})', '''	local scratch = single.projectionScratch
	if scratch == nil then
		scratch = { current = {}, seen = {}, present = {}, added = {} }
		single.projectionScratch = scratch
	end
	local buffers = single.projectionBuffers
	if buffers == nil then
		buffers = {
			{ owned = {}, wrappers = {}, sessions = {} },
			{ owned = {}, wrappers = {}, sessions = {} },
		}
		single.projectionBuffers = buffers
	end
	local slot = (single.projectionSlot or 0) % 2 + 1
	local nextBuffer, retired = buffers[slot], buffers[3 - slot]
	-- Clear the unpublished destination, never the source before reading it.
	clear_projection_table(nextBuffer.owned)
	clear_projection_table(nextBuffer.wrappers)
	clear_projection_table(nextBuffer.sessions)
	for _, map in pairs(scratch) do clear_projection_table(map) end
	local current = scratch.current
	for _, avatar in ipairs(avatars or runtime.avatars or {})''')
        text = replace_once(text, '\tlocal owned, seen = {}, {}\n', '\tlocal owned, seen = nextBuffer.owned, scratch.seen\n')
        text = replace_once(text, '\tlocal present, wrappers = {}, {}\n', '\tlocal present, wrappers = scratch.present, nextBuffer.wrappers\n')
        text = replace_once(text, '\tlocal sessions, added = {}, {}\n', '\tlocal sessions, added = nextBuffer.sessions, scratch.added\n')
        text = replace_once(text, '\tsingle.wrappers, single.sessions = wrappers, sessions\n\treturn single', '''	single.wrappers, single.sessions = wrappers, sessions
	single.projectionSlot = slot
	-- The retired output is no longer input. Empty it immediately so removal
	-- does not retain another generation of Unit/session references.
	clear_projection_table(retired.owned)
	clear_projection_table(retired.wrappers)
	clear_projection_table(retired.sessions)
	for _, map in pairs(scratch) do clear_projection_table(map) end
	return single''')
        # Same five terminal paths as the validated active-dispatch-r3 array.
        assert text.count('runtime.activeDispatch = nil') == 5
        text = text.replace('runtime.activeDispatch = nil', 'runtime.activeDispatch = nil; Single.clear_projection(runtime)')
    text = replace_once(text, 'M.VERSION = "2.3.19"', 'M.VERSION = "2.3.21"')
    return text

def main():
    assert not OUT.exists(), 'Evidence is write-once; use a new stage'
    OUT.mkdir()
    frozen = protected_files()
    (OUT/'protected-before.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2),encoding='utf-8')
    original = (PROD/'single_remote_A_runtime.lua').read_text('utf-8-sig')
    manifest = json.loads((PROD/'single_remote_release_manifest.json').read_text('utf-8-sig'))
    accepted = next(s for s in manifest['sources'] if s['variant']=='A')
    assert hashlib.sha256((PROD/'single_remote_A_runtime.lua').read_bytes()).hexdigest()==accepted['runtimeSha256']
    source = OUT/'A-source'; source.mkdir()
    (source/'physbone_runtime.lua').write_text(build_runtime(original),encoding='utf-8',newline='\n')
    (source/'physbone_compat.lua').write_bytes((PROD/'single_remote_compat.lua').read_bytes())
    assert hashlib.sha256((source/'physbone_compat.lua').read_bytes()).hexdigest()==accepted['compatSha256']
    candidate = json.loads(json.dumps(manifest))
    candidate['sources']=[dict(accepted, runtimeVersion='2.3.21', runtimePath=str(source/'physbone_runtime.lua'),
        runtimeSha256=hashlib.sha256((source/'physbone_runtime.lua').read_bytes()).hexdigest())]
    candidate['baselineFormalReleaseReference']=candidate.pop('formalRelease',None)
    candidate['compatPath']=str(source/'physbone_compat.lua')
    candidate['realGameAcceptanceStatus']='A21-ISOLATED-CANDIDATE-PENDING-PHYSICS-AND-FPS'
    candidate['acceptedFeedback']={'baselineOnly':manifest['acceptedFeedback'],
        'newUserWords':'根据线索，继续优化a包。可以确定的是，a包4名玩家时候使用chef关掉物理插件后，至少上升了15帧，达到不安装物理时的帧数。',
        'scope':'Reported four-player disable delta; no absolute FPS/frametime supplied; NOT A21 acceptance'}
    candidate['managerEmbeddedDefaultNotChanged']=True
    candidate['candidateChanges']=['active-only-dispatch-r3','empty-consumer-pre-alive-rejection','private-projection-double-buffer-and-scratch-reuse']
    candidate['unchanged']=['compat solver and full certificate/catalog bytes','local stride1','full lifecycle health/inventory checks','all-session peak scan','normal Core and config','accepted A19/B20','models/binds/profiles/animations','game deployment']
    candidate['templateSha256']['a21CandidateBuilder']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'candidate-manifest.json').write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'builder-snapshot.py').write_bytes(Path(__file__).read_bytes())
    assert protected_files()==frozen
    print('A21 isolated source ready; compat byte-identical; production untouched')

if __name__=='__main__': main()
