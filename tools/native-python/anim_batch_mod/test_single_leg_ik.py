"""Single-only leg IK: singularity, reach, model seeds and worker isolation."""
import copy, math, tempfile, unittest
from pathlib import Path
from anim_batch_mod import processor as p, single_skeleton as single
from anim_batch_mod.archive import TocEntry
from anim_batch_mod.batch import BatchJob, build_batch_entries, unit_context_signature
from anim_batch_mod.constants import ANIMATION_TYPE_ID
from anim_batch_mod.formats import AnimationBoneState, AnimationData, AnimationEntry, BonesData, LocalTransform, UnitData
from anim_batch_mod.math3d import quat_multiply, quat_rotate
class FakeResourceIndex:
    """Small in-memory animation index; keep the runtime regression self-contained."""
    def __init__(self, entries, unit_entries):
        self.entries = entries
    def resolve(self, file_id, type_id):
        entry = self.entries[file_id]
        if entry.type_id != type_id:
            raise LookupError('Wrong fixture resource type')
        return 'package', entry


Q=[0.,0.,0.,1.]
def angle(a,b):
 d=abs(sum(x*y for x,y in zip(a,b)))/math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
 return math.degrees(2*math.acos(min(1.,d)))
def knee_q(a):return [0.,0.,math.sin(-a/2),math.cos(a/2)]
def chain(a=0.,size=1.):
 return [p.WorldTransform([0.,0.,0.],Q[:],[1.,1.,1.]),p.WorldTransform([.4*size,0.,0.],knee_q(a),[1.,1.,1.]),p.WorldTransform([.4*size,0.,0.],Q[:],[1.,1.,1.])]
def fixture():
 b=BonesData(['boss','r_thigh','r_knee','r_foot'],[1,2,3,4])
 u=UnitData(0,0,[LocalTransform([0,0,0],Q[:],[1,1,1]),LocalTransform([0,0,0],Q[:],[1,1,1]),LocalTransform([.4,0,0],knee_q(.1),[1,1,1]),LocalTransform([.4,0,0],Q[:],[1,1,1])],[None,0,1,2],b.hashes[:])
 a=AnimationData(initial_bone_states=[AnimationBoneState(list(t.position),list(t.rotation),list(t.scale)) for t in u.transforms],animation_length=.1,entries=[AnimationEntry(type=0,subtype=5,bone=2,time=100.,data2=knee_q(.00001))])
 c=p.ModConfig({},required_bone='boss',ik_chains={'r_foot':p.IKChainConfig(['r_thigh','r_knee'])},leg_ik_bind_axes=p.derive_leg_bind_axes(u,b,{'r_foot':p.IKChainConfig(['r_thigh','r_knee'])}))
 return u,b,a,c

