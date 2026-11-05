"""Read only: collect bounded B12 log excerpts and minidump metadata."""
import hashlib
import json
import struct
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/native-v21-b13-20261104/evidence'
GAME = Path.home() / 'AppData/Roaming/Arrowhead/Helldivers2'
DUMPS = (
    'dump-2026-11-04-23.20.44-3eb35b73-DESKTOP-7PST9TE-17562.dmp',
    'dump-2026-11-04-23.21.38-a2ba8579-DESKTOP-7PST9TE-8797.dmp',
    'dump-2026-11-04-23.22.28-ab78cdcf-DESKTOP-7PST9TE-7187.dmp',
)


def metadata(path, data):
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                modified=datetime.fromtimestamp(path.stat().st_mtime).isoformat())


def parse_dump(path):
    data = path.read_bytes()
    def unpack(fmt, offset):
        return struct.unpack_from('<' + fmt, data, offset)
    assert data[:4] == b'MDMP'
    count, directory = unpack('II', 8)
    streams = {kind: (size, rva) for kind, size, rva in
               (unpack('III', directory + i * 12) for i in range(count))}
    modules = []
    _, rva = streams[4]
    for i in range(unpack('I', rva)[0]):
        base, size, checksum, timestamp, name = unpack('QIIII', rva + 4 + i * 108)
        length = unpack('I', name)[0]
        text = data[name + 4:name + 4 + length].decode('utf-16-le')
        modules.append(dict(base=base, size=size, name=text))
    def address(value):
        for module in modules:
            if module['base'] <= value < module['base'] + module['size']:
                return dict(address=hex(value), module=module['name'], rva=hex(value-module['base']))
        return dict(address=hex(value))
    _, exc = streams[6]
    tid = unpack('I', exc)[0]
    code, flags = unpack('II', exc + 8)
    exception_address = unpack('Q', exc + 24)[0]
    param_count = unpack('I', exc + 32)[0]
    params = list(unpack('Q' * min(param_count, 15), exc + 40))
    context_size, context = unpack('II', exc + 160)
    arch = unpack('H', streams[7][1])[0]
    registers = {}
    if arch == 9 and context_size >= 256:
        for name, offset in dict(rax=120, rcx=128, rdx=136, rbx=144, rsp=152,
                                 rbp=160, rsi=168, rdi=176, r8=184, r9=192, rip=248).items():
            registers[name] = address(unpack('Q', context+offset)[0])
    stack_candidates = []
    _, threads = streams[3]
    for i in range(unpack('I', threads)[0]):
        row = threads + 4 + i * 48
        if unpack('I', row)[0] != tid:
            continue
        stack_base, stack_size, stack_rva = unpack('QII', row+24)
        rsp = int(registers.get('rsp', {}).get('address', hex(stack_base)), 16)
        start = max(0, rsp-stack_base)
        for offset in range(start, min(start+1024, stack_size)-7, 8):
            item = address(unpack('Q', stack_rva+offset)[0])
            if 'module' in item:
                stack_candidates.append(dict(stackOffset=hex(offset-start), **item))
    return dict(**metadata(path, data), architecture=arch, thread=tid,
                exception=dict(code=hex(code), flags=hex(flags), **address(exception_address),
                               parameters=[hex(n) for n in params]),
                registers=registers, stackAddressCandidates=stack_candidates,
                stackNote='Address scan only; these are not unwound or symbolized frames.')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    provenance = []
    for name in ('hd2physbone.log', 'chef_loader.log'):
        path = GAME/name
        data = path.read_bytes()
        provenance.append(metadata(path, data))
        lines = []
        for line in data.decode('utf-8', errors='replace').splitlines():
            if not line.startswith('23:') or '[scene_probe]' in line:
                continue
            # Bounded latest sessions; avoid previous observers' large rows.
            if '23:20:' <= line[:6] <= '23:24:':
                lines.append(line[:5000])
        (OUT/name.replace('.log', '-excerpt.log')).write_text('\n'.join(lines)+'\n', encoding='utf-8')
    reports = [parse_dump(GAME/'dumps'/name) for name in DUMPS]
    report = dict(status='COLLECTED', sources=provenance, dumps=reports,
                  sameExceptionSite=len({(r['exception'].get('module'), r['exception'].get('rva'),
                                         r['exception']['code']) for r in reports}) == 1)
    (OUT/'crash-evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(sameExceptionSite=report['sameExceptionSite'],
                         dumps=[dict(name=Path(r['path']).name, exception=r['exception'],
                                     registers=r['registers'], stack=r['stackAddressCandidates'][:12]) for r in reports]),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
