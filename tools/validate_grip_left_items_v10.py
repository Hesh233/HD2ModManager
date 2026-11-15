"""V10 readback and real Chef parser/sandbox entry smoke; no game IO."""
import inspect,json,sys
from pathlib import Path
import validate_detailed_grip_test as readback
import verify_grip_equipment_v9_entry as entry
import build_grip_left_items_v10 as builder
OUT,VERSION=builder.OUT,builder.VERSION

def main():
 global OUT,VERSION
 OUT,VERSION=builder.OUT,builder.VERSION
 readback.OUT=OUT;readback.VERSION=VERSION
 fn=inspect.getsource(readback.main).replace("p['logging']['maxBytes']==8*1024*1024", "p['logging']['maxBytes']==16*1024*1024")
 env=dict(readback.__dict__);exec(compile(fn,'<v10-readback>','exec'),env);env['main']()
 fn=inspect.getsource(entry.main).replace('_EQUIPMENT_PERF_V9_',f'_{builder.TAG}_')
 env=dict(entry.__dict__);env['OUT']=OUT;env['VERSION']=VERSION;exec(compile(fn,'<v10-chef-entry>','exec'),env);env['main']()
 p=json.loads((OUT/'test06/B23-profile.json').read_text(encoding='utf-8'));assert p['testRepairs']['leftHeldItems']['enabled'] and p['testRepairs']['equipmentV10']['carryMounts']['pistol']
 assert len(p['testRepairs']['heldEquipment']['rigidRight'])>=23
 for id in ['819ec78bcaf69c49','612f7f6193fb1b2b','076692fd83a83c5c','48fd06b465e8b681','72fe4b13f726c344','16051937941bb709']:
  assert p['consumers'][id]['verifiedComponent'] and id in p['allowedConsumers']
 if builder.REVISION>=11:
  assert p['testRepairs']['leftHeldItems']['recoverLocalOffset'] and p['testRepairs']['leftHeldItems']['requireExternalParent'] and p['testRepairs']['leftHeldItems']['reloadComponentsOnly']
  assert p['testRepairs']['equipmentV10']['alternateLinkedRoots'] and p['consumers']['16051937941bb709']['repairFamily']=='EQUIPMENT_V10'
 if builder.REVISION>=12:
  assert all(0 in p['consumers'][rid]['heldRoots'] for rid in ('005c2262f672caf4','07d605bd50c98461','503c0e01fbafa86a'))
  assert all(rid in p['testRepairs']['heldEquipment']['rigidRight'] for rid in builder.V12_MELEE)
 print(f'V{builder.REVISION} additional profile checks PASS')
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,choices=(10,11,12),default=10);builder.configure_revision(parser.parse_args().revision)
 sys.stdout.reconfigure(encoding='utf-8');main()
