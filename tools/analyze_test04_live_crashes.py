"""Read-only live test04 evidence collection; never changes game or library files."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from analyze_native_b12_crashes import parse_dump

ROOT = Path(__file__).resolve().parents[1]
ZONE = timezone(timedelta(hours=8))

def metadata(path, data):
    return {'path': str(path.resolve()), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'modifiedAsiaShanghai': datetime.fromtimestamp(path.stat().st_mtime, ZONE).isoformat()}

def collect(game, out):
    out.mkdir(parents=True, exist_ok=True)
    sources = []
    snapshots = {}
    for name in ('chef_loader.log', 'chef_loader_trace.txt', 'chef_loader_health.txt', 'chef_loader_settings.txt'):
        path = game / name
        if not path.exists():
            continue
        data = path.read_bytes()
        sources.append(metadata(path, data))
        (out / name).write_bytes(data)
        snapshots[name] = data.decode('utf-8', errors='replace').splitlines()
    sessions = []
    for n, line in enumerate(snapshots.get('chef_loader.log', []), 1):
        if '==== Chef Shared Loader' in line:
            sessions.append({'start': line[:8], 'startLine': n, 'events': [], 'uncleanPrevious': False, 'cleanShutdown': False})
        if not sessions:
            continue
        s = sessions[-1]
        if 'last launch ended without a clean shutdown' in line:
            s['uncleanPrevious'] = True
        if 'shutdown (clean)' in line:
            s['cleanShutdown'] = True
        if any(k in line for k in ('could not start', 'attachment_fix off', 'switched on', 'switched off', 'world ', 'shutdown (clean)', 'found ', 'last launch ended')):
            s['events'].append({'line': n, 'text': line[:2000]})
        s['lastLine'] = n
        s['lastTime'] = line[:8]
    # Loader rows have no calendar date. Bound to the most recent ten launches,
    # not all historical launches with a clock time after 16:00.
    sessions = sessions[-10:]
    dumps = []
    for path in sorted((game / 'dumps').glob('dump-2026-11-06-16.*.dmp')):
        r = parse_dump(path)
        r['modifiedAsiaShanghai'] = datetime.fromtimestamp(path.stat().st_mtime, ZONE).isoformat()
        registers=r['registers']
        delta=int(registers['rcx']['address'],16)-int(registers['rbx']['address'],16)
        r['parentMatrixEvidence']={'rcxMinusRbx':hex(delta),'matrixStride':64,
                                  'parentIndexFromAddress':delta//64,
                                  'faultReadMatchesRcxPlus16':int(r['exception']['parameters'][1],16)==int(registers['rcx']['address'],16)+16}
        # The timestamp in the filename is not the Lua failure timestamp; keep both.
        r['dumpNameTime'] = re.search(r'2026-11-06-(\d{2}\.\d{2}\.\d{2})', path.name).group(1).replace('.', ':')
        dumps.append(r)
    sites = {(r['exception'].get('module'), r['exception'].get('rva'), r['exception']['code']) for r in dumps}
    report = {'status': 'COLLECTED', 'capturedAsiaShanghai': datetime.now(ZONE).isoformat(),
              'sources': sources, 'sessions': sessions, 'dumps': dumps,
              'sameExceptionSite': len(sites) == 1, 'gameModified': False,
              'stackWarning': 'Module-address candidates only, not symbolized/unwound stack frames.'}
    (out / 'crash-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    excerpt = [f"SESSION {s['start']} previousUnclean={s['uncleanPrevious']} clean={s['cleanShutdown']}\n" + '\n'.join(f"L{e['line']}: {e['text']}" for e in s['events']) for s in sessions]
    (out / 'recent-loader-excerpt.log').write_text('\n\n'.join(excerpt)+'\n', encoding='utf-8')
    print(json.dumps({'sameExceptionSite': report['sameExceptionSite'], 'sessions': [dict(start=s['start'], last=s['lastTime'], clean=s['cleanShutdown'], mismatch=any('version_mismatch' in e['text'] for e in s['events'])) for s in sessions],
                      'dumps': [dict(file=Path(d['path']).name, exception=d['exception'], stackCandidates=d['stackAddressCandidates'][:3]) for d in dumps]}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-log-dir', type=Path, default=Path.home() / 'AppData/Roaming/Arrowhead/Helldivers2')
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/test04-live-crash-audit-20261106/evidence')
    args = parser.parse_args()
    collect(args.game_log_dir, args.output)
