"""Small, frozen-input tests for the canonical project and shared hand contract."""
import copy
import hashlib
import json
import tomllib
import unittest
import zipfile
from pathlib import Path
from prepare_native_v31_b23 import ROOT,load
from anim_batch_mod.attachment_skeleton import validate_attachment_transfer_contract,attachment_swap_plan
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import BONE_TYPE_ID

PROJECT=ROOT/'projects/test01-native-grip'

class ArchivedGripProjectTests(unittest.TestCase):
    def setUp(self):
        self.spec=load(PROJECT/'project.json');self.profile=load(PROJECT/self.spec['profile'])
        self.manifest=load(PROJECT/self.spec['sourceSkeleton'])
        self.swap=tomllib.loads((PROJECT/self.spec['animationConfig']).read_text(encoding='utf-8-sig'))['attachment_swap']
        with zipfile.ZipFile(PROJECT/self.spec['baseline']) as z:
            self.avatar=UnitData.parse(z.read('runtime-avatar.toc'))
            patch=TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_5'),z.read('9ba626afa44a3aa3.patch_5.gpu_resources'),b'')
        self.bones=BonesData.parse(next(e.toc_data for e in patch.entries.values() if e.type_id==BONE_TYPE_ID))
    def contract(self,profile=None,swap=None):
        return validate_attachment_transfer_contract(profile or self.profile,self.avatar,self.bones,self.manifest,swap or self.swap)
    def test_shared_normalizer_and_actual_channel_direction(self):
        plan=attachment_swap_plan(self.swap)
        self.assertEqual([p['native'] for p in plan['pairs']],['attach_hand_r','attach_hand_l'])
        report=self.contract();right,left=report['pairs']
        self.assertEqual((right['nativeChannel'],right['sourceBakeChannel'],right['referenceChannel']),(16,137,203))
        self.assertEqual((left['nativeChannel'],left['sourceBakeChannel'],left['referenceChannel']),(19,114,202))
    def test_duplicate_native_targets_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            attachment_swap_plan({'left_native':'attach_hand_r'})
    def test_swapped_output_cannot_be_original_reference(self):
        p=copy.deepcopy(self.profile);p['originalMount']=copy.deepcopy(p['target'])
        with self.assertRaisesRegex(ValueError,'independent'):
            self.contract(profile=p)
    def test_legacy_weapon_bone_cannot_be_runtime_calibration(self):
        p=copy.deepcopy(self.profile)
        bone=next(n for n in self.manifest['bones'] if n.get('sourceName')=='ValveBiped.weapon_bone')
        index=self.avatar.name_hashes.index(bone['hash'])
        p['sourceRight']=dict(name=bone['name'],index=index,parent=self.avatar.parents[index],hash=bone['hash'])
        with self.assertRaisesRegex(ValueError,'converter hand'):
            self.contract(profile=p)
    def test_pose_swap_rejected_for_position_only_runtime(self):
        swap=copy.deepcopy(self.swap);swap['policy']='pose'
        with self.assertRaisesRegex(ValueError,'Position-only'):
            self.contract(swap=swap)
    def test_frozen_baseline_and_release_hashes(self):
        self.assertEqual(hashlib.sha256((PROJECT/self.spec['baseline']).read_bytes()).hexdigest(),self.spec['baselineSha256'])
        for row in self.spec['releases']:
            path=PROJECT/row['path'];self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),row['sha256'])
            with zipfile.ZipFile(path) as z:
                self.assertNotIn('9ba626afa44a3aa3.patch_2',z.namelist())
                self.assertEqual(z.testzip(),None)

if __name__=='__main__':unittest.main()
