import copy
import math
import unittest
from anim_batch_mod.formats import LocalTransform
from anim_batch_mod.math3d import quat_multiply, quat_inverse
from anim_batch_mod.processor import _apply_two_bone_ik, _calculate_world_transforms


class UpperArmRollTests(unittest.TestCase):
    def test_small_target_motion_does_not_accumulate_transport_error(self):
        state={}
        for i in range(501):
            target=[.4,0.,i*.00001]
            local=[LocalTransform([0.,0.,0.],[0.,0.,0.,1.],[1.]*3),
                   LocalTransform([.235,0.,0.],[0.,0.,math.sin(-.15),math.cos(-.15)],[1.]*3),
                   LocalTransform([.216,0.,0.],[0.,0.,0.,1.],[1.]*3)]
            _apply_two_bone_ik(local,[None,0,1],0,1,2,target,[0.,0.,0.,1.],pole_state=state,soft_distance=.008)
            hand=_calculate_world_transforms(local,[None,0,1])[2]
            self.assertLess(math.dist(hand.position,target),1e-6)

    def test_upper_arm_roll_survives_unchanged_elbow_plane(self):
        state = {}
        outputs = []
        bend = [0., 0., math.sin(-.15), math.cos(-.15)]
        for i in range(61):
            angle = math.pi / 2 * i / 60
            roll = [math.sin(angle / 2), 0., 0., math.cos(angle / 2)]
            # Same shoulder/elbow/wrist positions, different upper-arm roll.
            local = [LocalTransform([0., 0., 0.], roll, [1.] * 3),
                     LocalTransform([.235, 0., 0.], quat_multiply(quat_inverse(roll), bend), [1.] * 3),
                     LocalTransform([.216, 0., 0.], [0., 0., 0., 1.], [1.] * 3)]
            _apply_two_bone_ik(local, [None, 0, 1], 0, 1, 2, [.4, 0., 0.], [0., 0., 0., 1.],
                               pole_state=state, soft_distance=.008, delta_time=1 / 60)
            worlds = _calculate_world_transforms(local, [None, 0, 1])
            self.assertLess(math.dist(worlds[2].position, [.4, 0., 0.]), 1e-6)
            self.assertLess(1 - abs(worlds[2].rotation[3]), 1e-7)
            outputs.append(copy.deepcopy(worlds))
        a, b = outputs[0][0].rotation, outputs[-1][0].rotation
        angle = 2 * math.acos(min(1., abs(sum(x * y for x, y in zip(a, b)))))
        self.assertAlmostEqual(angle, math.pi / 2, places=5,
                               msg='IK erased the upper-arm roll despite an unchanged elbow plane')


if __name__ == '__main__':
    unittest.main()
