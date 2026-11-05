"""Replace only the Avatar envelope of verified v13; never rebake animations."""
import copy
import hashlib
import shutil
import struct
import sys
import tomllib
from collections import Counter
from pathlib import Path

from package_native_v13 import ROOT, WORK, PROJECT, RELEASE, digest, load, save_json
from package_native_v10 import records, payload
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.archive import InlinePatchWriter, TocArchive, TocEntry
from anim_batch_mod.constants import UNIT_TYPE_ID, ANIMATION_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID
from anim_batch_mod.native_skeleton import load_avatar_template, load_manifest, append_unit, append_bones, append_state_machine_masks
from anim_batch_mod.formats import UnitData, BonesData


def main():
    baseline = WORK/'baseline-v13'
    baseline.mkdir(exist_ok=True)
    for name in ('animation-final-audit.json', 'package-inspection.json', 'package-report.json'):
        dest = baseline/name
        assert not dest.exists(), 'Already integrated: '+str(dest)
        shutil.copy2(WORK/name, dest)
    shutil.copy2(PROJECT/'animations/build-report.json', baseline/'build-report.json')
    shutil.copy2(PROJECT/'config.toml', baseline/'config.toml')
    shutil.copy2(RELEASE/'delivery-verification.json', baseline/'delivery-verification.json')
    build = load(baseline/'build-report.json')
    old = RELEASE/'project/animations/runtime/9ba626afa44a3aa3.patch_2'
    assert digest(old) == next(r['sha256'] for r in build['files'] if r['path'].endswith('.patch_2'))
    prior_audit = load(baseline/'animation-final-audit.json')
    assert prior_audit['status'] == 'PASS' and prior_audit['animations'] == 3180
    feedback = load(WORK/'feedback.json')
    assert feedback['previewProbes']['C7_expandedStandaloneMesh'] == 'user confirmed preview normal with B3'

    template = PROJECT/'avatar-template/9ba626afa44a3aa3.patch_0'
    template.parent.mkdir(exist_ok=True)
    for suffix in ('', '.gpu_resources', '.stream'):
        shutil.copy2(WORK/('preview-probe/C6/9ba626afa44a3aa3.patch_0'+suffix), Path(str(template)+suffix))
    original = TocEntry(0x4d1c334d294dfa97, UNIT_TYPE_ID, bytearray((WORK/'vanilla-avatar.toc').read_bytes()))
    entry = load_avatar_template(template, original)
    manifest = load_manifest(PROJECT/'source-skeleton.json')
    expanded = copy.deepcopy(entry)
    expanded.toc_data = bytearray(append_unit(entry.toc_data, manifest))
    c7path = WORK/'preview-probe/C7/9ba626afa44a3aa3.patch_0'
    c7 = TocArchive.parse_parts(c7path.read_bytes(), Path(str(c7path)+'.gpu_resources').read_bytes())
    c7entry = c7.entries[original.file_id, UNIT_TYPE_ID]
    assert expanded.toc_data == c7entry.toc_data and expanded.gpu_data == c7entry.gpu_data
    assert len(UnitData.parse(expanded.toc_data).transforms) == 255

    destination = PROJECT/'animations/runtime/9ba626afa44a3aa3.patch_2'
    assert not destination.exists()
    old_records = records(old)
    writer = InlinePatchWriter(TocArchive(0, bytes(56), {}), destination,
                               Counter(r[1] for r in old_records), standalone=True)
    try:
        for row in old_records:
            assert row[3] == row[4] == row[8] == row[9] == 0
            value = expanded if row[1] == UNIT_TYPE_ID else TocEntry(row[0], row[1], payload(old, row))
            writer.append(value)
        paths = writer.finish()
    finally:
        writer.close()

    final_records = records(destination)
    assert [(r[0], r[1]) for r in final_records] == [(r[0], r[1]) for r in old_records]
    verified = []
    for before, after in zip(old_records, final_records):
        before_sha = hashlib.sha256(payload(old, before)).hexdigest()
        after_bytes = payload(destination, after)
        after_sha = hashlib.sha256(after_bytes).hexdigest()
        assert after[2] % 16 == after[3] == after[8] == 0
        if after[1] == UNIT_TYPE_ID:
            assert after_bytes == c7entry.toc_data and after[9] == len(c7entry.gpu_data) and after[4] == 0
        else:
            assert before_sha == after_sha and after[9] == after[4] == 0
        verified.append(dict(id=str(after[0]), type=f'{after[1]:016x}', sha256=after_sha,
                             unchanged=after[1] != UNIT_TYPE_ID))
    assert sum(r[1] == ANIMATION_TYPE_ID for r in final_records) == 3180
    assert Path(str(destination)+'.gpu_resources').read_bytes() == c7entry.gpu_data
    base = ROOT/'outputs/native-fix-20261103'
    def one(kind):
        return payload(destination, next(r for r in final_records if r[1] == kind))
    assert one(BONE_TYPE_ID) == append_bones((base/'bones.toc').read_bytes(), manifest)
    assert one(STATE_MACHINE_TYPE_ID) == append_state_machine_masks((base/'state-machine.toc').read_bytes(),
        BonesData.parse((base/'bones.toc').read_bytes()), manifest)[0]

    config = PROJECT/'config.toml'
    config.write_text(config.read_text(encoding='utf-8').replace('[native_skeleton]',
        '[native_skeleton]\navatar_template = "avatar-template/9ba626afa44a3aa3.patch_0"', 1), encoding='utf-8')
    before_config = tomllib.loads((baseline/'config.toml').read_text(encoding='utf-8'))
    after_config = tomllib.loads(config.read_text(encoding='utf-8'))
    assert after_config['native_skeleton'].pop('avatar_template') == 'avatar-template/9ba626afa44a3aa3.patch_0'
    assert before_config == after_config
    shutil.copy2(config, PROJECT/'animations/config.toml')
    shutil.copytree(template.parent, PROJECT/'animations/avatar-template', dirs_exist_ok=True)
    build['config_sha256'] = digest(config)
    build['avatar_template'] = dict(path='avatar-template/9ba626afa44a3aa3.patch_0', composite_ref=0,
        toc_sha256=hashlib.sha256(entry.toc_data).hexdigest(), gpu_sha256=hashlib.sha256(entry.gpu_data).hexdigest(),
        gpu_bytes=len(entry.gpu_data), original_bind_byte_identical=True)
    build['files'] = [dict(path='runtime/'+p.name, bytes=p.stat().st_size, sha256=digest(p)) for p in paths]
    build['preview_repack'] = dict(animations_rebaked=False, unchanged_animation_payloads=3180,
        original_patch_sha256=digest(old), c6_user_result='normal', c7_user_result='normal')
    save_json(PROJECT/'animations/build-report.json', build)
    report = dict(status='PASS', gameTested=False, componentGameTests={'B3+C6':'normal','B3+C7':'normal'},
        fullCompanionGameTest='pending', animations=3180, unchangedAnimations=3180, unchangedBones=True,
        unchangedStateMachine=True, avatarEqualsC7=True, originalAvatarNodes=107, extendedAvatarNodes=255,
        gpuBytes=len(entry.gpu_data), gpuSha256=hashlib.sha256(entry.gpu_data).hexdigest(),
        baselinePatchSha256=digest(old), baselineAuditSha256=digest(baseline/'animation-final-audit.json'),
        patchSha256=digest(destination), resources=verified)
    save_json(WORK/'preview-integration-audit.json', report)
    prior_audit.update(avatarEnvelope='standalone mesh, identical to user-tested C7', gpuBytes=len(entry.gpu_data),
        compactBytes=destination.stat().st_size, previewIntegrationAuditSha256=digest(WORK/'preview-integration-audit.json'),
        validationMethod='Prior full animation audit retained; every animation, Bones and state payload SHA-256 unchanged')
    save_json(WORK/'animation-final-audit.json', prior_audit)
    print('PASS: C7 Avatar + GPU integrated; 3180 animations, Bones and state are unchanged.', flush=True)


if __name__ == '__main__':
    main()
