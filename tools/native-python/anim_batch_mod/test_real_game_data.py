from __future__ import annotations

import os
import unittest
from pathlib import Path

from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import BASE_ARCHIVE_ID


@unittest.skipUnless(
    os.environ.get("HD2_GAME_DATA"),
    "Set HD2_GAME_DATA to run integration tests against installed game data",
)
class RealGameDataTest(unittest.TestCase):
    def test_base_archive_loads(self):
        store = PackageStore(Path(os.environ["HD2_GAME_DATA"]))
        self.assertTrue(store.has_package(BASE_ARCHIVE_ID))
        archive = TocArchive.load_toc_only(store, BASE_ARCHIVE_ID)
        self.assertTrue(archive.entries)


if __name__ == "__main__":
    unittest.main()
