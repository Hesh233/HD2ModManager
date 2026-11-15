"""Read-only source gate regressions; no model/profile/library changes."""
import copy, json, unittest
from pathlib import Path
from check_attachment_profile import check_physics_sources
ROOT=Path(__file__).resolve().parents[1]

class PhysicsRouteGuardTests(unittest.TestCase):
    def setUp(self):
        self.info=json.loads((ROOT/'tools/native-python/anim_batch_mod/build-info.json').read_text(encoding='utf-8-sig'))
        self.source=ROOT/'HD2PhysBoneCompat/src'
    def test_current_sources(self):
        self.assertTrue(check_physics_sources(self.info,self.source))
    def test_missing_direct_module(self):
        self.info['physicsSourceFiles'].pop()
        with self.assertRaises(ValueError):check_physics_sources(self.info,self.source)
    def test_duplicate_module(self):
        self.info['physicsSourceFiles'][-1]=copy.deepcopy(self.info['physicsSourceFiles'][0])
        with self.assertRaises(ValueError):check_physics_sources(self.info,self.source)
    def test_stale_hash(self):
        self.info['physicsSourceFiles'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):check_physics_sources(self.info,self.source)
    def test_direct_version_drift(self):
        self.info['directPhysicsRuntimeVersion']='2.1.23'
        with self.assertRaises(ValueError):check_physics_sources(self.info,self.source)
    def test_policy_drift(self):
        self.info['physicsRoutingPolicy']='legacy'
        with self.assertRaises(ValueError):check_physics_sources(self.info,self.source)

if __name__=='__main__':unittest.main()
