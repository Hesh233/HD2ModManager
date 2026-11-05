"""Read-only comparison of the supplied straightened Unit attachment frames."""
import copy,hashlib,json,math,struct,sys,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData,AnimationData,AnimationBoneState
from anim_batch_mod.native_skeleton import load_manifest,local_pose,row_pose,_reference_rotations,convert_clip,append_unit,append_bones
from anim_batch_mod.motion_skeleton import source_local
from anim_batch_mod.processor import WorldTransform,ModConfig,_calculate_world_transforms,modify_animation_with_world_compensation
from anim_batch_mod.math3d import quat_inverse,quat_multiply,quat_rotate,vec_sub,vec_add
W=ROOT/'outputs/native-v8-20261104';W.mkdir(parents=True,exist_ok=True)
P=ROOT/'outputs/native-v7-20261104/project';B=ROOT/'outputs/native-fix-20261103'
path=ROOT.parent/'unit_anim/9ba626afa44a3aa3.patch_0';data=path.read_bytes();nt,n=struct.unpack_from('<II',data,4)
b=BonesData.parse((B/'bones.toc').read_bytes());original_raw=(B/'avatar.toc').read_bytes();original=UnitData.parse(original_raw)
units=[]
for i in range(n):
    r=struct.unpack_from('<QQQQQQQIIIIII',data,72+32*nt+80*i)
    if r[1]==UNIT_TYPE_ID:
        raw=data[r[2]:r[2]+r[7]];u=UnitData.parse(raw)
        units.append((r[0],raw,u))
matches=[r for r in units if all(h in r[2].name_hashes for h in b.hashes)]
assert len(matches)==1,(len(units),len(matches))
fid,reference_raw,reference=matches[0]
(W/'unit-anim-reference.toc').write_bytes(reference_raw)
m=load_manifest(P/'source-skeleton.json');profile=json.loads((P/'attachment-profile.json').read_text());cfg=ModConfig.load(P/'config.toml');opts=tomllib.loads((P/'config.toml').read_text())['native_skeleton']
omap={name:original.name_hashes.index(h) for name,h in zip(b.names,b.hashes)};rmap={name:reference.name_hashes.index(h) for name,h in zip(b.names,b.hashes)}
ow=_calculate_world_transforms(original.transforms,original.parents);rw=_calculate_world_transforms(reference.transforms,reference.parents)
sw=[row_pose(row['world']) for row in m['bones']];sb=[local_pose(source_local(row,i,m)) for i,row in enumerate(m['bones'])]
source={row['driver']:i for i,row in enumerate(m['bones']) if row['driver']}
calibrated,_=_reference_rotations(m['bones'],sb,sw,ow,omap,m)
straight_calibrated,_=_reference_rotations(m['bones'],sb,sw,rw,rmap,m)
def angle(a,b):
    d=abs(sum(x*y for x,y in zip(a,b)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return math.degrees(2*math.acos(min(1.,max(-1.,d))))
def rel(a,t):
    qi=quat_inverse(a.rotation)
    return WorldTransform(quat_rotate(qi,vec_sub(t.position,a.position)),quat_multiply(qi,t.rotation),[1.,1.,1.])
def pd(t):return dict(position=t.position,rotation=t.rotation,scale=t.scale)
def diff(a,b):return dict(positionMetres=math.dist(a.position,b.position),rotationDegrees=angle(a.rotation,b.rotation))
def axispose(q,t):return WorldTransform(quat_rotate(q,t.position),quat_multiply(q,t.rotation),t.scale)
byname={row['standardName']:row for row in profile['vpk'] if row.get('standardName')}
rows=[]
for name,anchor in [('attach_hand_l','l_hand'),('attach_hand_r','r_hand'),('attach_weapon','r_hand')]:
    row=byname[name];si=source[anchor];old=rel(ow[omap[anchor]],ow[omap[name]]);new=rel(rw[rmap[anchor]],rw[rmap[name]])
    old_axis=quat_multiply(quat_inverse(calibrated[si]),ow[omap[anchor]].rotation)
    straight_axis=quat_multiply(quat_inverse(straight_calibrated[si]),rw[rmap[anchor]].rotation)
    direct_axis=quat_multiply(quat_inverse(sw[si].rotation),rw[rmap[anchor]].rotation)
    rows.append(dict(name=name,anchor=anchor,originalAnchorWorld=pd(ow[omap[anchor]]),straightAnchorWorld=pd(rw[rmap[anchor]]),sourceBindWorld=pd(sw[si]),originalRelative=pd(old),straightRelative=pd(new),relativeDifference=diff(old,new),profileAxis=row['axisCorrection'],recomputedOriginalAxis=old_axis,straightCalibratedAxis=straight_axis,directStraightBindAxis=direct_axis,profileAxisVsRecomputedOriginalDegrees=angle(row['axisCorrection'],old_axis),profileAxisVsStraightCalibratedDegrees=angle(row['axisCorrection'],straight_axis),profileAxisVsDirectStraightBindDegrees=angle(row['axisCorrection'],direct_axis),sourceOffsetUsingCurrentAxis=pd(axispose(row['axisCorrection'],new)),sourceOffsetUsingStraightAxis=pd(axispose(straight_axis,new)),sourceOffsetUsingDirectStraightAxis=pd(axispose(direct_axis,new))))
comparison=[]
oldref=ROOT/'outputs/native-v6-20261104/avatar-reference.toc'
if oldref.exists():
    oldunit=UnitData.parse(oldref.read_bytes());oldworld=_calculate_world_transforms(oldunit.transforms,oldunit.parents)
    for name in ('l_hand','r_hand','attach_hand_l','attach_hand_r','attach_weapon'):
        comparison.append(dict(name=name,**diff(oldworld[oldunit.name_hashes.index(b.hashes[b.names.index(name)])],rw[rmap[name]])))
def stored_check(raw,u,worlds):
    off=struct.unpack_from('<I',raw,52)[0]+16+64*len(u.transforms)
    stored=[row_pose(struct.unpack_from('<16f',raw,off+64*i)) for i in range(len(u.transforms))]
    errors=[dict(index=i,**diff(a,c)) for i,(a,c) in enumerate(zip(stored,worlds))]
    return dict(maxPositionMetres=max(e['positionMetres'] for e in errors),maxRotationDegrees=max(e['rotationDegrees'] for e in errors),worstPosition=max(errors,key=lambda e:e['positionMetres']))
report=dict(validationStatus='COMPLETE',gameTested=False,referencePatch=str(path),referencePatchSha256=hashlib.sha256(data).hexdigest(),referenceUnitId=f'{fid:016x}',referenceUnitsInPatch=len(units),referenceUnitNodes=len(reference.transforms),oldAvatarReferenceComparison=comparison,originalStoredWorldCheck=stored_check(original_raw,original,ow),straightStoredWorldCheck=stored_check(reference_raw,reference,rw),modelScale=m['modelScale'],rows=rows)
(W/'attachment-reference-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
for row in rows:print(json.dumps({k:v for k,v in row.items() if k in ('name','relativeDifference','profileAxisVsRecomputedOriginalDegrees','profileAxisVsStraightCalibratedDegrees','profileAxisVsDirectStraightBindDegrees')},indent=2))
