"""Generate per-model native post-IK arm calibration from serialized rig data."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.formats import UnitData, BonesData
from anim_batch_mod.math3d import quat_inverse, quat_inverse_rotate, quat_multiply, vec_sub
from anim_batch_mod.processor import WorldTransform, _calculate_world_transforms, _cross
from anim_batch_mod.motion_skeleton import source_local, source_parent, layers


def calibration(project):
    manifest = native.load_manifest(project / 'source-skeleton.json')
    base = ROOT / 'outputs/native-fix-20261103'
    unit = UnitData.parse((base / 'avatar.toc').read_bytes())
    bones = BonesData.parse((base / 'bones.toc').read_bytes())
    nodes = manifest['bones']; offset = len(unit.transforms)
    driver_by_name = {name: unit.name_hashes.index(h) for name, h in zip(bones.names, bones.hashes)}
    by_driver = {n['driver']: i for i, n in enumerate(nodes) if n['driver']}
    binds = [native.local_pose(source_local(n, i, manifest)) for i, n in enumerate(nodes)]
    driver_bind = _calculate_world_transforms(unit.transforms, unit.parents)
    refs, locals_ = native._reference_rotations(nodes, binds, [native.row_pose(n['world']) for n in nodes],
                                              driver_bind, driver_by_name, manifest)
    expanded = UnitData.parse(native.append_unit((base / 'avatar.toc').read_bytes(), manifest))
    ref_local = list(expanded.transforms)
    for i, (bind, q) in enumerate(zip(binds, locals_)):
        ref_local[offset+i] = WorldTransform(list(bind.position), q, [1., 1., 1.])
    worlds = _calculate_world_transforms(ref_local, expanded.parents)
    names = {native.bone_name_hash(n): n for n in bones.names}
    for line in (ROOT / 'HD2ModManager/Resources/AssetMetadata/bonehash.txt').read_text(encoding='utf-8-sig').splitlines():
        parts = line.split(' ', 1)
        if len(parts) == 2 and parts[0].isdigit():
            names[int(parts[0])] = parts[1]
    names.update({n['hash']: n['name'] for n in native.animation_nodes(manifest)})
    names.update({n['hash']: n['name'] for n in layers(manifest)})
    result = []
    for side in ('l', 'r'):
        drivers = [f'{side}_{joint}' for joint in ('shoulder', 'elbow', 'hand')]
        a,b,c = [by_driver[d] for d in drivers]
        assert nodes[b]['parent'] == a and nodes[c]['parent'] == b
        indices = [offset+a, offset+b, offset+c]
        first = vec_sub(worlds[offset+b].position, worlds[offset+a].position)
        second = vec_sub(worlds[offset+c].position, worlds[offset+b].position)
        normal = _cross(first, second); n = math.sqrt(sum(v*v for v in normal))
        assert n > 1e-8
        hinge = quat_inverse_rotate(worlds[offset+a].rotation, [v/n for v in normal])
        parent = expanded.parents[offset+a]
        scale_checks = set(indices)
        cursor = parent
        while cursor is not None:
            assert cursor not in scale_checks
            scale_checks.add(cursor);cursor = expanded.parents[cursor]
        native_indices = [driver_by_name[d] for d in drivers]
        checked = sorted(scale_checks | set(native_indices))
        row = dict(side=side, root=offset+a, mid=offset+b, hand=offset+c, parent=parent,
                   nativeUpper=native_indices[0], nativeForearm=native_indices[1], nativeHand=native_indices[2],
                   upperOffset=list(binds[b].position), forearmOffset=list(binds[c].position), hingeAxis=hinge,
                   scaleChecks=sorted(scale_checks),
                   nodes=[dict(name=names[expanded.name_hashes[i]], index=i) for i in checked if expanded.name_hashes[i] in names])
        for key, i, driver in zip(('upperCalibration', 'forearmCalibration', 'handCalibration'), (a,b,c), native_indices):
            row[key] = quat_multiply(quat_inverse(driver_bind[driver].rotation), refs[i])
        result.append(row)
    return result, expanded, ref_local


def main():
    project = ROOT / 'outputs/native-v13-20261104/project'
    rows, expanded, ref_local = calibration(project)
    path = project / 'attachment-profile.json'
    profile = json.loads(path.read_text(encoding='utf-8'))
    profile.update(revision='test01-v13-A', armSync=False, armChains=rows)
    next(r for r in profile['vpk'] if r['standardName']=='sling')['policy'] = 'original-world'
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
