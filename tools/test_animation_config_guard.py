import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("config_guard", Path(__file__).with_name("check_animation_config.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

class AnimationConfigGuardTests(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); bundle = root / "anim_batch_mod"; bundle.mkdir()
        raw = b"[single_skeleton]\nrotation_compensation = false\n"
        (root / "config.toml").write_bytes(raw); (bundle / "config.toml").write_bytes(raw)
        info = {"files": [{"name": "config.toml", "sha256": hashlib.sha256(raw).hexdigest().upper()}]}
        (bundle / "build-info.json").write_text(json.dumps(info), encoding="utf-8")
        return root, bundle, info
    def test_matching_config_and_case_insensitive_hash(self):
        root,bundle,_ = self.fixture(); self.assertEqual(guard.check(root/"config.toml",bundle)["status"], "PASS")
    def test_stale_default_rejected(self):
        root,bundle,_ = self.fixture(); (bundle/"config.toml").write_text("[single_skeleton]\nrotation_compensation = true\n")
        with self.assertRaisesRegex(ValueError,"drift"): guard.check(root/"config.toml",bundle)
    def test_stale_hash_rejected(self):
        root,bundle,info = self.fixture(); info["files"][0]["sha256"] = "0"*64
        (bundle/"build-info.json").write_text(json.dumps(info))
        with self.assertRaisesRegex(ValueError,"stale"): guard.check(root/"config.toml",bundle)
    def test_duplicate_or_missing_entry_rejected(self):
        for duplicate in (False,True):
            root,bundle,info = self.fixture(); info["files"] = info["files"]*2 if duplicate else []
            (bundle/"build-info.json").write_text(json.dumps(info))
            with self.assertRaises(ValueError): guard.check(root/"config.toml",bundle)
    def test_missing_root_not_silently_replaced(self):
        root,bundle,_ = self.fixture()
        with self.assertRaises(FileNotFoundError): guard.check(root/"missing.toml",bundle)
    def test_intentional_custom_config_supported_not_hardcoded_to_07(self):
        root,bundle,info = self.fixture(); raw=b"[single_skeleton]\nrotation_compensation = true\n"
        (root/"config.toml").write_bytes(raw);(bundle/"config.toml").write_bytes(raw)
        info["files"][0]["sha256"]=hashlib.sha256(raw).hexdigest();(bundle/"build-info.json").write_text(json.dumps(info))
        self.assertTrue(guard.check(root/"config.toml",bundle)["singleRotationCompensation"])
if __name__ == "__main__": unittest.main()
