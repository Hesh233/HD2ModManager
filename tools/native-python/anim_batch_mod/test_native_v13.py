import math
import unittest

from anim_batch_mod.math3d import quat_multiply, quat_rotate
from anim_batch_mod.processor import _apply_two_bone_ik, _calculate_world_transforms, _cross
from anim_batch_mod.test_native_v12 import chain


class AnatomicalElbowTests(unittest.TestCase):
    def test_pole_history_cannot_reverse_local_elbow_flexion(self):
        for side in (-1, 1):
            state = {}
            for frame in range(16):
                local = chain(90, side)
                # A transition can change the source arm's roll before the
                # smoothed pole catches up. Flexion remains anatomically valid.
                angle = 0 if frame == 0 else math.pi
                local[0].rotation = quat_multiply(local[0].rotation,
                    [math.sin(angle/2), 0., 0., math.cos(angle/2)])
                before = _calculate_world_transforms(local, [None, 0, 1])
                target, palm = before[2].position, before[2].rotation
                _apply_two_bone_ik(local, [None, 0, 1], 0, 1, 2, target, palm,
                                   pole_state=state, delta_time=1/30)
                forearm = quat_rotate(local[1].rotation, local[2].position)
                signed = _cross(local[1].position, forearm)[2] * side
                self.assertLess(signed, -.01, (side, frame, signed))
                after = _calculate_world_transforms(local, [None, 0, 1])
                self.assertLess(math.dist(after[2].position, target), 1e-6)
                self.assertLess(1 - abs(sum(a*b for a,b in zip(after[2].rotation, palm))), 1e-7)


if __name__ == '__main__':
    unittest.main()
