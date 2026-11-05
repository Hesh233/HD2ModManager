import math
import unittest
from anim_batch_mod.formats import LocalTransform
from anim_batch_mod.processor import _apply_two_bone_ik, _calculate_world_transforms


def chain(bend, side=1):
    a = side * math.radians(bend) / 2
    return [LocalTransform([0., 0., 0.], [0., 0., math.sin(a/2), math.cos(a/2)], [1.]*3),
            LocalTransform([.25, 0., 0.], [0., 0., math.sin(-a), math.cos(-a)], [1.]*3),
            LocalTransform([.25, 0., 0.], [0., 0., 0., 1.], [1.]*3)]


class ElbowDirectionTests(unittest.TestCase):
    def test_unchanged_target_preserves_both_elbow_sides(self):
        for degrees in (30, 60, 90, 120):
            for side in (-1, 1):
                with self.subTest(degrees=degrees, side=side):
                    local = chain(degrees, side)
                    before = _calculate_world_transforms(local, [None, 0, 1])
                    _apply_two_bone_ik(local, [None, 0, 1], 0, 1, 2,
                                       before[2].position, pole_state={})
                    after = _calculate_world_transforms(local, [None, 0, 1])
                    self.assertLess(math.dist(after[1].position, before[1].position), 1e-7)
                    self.assertLess(math.dist(after[2].position, before[2].position), 1e-7)

    def test_bent_elbow_can_leave_previous_hemisphere(self):
        state = {}
        for side in (1, -1):
            # A clear bend must eventually follow the input even when history
            # begins on the opposite side; rate limiting may delay the turn.
            for _ in range(61):
                local = chain(90, side)
                before = _calculate_world_transforms(local, [None, 0, 1])
                _apply_two_bone_ik(local, [None, 0, 1], 0, 1, 2,
                                   before[2].position, pole_state=state, delta_time=1/60)
            after = _calculate_world_transforms(local, [None, 0, 1])
            self.assertLess(math.dist(after[1].position, before[1].position), 1e-7)


if __name__ == '__main__':
    unittest.main()
