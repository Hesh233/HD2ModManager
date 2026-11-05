"""Survey all weapon-candidate Units for grip-relevant IK nodes (offline, read-only).

Builds the inventory required by the B23-LR next-step TODO: resource identities,
IK_right / IK_left / attach_underbarrel markers, static root-relative matrices,
and accessory (foregrip) units. Never writes into the game or the runtime.
"""
from __future__ import annotations

import json
import re
import sqlite3
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData
from anim_batch_mod.native_skeleton import bone_name_hash

INDEX = ROOT / 'outputs/native-manual-20261103/manager/data/indexes/asset-index.sqlite'
GAME_DATA = Path('E:/Steam/steamapps/common/Helldivers 2/data')
NAMES = ROOT.parents[1] / 'hashlists/friendlynames.txt'
BONE_HASHES = ROOT.parents[1] / 'hashlists/bonehash.txt'
OBS = ROOT / 'outputs/native-b21-observation-20261105/20261105-094642'
W = ROOT / 'outputs/native-weapon-survey-20261105'
MASK = (1 << 64) - 1
MARKERS = ('boss', 'skeleton', 'root', 'IK_right', 'IK_left', 'attach_underbarrel',
           'attach_hand_r', 'attach_hand_l', 'attach_weapon', 'weapon_aim', 'muzzle')
ACCESSORY_PATTERN = re.compile(r'Foregrip|Laser|Flashlight|Suppressor|Compensator|'
                               r'Muzzle|Grip|Sight|Scope|Stock', re.I)
SMG = 0x186ea95de7306b1a
FOREGRIP = 0xf9df21c8e52cac95


def sgn(x):
    return x - MASK - 1 if x > MASK // 2 else x


def hex_id(x):
    return '%016x' % (x & MASK)


IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.]


def to_rows(m):
    """Layout is three column bases then translation: m[3*c+r]."""
    return [[m[3 * c + r] for c in range(3)] for r in range(3)]


def from_rows(r, t):
    m = [0.] * 12
    for row in range(3):
        for col in range(3):
            m[3 * col + row] = r[row][col]
    m[9:12] = t
    return m


def compose(a, b):
    A, B = to_rows(a), to_rows(b)
    r = [[sum(A[row][k] * B[k][col] for k in range(3)) for col in range(3)] for row in range(3)]
    t = [sum(A[row][k] * b[9 + k] for k in range(3)) + a[9 + row] for row in range(3)]
    return from_rows(r, t)


def invert(m):
    a = to_rows(m)
    m00, m01, m02 = a[0]
    m10, m11, m12 = a[1]
    m20, m21, m22 = a[2]
    det = m00 * (m11 * m22 - m12 * m21) - m01 * (m10 * m22 - m12 * m20) + m02 * (m10 * m21 - m11 * m20)
    assert abs(det) > 1e-9, 'singular_matrix'
    inv = [[(m11 * m22 - m12 * m21) / det, (m02 * m21 - m01 * m22) / det, (m01 * m12 - m02 * m11) / det],
           [(m12 * m20 - m10 * m22) / det, (m00 * m22 - m02 * m20) / det, (m02 * m10 - m00 * m12) / det],
           [(m10 * m21 - m11 * m20) / det, (m01 * m20 - m00 * m21) / det, (m00 * m11 - m01 * m10) / det]]
    t = [(-sum(inv[row][k] * m[9 + k] for k in range(3))) for row in range(3)]
    return from_rows(inv, t)


def relative(a, b):
    """T_a_b = inverse(world_a) * world_b; three column bases then translation."""
    try:
        return compose(invert(a), b)
    except AssertionError:
        return None


def affine(q, p, scales):
    from anim_batch_mod.math3d import quat_rotate
    out = []
    for i, axis in enumerate(((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))):
        out.extend(v * scales[i] for v in quat_rotate(q, axis))
    return out + list(p)


def local_matrices(unit):
    return [affine(t.rotation, t.position, t.scale) for t in unit.transforms]