class SingleLegSolverTests(unittest.TestCase):
 def solve(self,a,target,state=None,size=1.,dt=1/30):
  local=chain(a,size);p._apply_stable_leg_ik(local,[None,0,1],0,1,2,target,Q,state={} if state is None else state,bind_axis=[0,0,-1],delta_time=dt)
  world=p._calculate_world_transforms(local,[None,0,1]);self.assertAlmostEqual(p._distance(world[0].position,world[1].position),.4*size,places=7);self.assertAlmostEqual(p._distance(world[1].position,world[2].position),.4*size,places=7);self.assertLess(angle(world[2].rotation,Q),.001)
  self.assertTrue(all(math.isfinite(v) for t in local for v in t.position+t.rotation+t.scale));return local,world
 def test_target_crossing_straight_leg_axis_no_longer_flips_knee(self):
  state={};a,wa=self.solve(0.,[.75,-.0001,0],state);b,wb=self.solve(0.,[.75,.0001,0],state)
  self.assertLess(angle(a[1].rotation,b[1].rotation),.001);self.assertLess(p._distance(wa[1].position,wb[1].position),.0002)
 def test_initial_straight_frame_uses_bind_plane_without_history(self):
  a,_=self.solve(0.,[.75,-.0001,0]);b,_=self.solve(0.,[.75,.0001,0]);self.assertLess(angle(a[1].rotation,b[1].rotation),.001)
 def test_near_straight_source_sign_change_keeps_continuous_hemisphere(self):
  state={};a,_=self.solve(.000001,[.75,.001,0],state);b,_=self.solve(-.000001,[.75,.001,0],state);self.assertLess(angle(a[1].rotation,b[1].rotation),.001)
 def test_reliable_bent_leg_retains_source_plane(self):
  a,wa=self.solve(.5,[.7,.05,0]);b,wb=self.solve(-.5,[.7,.05,0]);self.assertGreater(p._distance(wa[1].position,wb[1].position),.1)
 def test_reliable_bent_leg_plane_is_not_globally_rate_limited(self):
  state={};base=chain(.5)
  p._apply_stable_leg_ik(base,[None,0,1],0,1,2,[.7,0,0],Q,state=state,bind_axis=[0,0,-1],delta_time=1/30)
  twist=[math.sin(math.pi/4),0,0,math.cos(math.pi/4)];local=chain(.5);local[0].rotation=twist
  fresh=copy.deepcopy(local)
  p._apply_stable_leg_ik(local,[None,0,1],0,1,2,[.7,0,0],Q,state=state,bind_axis=[0,0,-1],delta_time=1/30)
  p._apply_stable_leg_ik(fresh,[None,0,1],0,1,2,[.7,0,0],Q,state={},bind_axis=[0,0,-1],delta_time=1/30)
  for a,b in zip(local,fresh):self.assertLess(angle(a.rotation,b.rotation),.001)
 def test_soft_reach_does_not_move_interior_foot_target(self):
  _,w=self.solve(.2,[.75,.001,0]);self.assertLess(p._distance(w[2].position,[.75,.001,0]),1e-7)
 def test_soft_reach_keeps_flexion_at_maximum_extension(self):
  local,w=self.solve(.2,[.8,0,0]);self.assertGreater(angle(local[1].rotation,Q),5.);self.assertLess(.8-w[2].position[0],.8*p.LEG_IK_SOFT_RATIO)
 def test_soft_reach_is_continuous_on_both_sides_of_threshold(self):
  x=.8-.8*p.LEG_IK_SOFT_RATIO-1e-7;a,_=self.solve(.1,[x-1e-7,0,0]);b,_=self.solve(.1,[x+1e-7,0,0]);self.assertLess(angle(a[1].rotation,b[1].rotation),.002)
 def test_soft_reach_is_continuous_across_old_hard_limit(self):
  a,_=self.solve(.1,[.8-.000001,0,0]);b,_=self.solve(.1,[.8+.000001,0,0]);self.assertLess(angle(a[1].rotation,b[1].rotation),.01)
 def test_unreachable_and_zero_distance_targets_remain_finite(self):
  for target in ([2.,0,0],[0.,0,0],[-2.,0,0]):self.solve(.2,target)
 def test_relative_soft_reach_scales_with_model_lengths(self):
  a,wa=self.solve(.1,[.8,0,0]);b,wb=self.solve(.1,[.16,0,0],size=.2);self.assertLess(angle(a[1].rotation,b[1].rotation),.01);self.assertAlmostEqual(wa[2].position[0]*.2,wb[2].position[0],places=6)
 def test_parent_rotation_transports_history_in_parent_coordinates(self):
  state={};base=chain(.01);local=[p.WorldTransform([0,0,0],Q[:],[1,1,1])]+base
  p._apply_stable_leg_ik(local,[None,0,1,2],1,2,3,[.75,.001,0],Q,state=state,bind_axis=[0,0,-1],delta_time=1/30)
  old=copy.deepcopy(local);turn=[0,0,1,0];local=[p.WorldTransform([0,0,0],turn,[1,1,1])]+chain(.01)
  p._apply_stable_leg_ik(local,[None,0,1,2],1,2,3,quat_rotate(turn,[.75,.001,0]),turn,state=state,bind_axis=[0,0,-1],delta_time=1/30)
  self.assertLess(angle(old[2].rotation,local[2].rotation),.001)
 def test_periodic_straight_crossings_keep_loop_end_pose(self):
  state={};first=last=None
  for i in range(61):
   a=.02*math.sin(i*math.tau/60);local,_=self.solve(a,[.75,.001*math.cos(i*math.tau/60),0],state)
   if i==0:first=local
   last=local
  self.assertLess(angle(first[0].rotation,last[0].rotation),.001);self.assertLess(angle(first[1].rotation,last[1].rotation),.001)

