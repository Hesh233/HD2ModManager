"""Animation block inspection and lossless removal of constant float tracks."""
from dataclasses import dataclass
import struct


@dataclass
class AnimationBlock:
    header: bytes
    flags: list[bool]
    states: list[bytes]
    hash_floats: bytes
    entries: list[tuple[float, int | None, bytes]]
    end: int


def read_block(data, start=0):
    _, count, _, _, h1, h2 = struct.unpack_from('<IIfIII', data, start)
    offset = start + 24 + 8 * (h1 + h2) + 2
    header = bytes(data[start:offset])
    flag_size = ((3 * count + 7) // 8 + 1) // 2 * 2
    raw_flags = data[offset:offset + flag_size]
    flags = [bool(raw_flags[i // 8] & (1 << (i % 8))) for i in range(count * 3)]
    offset += flag_size
    states = []
    for i in range(count):
        size = sum((4 if j == 1 else 6) if flags[3*i+j] else (16 if j == 1 else 12) for j in range(3))
        states.append(bytes(data[offset:offset+size])); offset += size
    hash_floats = bytes(data[offset:offset+4*h1]); offset += 4*h1
    entries = []
    while True:
        entry_start = offset
        word = struct.unpack_from('<H', data, offset)[0]
        kind = word >> 14
        if kind:
            bone = (word >> 4) & 0x3ff
            time = ((word & 15) << 16) | struct.unpack_from('<H', data, offset+2)[0]
            offset += 8 if kind == 3 else 10
        else:
            if word == 3:
                offset += 2
                break
            if word not in (2, 4, 5, 6):
                raise ValueError(f'Unknown animation entry subtype {word}')
            bone, seconds = struct.unpack_from('<If', data, offset+2)
            time = seconds * 1000
            # Events carry a hash here, not a channel index.
            if word == 2: bone = None
            offset += 10 + (16 if word == 5 else 12 if word in (4, 6) else 0)
        if offset > len(data): raise ValueError('Truncated animation entry')
        entries.append((time, bone, bytes(data[entry_start:offset])))
    return AnimationBlock(header, flags, states, hash_floats, entries, offset)


def read_blocks(data):
    first = read_block(data)
    second = read_block(data, first.end + 4)
    if second.end + 4 != len(data): raise ValueError('Unexpected animation trailer')
    if struct.unpack_from('<I', data, first.end)[0] != first.end:
        raise ValueError('Invalid first animation block size')
    if struct.unpack_from('<I', data, second.end)[0] != second.end-first.end-4:
        raise ValueError('Invalid second animation block size')
    return first, second


def preserve_driver_channels(original, extended):
    """Retired: mixed compressed/float streams cause native armor animation stalls."""
    raise ValueError('Mixed driver streams are unsupported; rebuild with native-project (unified float sampling)')


def compact_constant_tracks(data):
    """A constant component needs only its initial state, never thousands of repeated keys.

    Compare serialized float values exactly. This removes no motion and retains
    synchronized times for every component that actually changes.
    """
    from .formats import AnimationData
    animation = AnimationData.parse(data)
    varying = set()
    def component(entry):
        return 0 if entry.is_position else 1 if entry.is_rotation else 2 if entry.is_scale else None
    for entry in animation.entries:
        kind=component(entry)
        if kind is None: continue
        state=animation.initial_bone_states[entry.bone]
        base=(state.position,state.rotation,state.scale)[kind]
        if entry.data2!=base and not (kind==1 and entry.data2==[-v for v in base]):
            varying.add((entry.bone,kind))
    count=len(animation.entries)
    animation.entries=[e for e in animation.entries if component(e) is None or (e.bone,component(e)) in varying]
    return animation.to_bytes(),count-len(animation.entries)

