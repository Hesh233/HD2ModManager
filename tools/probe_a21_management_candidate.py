"""Real-model five-phase A21 probes using unchanged A19 harness; write-once outputs."""
from pathlib import Path
import argparse, sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import replace_once
LAB=ROOT/'outputs/physics-A21-management-candidate-20261117'
ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['baseline','candidate','actual'],required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
s=(ROOT/'tools/analyze_a19_hotpath_candidates.py').read_text('utf-8-sig')
s=replace_once(s,'from pathlib import Path','from pathlib import Path\nfrom build_a21_management_candidate import build_runtime')
s=replace_once(s,'changed = candidate(original, a.variant)',"changed = original if a.variant == 'baseline' else build_runtime(original)")
s=s.replace('experimentalDispatch','activeDispatch')
s=replace_once(s,"record = [int(u.id), name, [env['py'](v) for v in values]]", "record = [int(env['state'].frame), int(u.id), name, [env['py'](v) for v in values]]\n            global_trace.update(json.dumps(record, sort_keys=True, separators=(',', ':')).encode())")
s=replace_once(s,'tracing = False\n\n    def trace_write', 'tracing = False\n    global_trace = hashlib.sha256()\n\n    def trace_write')
s=replace_once(s,'nonlocal tracing\n', 'nonlocal tracing, global_trace\n')
s=replace_once(s,"env['updates'].clear(); env['writes'].clear(); traces.clear()", "env['updates'].clear(); env['writes'].clear(); traces.clear(); global_trace = hashlib.sha256()")
s=replace_once(s,'instructionSamples=int(lua.globals().instructionSamples),', 'globalCallbackWriteTraceSha256=global_trace.hexdigest(),\n            instructionSamples=int(lua.globals().instructionSamples),')
s=replace_once(s,'sessions = list(state.sessions.values())', '''if a.variant == 'active-dispatch':
            check_projection = lua.eval("""function(s)
                local b=s.projectionBuffers; local p=s.projectionSlot
                assert(b and p and s.projectionScratch)
                for _,map in pairs(s.projectionScratch) do assert(next(map)==nil) end
                for _,map in pairs(b[3-p]) do assert(next(map)==nil) end
                assert(s.wrappers==b[p].wrappers)
                for source,view in pairs(s.wrappers) do
                    assert(view.source==source and getmetatable(view).__index==source)
                end
                return true
            end""")
            check(check_projection(state.singleState), label+': projection identity/empty retired buffers')
        sessions = list(state.sessions.values())''')
s=replace_once(s,"label+': full ledger and dispatch field cleared')", "label+': full ledger and dispatch field cleared')\n            check(state.singleState is None or (state.singleState.projectionBuffers is None and state.singleState.projectionScratch is None),label+': projection pool detached on terminal path')")
s=replace_once(s,"check(state.activeDispatch is None, 'uninstall clears dispatch even while fixture retains runtime state')", "check(state.activeDispatch is None, 'uninstall clears dispatch even while fixture retains runtime state')\n        check(state.singleState is None, 'uninstall releases projection pool with singleState')")
s=s.replace("writeTraceScope='Per-Unit successful setter sequence/node/value within each sample window only; excludes callback timing, cross-Unit ordering and transition/release/uninstall equivalence'", "writeTraceScope='Successful setters include runtime callback frame/Unit/order/node/value within each sample window; transition/release/uninstall writes excluded'")
if a.mode=='actual':
    old="LAB/'release-candidate/A-extracted/physbone_runtime.lua'"
    s=s.replace(old,"ROOT/'outputs/physics-A21-management-candidate-20261117/release-candidate/A-extracted/physbone_runtime.lua'")
    s=replace_once(s,"assert original == (PROD/'single_remote_A_runtime.lua').read_text('utf-8-sig')", "assert original == (ROOT/'outputs/physics-A21-management-candidate-20261117/A-source/physbone_runtime.lua').read_text('utf-8-sig')")
    s=replace_once(s,"changed = original if a.variant == 'baseline' else build_runtime(original)",'changed = original')
    s=s.replace("LAB/'release-candidate/A-extracted'", "ROOT/'outputs/physics-A21-management-candidate-20261117/release-candidate/A-extracted'")
    s=s.replace("LAB/'release-candidate/A-export/physics-runtime.zip'", "ROOT/'outputs/physics-A21-management-candidate-20261117/release-candidate/A-export/physics-runtime.zip'")
    s=s.replace("candidateSourceSubstitutedAfterParser=a.variant!='baseline'",'candidateSourceSubstitutedAfterParser=False')
    s=s.replace('notCandidatePackageValidation=True','notCandidatePackageValidation=False')
    s=s.replace("'sourceSubstitutionAfterParser': a.variant != 'baseline'", "'sourceSubstitutionAfterParser': False")
    s=s.replace("'notCandidatePackageValidation': True", "'notCandidatePackageValidation': False")
    s=s.replace('PASS_ISOLATED_HOTPATH_NOT_RELEASE_NOT_FPS','PASS_ACTUAL_A21_ZIP_CHEF_HOTPATH_NOT_GAME_FPS')
    s=s.replace('acceptedZipSha256=', 'actualCandidateZipSha256=')
    s=s.replace('actualChefParserForBaseline=True', 'actualChefParserForBaseline=False, actualChefParserForCandidate=True')
    s=s.replace('acceptedParsedSourceSha256','parsedCandidateSourceSha256')
argv=['probe-a21', '--variant', 'baseline' if a.mode=='baseline' else 'active-dispatch','--output',str(a.output)]
# The snapshot is persisted by the runner itself with this wrapper's source hash.
sys.argv=argv
scope={'__file__':str(Path(__file__)), '__name__':'__main__'}
exec(compile(s,str(Path(__file__)),'exec'),scope)