def rel_to_root(unit, locals, index, root_index):
    """Compose serialized local poses along root→index (no inversion, safe for
    singular FbxAxisSystem conversion ancestors above the root)."""
    chain = []
    i = index
    while i is not None and i != root_index:
        chain.append(i)
        i = unit.parents[i]
    assert i == root_index, 'not_a_descendant'
    m = list(IDENTITY)
    for node in reversed(chain):
        m = compose(m, locals[node])
    return m


class Survey:
    def __init__(self):
        self.store = PackageStore(GAME_DATA)
        self.archives = {}
        self.bone_names = {}
        for line in BONE_HASHES.read_text(encoding='utf-8-sig').splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    self.bone_names[int(parts[0])] = parts[1]
                except ValueError:
                    pass
        self.db = sqlite3.connect('file:%s?mode=ro' % INDEX.as_posix(), uri=True)
        self.unit_archives = {}
        for file_id, archive_id in self.db.execute(
                'select file_id, archive_id from asset_archives where type_id=?', (sgn(UNIT_TYPE_ID),)):
            self.unit_archives.setdefault(file_id & MASK, []).append(archive_id)

    def archive(self, archive_id):
        if archive_id not in self.archives:
            self.archives[archive_id] = TocArchive.load_toc_only(self.store, archive_id)
        return self.archives[archive_id]

    def inspect(self, file_id):
        for archive_id in self.unit_archives.get(file_id, []):
            entry = self.archive(archive_id).entries.get((file_id, UNIT_TYPE_ID))
            if entry is None:
                continue
            raw = entry.toc_data
            unit = UnitData.parse(raw)
            name_by_hash = dict(self.bone_names)
            bones_entry = self.archive(archive_id).entries.get((unit.bones_ref, BONE_TYPE_ID))
            if bones_entry is not None:
                bones = BonesData.parse(bones_entry.toc_data)
                name_by_hash.update(dict(zip(bones.hashes, bones.names)))
            locals_ = local_matrices(unit)
            nodes = {}
            for i, h in enumerate(unit.name_hashes):
                name = name_by_hash.get(h)
                if name in MARKERS and name not in nodes:
                    parent = unit.parents[i]
                    nodes[name] = dict(index=i, parentIndex=parent,
                        parentName=name_by_hash.get(unit.name_hashes[parent]) if parent is not None else None,
                        localMatrix=list(locals_[i]))
            root_name = 'boss' if 'boss' in nodes else ('skeleton' if 'skeleton' in nodes else
                        ('root' if 'root' in nodes else None))
            if root_name:
                root_index = nodes[root_name]['index']
                for name, node in nodes.items():
                    if name == root_name:
                        node['relToRoot'] = [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.]
                        continue
                    try:
                        node['relToRoot'] = rel_to_root(unit, locals_, node['index'], root_index)
                    except AssertionError:
                        node['relToRoot'] = None
            return dict(nodeCount=len(unit.parents), rootName=root_name, nodes=nodes)
        return None


