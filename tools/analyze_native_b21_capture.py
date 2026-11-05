"""Analyze B21 JSONL observations with standard Python; never attach to the game.

Matrices contain three basis columns followed by world/local translation.
Each loaded event starts a session. Relations retain both unit identities and
world labels; all cross-unit relations remain ownership-unverified candidates.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

MARKER = '[native_capture] '
ARM = {side + name for side in ('l_', 'r_') for name in
       ('clavicle', 'shoulder', 'elbow', 'hand', 'hand_twist')}
GRIPS = {'l_hand', 'r_hand', 'l_hand_twist', 'r_hand_twist',
         'attach_hand_l', 'attach_hand_r', 'weapon_aim', 'IK_left', 'IK_right'}


def transpose(a):
    return [list(r) for r in zip(*a)]


def mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def mv(a, v):
    return [sum(a[r][k] * v[k] for k in range(3)) for r in range(3)]


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def basis(m):
    return [[m[r + c * 3] for c in range(3)] for r in range(3)]


def determinant(a):
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
            - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))


def inverse(a):
    d = determinant(a)
    lengths = [norm(c) for c in transpose(a)]
    if min(lengths) < 1e-12 or abs(d) < math.prod(lengths) * 1e-8:
        raise ValueError('singular or ill-conditioned basis')
    adj = [
        [a[1][1]*a[2][2]-a[1][2]*a[2][1], a[0][2]*a[2][1]-a[0][1]*a[2][2], a[0][1]*a[1][2]-a[0][2]*a[1][1]],
        [a[1][2]*a[2][0]-a[1][0]*a[2][2], a[0][0]*a[2][2]-a[0][2]*a[2][0], a[0][2]*a[1][0]-a[0][0]*a[1][2]],
        [a[1][0]*a[2][1]-a[1][1]*a[2][0], a[0][1]*a[2][0]-a[0][0]*a[2][1], a[0][0]*a[1][1]-a[0][1]*a[1][0]],
    ]
    return [[v / d for v in row] for row in adj]


def rotation(m):
    """Proper polar rotation; reject reflections instead of calling them twists."""
    a = basis(m)
    if determinant(a) <= 0:
        return None
    try:
        scale = max(norm(c) for c in transpose(a))
        a = [[v / scale for v in row] for row in a]
        for _ in range(40):
            inv_t = transpose(inverse(a))
            b = [[(a[r][c] + inv_t[r][c]) / 2 for c in range(3)] for r in range(3)]
            error = max(abs(b[r][c] - a[r][c]) for r in range(3) for c in range(3))
            a = b
            if error < 1e-10:
                return a
    except (ValueError, ZeroDivisionError):
        pass
    return None


def angle(a, b=None):
    if a is None:
        return None
    r = a if b is None else mul(transpose(a), b)
    return math.degrees(math.acos(max(-1.0, min(1.0, (sum(r[i][i] for i in range(3)) - 1) / 2))))


def valid_matrix(m):
    return (isinstance(m, list) and len(m) == 12 and
            all(type(v) in (int, float) and math.isfinite(v) and abs(v) < 1e12 for v in m))


def affine_relative(a, b):
    inv = inverse(basis(a))
    r = mul(inv, basis(b))
    return [r[j][c] for c in range(3) for j in range(3)] + mv(inv, [b[9 + j] - a[9 + j] for j in range(3)])


def compose(a, b):
    r = mul(basis(a), basis(b))
    t = mv(basis(a), b[9:])
    return [r[j][c] for c in range(3) for j in range(3)] + [t[j] + a[9 + j] for j in range(3)]


def summary(values):
    if not values:
        return dict(count=0)
    ordered = sorted(values)
    return dict(count=len(values), minimum=min(values), maximum=max(values),
                mean=statistics.fmean(values), median=statistics.median(values),
                p95=ordered[max(0, math.ceil(len(ordered) * .95) - 1)],
                stddev=statistics.pstdev(values))


class Metrics:
    def __init__(self):
        self.values = defaultdict(list)

    def add(self, key, value):
        if value is not None:
            if isinstance(value, (list, tuple)):
                for axis, v in zip('XYZ', value):
                    self.values[key + axis].append(v)
            else:
                self.values[key].append(value)

    def report(self):
        return {k: summary(v) for k, v in sorted(self.values.items())}


def unit_key(row):
    return (row['world'], row['id'], row['resource'], row['layout'], row['nodeCount'])


def unit_meta(row):
    return {k: row[k] for k in ('world', 'id', 'resource', 'kind', 'layout', 'nodeCount')}


def node_meta(row, node):
    return dict(unit_meta(row), name=node['name'], index=node['index'], skinInput=node['skinInput'])


def is_hand(name):
    return name in GRIPS or name.endswith(('_l_hand', '_r_hand', '_l_hand_twist', '_r_hand_twist'))


def prepare_row(row):
    assert row['phase'] in ('update', 'render')
    assert all(type(row[k]) is int and row[k] >= 1 for k in ('sample', 'id', 'world', 'nodeCount'))
    assert type(row['frame']) is int and type(row['time']) in (int, float) and math.isfinite(row['time'])
    assert all(isinstance(row[k], str) for k in ('resource', 'kind', 'layout'))
    assert row.get('owner') == 'unverified'
    assert isinstance(row['nodes'], list) and row['nodes']
    seen_names, seen_indices = set(), set()
    for n in row['nodes']:
        assert isinstance(n['name'], str) and n['name'] not in seen_names
        assert type(n['index']) is int and 1 <= n['index'] <= row['nodeCount'] and n['index'] not in seen_indices
        assert type(n['skinInput']) is bool
        assert valid_matrix(n['worldMatrix']) and valid_matrix(n['localMatrix'])
        assert n.get('parentWorld') is None or valid_matrix(n['parentWorld'])
        seen_names.add(n['name'])
        seen_indices.add(n['index'])
        n['_worldRotation'] = rotation(n['worldMatrix'])
        n['_localRotation'] = rotation(n['localMatrix'])
    row['_nodes'] = {n['name']: n for n in row['nodes']}
    return row


class Session:
    def __init__(self, number, loaded, line, prefix, first_sample=1, last_sample=None):
        self.number, self.loaded, self.line, self.prefix = number, loaded, line, prefix
        self.first_sample, self.last_sample = first_sample, last_sample
        self.events, self.issues = Counter(), Counter()
        self.examples = []
        self.block = None
        self.units, self.callbacks, self.relations = {}, {}, {}
        self.phase_samples = Counter()
        self.sample_pairs = 0
        self.complete = None

    def issue(self, kind, detail=None):
        self.issues[kind] += 1
        if detail is not None and len(self.examples) < 30:
            self.examples.append(dict(kind=kind, detail=str(detail)[:250]))

    def begin_block(self, sample, frame):
        if self.block is not None and (sample, frame) != self.block['key']:
            self.flush()
        if self.block is None:
            self.block = dict(key=(sample, frame), rows=defaultdict(dict),
                              begins=set(), ends=set(), duplicates=set())

    def accept(self, row, line):
        event = row.get('event', 'missing_event')
        self.events[event] += 1
        if event == 'complete':
            self.complete = row
        if event in ('unavailable', 'callback_error', 'incomplete_pair'):
            self.issue(event, dict(line=line, **row))
        if event == 'scan':
            if row.get('errors', 0):
                self.issue('scan_errors', row)
            if row.get('truncated', 0):
                self.issue('scan_truncated', row)
        if event not in ('phase_begin', 'phase_end', 'unit'):
            return
        try:
            sample, frame, phase = row['sample'], row['frame'], row['phase']
            assert type(sample) is int and sample >= 1 and type(frame) is int and phase in ('update', 'render')
            self.begin_block(sample, frame)
            b = self.block
            if event == 'phase_begin':
                assert row.get('indexBase') == 1 and row.get('readOnly') is True
                if phase in b['begins']:
                    self.issue('duplicate_phase_begin', line)
                b['begins'].add(phase)
            elif event == 'phase_end':
                b['ends'].add(phase)
            else:
                row = prepare_row(row)
                key = unit_key(row)
                if (phase, key) in b['duplicates']:
                    return
                if key in b['rows'][phase]:
                    self.issue('duplicate_unit_sample', dict(line=line, id=row['id']))
                    del b['rows'][phase][key]
                    b['duplicates'].add((phase, key))
                else:
                    row['_line'] = line
                    b['rows'][phase][key] = row
        except (AssertionError, KeyError, TypeError, ValueError, OverflowError) as error:
            self.issue('invalid_record', dict(line=line, reason=str(error)))

    def observe_unit(self, row):
        key = unit_key(row)
        item = self.units.setdefault(key, dict(**unit_meta(row), phases=Counter(), nodes={}))
        item['phases'][row['phase']] += 1
        for n in row['nodes']:
            record = item['nodes'].setdefault((n['name'], n['index']), dict(
                name=n['name'], index=n['index'], skinInput=n['skinInput'],
                serializedParent=n.get('serializedParent'), runtimeParents=Counter(),
                parentStates=Counter(), metrics=Metrics(), invalidRotationCount=0))
            record['runtimeParents'][str(n.get('runtimeParent'))] += 1
            record['parentStates'][n.get('parentState', 'unknown')] += 1
            if n['_worldRotation'] is None:
                record['invalidRotationCount'] += 1
            record['metrics'].add('worldBasisLength', [norm(c) for c in transpose(basis(n['worldMatrix']))])
            if n.get('parentWorld') is not None:
                predicted = compose(n['parentWorld'], n['localMatrix'])
                record['metrics'].add('candidateParentPositionResidualMetres',
                                      norm([predicted[9 + j] - n['worldMatrix'][9 + j] for j in range(3)]))
                rp = rotation(predicted)
                if rp is not None and n['_worldRotation'] is not None:
                    record['metrics'].add('candidateParentRotationResidualDegrees', angle(rp, n['_worldRotation']))

    def relation(self, category, a, an, b, bn):
        na, nb = a['_nodes'].get(an), b['_nodes'].get(bn)
        if na is None or nb is None or a['world'] != b['world']:
            return
        key = (category, unit_key(a), an, na['index'], unit_key(b), bn, nb['index'], a['phase'])
        item = self.relations.setdefault(key, dict(category=category, phase=a['phase'],
            a=node_meta(a, na), b=node_meta(b, nb), owner='same_unit' if unit_key(a) == unit_key(b) else 'unverified',
            samples=0, firstSample=a['sample'], lastSample=a['sample'],
            firstLogLines=[a['_line'], b['_line']], metrics=Metrics(), invalidRotationCount=0,
            firstRelativeAffine=None, firstOffset=None, _firstRotation=None))
        item['samples'] += 1
        item['lastSample'] = a['sample']
        item['metrics'].add('callbackTimeSeconds', a['time'])
        ma, mb = na['worldMatrix'], nb['worldMatrix']
        delta = [mb[9 + j] - ma[9 + j] for j in range(3)]
        item['metrics'].add('worldOriginDistanceMetres', norm(delta))
        if item['firstRelativeAffine'] is None:
            try:
                item['firstRelativeAffine'] = affine_relative(ma, mb)
            except ValueError:
                pass
        ra, rb = na['_worldRotation'], nb['_worldRotation']
        if ra is None or rb is None:
            item['invalidRotationCount'] += 1
            return
        offset = mv(transpose(ra), delta)
        relrot = mul(transpose(ra), rb)
        if item['_firstRotation'] is None:
            item['firstOffset'], item['_firstRotation'] = offset, relrot
        item['metrics'].add('offsetInARotationFrameMetres', offset)
        item['metrics'].add('offsetChangeFromFirstMetres', norm([offset[i] - item['firstOffset'][i] for i in range(3)]))
        item['metrics'].add('relativeRotationDegrees', angle(relrot))
        item['metrics'].add('rotationChangeFromFirstDegrees', angle(item['_firstRotation'], relrot))

    def phase_relations(self, rows):
        by_world = defaultdict(list)
        for row in rows:
            self.observe_unit(row)
            by_world[row['world']].append(row)
        for group in by_world.values():
            avatars = [r for r in group if r['kind'] == 'avatar']
            models = [r for r in group if r['kind'] in ('native_armor', 'test01_model')]
            guns = [r for r in group if r['kind'] == 'weapon']
            grips = [r for r in group if r['kind'] == 'foregrip']
            for a in avatars:
                for an, bn in (('l_hand', 'attach_hand_l'), ('r_hand', 'attach_hand_r'),
                               ('attach_hand_r', 'weapon_aim')):
                    self.relation('avatar_internal', a, an, a, bn)
                for name in a['_nodes']:
                    if name.startswith('hd2n_'):
                        for native in ('l_hand', 'r_hand', 'l_hand_twist', 'r_hand_twist'):
                            if name.endswith('_' + native):
                                self.relation('hybrid_native_to_source', a, native, a, name)
                for model in models:
                    for name, n in model['_nodes'].items():
                        if n['skinInput'] and (name in ARM or (name.startswith('hd2n_') and is_hand(name))):
                            self.relation('avatar_to_skin_input', a, name, model, name)
                for gun in guns:
                    for an, bn in (('l_hand', 'IK_left'), ('l_hand_twist', 'IK_left'), ('attach_hand_l', 'IK_left'),
                                   ('r_hand', 'IK_right'), ('r_hand_twist', 'IK_right'), ('attach_hand_r', 'IK_right'),
                                   ('attach_hand_r', 'boss'), ('weapon_aim', 'boss'), ('weapon_aim', 'IK_right')):
                        self.relation('avatar_to_weapon_candidate', a, an, gun, bn)
                for grip in grips:
                    for an in ('l_hand', 'l_hand_twist', 'attach_hand_l'):
                        self.relation('avatar_to_foregrip_candidate', a, an, grip, 'IK_left')
            for model in models:
                for name, n in model['_nodes'].items():
                    if not n['skinInput']:
                        continue
                    side = ('left' if name == 'l_hand' or name.endswith('_l_hand') else
                            'right' if name == 'r_hand' or name.endswith('_r_hand') else None)
                    if side is None:
                        continue
                    for gun in guns:
                        self.relation('skin_input_to_weapon_candidate', model, name, gun, 'IK_' + side)
                    if side == 'left':
                        for grip in grips:
                            self.relation('skin_input_to_foregrip_candidate', model, name, grip, 'IK_left')
            for gun in guns:
                for grip in grips:
                    for an, bn in (('attach_underbarrel', 'skeleton'), ('attach_underbarrel', 'IK_left'),
                                   ('IK_left', 'IK_left')):
                        self.relation('weapon_to_foregrip_candidate', gun, an, grip, bn)
            for grip in grips:
                self.relation('foregrip_internal', grip, 'skeleton', grip, 'IK_left')

    def callback_pair(self, a, b):
        for name, na in a['_nodes'].items():
            nb = b['_nodes'].get(name)
            if nb is None or nb['index'] != na['index']:
                self.issue('node_pair_missing', dict(id=a['id'], name=name))
                continue
            key = unit_key(a) + (name, na['index'])
            item = self.callbacks.setdefault(key, dict(node=node_meta(a, na), pairs=0,
                firstSample=a['sample'], lastSample=a['sample'], firstLogLines=[a['_line'], b['_line']],
                metrics=Metrics(), invalidRotationCount=0))
            item['pairs'] += 1
            item['lastSample'] = a['sample']
            item['metrics'].add('callbackGapSeconds', b['time'] - a['time'])
            for space in ('world', 'local'):
                x, y = na[space + 'Matrix'], nb[space + 'Matrix']
                delta = [y[9 + j] - x[9 + j] for j in range(3)]
                item['metrics'].add(space + 'PositionDeltaMetres', delta)
                item['metrics'].add(space + 'PositionDistanceMetres', norm(delta))
                ra, rb = na['_' + space + 'Rotation'], nb['_' + space + 'Rotation']
                if ra is not None and rb is not None:
                    item['metrics'].add(space + 'RotationDeltaDegrees', angle(ra, rb))
                else:
                    item['invalidRotationCount'] += 1

    def flush(self):
        block, self.block = self.block, None
        if block is None:
            return
        sample = block['key'][0]
        if sample < self.first_sample or (self.last_sample is not None and sample > self.last_sample):
            return
        complete = block['begins'] & block['ends']
        for phase in ('update', 'render'):
            if phase in complete:
                self.phase_samples[phase] += 1
                self.phase_relations(list(block['rows'][phase].values()))
            elif phase in block['begins'] or block['rows'][phase]:
                self.issue('partial_phase_excluded', dict(sample=sample, phase=phase))
        if complete == {'update', 'render'}:
            self.sample_pairs += 1
            a, b = block['rows']['update'], block['rows']['render']
            self.issues['unpaired_unit_snapshots'] += len(a.keys() ^ b.keys())
            for key in a.keys() & b.keys():
                self.callback_pair(a[key], b[key])
        elif 'update' in complete:
            self.issue('sample_without_render', sample)

    def report(self):
        self.flush()

        def finish(item):
            return {k: v.report() if isinstance(v, Metrics) else dict(v) if isinstance(v, Counter) else v
                    for k, v in item.items() if not k.startswith('_')}

        units = []
        for _, row in sorted(self.units.items()):
            units.append(dict(finish(row), nodes=[finish(n) for _, n in sorted(row['nodes'].items())]))
        return dict(session=self.number, loadedEventPresent=self.loaded is not None, startLine=self.line,
            logTimestamp=self.prefix, loaded=self.loaded, complete=self.complete, eventCounts=dict(self.events),
            issues={k: v for k, v in self.issues.items() if v}, issueExamples=self.examples,
            completedPhases=dict(self.phase_samples), completedSamplePairs=self.sample_pairs,
            units=units, layouts=sorted({r['layout'] for r in units if r['kind'] == 'avatar'}),
            callbackDifferences=[finish(row) for _, row in sorted(self.callbacks.items())],
            relations=[finish(row) for _, row in sorted(self.relations.items())])


def analyze(path, provenance='unverified', first_sample=1, last_sample=None):
    path = Path(path)
    assert provenance in ('game_log', 'simulated_fixture', 'unverified')
    if provenance == 'game_log' and 'fixture' in path.name.lower():
        raise ValueError('Fixture-named input cannot be classified as a game log.')
    reports, current, parse_errors = [], None, []
    ignored, marker_lines = 0, 0
    with path.open(encoding='utf-8-sig', errors='replace') as stream:
        for line_number, line in enumerate(stream, 1):
            if MARKER not in line:
                ignored += 1
                continue
            marker_lines += 1
            prefix, body = line.split(MARKER, 1)
            try:
                row = json.loads(body)
                if not isinstance(row, dict):
                    raise ValueError('event is not an object')
            except (ValueError, TypeError) as error:
                parse_errors.append(dict(line=line_number, reason=str(error)[:150]))
                continue
            if row.get('event') == 'loaded':
                if current is not None:
                    reports.append(current.report())
                current = Session(len(reports) + 1, row, line_number, prefix.strip(), first_sample, last_sample)
            elif current is None:
                current = Session(len(reports) + 1, None, line_number, prefix.strip(), first_sample, last_sample)
            current.accept(row, line_number)
    if current is not None:
        reports.append(current.report())
    pairs = sum(r['completedSamplePairs'] for r in reports)
    observed = any(r['units'] for r in reports)
    issues = parse_errors or any(r['issues'] or not r['loadedEventPresent'] for r in reports)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(status='NO_SAMPLES' if not observed else 'ANALYZED_WITH_DIAGNOSTICS' if issues else 'ANALYZED',
        input=str(path.resolve()), inputSha256=sha, provenance=provenance,
        gamePoseCaptured=provenance == 'game_log' and observed, provenanceSpecifiedByCaller=True,
        markerLines=marker_lines, ignoredLines=ignored, parseErrors=parse_errors,
        sampleFilter=dict(first=first_sample, last=last_sample), completedSamplePairs=pairs,
        indexBase=1, matrixConvention='three basis columns, then translation; twelve numeric elements',
        rotationMethod='proper polar rotation; reflected/singular bases excluded from angular metrics',
        relativeOffsetUnits='metres in the proper rotation frame of A, with scale removed',
        limits=[
            'Every cross-unit relation is a candidate with unverified ownership; proximity and correlation do not identify an IK driver.',
            'Session boundaries, both unit instance IDs, layouts and per-snapshot world labels are retained; no cross-session or cross-world pairing.',
            'World labels are enumeration labels, not persistent engine IDs. Unit IDs are collector-local to each loaded session.',
            'The update/render callbacks have unverified positions relative to engine animation/IK.',
            'A native_107 Avatar confirms the observed node layout only, not that all model/animation Mods are absent.',
            'Candidate parent composition is a residual check; scene_graph_parent alone does not identify an external Unit parent.',
            'Partial callback phases are excluded. Action names such as reload/aim are not recorded by this collector.',
        ], sessions=reports)


def markdown(report):
    lines = ['# B21 动态日志分析', '',
        f"数据来源：{report['provenance']}；状态：{report['status']}。",
        f"已配对回调：{report['completedSamplePairs']} 组；会话：{len(report['sessions'])}。", '']
    if not report['gamePoseCaptured']:
        lines += ['**此报告不包含已确认的游戏实机采集。模拟数据仅用于验证分析程序。**', '']
    lines += ['下列跨 Unit 关系均为候选关系，所属角色及 IK 驱动优先级尚未确认。',
              '旋转采用去除缩放后的正交基；偏移变化不能单独证明或排除握持错误。', '']
    for session in report['sessions']:
        lines += [f"## 会话 {session['session']}", '',
            f"布局：{', '.join(session['layouts']) or '未发现 Avatar'}；完整回调对：{session['completedSamplePairs']}。",
            f"诊断：{json.dumps(session['issues'], ensure_ascii=False)}。", '',
            '### 手部在两个回调之间的变化', '',
            '| Unit 资源／实例／世界 | 骨骼 | 配对数 | 世界位置差最大值 (m) | 世界旋转差最大值 (°) |',
            '| --- | --- | ---: | ---: | ---: |']
        for row in session['callbackDifferences']:
            n, m = row['node'], row['metrics']
            if not is_hand(n['name']):
                continue
            r = m.get('worldRotationDeltaDegrees', {}).get('maximum')
            lines.append(f"| {n['resource']} / {n['id']} / {n['world']} | {n['name']} | {row['pairs']} | "
                         f"{m['worldPositionDistanceMetres']['maximum']:.6g} | {r if r is None else format(r, '.6g')} |")
        lines += ['', '### 渲染回调中的候选对应关系', '',
            '完整数据（包括 update、局部矩阵变化、索引和相对矩阵）保留在同名 JSON 中。', '',
            '| 关系 | A 骨骼 (实例) → B 骨骼 (实例) | 世界编号 | 原点距离中位数 (m) | 相对偏移较首帧最大变化 (m) | 相对朝向较首帧最大变化 (°) |',
            '| --- | --- | ---: | ---: | ---: | ---: |']
        for row in session['relations']:
            a, b, m = row['a'], row['b'], row['metrics']
            if row['phase'] != 'render' or not (is_hand(a['name']) or is_hand(b['name'])):
                continue
            d = m['worldOriginDistanceMetres']['median']
            p = m.get('offsetChangeFromFirstMetres', {}).get('maximum')
            r = m.get('rotationChangeFromFirstDegrees', {}).get('maximum')
            lines.append(f"| {row['category']} | {a['name']} ({a['id']}) → {b['name']} ({b['id']}) | "
                         f"{a['world']} | {d:.6g} | {p if p is None else format(p, '.6g')} | "
                         f"{r if r is None else format(r, '.6g')} |")
        lines.append('')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--provenance', choices=('game_log', 'simulated_fixture', 'unverified'), default='unverified')
    parser.add_argument('--output', type=Path, required=True, help='JSON report path; a Markdown report is written beside it.')
    parser.add_argument('--first-sample', type=int, default=1)
    parser.add_argument('--last-sample', type=int)
    args = parser.parse_args()
    if args.first_sample < 1 or (args.last_sample is not None and args.last_sample < args.first_sample):
        parser.error('Invalid sample interval')
    report = analyze(args.log, args.provenance, args.first_sample, args.last_sample)
    if args.output.resolve() == args.log.resolve() or args.output.with_suffix('.md').resolve() == args.log.resolve():
        parser.error('Output must not overwrite the capture log')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    args.output.with_suffix('.md').write_text(markdown(report), encoding='utf-8')
    print(f"{report['status']}: {len(report['sessions'])} sessions, {report['completedSamplePairs']} callback pairs, "
          f"provenance={report['provenance']}, gamePoseCaptured={report['gamePoseCaptured']}")


if __name__ == '__main__':
    main()
