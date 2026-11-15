"""Complete historical suite plus V10 held/released/holstered equipment checks."""
from pathlib import Path
import inspect,json,sys
import audit_detailed_grip_test as base
import build_grip_left_items_v10 as builder
OUT=builder.OUT

def main():
 global OUT
 OUT=builder.OUT
 base.OUT=OUT;fn=inspect.getsource(base.main)
 old="+(tests/'native_grip_equipment_v9_harness.lua').read_text(encoding='utf-8-sig')"
 ids=list(json.loads((OUT/'throwables.json').read_text(encoding='utf-8')))
 from prepare_native_v31_b23 import lua
 extra="+ '\\nlocal test_v10_throwable_ids="+lua(ids).replace('\\','\\\\').replace("'","\\'")+"\\n' +(tests/'native_grip_left_items_v10_harness.lua').read_text(encoding='utf-8-sig')"
 if builder.REVISION>=11:
  # The old harness ignored child locals and returned an internal parent for linked roots.
  # Model external links faithfully only for this opt-in revision.
  wrapper="local v11Parent=U.scene_graph_parent;U.scene_graph_parent=function(u,n)if u.linkOwner and not u.legacyParentRead and n==u.linkRoot then recycled();return nil end;return v11Parent(u,n)end\n"
  pos="+(tests/'native_grip_left_items_v10_harness.lua')"
  assert pos in extra;extra=extra.replace(pos,"+"+repr(wrapper)+pos,1)
  extra+="+(tests/'native_grip_left_items_v11_harness.lua').read_text(encoding='utf-8-sig')"
 if builder.REVISION>=12:extra+="+(tests/'native_grip_left_items_v12_harness.lua').read_text(encoding='utf-8-sig')"
 assert old in fn;fn=fn.replace(old,old+extra,1)
 needle=" result.update(negativeControls=controls"
 controls=""" for label,broken,expected in [
  ('leftHeldItems',source.replace('local policy=test and test.leftHeldItems','local policy=false',1),'TEST V10 left native-held follower missing'),
  ('carriedMountScope',source.replace('if test and test.equipmentV10 and test.equipmentV10.enabled then','if false then',1),'TEST V10 holstered gun/component refresh missing')
 ]:
  assert broken!=source
  try:run_harness(p,f,h,source=broken)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing V10 negative control '+label)
"""
 if builder.REVISION>=11:
  controls+=""" for label,broken,expected in [
  ('nonidentityLinkedLocal',source.replace('expected=compose(mountRow.basis,localPose)','expected=mountRow.basis',1),'TEST V11 nonidentity left-linked local not recovered'),
  *([] if builder_revision>=12 else [('externalParentGate',source.replace('(not requireExternal or external)','true',1),'TEST V11 internal-parent lookalike was claimed')]),
  ('externalRootRefresh',source.replace('if test.equipmentV10.alternateLinkedRoots then','if false then',1),'TEST V11 Reprimand'),
  ('linkGraphTelemetry',source.replace("event='test_equipment_graph'","event='test_equipment_graph_off'",1),'TEST V11 bounded link/graph telemetry missing')
 ]:
  assert broken!=source
  try:run_harness(p,f,h,source=broken)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing V11 negative control '+label)
"""
 if builder.REVISION>=12:
  controls+=""" for label,broken,expected in [
  ('unitRootComposition',source.replace('if recover and policy.unitRootComposeOnly and index==0 then matched=false end','if recover and index==0 then return end',1),'TEST V10 left native-held follower missing'),
  ('internalChildGate',source.replace('(not requireExternal or external)','true',1),'TEST V12 internal child lookalike claimed'),
  ('meleeNativeFollow',source.replace('local spec=policy.rigidRight[item.spec.resource]','local spec=policy.rigidRight[item.spec.resource];if spec and spec.itemType=="melee" then spec=nil end',1),'TEST V12 native melee right follower missing')
 ]:
  assert broken!=source
  try:run_harness(p,f,h,source=broken)
  except Exception as e:
   assert expected in str(e),str(e);controls[label]=True
  else:raise AssertionError('Missing V12 negative control '+label)
"""
 assert needle in fn;fn=fn.replace(needle,controls+needle,1);fn=fn.replace('controls[label]=True','controls[label]=True;print("Negative control PASS:",label,flush=True)');env=dict(base.__dict__);env['builder_revision']=builder.REVISION;exec(compile(fn,'<v10-full-audit>','exec'),env);env['main']()
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,choices=(10,11,12),default=10);parser.add_argument('--quick',action='store_true')
 args=parser.parse_args();builder.configure_revision(args.revision);sys.stdout.reconfigure(encoding='utf-8');main()
