import copy,math,unittest
from anim_batch_mod.attachment_skeleton import append_source_attachment_animation,source_attachment_pose
from anim_batch_mod.formats import AnimationData,AnimationBoneState,AnimationEntry,BonesData,UnitData,LocalTransform
from anim_batch_mod.processor import _build_tracks,_calculate_world_transforms

class SourceAttachmentTests(unittest.TestCase):
    def fixture(self,additive=False):
        unit=UnitData(1,2,[LocalTransform([0,0,0],[0,0,0,1],[1,1,1]),
            LocalTransform([0,0,1],[0,0,0,1],[1,1,1]),LocalTransform([.1,0,0],[0,0,0,1],[1,1,1])],
            [None,0,1],[10,11,12])
        row=dict(index=2,driverAnchorIndex=1,axisCorrection=[0,0,0,1])
        states=[AnimationBoneState(t.position,t.rotation,t.scale,False,False,False) for t in unit.transforms]
        if additive:states=[AnimationBoneState([0,0,0],[0,0,0,1],[0,0,0],False,False,False) for _ in states]
        return unit,BonesData(['root','hand','weapon'],[10,11,12]),row,AnimationData(initial_bone_states=states,animation_length=1.,is_additive=additive)

    def test_configured_hand_translation_does_not_change_weapon_offset(self):
        unit,bones,row,clip=self.fixture()
        clip.entries=[AnimationEntry(0,4,1,1000.,[0,0,1.45])]
        result=AnimationData()
        append_source_attachment_animation(result,clip,bones,unit,{'sourceAttachmentShadows':[row]},[0.,1000.])
        tracks=_build_tracks(result)
        self.assertEqual(tracks[0][0].evaluate(0),[.1,0.,0.])
        self.assertEqual(tracks[0][0].evaluate(1000),[.1,0.,0.])
        self.assertEqual(len(clip.initial_bone_states),3)

    def test_neutral_additive_reference_does_not_double_bind_offset(self):
        unit,bones,row,clip=self.fixture(True);result=AnimationData(is_additive=True)
        append_source_attachment_animation(result,clip,bones,unit,{'sourceAttachmentShadows':[row]},[0.,1000.])
        self.assertEqual(result.initial_bone_states[0].position,[0.,0.,0.])
        self.assertEqual(result.initial_bone_states[0].rotation,[0.,0.,0.,1.])

    def test_source_axis_correction_rotates_offset_and_orientation_together(self):
        unit,bones,row,clip=self.fixture();row['axisCorrection']=[0,0,math.sqrt(.5),math.sqrt(.5)]
        pose=source_attachment_pose(_calculate_world_transforms(unit.transforms,unit.parents),row)
        self.assertLess(math.dist(pose.position,[0,.1,0]),1e-10)
        self.assertEqual(pose.rotation,row['axisCorrection'])

if __name__=='__main__':unittest.main()
