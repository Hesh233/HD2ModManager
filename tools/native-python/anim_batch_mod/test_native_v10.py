import copy
import math
import unittest
from anim_batch_mod.formats import LocalTransform
from anim_batch_mod.math3d import quat_multiply
from anim_batch_mod.processor import _apply_two_bone_ik, _calculate_world_transforms

class SourceJointRollTests(unittest.TestCase):
    def test_forearm_full_roll_cycle_keeps_motion_and_returns(self):
        state={};angles=[];previous=None;start=None
        for i in range(181):
            a=i*math.pi/90
            local=[LocalTransform([0.,0.,0.],[0.,0.,0.,1.],[1.]*3),
                   LocalTransform([.235,0.,0.],quat_multiply([0.,0.,math.sin(-.15),math.cos(-.15)],[math.sin(a/2),0.,0.,math.cos(a/2)]),[1.]*3),
                   LocalTransform([.216,0.,0.],[0.,0.,0.,1.],[1.]*3)]
            _apply_two_bone_ik(local,[None,0,1],0,1,2,[.4,0.,0.],[0.,0.,0.,1.],pole_state=state,soft_distance=.008,delta_time=1/60)
            q=_calculate_world_transforms(local,[None,0,1])[1].rotation
            if start is None:start=q
            if previous is not None:angles.append(2*math.acos(min(1.,abs(sum(x*y for x,y in zip(previous,q))))))
            previous=q
        self.assertAlmostEqual(sum(angles),2*math.pi,places=5)
        self.assertLess(max(angles),math.radians(2.01))
        self.assertLess(1-abs(sum(x*y for x,y in zip(start,previous))),1e-7)

    def test_forearm_roll_remains_animated_with_fixed_grip(self):
        state={};outputs=[]
        for i in range(61):
            roll=math.pi/2*i/60
            bend=[0.,0.,math.sin(-.15),math.cos(-.15)]
            q=quat_multiply(bend,[math.sin(roll/2),0.,0.,math.cos(roll/2)])
            local=[LocalTransform([0.,0.,0.],[0.,0.,0.,1.],[1.]*3),
                   LocalTransform([.235,0.,0.],q,[1.]*3),
                   LocalTransform([.216,0.,0.],[0.,0.,0.,1.],[1.]*3)]
            _apply_two_bone_ik(local,[None,0,1],0,1,2,[.4,0.,0.],[0.,0.,0.,1.],pole_state=state,soft_distance=.008,delta_time=1/60)
            w=_calculate_world_transforms(local,[None,0,1]);outputs.append(copy.deepcopy(w))
            self.assertLess(math.dist(w[2].position,[.4,0.,0.]),1e-6)
            self.assertLess(1-abs(w[2].rotation[3]),1e-7)
        a,b=outputs[0][1].rotation,outputs[-1][1].rotation
        angle=2*math.acos(min(1.,abs(sum(x*y for x,y in zip(a,b)))))
        self.assertAlmostEqual(angle,math.pi/2,places=5,msg='IK froze animated forearm axial rotation')
        self.assertLess(math.dist(outputs[0][1].position,outputs[-1][1].position),1e-7)

if __name__=='__main__':unittest.main()
