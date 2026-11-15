"""Actual FP97/model264 receiver/lifecycle fixture and immutable prefix/package checks."""
from pathlib import Path
import argparse,hashlib,json,struct,sys,zipfile
import numpy as np
import build_detailed_grip_test as b
from build_first_person_source_test import ROOT,OUT,VERSION,SOURCE_NAME,TAG
from prepare_native_v31_b23 import legacy_arm_math, compose_source
from audit_native_b23_107_issues import plain
from lupa.lua51 import LuaRuntime
from verify_test04_lua_entry import exercise

def run_fixture(p,fp,model,live,source,tap=None):
 vm=LuaRuntime(unpack_returned_tuples=True);vm.globals().contract=vm.table_from(p,recursive=True);vm.globals().fp_fixture=vm.table_from(dict(resource=p['avatar']['resource'],matrices=b.matrices(fp),parents=fp.parents,hashes=fp.name_hashes),recursive=True);vm.globals().model_fixture=vm.table_from(dict(resource=p['model']['resource'],matrices=b.matrices(model),parents=model.parents,hashes=model.name_hashes),recursive=True)
 vm.globals().live_samples=vm.table_from(live['samples'],recursive=True);vm.globals().f32=lambda x:float(np.float32(x))
 vm.globals().hash_name=b.bone_name_hash;vm.globals().arm_math=vm.execute(legacy_arm_math());vm.globals().guard_module=vm.execute((ROOT/'HD2PhysBoneCompat/src/native_first_person_guard.lua').read_text(encoding='utf-8-sig'));vm.globals().source_module=vm.execute(source)
 vm.globals().fixture_log_tap=tap
 return plain(vm.execute((ROOT/'HD2PhysBoneCompat/test/first_person_source_receiver_harness.lua').read_text(encoding='utf-8-sig')))

