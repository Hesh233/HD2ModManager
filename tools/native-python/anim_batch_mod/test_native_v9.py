import copy
import math
import unittest

from anim_batch_mod.processor import _apply_two_bone_ik, _calculate_world_transforms
from anim_batch_mod.formats import LocalTransform
from anim_batch_mod.math3d import quat_multiply, quat_rotate, quat_inverse
from anim_batch_mod.native_skeleton import append_animation
from anim_batch_mod.test_native_skeleton import fixture


class StableSourceTests(unittest.TestCase):
    def test_closed_target_path_does_not_accumulate_axial_roll(self):
        parents=[None,0,1];state={};start=None;end=None
        for i in range(181):
            angle=i*2*math.pi/180
            local=[LocalTransform([0.,0.,0.],[0.,0.,0.,1.],[1.]*3),
                   LocalTransform([.235,0.,0.],[0.,0.,-.1,math.sqrt(.99)],[1.]*3),
                   LocalTransform([.216,0.,0.],[0.,0.,0.,1.],[1.]*3)]
            target=[.36,.03*math.sin(angle),.02*math.sin(2*angle)]
            _apply_two_bone_ik(local,parents,0,1,2,target,[0.,0.,0.,1.],pole_state=state,soft_distance=.008,delta_time=1/60)
            if start is None:start=copy.deepcopy(local)
            end=local
        for a,b in zip(start,end):
            self.assertLess(1-abs(sum(x*y for x,y in zip(a.rotation,b.rotation))),1e-7)

    def test_pole_crossing_and_unreachable_target_preserve_lengths(self):
        parents=[None,0,1]
        state={}
        paths=[]
        for stable in (False,True):
            points=[]
            for i in range(121):
                # Infinitesimal input bend changes side at frame 60 while the
                # wrist target stays continuous and comfortably reachable.
                tilt=(i-60)*1e-7
                local=[LocalTransform([0.,0.,0.],[0.,0.,math.sin(tilt/2),math.cos(tilt/2)],[1.]*3),
                       LocalTransform([.235,0.,0.],[0.,0.,0.,1.],[1.]*3),
                       LocalTransform([.216,0.,0.],[0.,0.,0.,1.],[1.]*3)]
                _apply_two_bone_ik(local,parents,0,1,2,[.4,0.,0.],[0.,0.,0.,1.],pole_state=state if stable else None,soft_distance=.008 if stable else 0.,delta_time=1/60)
                w=_calculate_world_transforms(local,parents)
                self.assertAlmostEqual(math.dist(w[0].position,w[1].position),.235,places=7)
                self.assertAlmostEqual(math.dist(w[1].position,w[2].position),.216,places=7)
                self.assertLess(math.dist(w[2].position,[.4,0.,0.]),1e-6)
                points.append(w[1].position)
            paths.append(max(math.dist(a,b) for a,b in zip(points,points[1:])))
        self.assertGreater(paths[0],.1)
        self.assertLess(paths[1],.025)
        self.assertLess(paths[1],paths[0]/5)

    def test_soft_reach_and_parent_motion(self):
        parents=[None,0,1,2]
        state={};last=None;maximum=0.
        for i in range(201):
            turn=.007*i;q=[0.,0.,math.sin(turn/2),math.cos(turn/2)]
            local=[LocalTransform([0.,0.,0.],q,[1.]*3),
                   LocalTransform([0.,0.,0.],[0.,0.,.05,math.sqrt(1-.05**2)],[1.]*3),
                   LocalTransform([.235,0.,0.],[0.,0.,-.1,math.sqrt(.99)],[1.]*3),
                   LocalTransform([.216,0.,0.],[0.,0.,0.,1.],[1.]*3)]
            target=quat_rotate(q,[.42+i*.0004,0.,0.])
            _apply_two_bone_ik(local,parents,1,2,3,target,q,pole_state=state,soft_distance=.008,delta_time=1/60)
            w=_calculate_world_transforms(local,parents)
            p=quat_rotate(quat_inverse(q),w[2].position)
            if last is not None:maximum=max(maximum,math.dist(p,last))
            last=p
            self.assertAlmostEqual(math.dist(w[1].position,w[2].position),.235,places=7)
            self.assertAlmostEqual(math.dist(w[2].position,w[3].position),.216,places=7)
            self.assertLessEqual(math.dist(w[1].position,w[3].position),.451)
        self.assertLess(maximum,.003)

    def test_foot_correction_and_additive_basis(self):
        for additive in (False,True):
            u,b,m,a=fixture(additive)
            b.names[0]='l_foot';m['bones'][1]['driver']='l_foot'
            # A nonzero additive rotation/translation exercises basis change.
            if additive:
                a.initial_bone_states[0].rotation=[math.sin(.1),0.,0.,math.cos(.1)]
                a.initial_bone_states[0].position=[.03,.04,.05]
            old=copy.deepcopy(a);new=copy.deepcopy(a)
            append_animation(old,b,u,m,sample_times=[0.])
            append_animation(new,b,u,m,sample_times=[0.],foot_y_degrees={'l_foot':20.})
            before=old.initial_bone_states[4];after=new.initial_bone_states[4]
            c=[0.,math.sin(math.radians(10)),0.,math.cos(math.radians(10))]
            expected=quat_multiply(quat_multiply(quat_inverse(c),before.rotation),c) if additive else quat_multiply(before.rotation,c)
            self.assertLess(1-abs(sum(x*y for x,y in zip(expected,after.rotation))),1e-7)
            p=quat_rotate(quat_inverse(c),before.position) if additive else before.position
            self.assertLess(math.dist(p,after.position),1e-8)
            for i in (0,1,2,3,5):self.assertEqual(old.initial_bone_states[i],new.initial_bone_states[i])


if __name__=='__main__':unittest.main()
