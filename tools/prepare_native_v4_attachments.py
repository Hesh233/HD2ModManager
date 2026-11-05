"""Prepare both attachment pose profiles. Does not edit shipped scene graphs."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT.parents[1]))
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import load_manifest,local_pose,row_pose,_reference_rotations,bone_name_hash
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_inverse,quat_multiply

WORK=ROOT/'outputs/native-v4-20261103';PROJECT=WORK/'project';BASE=ROOT/'outputs/native-fix-20261103'

def main():
    u=UnitData.parse((BASE/'avatar.toc').read_bytes());b=BonesData.parse((BASE/'bones.toc').read_bytes())
    m=load_manifest(PROJECT/'models/test01/source-skeleton.json')
    names={}
    for line in (WORK/'manager-release/data/resources/bonehash.txt').read_text(encoding='utf-8-sig').splitlines():
        fields=line.strip().split(' ',1)
        if len(fields)==2:names[int(fields[0])]=fields[1]
    names.update(zip(b.hashes,b.names))
    labels=[names.get(h,f'hash_{h:08x}') for h in u.name_hashes]
    by_name={n:i for i,n in enumerate(labels)};by_hash={h:i for i,h in enumerate(u.name_hashes)}
    head=by_name['head'];requested={'sling','target_designator','boss_aim','climb_ref','support','support_mg','backpack'}
    chosen=set();head_nodes=set()
    for i,name in enumerate(labels):
        if u.parents[i]==head or u.parents[i] in head_nodes:head_nodes.add(i)
        if (u.parents[i]==head or name.startswith(('attach_','cape')) or name in requested
            or u.parents[i] in chosen):chosen.add(i)
    dw=_calculate_world_transforms(u.transforms,u.parents)
    driver_by_name={name:by_hash[h] for name,h in zip(b.names,b.hashes)}
    sw=[row_pose(n['world']) for n in m['bones']]
    reference,_=_reference_rotations(m['bones'],[local_pose(n['local']) for n in m['bones']],sw,dw,driver_by_name)
    mapped={driver_by_name[n['driver']]:i for i,n in enumerate(m['bones']) if n['driver'] is not None}
    def pose(t):return dict(position=t.position,rotation=t.rotation,scale=t.scale)
    native=[];vpk=[]
    used=set(u.name_hashes)|{n['hash'] for n in m['bones']}
    for i in sorted(chosen):
        parent=u.parents[i]
        native.append(dict(index=i,name=names.get(u.name_hashes[i]),label=labels[i],hash=u.name_hashes[i],
            parentIndex=parent,parentName=labels[parent] if parent is not None else None,
            animationChannel=b.hashes.index(u.name_hashes[i]) if u.name_hashes[i] in b.hashes else None,
            localBind=pose(u.transforms[i]),worldBind=pose(dw[i]),policy='original-animated-pose'))
        anchor=parent
        while anchor is not None and anchor not in mapped:anchor=u.parents[anchor]
        virtual=f"{m['boneNamespace']}_attach_{i:03d}_{labels[i].lower()}"
        h=bone_name_hash(virtual);assert h not in used;used.add(h)
        row=dict(index=i,ownerSlot='head' if i in head_nodes else 'body',standardName=names.get(u.name_hashes[i]),standardHash=u.name_hashes[i],
            virtualName=virtual,virtualHash=h,parentVirtualIndex=parent if parent in chosen else None,
            emittedToSceneGraph=False,calibrationVerified=False)
        if anchor is None:
            row.update(policy='original-world',reason='No mapped anatomical ancestor; controller/world-space semantics need game observation.')
        else:
            si=mapped[anchor]
            row.update(policy='source-anchor-relative-animation',driverAnchorIndex=anchor,
                driverAnchorName=labels[anchor],sourceAnchorName=m['bones'][si]['name'],sourceAnchorIndex=si,
                axisCorrection=quat_multiply(quat_inverse(reference[si]),dw[anchor].rotation),
                translationScale=1.0,
                translationPolicy='Keep equipment offset in metres; source anchor already contains the 1.05 model scale.')
        vpk.append(row)
    mapping=json.loads((WORK/'o3-mapping.json').read_text())['mappings']
    old=json.loads((PROJECT/'attachment-profile-research.json').read_text(encoding='utf-8-sig'))
    result=dict(version=1,status='prepared-for-offline-evaluation',runtimeEnabled=False,
        sceneGraphModified=False,boneNamespace=m['boneNamespace'],indexBasis='zero-based Unit TransformInfo',
        targets={slot:sorted({r['targetUnit'] for r in mapping if r['part'].startswith(prefix)})
            for slot,prefix in [('body','Torso/Armor/'),('head','Helmet/')]},requestedGroups=['head descendants','sling','attach_*',
            'target_designator','boss_aim','climb_ref','support','cape*','support_mg','backpack'],
        native=native,vpk=vpk,weaponCandidates=old.get('profiles',old.get('weaponCandidates',[])),
        selectionRule='Require current-frame verified armor-to-avatar ownership, actual armor rig identity and body resource; never proximity or avatar bone presence.',
        phaseRequirement='Read original animation snapshot before any override; apply after animation and before attachment consumers.',
        restoreRule='Use the current frame original animation, never a cached bind or last-frame overridden pose.',
        blockers=['No verified cross-Unit equipment ownership query in current Lua integration.',
            'Animation/equipment callback order has not been observed in game.',
            'Controller-space helpers and weapon-specific offsets require in-game calibration.'])
    target=PROJECT/'attachment-profile-research.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(entries=len(native),sourceAnchored=sum(r['policy']=='source-anchor-relative-animation' for r in vpk),
        controllerFallbacks=[r['standardName'] for r in vpk if r['policy']=='original-world'],
        unknownHeadNodes=[r['label'] for r in native if r['name'] is None]),ensure_ascii=False))
if __name__=='__main__':main()
