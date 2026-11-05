import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.native_skeleton import main
if __name__=='__main__':
    p=ROOT/'outputs/native-v10-20261104/project'
    raise SystemExit(main(['--manifest',str(p/'source-skeleton.json'),'--config',str(p/'config.toml'),
        '--game-data',r'E:\Steam\steamapps\common\Helldivers 2\data','--output',str(p/'animations')]))
