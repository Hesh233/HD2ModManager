"""Accepted single-R2 output compaction; never imported by the native/dual route.

Only serialized-exact constant position/rotation interior keys are removed.
Initial pose, two boundary frames at each end, track endpoints, every scale and
event record, and complete additive bytes remain untouched. No quantization,
tolerance, quaternion-sign folding, reordering or source-animation rebaking.
"""
import struct
import math
import hashlib
import collections

OUTPUT_ENCODING_PROFILE = 'single-constant-float-boundary2-v1'
BOUNDARY_FRAMES_EACH_END = 2
F32 = struct.Struct('<f')
U16 = struct.Struct('<H')
U32 = struct.Struct('<I')

def _inspect_header(data,start=0):
    if start+26>len(data):raise ValueError('Truncated header')
    unk,n,duration,total,h1,h2=struct.unpack_from('<IIfIII',data,start)
    if not 0<n<=4096 or not math.isfinite(duration):raise ValueError('Invalid channels/duration')
    off=start+26+8*(h1+h2);nf=((3*n+7)//8+1)//2*2
    flags=data[off:off+nf];off+=nf;bases=[];compressed=[];additive=False
    for i in range(n):
        for c in range(3):
            bit=bool(flags[(i*3+c)//8]&(1<<((i*3+c)%8)))
            sz=(4 if c==1 else 6) if bit else (16 if c==1 else 12)
            b=data[off:off+sz]
            if len(b)!=sz:raise ValueError('Truncated initial pose')
            bases.append(b);compressed.append(bit)
            if c==2:
                scale_x=(struct.unpack_from('<H',b)[0]-32767.0)*(10.0/32767.0) if bit else F32.unpack_from(b)[0]
                additive|=scale_x==0.
            off+=sz
    off+=4*h1
    if off>len(data):raise ValueError('Truncated hash floats')
    return dict(start=start,entry_start=off,channels=n,duration=duration,total=total,bases=bases,compressed=compressed,additive=additive)

def _records(data,h):
    off=h['entry_start'];index=0
    while True:
        if off+2>len(data):raise ValueError('Missing end marker')
        w=U16.unpack_from(data,off)[0];typ=w>>14
        if typ:
            c={1:2,2:0,3:1}[typ];bone=(w>>4)&1023;size=8 if typ==3 else 10
            key=3*bone+c;timebytes=None;value=data[off+4:off+size]
        else:
            if w==3:return off+2
            if w not in (2,4,5,6):raise ValueError(f'Unknown subtype {w}')
            size=10 if w==2 else 26 if w==5 else 22
            if off+size>len(data):raise ValueError('Truncated entry')
            seconds=F32.unpack_from(data,off+6)[0]
            if not math.isfinite(seconds):raise ValueError('Non-finite key time')
            timebytes=data[off+6:off+10]
            key=None if w==2 else 3*U32.unpack_from(data,off+2)[0]+w-4
            value=data[off+10:off+size]
        if key is not None and key>=3*h['channels']:raise ValueError('Key channel out of range')
        if off+size>len(data):raise ValueError('Truncated entry')
        yield index,off,size,key,timebytes,value,typ
        index+=1;off+=size

def _block_end(data,h):
    off=h['entry_start']
    for _,at,sz,*_ in _records(data,h):off=at+sz
    if U16.unpack_from(data,off)[0]!=3:raise ValueError('Bad terminator')
    return off+2

def _layout(data):
    h=_inspect_header(data);end=_block_end(data,h)
    if end+4>len(data) or U32.unpack_from(data,end)[0]!=end:raise ValueError('Invalid first block trailer')
    second=end+4;h2=_inspect_header(data,second);end2=_block_end(data,h2)
    if end2+4!=len(data) or U32.unpack_from(data,end2)[0]!=end2-second:raise ValueError('Invalid second block trailer')
    if h['total']!=len(data):raise ValueError('Invalid animation total size')
    if data[:12]!=data[second:second+12] or data[16:end]!=data[second+16:end2]:raise ValueError('Distinct animation blocks are not supported by this single cutter')
    return h,h2,end,end2

def compact_single_animation(data,expected_channels=None):
    boundary_frames=BOUNDARY_FRAMES_EACH_END
    data=bytes(data)
    h,h2,end,end2=_layout(data)
    if expected_channels is not None and h['channels']!=expected_channels:raise ValueError('Single animation channel count changed')
    if h['additive']:
        return data,dict(additive=True,unchanged=True,removed_keys_one_block=0,removed_bytes=0,protected_time_bits=[],all_retained_records_byte_exact=True)
    if any(h['compressed']):raise ValueError('Normal input must retain the all-float R2 initial pose')
    counts=[0]*(3*h['channels']);first={};last={};varying=set();times={};events=[]
    for ix,off,sz,k,t,v,typ in _records(data,h):
        if typ not in (0,1):raise ValueError('Normal input position/rotation must retain R2 float format')
        if k is None:events.append(data[off:off+sz]);continue
        counts[k]+=1;first.setdefault(k,ix);last[k]=ix
        if t is not None:times[t]=F32.unpack(t)[0]
        # Strict serialized equality ONLY: no epsilon, normalization or q/-q folding.
        if k%3==2 or typ or v!=h['bases'][k]:varying.add(k)  # All original scale _records are protected, including compressed ones.
    sorted_times=sorted(times,key=times.get)
    protected=set(sorted_times[:boundary_frames]+sorted_times[-boundary_frames:])
    constant={k for k,n in enumerate(counts) if n and k not in varying}
    kept=bytearray();removed=0;removed_bytes=0;protected_keys=0;reasons=collections.Counter();retained_hash=hashlib.sha256();event_hash=hashlib.sha256()
    # Preserve original ordering and original record/time/payload bits. Never reserialize poses.
    for ix,off,sz,k,t,v,typ in _records(data,h):
        keep=k is None or k in varying or t in protected or ix==first.get(k) or ix==last.get(k)
        raw=data[off:off+sz]
        if keep:
            kept.extend(raw);retained_hash.update(raw)
            if k is None:event_hash.update(raw)
            if k in constant:protected_keys+=1
        else:
            if v!=h['bases'][k]:raise AssertionError('Attempted to remove motion')
            removed+=1;removed_bytes+=sz;reasons[('position','rotation','scale')[k%3]]+=1
    p1=bytearray(data[:h['entry_start']]);p2=bytearray(data[h2['start']:h2['entry_start']])
    b1=p1+kept+b'\x03\x00';b2=p2+kept+b'\x03\x00';total=len(b1)+len(b2)+8
    struct.pack_into('<I',b1,12,total)
    candidate=bytes(b1)+U32.pack(len(b1))+bytes(b2)+U32.pack(len(b2))
    ch,ch2,ce,ce2=_layout(candidate)
    if candidate[:12]!=data[:12] or candidate[16:ch['entry_start']]!=data[16:h['entry_start']]:raise AssertionError('Initial pose/header changed')
    if candidate[ch2['start']:ch2['entry_start']]!=data[h2['start']:h2['entry_start']]:raise AssertionError('Second initial pose/header changed')
    check_hash=hashlib.sha256();check_events=hashlib.sha256();after_times=set();afterfirst={};afterlast={}
    for ix,off,sz,k,t,v,typ in _records(candidate,ch):
        raw=candidate[off:off+sz];check_hash.update(raw)
        if k is None:check_events.update(raw)
        else:
            after_times.add(t);afterfirst.setdefault(k,raw);afterlast[k]=raw
    if check_hash.digest()!=retained_hash.digest() or check_events.digest()!=event_hash.digest():raise AssertionError('Retained keys/events changed')
    if not protected.issubset(after_times):raise AssertionError('Boundary time frame lost')
    if len(data)-len(candidate)!=2*removed_bytes:raise AssertionError('Removal size mismatch')
    return candidate,dict(additive=False,unchanged=candidate==data,constant_tracks=len(constant),removed_keys_one_block=removed,removed_bytes=2*removed_bytes,
        removed_components_one_block=dict(reasons),protected_constant_keys_one_block=protected_keys,protected_time_bits=[t.hex() for t in sorted(protected,key=lambda x:F32.unpack(x)[0])],
        original_compressed_scale_keys_one_block=sum(1 for *_,typ in _records(data,h) if typ==1),boundary_frames_each_end=boundary_frames,retained_record_sha256_one_block=retained_hash.hexdigest(),event_sha256_one_block=event_hash.hexdigest(),all_retained_records_byte_exact=True)

