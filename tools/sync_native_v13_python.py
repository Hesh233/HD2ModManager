"""Synchronize rebuild code without republishing unchanged .NET binaries."""
import shutil
from package_native_v13 import ROOT, WORK, digest, load, save_json


def main():
    for directory in (ROOT/'tools/native-python/anim_batch_mod', WORK/'manager/anim_batch_mod'):
        for file in ROOT.parent.glob('*.py'):
            shutil.copy2(file, directory/file.name)
        info = load(directory/'build-info.json')
        for row in info['files']:
            row['sha256'] = digest(directory/row['name'])
        info['sourceRevision'] = 'test01-v13-standalone-avatar'
        save_json(directory/'build-info.json', info)
    log = WORK/'python-preview-regression.log'
    assert 'Ran 113 tests' in log.read_text(encoding='utf-8-sig')
    assert 'OK (skipped=1)' in log.read_text(encoding='utf-8-sig')
    save_json(WORK/'python-regression.json', dict(status='PASS', tests=113, skipped=1,
        log=log.name, logSha256=digest(log)))
    print('Bundled Python synchronized; regression report updated.', flush=True)


if __name__ == '__main__':
    main()
