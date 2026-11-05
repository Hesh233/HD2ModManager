"""Preserve the latest complete B21 game session without changing game logs."""
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from package_native_v12 import ROOT, save_json, digest


def main():
    source = Path(os.environ['APPDATA']) / 'Arrowhead/Helldivers2/hd2_native_grip_capture.log'
    before = source.stat()
    sessions, offset, count = [], 0, 0
    h = hashlib.sha256()
    with source.open('rb') as stream:
        for count, line in enumerate(stream, 1):
            h.update(line)
            if b'[native_capture] ' in line:
                prefix, body = line.split(b'[native_capture] ', 1)
                if b'"event":"loaded"' in body:
                    if sessions:
                        sessions[-1]['endByte'] = offset
                        sessions[-1]['endLine'] = count - 1
                    sessions.append(dict(startByte=offset, startLine=count,
                        started=prefix.decode('utf-8').strip(), loaded=json.loads(body)))
                elif b'"event":"complete"' in body and sessions:
                    sessions[-1].update(completed=prefix.decode('utf-8').strip(), complete=json.loads(body))
            offset += len(line)
    assert sessions, 'No B21 loaded event in log'
    sessions[-1].update(endByte=offset, endLine=count)
    selected = sessions[-1]
    assert selected.get('complete', {}).get('reason') == 'shutdown', 'Latest game capture has not shut down cleanly'
    stamp = datetime.strptime(selected['started'], '%Y-%m-%d %H:%M:%S').strftime('%Y%m%d-%H%M%S')
    output = ROOT / 'outputs/native-b21-observation-20261105' / stamp
    output.mkdir(parents=True, exist_ok=True)
    captured = output / 'native-grip-latest.log'
    with source.open('rb') as stream, captured.open('wb') as target:
        stream.seek(selected['startByte'])
        shutil.copyfileobj(stream, target)
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'Game log changed during snapshot'
    assert captured.stat().st_size == selected['endByte'] - selected['startByte']

    units, events, diagnostics = {}, Counter(), []
    with captured.open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            prefix, body = line.split('[native_capture] ', 1)
            row = json.loads(body)
            event = row['event']
            events[event] += 1
            if event == 'unit':
                key = (row['world'], row['id'], row['resource'], row['layout'])
                item = units.setdefault(key, dict(
                    world=row['world'], id=row['id'], resource=row['resource'], kind=row['kind'], layout=row['layout'],
                    nodeCount=row['nodeCount'], phases=Counter(), firstSample=row['sample'], lastSample=row['sample'],
                    firstTime=row['time'], lastTime=row['time'], firstLogTime=prefix.strip(), lastLogTime=prefix.strip(),
                    firstLine=number, lastLine=number, visibility=Counter(),
                    handNodes=[dict(name=n['name'], index=n['index'], skinInput=n['skinInput']) for n in row['nodes']
                               if 'hand' in n['name'] or n['name'].startswith('IK_')]))
                item['phases'][row['phase']] += 1
                item['visibility'][str(row['visibility'])] += 1
                item.update(lastSample=row['sample'], lastTime=row['time'], lastLogTime=prefix.strip(), lastLine=number)
            elif event in ('unavailable', 'callback_error', 'incomplete_pair') or (
                event == 'scan' and (row.get('errors', 0) or row.get('truncated', 0))):
                diagnostics.append(dict(line=number, timestamp=prefix.strip(), event=row))
    assert events['loaded'] == events['complete'] == 1
    assert events['phase_begin'] == events['phase_end'] == selected['complete']['samples'] * 2

    chef_path = source.with_name('chef_loader.log')
    chef_bytes = chef_path.read_bytes()
    (output / 'chef-loader-snapshot.log').write_bytes(chef_bytes)
    chef_lines = chef_bytes.decode('utf-8-sig').splitlines()
    starts = [i for i, line in enumerate(chef_lines) if '==== Chef Shared Loader' in line]
    chunks = [chef_lines[i:starts[n+1] if n+1 < len(starts) else len(chef_lines)] for n, i in enumerate(starts)]
    clock = selected['started'][11:]
    matches = [c for c in chunks if any(line.startswith(clock) and 'started mods/hd2modmanager/native_grip_capture' in line for line in c)]
    assert len(matches) == 1, 'Ambiguous Chef session association'
    chef = matches[0]
    assert any('shutdown (clean)' in line for line in chef)
    (output / 'chef-latest.log').write_text('\n'.join(chef) + '\n', encoding='utf-8')
    report = dict(status='CAPTURED', latestSessionOrdinal=len(sessions), totalSessions=len(sessions),
        source=str(source), sourceBytes=before.st_size, sourceSha256=h.hexdigest(),
        sourceModified=datetime.fromtimestamp(before.st_mtime, timezone(timedelta(hours=8))).isoformat(),
        sourceUnchangedDuringCopy=True, snapshot=str(captured), snapshotSha256=digest(captured),
        selected=selected, sessionIndex=sessions, eventCounts=dict(events), units=list(units.values()), diagnostics=diagnostics,
        chefSourceSha256=hashlib.sha256(chef_bytes).hexdigest(), chefCleanShutdown=True,
        chefStartedAddons=[line for line in chef if re.search(r' \| started mods/', line)],
        chefBootScripts=[line for line in chef if "running another mod's boot script" in line],
        chefWarnings=[line for line in chef if 'hang watchdog: on' not in line and any(
            s in line for s in ('blocked:', 'over its frame budget', 'switched off', 'failed', 'error:'))],
        gamePoseCaptured=True, gameLogWritten=False, previousSessionExcluded=True)
    save_json(output / 'snapshot-manifest.json', report)
    print(json.dumps(dict(output=str(output), selected=selected, eventCounts=dict(events),
        units=[{k: r[k] for k in ('world','id','resource','kind','layout','firstSample','lastSample')} for r in units.values()],
        diagnostics=len(diagnostics), chefWarnings=report['chefWarnings']), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