def main(argv=None):
 global OUT
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,default=OUT);OUT=parser.parse_args(argv).out.resolve()
 p=b.load(OUT/'fp-source-contract.json');fpraw=(OUT/'fp-expanded-unit.toc').read_bytes();modelraw=(OUT/'fp-model-unit.toc').read_bytes();fp=b.UnitData.parse(fpraw);model=b.UnitData.parse(modelraw)
 live=b.load(ROOT/'HD2PhysBoneCompat/test/fixtures/first_person_source_live_a1_20261109_135025.json')
 source=(ROOT/'HD2PhysBoneCompat/src/first_person_source_test.lua').read_text(encoding='utf-8-sig')
 result=run_fixture(p,fp,model,live,source);logs=result.pop('logs');result['gameTested']=False
 captures=[r for r in logs if r.get('event')=='fp_native_and_melee_capture'];assert captures and all(len(r['nativePoses'])==47 for r in captures),'FP47 capture not complete'
 result['nativeFP47CaptureVerified']=True
 controls={}
 variants=[
  ('missingNativeInputRefresh',source.replace('W.update_unit(a.world,a.unit);self.stats.nativeInputRefreshes=self.stats.nativeInputRefreshes+1','self.stats.nativeInputRefreshes=self.stats.nativeInputRefreshes+1',1),'stale native producer cache caused Source readback failure'),
  ('sharedDiagnosticSlot',source.replace('local slot=r.event',"local slot='shared'",1),'native capture starved successful receiver diagnostics'),
  ('sourceMotionOnly',source.replace('and modelSpan>=(p.motionProofMetres or .002)and motionAgreement<=(p.motionAgreementTolerance or .0002)','',1),'tolerance-matching frozen receiver displayed'),
  ('disabledSourceWorldProof',source.replace('if worldError>=.0002 then','if worldError>=100 then',1),'frozen Source output was displayed'),
 ]
 for label,broken,expected in variants:
  assert broken!=source
  tapped=[]
  try:run_fixture(p,fp,model,live,broken,lambda r:tapped.append(plain(r)))
  except Exception as error:
   assert expected in str(error),str(error)
   failures=[r for r in tapped if r.get('event')=='fp_source_unavailable']
   controls[label]=dict(detected=True,assertion=expected,lastFailure=failures[-1] if failures else None)
  else:raise AssertionError('Missing negative control '+label)
 # Historical A1 is read from its delivered source, never regenerated/overwritten.
 old_entry=(ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/receiver-a1/hd2attachmentfix-FP-A1.lua').read_text(encoding='utf-8')
 old_source=old_entry.split('local FirstPersonSource=(function()\n',1)[1].split('\nend)()\nlocal profile=',1)[0]
 tapped=[]
 try:run_fixture(p,fp,model,live,old_source,lambda r:tapped.append(plain(r)))
 except Exception as error:
  assert 'stale native producer cache caused Source readback failure' in str(error),str(error)
  failures=[r for r in tapped if r.get('event')=='fp_source_unavailable'];assert failures and 'fp_source_world_readback' in failures[-1]['reason']
  controls['oldA1ReadbackFailureReproduced']=dict(detected=True,sourceSha256=hashlib.sha256(old_source.encode()).hexdigest(),failure=failures[-1],syntheticCacheSchedule=True,liveRootCauseNotDirectlyObserved=True)
 else:raise AssertionError('A1 did not reproduce old-cache readback failure')
 result['negativeControls']=controls

 profile=b.load(OUT/'B23-profile.json');row=b.load(OUT/'build-report.json');entry=(OUT/SOURCE_NAME).read_text(encoding='utf-8');assert compose_source(profile)==entry,'Package composed Lua differs from current tested modules';assert hashlib.sha256(entry.encode()).hexdigest()==row['luaSha256'];smoke=exercise(entry);assert smoke['started'] and smoke['version']==VERSION and smoke['writes']==0 and smoke['closed']==1,smoke
 old=ROOT/'outputs/grip-left-items-test-20261109-v10/v12';oldrow=next(r for r in b.load(old/'build-report.json')if r['model']=='test06')
 with zipfile.ZipFile(row['package'])as z,zipfile.ZipFile(oldrow['package'])as baseline:
  assert z.testzip()is None
  lua_archive=b.TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_0'),load_external_data=False);assert len(lua_archive.entries)==1
  lua_payload=bytes(next(iter(lua_archive.entries.values())).toc_data);size,version=struct.unpack_from('<II',lua_payload);assert version==2 and lua_payload[8:8+size]==entry.encode('utf-8')
  for name in('9ba626afa44a3aa3.patch_1','9ba626afa44a3aa3.patch_1.gpu_resources','9ba626afa44a3aa3.patch_1.stream'):assert z.read(name)==baseline.read(name)
  resources=b.TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_2'),load_external_data=False);assert len(resources.entries)==1
  e=next(iter(resources.entries.values()));assert e.file_id==int(p['avatar']['resource'],16)and e.type_id==b.UNIT_TYPE_ID and bytes(e.toc_data)==fpraw
  assert z.read('9ba626afa44a3aa3.patch_2.gpu_resources')==z.read('9ba626afa44a3aa3.patch_2.stream')==b''
 old_profile=b.load(old/'test06/B23-profile.json');protected_profile=json.loads(json.dumps(profile));protected_profile.pop('firstPersonSource');protected_profile['variant']=old_profile['variant'];protected_profile['testRepairs'].pop('meleeCapture');protected_profile['testRepairs']['version']=old_profile['testRepairs']['version'];protected_profile['testRepairs']['logTag']=old_profile['testRepairs']['logTag'];assert protected_profile==old_profile,'TP/railgun/muzzle/reload math/profile changed'
 a1=ROOT/'outputs/grip-left-items-analysis-20261109/fp-start/receiver-a1'
 for name in ('fp-native-unit.toc','fp-expanded-unit.toc','fp-native.bones','fp-model-unit.toc'):assert (OUT/name).read_bytes()==(a1/name).read_bytes(),name
 for path,h in row['originalModelInputs'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 (OUT/'receiver-runtime-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 report=dict(status='PASS_PENDING_GAME_TEST',runtime=result,packageReadback=True,native63AndAnimation47Preserved=True,tpCompanionsByteIdentical=True,originalModelInputsUnchanged=True,a1FpGraphByteIdentical=True,tpPoliciesIncludingRailgunMuzzleReloadUnchanged=True,composedPackageLuaMatchesTestedSource=True,entrySmoke={k:v for k,v in smoke.items()if k!='logs'},fpSourceUnitSha256=hashlib.sha256(fpraw).hexdigest(),gameDeployed=False,gameTested=False,gpuPaletteObserved=False)
 (OUT/'receiver-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
