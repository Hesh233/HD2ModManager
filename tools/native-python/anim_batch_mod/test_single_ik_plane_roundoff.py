"""Regression for roundoff-sized bend normals, not a blanket IK/pole change."""
import math
import unittest
from anim_batch_mod import processor as p
from anim_batch_mod.math3d import quat_normalize


class SingleIkPlaneRoundoffTests(unittest.TestCase):
    @staticmethod
    def fixture(angle):
        q = [0., math.sin(angle / 2.), 0., math.cos(angle / 2.)]
        return [p.WorldTransform([0., 0., 0.], [0., 0., 0., 1.], [1., 1., 1.]),
                p.WorldTransform([.2, 0., 0.], q, [1., 1., 1.]),
                p.WorldTransform([.2, 0., 0.], [0., 0., 0., 1.], [1., 1., 1.])]

    @staticmethod
    def orientation_error(a, b):
        dot = abs(sum(x*y for x, y in zip(quat_normalize(a), quat_normalize(b))))
        return math.degrees(2 * math.acos(min(1., dot)))

    def solve(self, angle, **kwargs):
        local = self.fixture(angle)
        target = [.35, .05, 0.]
        kwargs.setdefault('reject_unreliable_bend_normal', True)
        p._apply_two_bone_ik(local, [None, 0, 1], 0, 1, 2, target,
                             [0., 0., 0., 1.], **kwargs)
        world = p._calculate_world_transforms(local, [None, 0, 1])
        self.assertLess(p._distance(world[2].position, target), 1e-7)
        self.assertLess(self.orientation_error(world[2].rotation, [0., 0., 0., 1.]), 1e-5)
        self.assertAlmostEqual(.2, p._distance(world[0].position, world[1].position), places=7)
        self.assertAlmostEqual(.2, p._distance(world[1].position, world[2].position), places=7)
        return local, world

    def test_subthreshold_plane_cannot_turn_roundoff_into_axial_roll(self):
        baseline, _ = self.solve(0., preserve_bend_frame=True)
        for angle in (-5e-6, -1e-6, 1e-6, 5e-6):
            with self.subTest(input_angle=angle):
                result, _ = self.solve(angle, preserve_bend_frame=True)
                self.assertLess(self.orientation_error(result[0].rotation, baseline[0].rotation), .01)

    def test_sign_change_in_nearly_straight_input_does_not_flip_shoulder(self):
        left, _ = self.solve(-5e-6, preserve_bend_frame=True)
        right, _ = self.solve(5e-6, preserve_bend_frame=True)
        self.assertLess(self.orientation_error(left[0].rotation, right[0].rotation), .01)

    def test_trusted_hinge_axis_remains_effective_for_small_input_bend(self):
        baseline, _ = self.solve(0., preserve_bend_frame=True, hinge_axis=[0., 0., 1.])
        noisy, _ = self.solve(5e-6, preserve_bend_frame=True, hinge_axis=[0., 0., 1.])
        self.assertLess(self.orientation_error(baseline[0].rotation, noisy[0].rotation), .01)

    def test_reliable_plane_is_not_globally_disabled(self):
        left, _ = self.solve(-.05, preserve_bend_frame=True)
        right, _ = self.solve(.05, preserve_bend_frame=True)
        self.assertAlmostEqual(55.77147550456509, self.orientation_error(left[0].rotation, right[0].rotation), places=6)

    def test_legacy_default_is_not_changed_by_the_single_opt_in(self):
        left, _ = self.solve(-5e-6, preserve_bend_frame=True, reject_unreliable_bend_normal=False)
        right, _ = self.solve(5e-6, preserve_bend_frame=True, reject_unreliable_bend_normal=False)
        self.assertAlmostEqual(180., self.orientation_error(left[0].rotation, right[0].rotation), places=6)

    def test_existing_non_preserving_solver_keeps_its_bend_choice(self):
        left, _ = self.solve(-5e-6, preserve_bend_frame=False)
        right, _ = self.solve(5e-6, preserve_bend_frame=False)
        self.assertLess(self.orientation_error(left[0].rotation, right[0].rotation), .01)


if __name__ == '__main__':
    unittest.main()
