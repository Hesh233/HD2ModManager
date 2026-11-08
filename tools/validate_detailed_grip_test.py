"""Read-back validation of test Lua, exact existing rigs and model bindings."""
from pathlib import Path
import json,sys,zipfile,hashlib,struct
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/grip-rollback-ragdoll-test-20261108-v7';BASE=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
sys.path.insert(0,str(ROOT.parents[1]));sys.path.insert(0,str(BASE))
import lz4;sys.modules['utils.lz4_311']=lz4
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.formats import UnitData
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.native_skeleton import bone_name_hash
from prepare_native_v31_b23 import compose_source
from build_detailed_grip_test import VERSION
from lupa.lua51 import LuaRuntime

def main():
 reports=[]
 for row in json.loads((OUT/'build-report.json').read_text(encoding='utf-8')):
  name=row['model'];base=BASE/f'test-library/[骨骼挂点修正]{name}'
  with zipfile.ZipFile(row['package']) as z:
   assert z.testzip() is None;p=json.loads(z.read('attachment-profile.json'));manifest=json.loads(z.read('manifest.json'))
   assert '测试' in manifest['Name'] and '详细' in manifest['Name'] and VERSION in manifest['Description']
   assert p['testRepairs']['version']==VERSION and p['logging']['compact'] is False and p['logging']['detailed'] is True
   beacon=p['testRepairs']['beacon'];fixtures=json.loads((OUT/'equipment-fixtures.json').read_text(encoding='utf-8'));bf=fixtures[beacon['resource']]
   assert beacon['count']==bf['count']==37 and beacon['neverWriteBeaconOrEffects'] is True
   for node in p['consumers'][beacon['resource']]['nodes']:
    assert bf['hashes'][node['index']]==bone_name_hash(node['name'])
    if node.get('parent') is not None:assert bf['parents'][node['index']]==node['parent']
   for node in beacon['probeNodes']:assert bf['hashes'][node['index']]==node['hash']
   assert p['testRepairs']['aimDiagnostics']['readOnly'] is True
   assert 'nativeReverse' not in p['testRepairs'] and p['testRepairs']['reverseExperimentRemoved']
   assert p['testRepairs']['bodyDiagnostics']['readOnly'] and p['testRepairs']['bodyDiagnostics']['bypassNoAnimationStateMachine']
   assert p['testRepairs']['bodyDiagnostics']['requireObservedStateMachinePresent']
   assert p['testRepairs']['bodyDiagnostics']['maxUnownedModels']==6
   tracking=p['testRepairs']['gripTracking'];assert tracking['readOnly'] and tracking['solverUnchangedFromV4']
   assert tracking['resources']=={'dbb6c961c59fadc1':True}
   assert tracking['stages']==['final_output','next_render_input']

   assert p['testRepairs']['sg225Parts']['enabled'] is True
   for rid in p['testRepairs']['sg225Parts']['extraResources']+p['testRepairs']['sg225Parts']['muzzleResources']:
    spec=p['consumers'][rid];f=fixtures[rid]
    assert spec['count']==f['count'] and spec['repairFamily']=='SG225'
    for node in spec['nodes']:assert f['hashes'][node['index']]==bone_name_hash(node['name'])
   assert p['testRepairs']['reloadParts']['enabled'] is True
   for rid in p['testRepairs']['reloadParts']['resources']:
    spec=p['consumers'][rid];f=fixtures[rid]
    assert spec['count']==f['count'] and spec['repairFamily']=='HMG_LAS'
    for node in spec['nodes']:assert f['hashes'][node['index']]==bone_name_hash(node['name'])
   source=compose_source(p).encode('utf-8')
   raw=TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_0'),load_external_data=False);data=bytes(next(iter(raw.entries.values())).toc_data);n,v=struct.unpack_from('<II',data)
   assert v==2 and data[8:8+n]==source and n+8==len(data)
   ok,error=LuaRuntime().eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(source.decode());assert ok,error
   assert b'TEST_ONLY_DETAILED' in source and b'hd2_grip_TEST_DETAILED_' in source and b'test_grip_tracking_probe' in source
   for suffix in ('','.gpu_resources','.stream'):assert z.read('9ba626afa44a3aa3.patch_1'+suffix)==(base/('9ba626afa44a3aa3.patch_1'+suffix)).read_bytes()
   rig=TocArchive.parse_parts(z.read('9ba626afa44a3aa3.patch_1'),load_external_data=False)
   u=UnitData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID));assert len(u.parents)==p['avatar']['count']
   nodes=list(p['avatar']['nodes'])+p['leftGrip']['nodes']+p['leftGrip']['outputs']+p['rightGrip']['nodes']+p['rightGrip']['outputs']+p['testRepairs']['poseProbes']
   for pair in p['testRepairs']['bodyDiagnostics']['pairs']:
    nodes += [pair[k] for k in ('source','native','reference') if pair.get(k)]
   nodes += list(p['testRepairs']['gripTracking']['actorNodes'].values())
   nodes += [p[k] for k in ('sourceRight','sourceLeft','nativeRight','nativeLeft','target','originalMount','sourceRightMount') if p.get(k)]
   for a in p['attachments']:nodes += [a[k] for k in ('node','source','native','reference','sourceMount') if a.get(k)]
   for b in p['bodySync']['outputs']:nodes += [b[k] for k in ('node','native','reference','positionParent')]
   for node in nodes:
    assert u.name_hashes[node['index']]==bone_name_hash(node['name']),(name,node)
    if node.get('parent') is not None:assert u.parents[node['index']]==node['parent'],(name,node)
   models={}
   for folder in ('vpk2patch','Overwrite'):
    for file in (BASE/f'test-library/[原比例模型]{name}'/folder).glob('*.patch_*'):
     if not file.suffix.rsplit('_',1)[-1].isdigit():continue
     archive=TocArchive.parse_parts(file.read_bytes(),load_external_data=False)
     for e in archive.entries.values():
      if e.type_id==UNIT_TYPE_ID:models[f'{e.file_id:016x}']=UnitData.parse(e.toc_data)
   skin_rows={}
   for part in ('vpk','overwrite'):
    data=json.loads((ROOT/f'outputs/grip-ragdoll-followup-20261108/{name}-skin-{part}.json').read_text(encoding='utf-8'))
    for r in data['rows']:skin_rows[r['resource']]=r['weightedNodes']
   for rid,spec in p['models'].items():
    m=models[rid];assert len(m.parents)==spec['count']
    assert [(r['index'],r['hash'],r['weightedVertices']) for r in spec['testSkinProbes']]==[(r['index'],r['hash'],r['weightedVertices']) for r in skin_rows[rid]]
    for node in spec['nodes']+spec.get('testWristProbes',[])+spec.get('testGripProbes',[])+spec.get('testSkinProbes',[]):
     assert m.name_hashes[node['index']]==bone_name_hash(node['name'])
     if node.get('parent') is not None:assert m.parents[node['index']]==node['parent']
   reports.append(dict(weightedProbeNodes=sum(len(v['testSkinProbes']) for v in p['models'].values()),modelOnlyProbeNodes=sum(not n['avatarSameHashAvailable'] for v in p['models'].values() for n in v['testSkinProbes']),model=name,avatarNodes=len(u.parents),avatarRows=len(nodes),models=len(p['models']),luaSha256=hashlib.sha256(source).hexdigest(),companionsByteIdentical=True,profileModelBindingsPass=True,testLabelPass=True))
 result=dict(status='PASS_PENDING_GAME_TEST',version=VERSION,packages=reports,gameTested=False,gameDeployed=False)
 (OUT/'package-readback-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
