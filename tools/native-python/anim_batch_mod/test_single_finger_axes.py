import copy,math,tempfile,unittest
from pathlib import Path
from anim_batch_mod import single_skeleton as single,processor as proc
from anim_batch_mod.formats import UnitData,BonesData,LocalTransform,AnimationData,AnimationBoneState

class SingleFingerAxisTests(unittest.TestCase):
    def fixture(self):
        names=['boss','cape4']+[f'{side}_{stem}_finger{k}' for side in ('l','r') for stem in ('thumb','index','middle','ring','pinky') for k in (1,2,3)]
        hashes=list(range(1,len(names)+1));indices={n:i for i,n in enumerate(names)}
        parents=[None,0]+[0 if n.endswith('1') else indices[n[:-1]+str(int(n[-1])-1)] for n in names[2:]]
        positions=[[0,0,0],[0,0,.1]]+[[.025,.01,.02] if n.endswith('1') else [.04 if n.endswith('2') else .02,0,0] for n in names[2:]]
        u=UnitData(1,2,[LocalTransform(p,[0,0,0,1],[1,1,1]) for p in positions],parents,hashes)
        b=BonesData(names,hashes);c=proc.ModConfig({n:[0.,0.,0.] for n in names},finger_axis_policy=proc.FINGER_AXIS_POLICY)
        return u,b,c
    def test_source_lengths_and_root_placement_can_change_without_changing_axes(self):
        u,b,c=self.fixture();c.offsets['l_thumb_finger1']=[.1,.2,-.1];c.offsets['l_thumb_finger2']=[-.01,0,0]
        proc.validate_native_finger_axes(u,b,c)
    def test_every_phalanx_axis_rejects_legacy_mismatch(self):
        for side in ('l','r'):
            for stem in ('thumb','index','middle','ring','pinky'):
                for k in (2,3):
                    with self.subTest(side=side,stem=stem,k=k):
                        u,b,c=self.fixture();c.offsets[f'{side}_{stem}_finger{k}']=[0,.02,0]
                        with self.assertRaisesRegex(ValueError,'finger-safe'):proc.validate_native_finger_axes(u,b,c)
    def test_zero_length_and_reversed_axes_are_rejected(self):
        for delta in (-.04,-.08):
            u,b,c=self.fixture();c.offsets['r_thumb_finger2']=[delta,0,0]
            with self.assertRaises(ValueError):proc.validate_native_finger_axes(u,b,c)
    def test_topology_and_incomplete_chain_are_rejected(self):
        u,b,c=self.fixture();u.parents[b.names.index('r_thumb_finger3')]=0
        with self.assertRaisesRegex(ValueError,'topology'):proc.validate_native_finger_axes(u,b,c)
        u,b,c=self.fixture();b.names.pop();b.hashes.pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):proc.validate_native_finger_axes(u,b,c)
    def test_effective_config_roundtrip_keeps_gate(self):
        u,b,c=self.fixture()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'single-config.toml';single._write_effective_config(p,c,{n:[0,0,0] for n in c.offsets})
            loaded=proc.ModConfig.load(p);self.assertEqual(loaded.finger_axis_policy,proc.FINGER_AXIS_POLICY)
            proc.validate_native_finger_axes(u,b,loaded)
    def test_derive_calibration_rejects_old_model_and_changed_finger_axes(self):
        u,b,c=self.fixture();m=copy.deepcopy(u);m.transforms[b.names.index('r_thumb_finger2')].position=[.01,.03,0]
        with self.assertRaisesRegex(ValueError,'finger-safe'):single._derive_calibration([(1,m)],u,b)
        m=copy.deepcopy(u);m.transforms[b.names.index('r_thumb_finger1')].rotation=[0,0,math.sin(.1),math.cos(.1)]
        with self.assertRaisesRegex(ValueError,'bind rotation'):single._derive_calibration([(1,m)],u,b)
    def test_derive_accepts_aligned_new_source_lengths(self):
        u,b,c=self.fixture();m=copy.deepcopy(u);m.transforms[b.names.index('r_thumb_finger2')].position=[.03,0,0]
        offsets,_,_=single._derive_calibration([(1,m)],u,b);self.assertAlmostEqual(offsets['r_thumb_finger2'][0],-.01)
    def test_processor_rechecks_contract_before_normal_or_additive_processing(self):
        for additive in (False,True):
            u,b,c=self.fixture();c.offsets['l_index_finger3']=[0,0,.02]
            a=AnimationData(initial_bone_states=[AnimationBoneState() for _ in b.names],is_additive=additive)
            with self.assertRaisesRegex(ValueError,'finger-safe'):proc.modify_animation_with_world_compensation(a,b,u,c,allow_additive=True)
    def test_normal_rotations_remain_identical_and_ordinary_batch_opts_out(self):
        u,b,c=self.fixture();a=AnimationData(initial_bone_states=[AnimationBoneState(position=t.position,rotation=t.rotation,scale=t.scale) for t in u.transforms])
        before=copy.deepcopy(a.initial_bone_states);proc.modify_animation_with_world_compensation(a,b,u,c)
        self.assertEqual([s.rotation for s in before],[s.rotation for s in a.initial_bone_states])
        c=proc.ModConfig({'cape4':[0,0,.01],'r_thumb_finger2':[0,.02,0]})
        a=AnimationData(initial_bone_states=[AnimationBoneState(position=t.position,rotation=t.rotation,scale=t.scale) for t in u.transforms])
        proc.modify_animation_with_world_compensation(a,b,u,c)
    def test_unknown_contract_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'policy'):proc.ModConfig({},finger_axis_policy='unknown')

if __name__=='__main__':unittest.main()
