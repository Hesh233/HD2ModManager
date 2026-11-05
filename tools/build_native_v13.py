import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from anim_batch_mod.native_skeleton import main

if __name__ == '__main__':
    project = ROOT / 'outputs/native-v13-20261104/project'
    raise SystemExit(main(['--manifest', str(project / 'source-skeleton.json'),
                          '--config', str(project / 'config.toml'),
                          '--game-data', r'E:\Steam\steamapps\common\Helldivers 2\data',
                          '--output', str(project / 'animations')]))
