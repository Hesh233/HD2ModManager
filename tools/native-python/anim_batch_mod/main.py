from __future__ import annotations

import sys
from pathlib import Path


if __package__ in (None, ""):
    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root))

from anim_batch_mod.cli import main


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "native-project":
        from anim_batch_mod.native_skeleton import main as native_main
        raise SystemExit(native_main(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "attachment-runtime":
        from anim_batch_mod.attachment_skeleton import main as attachment_main
        raise SystemExit(attachment_main(sys.argv[2:]))
    if len(sys.argv)>1 and sys.argv[1]=='prepare-config':
        from anim_batch_mod.native_config import main as config_main
        raise SystemExit(config_main(sys.argv[2:]))
    if len(sys.argv)>1 and sys.argv[1]=='prepare-native-model':
        from anim_batch_mod.attachment_skeleton import model_main
        raise SystemExit(model_main(sys.argv[2:]))
    raise SystemExit(main())
