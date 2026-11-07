"""Single v3 canonical bind / return / boundary continuity; legacy v1/v2 differential tests."""
import contextlib,io,math,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ['LOCALAPPDATA']=str(ROOT/'tmp')
base=ROOT/'outputs/vrd-analysis-20261107/lua-check/driver-update-test.py'
g={'__file__':str(base),'__name__':'__main__'}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(base.read_text(encoding='utf-8-sig').replace('1.2.0','1.2.1'),str(base),'exec'),g)
compat,lua,result,state=g['compat'],g['lua'],g['result'],g['state']
row=result.drivers[1]
result.rig.drivers.version=3;row.controlBindQ=lua.table(0,0,0,1);row.fadeOutside=True
checks=0

def qz(deg):return [0,0,math.sin(math.radians(deg)/2),math.cos(math.radians(deg)/2)]
def check(ok,message):
    global checks
    checks+=1
    if not ok:raise AssertionError(message)
def output(q):
    state['control_q']=q;state['rot_writes'].clear();row.lastWritten=None;row.smoothedQ=None
    for _ in range(80):compat.update_drivers(result,1/60)
    writes=[w for w in state['rot_writes'] if w[0]==64]
    check(len(writes)>0,'v3 must write a finite output or bind')
    return writes[-1][1:]
def dot(a,b):return abs(sum(x*y for x,y in zip(a,b)))
expect=[math.sin(math.radians(10)),0,0,math.cos(math.radians(10))]
for first in (0,37,90,145):
    row.controlQ0=lua.table(*qz(first))
    check(dot(output(qz(90)),expect)>.99999,'initial attach pose changed single VRD output')
for bind in (0,37,-60):
    row.controlBindQ=lua.table(*qz(bind))
    check(dot(output(qz(bind+90)),expect)>.99999,'canonical control-space delta incorrect')
row.controlBindQ=lua.table(0,0,0,1)
output(qz(90));out=output([0,1,0,0]);check(dot(out,[0,0,0,1])>.99999,'no match must return to bind')
check(dot(output(qz(90)),output([-v for v in qz(90)]))>.99999,'quaternion sign dependence')
previous=None;peak_jump=0
for i in range(1441):
    out=output(qz(-180+i*.25));check(abs(sum(v*v for v in out)-1)<1e-5,'non-unit output')
    if previous is not None:
        angle=2*math.degrees(math.acos(min(1,dot(previous,out))));peak_jump=max(peak_jump,angle)
    previous=out
check(peak_jump<1,'single rule boundary snaps by more than 1 deg per .25-deg sample')
# Actual serialized .NET v3 records: all driver axes / empty-domain / finite output sweep.
raw=(ROOT/'outputs/vrd-analysis-20261107/e2e-test01-single/test01/physbone-driver-rig.bin').read_bytes()
parsed=compat.parse_driver_rig(raw)
if isinstance(parsed,tuple):raise AssertionError(parsed[1])
check(parsed.version==3 and len(parsed.bones)==8,'real single rig must be v3/8 drivers')
real_peak=0;worst=None
for bone in parsed.bones.values():
    bone.fadeOutside=True
    for axis in ((1,0,0),(0,1,0),(0,0,1)):
        previous=None
        for deg in range(-180,181):
            sn=math.sin(math.radians(deg)/2);q=[axis[0]*sn,axis[1]*sn,axis[2]*sn,math.cos(math.radians(deg)/2)]
            out=compat.quatinterp(lua.table(*q),bone)
            if out is None:out=(0,0,0,1)
            check(all(math.isfinite(v) for v in out) and abs(sum(v*v for v in out)-1)<1e-5,'real driver invalid rotation')
            if previous is not None:
                step=2*math.degrees(math.acos(min(1,dot(previous,out))))
                if step>real_peak:real_peak=step;worst=dict(bone=bone.name,axis=axis,deg=deg,previous=previous,current=out)

            previous=out
# Adversarial animated control jumps: temporal output must obey the rate cap at all tested dt.
max_rate=0
for dt in (1/240,1/144,1/60,1/30,.1):
    row.smoothedQ=None;row.lastWritten=None
    previous=(0,0,0,1)
    for frame in range(180):
        state['control_q']=qz(90 if frame%40<20 else -150)
        compat.update_drivers(result,dt)
        out=tuple(row.smoothedQ[k] for k in range(1,5))
        rate=2*math.degrees(math.acos(min(1,dot(previous,out))))/dt
        max_rate=max(max_rate,rate);check(rate<=540.001,'v3 temporal rate cap exceeded')
        previous=out
saved_rules=row.rules
for bone in parsed.bones.values():
    row.rules=bone.rules;row.smoothedQ=None;row.lastWritten=None
    previous=(0,0,0,1)
    for frame in range(360):
        state['control_q']=qz((-175,0,120,-176,90,-90)[(frame//15)%6])
        compat.update_drivers(result,1/60)
        out=tuple(row.smoothedQ[k] for k in range(1,5))
        rate=2*math.degrees(math.acos(min(1,dot(previous,out))))*60
        max_rate=max(max_rate,rate);check(rate<=540.001,'real v3 driver temporal rate cap exceeded')
        previous=out
row.rules=saved_rules
# Math for old native containers must be identical, not merely visually similar.
old=lua.execute((ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua.before-single-vrd-fix.bak').read_text(encoding='utf-8-sig'))
row.fadeOutside=False
for deg in range(-180,181):
    q=lua.table(*qz(deg));a=old.quatinterp(q,row);b=compat.quatinterp(q,row)
    check(a==b,'legacy quaternion solver changed')
report=dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',checks=checks,syntheticStepDeg=.25,syntheticMaxOutputStepDeg=peak_jump,actualAxisSweepMaxOutputStepDeg=real_peak,actualDrivers=8,legacyMathExact=True,worstRawRuleStep=worst,maxTemporalRateDegPerSecond=max_rate)
(ROOT/'outputs/vrd-analysis-20261107/single-vrd-runtime-audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report))