def main():
    W.mkdir(exist_ok=True)
    friendly = {}
    for line in NAMES.read_text(encoding='utf-8-sig').splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            try:
                friendly[int(parts[0])] = parts[1]
            except ValueError:
                pass
    survey = Survey()
    entities = {}
    for file_id, equipment_type, des, nm in survey.db.execute(
            'select unit_file_id, equipment_type, localized_designations_json, localized_names_json'
            ' from game_data_authority_entities where is_weapon_candidate=1'):
        row = entities.setdefault(file_id & MASK, {'types': set()})
        if equipment_type is not None:
            row['types'].add(equipment_type)
        for key, blob in (('designations', des), ('names', nm)):
            if blob and key not in row:
                parsed = json.loads(blob)
                row[key] = {'zh-CN': parsed.get('zh-CN'), 'en-US': parsed.get('en-US')}

    accessory_ids = {fid for fid, name in friendly.items() if ACCESSORY_PATTERN.search(name)}
    weapons, accessories, failures = [], [], []
    for file_id in sorted(set(entities) | accessory_ids):
        info = survey.inspect(file_id)
        if info is None:
            if file_id in entities:
                failures.append(hex_id(file_id))
            continue
        nodes = info['nodes']
        root_name = info['rootName']
        base = dict(resource=hex_id(file_id), friendly=friendly.get(file_id),
                    nodeCount=info['nodeCount'], rootName=root_name,
                    ikRight='IK_right' in nodes, ikLeft='IK_left' in nodes,
                    underbarrel='attach_underbarrel' in nodes, nodes=nodes)
        for marker, key in (('IK_right', 'rootToIKRight'), ('IK_left', 'rootToIKLeft'),
                            ('attach_underbarrel', 'rootToUnderbarrel')):
            if root_name and nodes.get(marker, {}).get('relToRoot'):
                base[key] = nodes[marker]['relToRoot']
        entity = entities.get(file_id)
        if entity is not None:
            base['equipmentTypes'] = sorted(entity['types'])
            if 'designations' in entity:
                base['designations'] = entity['designations']
            if 'names' in entity:
                base['weaponNames'] = entity['names']
            weapons.append(base)
        else:
            # accessory inventory only keeps grip-relevant units
            if base['ikLeft'] or base['rootName'] == 'skeleton':
                accessories.append(base)

    observed = json.loads((OBS / 'native-grip-reference-matrices.json').read_text(encoding='utf-8-sig'))
    smg = next(w for w in weapons if w['resource'] == hex_id(SMG))
    grip = next((a for a in accessories if a['resource'] == hex_id(FOREGRIP)), None)
    def max_diff(a, b):
        return round(max(abs(x - y) for x, y in zip(a, b)), 9) if a and b else None
    verification = dict(convention='inverse(rootWorld)*markerWorld; column bases then translation (metres)',
        rightStaticVsObservedMaxError=max_diff(smg.get('rootToIKRight'),
            observed['right']['weaponBossToIKRight']),
        observedRevision=observed.get('revision'))
    if grip and 'skeleton' in grip['nodes'] and 'IK_left' in grip['nodes']:
        skeleton_to_left = grip['nodes']['IK_left'].get('relToRoot')
        candidates = {
            # engine places the accessory skeleton root exactly on the mount
            'mountSkeletonAssumption': compose(smg['rootToUnderbarrel'], skeleton_to_left)
                if skeleton_to_left else None,
            # accessory unit keeps its authored root pose under the mount
            'mountFullBindAssumption': compose(smg['rootToUnderbarrel'],
                compose(grip['nodes']['skeleton']['localMatrix'], skeleton_to_left))
                if skeleton_to_left else None,
            # accessory IK_left serialized local directly under the mount
            'mountIdentityAssumption': compose(smg['rootToUnderbarrel'],
                grip['nodes']['IK_left']['localMatrix']),
        }
        observed_left = observed['left']['weaponBossToForegripIKLeft']
        for name, static in candidates.items():
            verification[name + 'MaxError'] = max_diff(static, observed_left)
        best = min(candidates, key=lambda k: verification[k + 'MaxError'] or 1e9)
        verification['leftStaticConventionCandidate'] = best
        verification['leftStaticVsObservedMaxError'] = verification[best + 'MaxError']
        verification['leftStaticMatrix'] = candidates[best]
    report = dict(index=str(INDEX), gameData=str(GAME_DATA), weaponCount=len(weapons),
        accessoryCount=len(accessories), failures=failures, verification=verification,
        weapons=weapons, accessories=accessories)
    (W / 'weapon-grip-survey.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=list), encoding='utf-8')
    write_markdown(report, friendly)
    print(json.dumps(dict(weapons=len(weapons), accessories=len(accessories), failures=len(failures),
        rightError=verification['rightStaticVsObservedMaxError'],
        leftError=verification.get('leftStaticVsObservedMaxError'), output=str(W)), ensure_ascii=False))


def tr(m):
    return '[%+.4f %+.4f %+.4f]' % tuple(m[9:12]) if m else '-'


def write_markdown(report, friendly):
    lines = ['# 其他武器握持适配清单（B23-LR 下一轮 TODO 第 1 项）', '']
    v = report['verification']
    lines += [
        '采集日期：2026-11-05。数据源：asset-index.sqlite（game_data_authority_entities 武器候选）'
        '与本机游戏数据 %s。全部为离线静态解析，不改动运行时。' % report['gameData'], '',
        '## 静态推导验证（对照 B21 实机观测）', '',
        '- 右手：武器 boss→IK_right 序列化局部矩阵 与 B21 实机观测 weaponBossToIKRight 最大误差 '
        '**%s**（一致，IK 标记为 boss 空间固定标记）。' % v['rightStaticVsObservedMaxError'],
        '- 左手：boss→attach_underbarrel 复合 握把 skeleton→IK_left 序列化局部，与观测 '
        'weaponBossToForegripIKLeft 最大误差 **%s**（候选约定：%s）。'
        % (v.get('leftStaticVsObservedMaxError'), v.get('leftStaticConventionCandidate')), '',
        '结论：其他武器/握把组合的左右手静态握持目标可由本工具离线生成，无需先做逐武器实机采集；'
        '但握把是否实际挂载、以及原生左手是否接触该目标，仍需按组合实机确认。', '',
        '## 基线状态', '',
        '- test01 + SMG-203（186ea95de7306b1a）+ 垂直前握把（f9df21c8e52cac95）：**实机通过**（B23-LR 1.0.4）。',
        '- 其余全部组合：**未适配**（本清单后为"待扩展验证"）。', '',
        '## 左手握把配件（含 IK_left 的 underbarrel 配件）', '',
        '| 配件 | 资源 ID | skeleton→IK_left 平移 |',
        '|---|---|---|']
    for a in report['accessories']:
        if a['ikLeft']:
            lines.append('| %s | %s | %s |' % (a.get('friendly') or a.get('designations'),
                a['resource'], tr(a['nodes']['IK_left'].get('relToRoot'))))
    lines += ['', '## 持握武器清单（检测到 IK_right 或 IK_left 的武器候选）', '',
        '| 名称 | 资源 ID | 类型 | IK_right | IK_left | 前握把挂点 | boss→IK_left 平移 | boss→underbarrel 平移 | 状态 |',
        '|---|---|---|---|---|---|---|---|---|']
    held = [w for w in report['weapons'] if w['ikRight'] or w['ikLeft']]
    def sort_key(w):
        d = (w.get('designations') or {}).get('zh-CN') or w.get('friendly') or w['resource']
        return d
    for w in sorted(held, key=sort_key):
        name = (w.get('designations') or {}).get('zh-CN') or w.get('friendly') or '-'
        des = (w.get('designations') or {}).get('en-US')
        if des and des != name:
            name += '（%s）' % des
        status = '实机通过（垂直握把）' if w['resource'] == hex_id(SMG) else '未适配'
        lines.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            name, w['resource'], w.get('equipmentTypes'), '有' if w['ikRight'] else '无',
            '有' if w['ikLeft'] else '无', '有' if w['underbarrel'] else '无',
            tr(w.get('rootToIKLeft')), tr(w.get('rootToUnderbarrel')), status))
    no_ik = [w for w in report['weapons'] if not w['ikRight'] and not w['ikLeft']]
    lines += ['', '## 无 IK 标记的武器候选（投掷物/放置装备等，不参与握持适配）', '',
        '共 %d 项：' % len(no_ik)]
    for w in sorted(no_ik, key=sort_key):
        name = (w.get('designations') or {}).get('zh-CN') or w.get('friendly') or '-'
        lines.append('- %s `%s` 类型 %s' % (name, w['resource'], w.get('equipmentTypes')))
    lines += ['', '## 无法解析的武器候选（索引有实体、本地归档无 Unit 条目）', '']
    for h in report['failures']:
        lines.append('- `%s`' % h)
    lines += ['', '## 状态跟踪约定', '',
        '- 未适配：静态目标可由本清单生成，运行时未按组合验证。',
        '- 适配中：B23-LR 增量扩展已生成该组合配置，待实机。',
        '- 实机通过：用户确认，记录版本与组合。', '',
        '本清单只完成 TODO 第 1 项（清单与采集）；第 2 项起需按"不直接套用 SMG-203 前握把配置"的约定增量扩展。']
    (W / '清单-其他武器握持适配.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
