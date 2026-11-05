"""Measure anatomical bend-plane changes introduced by v12's grip solver."""
import copy
import json
import math
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod import native_skeleton as native
from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData
from anim_batch_mod.formats import AnimationData
from anim_batch_mod.math3d import quat_inverse_rotate, vec_sub
from anim_batch_mod.processor import ModConfig, _calculate_world_transforms, _cross
from anim_batch_mod.processor import _build_tracks, WorldTransform

WORK = ROOT / 'outputs/native-v13-20261104'
PROJECT = ROOT / 'outputs/native-v12-20261104/project'
original = native._apply_two_bone_ik
current_id = None
metrics = []
worst = None


def bend(local, parents, a, b, c):
    world = _calculate_world_transforms(local, parents, (a, b, c))
    first = vec_sub(world[b].position, world[a].position)
    second = vec_sub(world[c].position, world[b].position)
    norm = math.sqrt(sum(v*v for v in first) * sum(v*v for v in second))
    flex = math.degrees(math.acos(max(-1., min(1., sum(x*y for x,y in zip(first, second))/norm))))
    normal = quat_inverse_rotate(world[a].rotation, _cross(first, second))
    length = math.sqrt(sum(v*v for v in normal))
    return flex, [v / max(1e-12, length) for v in normal]


def observe(local, parents, a, b, c, target, rotation=None, **kwargs):
    global worst
    before = bend(local, parents, a, b, c)
    saved = copy.deepcopy(local)
    state = copy.deepcopy(kwargs)
    original(local, parents, a, b, c, target, rotation, **kwargs)
    after = bend(local, parents, a, b, c)
    if min(before[0], after[0]) < 5:
        return
    expected = kwargs.get('hinge_axis') or before[1]
    dot = max(-1., min(1., sum(x*y for x,y in zip(expected, after[1]))))
    row = dict(clip=current_id, root=a, inputFlexDegrees=before[0], outputFlexDegrees=after[0],
               anatomicalPlaneChangeDegrees=math.degrees(math.acos(dot)))
    metrics.append(row)
    if worst is None or row['anatomicalPlaneChangeDegrees'] > worst['measurement']['anatomicalPlaneChangeDegrees']:
        worst = dict(measurement=row, parents=parents, root=a, mid=b, end=c,
                     local=[dict(position=t.position, rotation=t.rotation, scale=t.scale) for t in saved],
                     target=target, rotation=rotation, options=state)


def main():
    global current_id
    manifest = json.loads((PROJECT / 'source-skeleton.json').read_text(encoding='utf-8'))
    config = ModConfig.load(PROJECT / 'config.toml')
    options = tomllib.loads((PROJECT / 'config.toml').read_text(encoding='utf-8'))['native_skeleton']
    base = ROOT / 'outputs/native-fix-20261103'
    unit = UnitData.parse((base / 'avatar.toc').read_bytes())
    bones = BonesData.parse((base / 'bones.toc').read_bytes())
    lookup = {int(r['id']):r for r in json.loads((PROJECT / 'animations/build-report.json').read_text(encoding='utf-8'))['animations']}
    store = PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
    archives = {}
    extended_unit = UnitData.parse(native.append_unit((base / 'avatar.toc').read_bytes(), manifest))
    extended_bones = BonesData.parse(native.append_bones((base / 'bones.toc').read_bytes(), manifest))
    mapping = [extended_unit.name_hashes.index(h) for h in extended_bones.hashes]
    source_indices = {n['driver']: len(unit.transforms)+i for i,n in enumerate(manifest['bones']) if n['driver']}
    def world_at(tracks, time):
        local = list(extended_unit.transforms)
        for channel, index in enumerate(mapping):
            local[index] = WorldTransform(*(tr[channel].evaluate(time) for tr in tracks))
        return _calculate_world_transforms(local, extended_unit.parents)
    def angle(a, b):
        norm = math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
        return math.degrees(2*math.acos(min(1., abs(sum(x*y for x,y in zip(a,b)))/norm)))
    clip_reports = []
    out = WORK / 'candidate-clips'
    out.mkdir(exist_ok=True)
    native._apply_two_bone_ik = observe
    for path in sorted((ROOT / 'outputs/native-v12-20261104/candidate-clips').glob('*.toc')):
        current_id = path.stem
        package = lookup[int(current_id)]['package']
        if package not in archives:
            archives[package] = TocArchive.load_toc_only(store, package)
        raw = archives[package].entries[int(current_id), ANIMATION_TYPE_ID].toc_data
        start = len(metrics)
        data, conversion = native.convert_clip(raw, bones, unit, manifest, config, options)
        (out / path.name).write_bytes(data)
        new = AnimationData.parse(data)
        old = AnimationData.parse(path.read_bytes())
        new_tracks, old_tracks = _build_tracks(new), _build_tracks(old)
        pe = qe = 0.
        steps = {}
        if not new.is_additive:
            for i in range(math.floor(new.animation_length*30)+1):
                time = i*1000/30
                nw, ow = world_at(new_tracks, time), world_at(old_tracks, time)
                for name in ('l_hand', 'r_hand'):
                    n = source_indices[name]
                    pe = max(pe, math.dist(nw[n].position, ow[n].position))
                    qe = max(qe, angle(nw[n].rotation, ow[n].rotation))
            for side in ('l', 'r'):
                for joint in ('shoulder', 'elbow'):
                    name = side+'_'+joint
                    channel = mapping.index(source_indices[name])
                    rotations = [new_tracks[1][channel].evaluate(i*1000/60) for i in range(math.floor(new.animation_length*60)+1)]
                    steps[name] = max((angle(a,b) for a,b in zip(rotations, rotations[1:])), default=0)
        clip_reports.append(dict(id=current_id, additive=new.is_additive, maxBakedHandPositionDifferenceMetres=pe,
                                 maxBakedPalmAngleDifferenceDegrees=qe, max60HzJointStepDegrees=steps,
                                 maxGripResidualMetres=conversion['max_standard_grip_error']))
        rows = metrics[start:]
        print(current_id, 'samples', len(rows), 'reversed', sum(r['anatomicalPlaneChangeDegrees'] > 90 for r in rows),
              'max', max((r['anatomicalPlaneChangeDegrees'] for r in rows), default=0), flush=True)
    report = dict(status='MEASURED', gameTested=False, samples=len(metrics),
                  reverseBendSamples=sum(r['anatomicalPlaneChangeDegrees'] > 90 for r in metrics),
                  worst=worst['measurement'] if worst else None)
    WORK.mkdir(exist_ok=True)
    (WORK / 'elbow-plane-analysis.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (WORK / 'elbow-worst-fixture.json').write_text(json.dumps(worst, indent=2), encoding='utf-8')
    (WORK / 'candidate-comparison.json').write_text(json.dumps(clip_reports, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
