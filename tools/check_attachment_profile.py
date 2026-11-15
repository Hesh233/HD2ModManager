"""Read-only release gate: versions, production repair data, code and skeleton preset hashes."""
from pathlib import Path
import argparse, ast, hashlib, json, re
VERSION='1.0.19'
MANAGER_VERSION='1.5.17'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
PHYSICS_FILES = {
    'physbone_compat.lua': ('physicsCompatVersion', r'^M\.version\s*=\s*"([^"\n]+)"'),
    'physbone_runtime.lua': ('physicsRuntimeVersion', r'^M\.VERSION\s*=\s*"([^"\n]+)"'),
    'direct/physbone_compat.lua': ('directPhysicsCompatVersion', r'^M\.version\s*=\s*"([^"\n]+)"'),
    'direct/physbone_runtime.lua': ('directPhysicsRuntimeVersion', r'^M\.VERSION\s*=\s*"([^"\n]+)"'),
    'physbone_routes.lua': ('physicsRouteVersion', r'local M = \{ VERSION = "([^"\n]+)"'),
}

def check_physics_sources(info, source_root):
    source_root = Path(source_root).resolve()
    rows = info.get('physicsSourceFiles', [])
    if len(rows) != len(PHYSICS_FILES) or {r['name'] for r in rows} != set(PHYSICS_FILES):
        raise ValueError('Physics route source coverage is missing/duplicated/incomplete')
    for row in rows:
        path = (source_root / row['name']).resolve()
        if not path.is_relative_to(source_root) or sha(path).lower() != row['sha256'].lower():
            raise ValueError('Physics source SHA mismatch: ' + row['name'])
        field, pattern = PHYSICS_FILES[row['name']]
        versions = re.findall(pattern, path.read_text(encoding='utf-8-sig'), re.MULTILINE)
        if len(versions) != 1 or versions[0] != info.get(field):
            raise ValueError('Physics source/manifest version mismatch: ' + field)
    if info.get('physicsRoutingPolicy') != 'explicit-route-legacy-local-v1':
        raise ValueError('Physics route policy is missing/stale')
    return True

def check(bundle, source_policy=None):
    bundle=Path(bundle).resolve();info=json.loads((bundle/'build-info.json').read_text(encoding='utf-8-sig'))
    for key in ('runtimeCompanionVersion','luaVersion','attachmentRepairPolicyVersion'):
        if info.get(key)!=VERSION:raise ValueError('Missing/stale '+key)
    if info.get('managerVersion')!=MANAGER_VERSION:raise ValueError('Manager profile release version mismatch')
    required={'attachment_repair_profile.py','attachment_repair_policy.json','runtime_companions.py','attachment_skeleton.py','config.toml'}
    for section in ('files','presetFiles'):
        seen=set()
        for row in info[section]:
            name=row['name'];p=(bundle/name).resolve()
            if name in seen or not p.is_relative_to(bundle) or sha(p).lower()!=row['sha256'].lower():
                raise ValueError('Missing/changed/duplicate runtime or skeleton file: '+name)
            seen.add(name)
        if section=='files' and not required.issubset(seen):raise ValueError('Profile dependencies are absent from build-info')
    required_presets={'presets/native-v15/preset.json','presets/native-v15/runtime-policy.json','presets/native-v15/grip-fixes-1.0.10.json','presets/native-v15/grip-fixes-1.0.11.json','presets/native-v15/arm-reference.patch_0','presets/native-v15/avatar-template.patch_0','presets/native-v15/avatar-template.patch_0.gpu_resources','presets/native-v15/avatar-template.patch_0.stream','presets/single-normal-reference/playback.zip'}
    if not required_presets.issubset({r['name'] for r in info['presetFiles']}):raise ValueError('Skeleton preset dependency coverage is incomplete')
    policy=bundle/'attachment_repair_policy.json';d=json.loads(policy.read_text(encoding='utf-8-sig'))
    if d['version']!=VERSION or d['schema']!='hd2-attachment-repair-policy-v1' or sha(policy)!=info['attachmentRepairPolicySha256']:
        raise ValueError('Production repair profile hash/version mismatch')
    if source_policy and policy.read_bytes()!=Path(source_policy).read_bytes():raise ValueError('Source/bundled repair policy drift')
    for name in ('runtime_companions.py','attachment_repair_profile.py'):
        tree=ast.parse((bundle/name).read_text(encoding='utf-8-sig'))
        versions=[n.value.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name)and t.id=='VERSION' for t in n.targets)]
        if versions!=[VERSION]:raise ValueError('Production profile/compiler version drift: '+name)
    if source_policy:
        check_physics_sources(info, Path(source_policy).resolve().parents[1])
    return dict(status='PASS',managerVersion=MANAGER_VERSION,repairVersion=VERSION,policySha256=sha(policy),consumers=len(d['fixedConsumers']),allowedConsumers=len(d['allowedConsumers']),skeletonPresetHashesValidated=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle-root',type=Path);p.add_argument('--manager-root',type=Path);p.add_argument('--source-policy',type=Path);a=p.parse_args()
    try:
        bundle=a.bundle_root or a.manager_root/'anim_batch_mod'
        result=check(bundle,a.source_policy)
        if a.manager_root and (a.manager_root/'config.toml').read_bytes()!=(bundle/'config.toml').read_bytes():raise ValueError('Root/bundled config mismatch; preserve user configuration')
        if a.manager_root and sha(a.manager_root/'config/attachment-fix.json')!=json.loads((bundle/'build-info.json').read_text(encoding='utf-8-sig'))['attachmentFixConfigSha256']:raise ValueError('Active bone configuration hash mismatch')
        print(json.dumps(result))
    except (ValueError,OSError,KeyError,TypeError)as e:raise SystemExit('Attachment profile gate FAILED: '+str(e))
