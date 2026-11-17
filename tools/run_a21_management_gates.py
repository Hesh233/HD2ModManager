"""A21 actual-ZIP regressions; narrow A-only adaptation of frozen 49-gate runner."""
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
from analyze_a19_hotpath_candidates import replace_once
LAB=ROOT/'outputs/physics-A21-management-candidate-20261117'
# Preserve and snapshot every adaptation; do not edit the established runners.
s=(ROOT/'tools/run_single_consumers_ship_fix_gates.py').read_text('utf-8-sig')
s=replace_once(s,"ROOT/'HD2PhysBoneCompat/src/production/single_remote_release_manifest.json'", "ROOT/'outputs/physics-A21-management-candidate-20261117/candidate-manifest.json'")
s=replace_once(s,"assert inputs['ACompat']==inputs['BCompat'];records=[]", "assert inputs['ACompat']=='3530bd37c701e1dea98affe1dfc30ff0716233813c011765249b57a6f821279b';records=[]")
s=replace_once(s,"for v in ['A','B']:","for v in ['A']:")
s=replace_once(s,'expected=49 if a.loader_size_fix else 47','expected=33 if a.loader_size_fix else 32')
(LAB/'a-only-gate-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['a21-gates','--evidence-root',str(LAB),'--loader-size-fix']
exec(compile(s,str(ROOT/'tools/run_single_consumers_ship_fix_gates.py'),'exec'),{'__file__':str(ROOT/'tools/run_single_consumers_ship_fix_gates.py'),'__name__':'a21_gates'})
# Actual aggregated addon installer/duplicate/uninstall checks, preserving original math guard.
s=(ROOT/'tools/verify_single_consumers_ship_fix.py').read_text('utf-8-sig')
s=replace_once(s,"PROD/'single_remote_release_manifest.json'", "ROOT/'outputs/physics-A21-management-candidate-20261117/candidate-manifest.json'")
s=s.replace("'loader-size-candidate-pending-physics-and-FPS'", "'A21-ISOLATED-CANDIDATE-PENDING-PHYSICS-AND-FPS'")
s=replace_once(s,"base=(LAB/('before/HD2PhysBoneCompat/src/production/single_remote_compat.lua'if a.loader_size_fix else'before-source/single_remote_compat.lua')).read_text('utf-8-sig')", "base=(PROD/'single_remote_compat.lua').read_text('utf-8-sig')")
s=s.replace('PASS_ACTUAL_LOADER_SIZE_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS','PASS_ACTUAL_A21_CANDIDATE_ZIP_NOT_GAME_PHYSICS_OR_FPS')
(LAB/'a-only-installer-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['a21-installers','--evidence-root',str(LAB),'--loader-size-fix']
exec(compile(s,str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'exec'),{'__file__':str(ROOT/'tools/verify_single_consumers_ship_fix.py'),'__name__':'a21_installers'})
# Encoding exactness, old oversized negative controls, exact inclusive 4MiB boundary.
s=(ROOT/'tools/test_single_consumer_loader_size.py').read_text('utf-8-sig')
(LAB/'size-runner-snapshot.py').write_text(s,encoding='utf-8')
sys.argv=['a21-size','--evidence-root',str(LAB)]
exec(compile(s,str(ROOT/'tools/test_single_consumer_loader_size.py'),'exec'),{'__file__':str(ROOT/'tools/test_single_consumer_loader_size.py'),'__name__':'a21_sizes'})
