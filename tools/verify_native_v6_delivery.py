"""Verify delivered bytes and preservation of the user's local test settings."""
import hashlib
import json
import re
import sys
from pathlib import Path

from package_native_v6 import WORK, PROJECT, RELEASE, digest, files, project_files

SNAPSHOT = WORK / 'delivery-settings-before.json'


def snapshot():
    result = {}
    for relative in ('test/settings.json', 'test/config.toml'):
        path = RELEASE / relative
        if path.exists():
            allowed = [digest(path)]
            if relative == 'test/config.toml':
                text = path.read_text(encoding='utf-8-sig')
                updated = re.sub(r'(?m)^(model_scale\s*=\s*)(?:1\.2|1\.05)\s*$', r'\g<1>1.08', text)
                if text != updated:
                    allowed.append(hashlib.sha256(updated.replace('\n', '\r\n').encode('utf-8-sig')).hexdigest())
            result[relative] = dict(allowedSha256=allowed)
    SNAPSHOT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved test settings snapshot')


def verify():
    report = json.loads((RELEASE / 'package-report.json').read_text(encoding='utf-8'))
    assert report['revision'] == 'native-v6' and not report['gameDeployed'] and not report['gameTested']
    for row in report['files']:
        path = RELEASE / row['name']
        assert path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], row['name']
    checked = 0
    for source, relative in project_files():
        assert digest(source) == digest(RELEASE / 'project' / relative), str(relative)
        checked += 1
    for source, relative in files(WORK / 'manager'):
        assert digest(source) == digest(RELEASE / 'manager' / relative), str(relative)
        if relative.parts[0] not in ('data', 'cache', 'logs', 'config', 'settings.json', 'config.toml'):
            assert digest(source) == digest(RELEASE / 'test' / relative), str(relative)
        checked += 1
    for relative, before in json.loads(SNAPSHOT.read_text(encoding='utf-8')).items():
        current = RELEASE / relative
        assert digest(current) in before['allowedSha256'], relative
    for relative in ('project/attachment-profile-research.json', 'project/research/attachment_profiles.lua',
                     'test01-物理运行时.zip', 'test01-物理运行时-v3.zip', 'test01-物理运行时-v4.zip','test01-物理运行时-v5.zip'):
        assert not (RELEASE / relative).exists(), relative
    result = dict(status='PASS', zipCount=len(report['files']), verifiedProjectAndManagerFiles=checked,
                  testSettingsPreserved=True, gameDeployed=False, gameTested=False)
    for path in (WORK / 'delivery-verification.json', RELEASE / 'delivery-verification.json'):
        path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    {'--snapshot': snapshot, '--verify': verify}[sys.argv[1]]()
