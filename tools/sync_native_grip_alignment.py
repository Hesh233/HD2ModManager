"""Embed the opt-in grip experiment into the standalone attachment adapter."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sync():
    folder = ROOT / 'HD2PhysBoneCompat/src'
    path = folder / 'native_attachments.lua'
    source = path.read_text(encoding='utf-8-sig')
    begin = '-- BEGIN NATIVE GRIP ALIGNMENT\n'
    end = '-- END NATIVE GRIP ALIGNMENT\n'
    assert source.count(begin) == source.count(end) == 1
    start = source.index(begin)
    stop = source.index(end, start) + len(end)
    module = (folder / 'native_grip_alignment.lua').read_text(encoding='utf-8-sig')
    block = begin + 'local NativeGripAlignment=(function()\n' + module + '\nend)()\n' + end
    path.write_text(source[:start] + block + source[stop:], encoding='utf-8', newline='\n')


if __name__ == '__main__':
    sync()