class SingleLegRoutingTests(unittest.TestCase):
 def test_bind_axis_is_derived_from_each_model_frame(self):
  u,b,a,c=fixture();axis=c.leg_ik_bind_axes['r_foot'];self.assertLess(angle([*axis,0.],[0,0,-1,0]),.001)
  v=copy.deepcopy(u);v.transforms[2].rotation=[0.,math.sin(.1/2),0.,math.cos(.1/2)];other=p.derive_leg_bind_axes(v,b,c.ik_chains)['r_foot'];self.assertLess(abs(sum(x*y for x,y in zip(axis,other))),.01)
 def test_effective_model_axes_round_trip_without_root_config_edits(self):
  u,b,a,c=fixture()
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'single-config.toml';single._write_effective_config(path,c,{});read=p.ModConfig.load(path);self.assertEqual(read.leg_ik_bind_axes,c.leg_ik_bind_axes)
 def test_invalid_axis_tables_are_rejected(self):
  for axes in ({'r_hand':[0,0,1]},{'r_foot':[0,0,0]},{'r_foot':[0,0,float('nan')]},{'r_foot':[0,1]}):
   with self.assertRaises(ValueError):p.ModConfig({},leg_ik_bind_axes=axes)
 def test_single_opt_in_requires_model_bind_axis(self):
  u,b,a,c=fixture();c.leg_ik_bind_axes={}
  with self.assertRaisesRegex(ValueError,'actual bind axis'):p.modify_animation_with_world_compensation(a,b,u,c,apply_ik_correction=True,stabilize_leg_ik=True)
 def test_default_modifier_never_calls_new_leg_solver(self):
  from unittest.mock import patch
  u,b,a,c=fixture()
  with patch.object(p,'_apply_stable_leg_ik',side_effect=AssertionError('default changed')):p.modify_animation_with_world_compensation(a,b,u,c,apply_ik_correction=True)
 def test_additive_opt_in_matches_legacy_additive_bytes(self):
  u,b,a,c=fixture()
  for state in a.initial_bone_states:state.scale=[0.,0.,0.];state.position=[0.,0.,0.];state.rotation=Q[:]
  a.is_additive=True
  before=copy.deepcopy(a);after=copy.deepcopy(a)
  opts=dict(allow_additive=True,apply_offsets_to_additive=False,apply_ik_correction=True,preserve_unmodified_channels=True,preserve_source_key_times=True)
  p.modify_animation_with_world_compensation(before,b,u,c,**opts);r=p.modify_animation_with_world_compensation(after,b,u,c,stabilize_leg_ik=True,**opts);self.assertEqual(before.to_bytes(),after.to_bytes());self.assertEqual(r.leg_ik_evaluations,0)
 def test_opt_in_reports_leg_diagnostics(self):
  u,b,a,c=fixture();r=p.modify_animation_with_world_compensation(a,b,u,c,apply_ik_correction=True,stabilize_leg_ik=True);self.assertGreater(r.leg_ik_evaluations,0);self.assertGreaterEqual(r.leg_ik_max_target_displacement,0)
 def test_new_leg_state_is_not_shared_by_clips_threads_or_processes(self):
  u,b,a,c=fixture();raw=a.to_bytes();index=FakeResourceIndex({1:TocEntry(1,ANIMATION_TYPE_ID,bytearray(raw)),2:TocEntry(2,ANIMATION_TYPE_ID,bytearray(raw))},{})
  jobs=[BatchJob(i,'package',u,b,unit_context_signature(u,b)) for i in (1,2)]
  results=[build_batch_entries(index,jobs,c,apply_ik_correction=True,stabilize_leg_ik=True,threads=n,use_processes=process) for n,process in ((1,False),(2,False),(2,True))]
  for r in results:self.assertFalse(r.fatal_issues);self.assertEqual(len(r.animations),2);self.assertTrue(all(x.modification.leg_ik_evaluations>0 for x in r.animations));self.assertEqual(bytes(r.entries[0].toc_data),bytes(r.entries[1].toc_data))
  self.assertEqual([bytes(e.toc_data) for e in results[0].entries],[bytes(e.toc_data) for e in results[1].entries]);self.assertEqual([bytes(e.toc_data) for e in results[0].entries],[bytes(e.toc_data) for e in results[2].entries])

if __name__=='__main__':unittest.main()

