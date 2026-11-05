"""Offline native-rig artifact audit and a two-clip real-data runtime smoke fixture."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from anim_batch_mod.archive import PackageStore, ResourceIndex, TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID, BONE_TYPE_ID, STATE_MACHINE_TYPE_ID, ANIMATION_TYPE_ID
from anim_batch_mod.formats import UnitData, BonesData, AnimationData, parse_state_machine_animation_ids
from anim_batch_mod.native_skeleton import validate_manifest, row_pose
from anim_batch_mod.processor import _calculate_world_transforms


def smoke_fixture(game, output, manifest, cache):
    output.mkdir(parents=True, exist_ok=False)
    store=PackageStore(game)
    index=ResourceIndex(store,cache,{UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID})
    try:
        index.load_or_build()
        _,unit_entry=index.resolve(int(manifest['referenceUnit'],0),UNIT_TYPE_ID)
        unit=UnitData.parse(unit_entry.toc_data)
        _,bones=index.resolve(unit.bones_ref,BONE_TYPE_ID)
        _,state=index.resolve(unit.state_machine_ref,STATE_MACHINE_TYPE_ID)
        selected={}
        for clip_id in parse_state_machine_animation_ids(state.toc_data):
            _,entry=index.resolve(clip_id,ANIMATION_TYPE_ID)
            clip=AnimationData.parse(entry.toc_data)
            if clip.is_additive not in selected:
                selected[clip.is_additive]=entry
            if len(selected)==2: break
        assert len(selected)==2, 'Need both additive and ordinary clips'
        state=copy.copy(state)
        state.toc_data=bytearray(136)
        struct.pack_into('<III',state.toc_data,0,0,1,76)
        struct.pack_into('<II',state.toc_data,76,1,8)
        struct.pack_into('<IIII',state.toc_data,84,0,0,1,16)
        struct.pack_into('<QIII',state.toc_data,100,0,0,2,20)
        struct.pack_into('<QQ',state.toc_data,120,*(e.file_id for e in selected.values()))
        archive=TocArchive.load_toc_only(store,manifest['referenceArchive'])
        archive.write_patch(output/manifest['referenceArchive'],[unit_entry,bones,state,*selected.values()])
        archive.write_patch(output/'9ba626afa44a3aa3',[])
        return {'diagnostic_fixture':True,'animations':[str(e.file_id) for e in selected.values()]}
    finally: index.close()


def read_patch(path):
    parts=[Path(str(path)+suffix) for suffix in ('.gpu_resources','.stream')]
    return TocArchive.parse_parts(path.read_bytes(),*(p.read_bytes() if p.exists() else b'' for p in parts))


def verify(models, animations, manifest):
    validate_manifest(manifest)
    sources=manifest['bones']
    units=[]
    max_world_error=0.
    for path in models.rglob('*.patch_*'):
        if path.suffix in ('.stream','.gpu_resources'): continue
        for entry in read_patch(path).entries_of_type(UNIT_TYPE_ID):
            unit=UnitData.parse(entry.toc_data)
            indices={h:i for i,h in enumerate(unit.name_hashes)}
            fk=_calculate_world_transforms(unit.transforms,unit.parents)
            for node in sources:
                i=indices[node['hash']]
                expected_parent=manifest['driverHashes'][0] if node['parent'] is None else sources[node['parent']]['hash']
                assert unit.name_hashes[unit.parents[i]]==expected_parent, 'Source parent changed'
                expected=row_pose(node['world'])
                error=math.dist(fk[i].position,expected.position)
                max_world_error=max(max_world_error,error)
                assert error < 1e-5, ('Source bind changed',node['name'],error)
                assert abs(sum(a*b for a,b in zip(fk[i].rotation,expected.rotation))) > 1-1e-5
            units.append(str(entry.file_id))
    assert len(units)==7, ('Expected seven body units',len(units))
    result={'model_units':len(units),'source_nodes_per_unit':len(sources),
            'max_serialized_bind_error_metres':max_world_error,'game_tested':False}
    if animations:
        report=json.loads((animations/'build-report.json').read_text(encoding='utf-8-sig'))
        assert report['status']=='complete'
        seen=set(); clips=set(); skeletons=0
        for file in report['files']:
            path=animations/file['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==file['sha256']
            if path.suffix in ('.stream','.gpu_resources'): continue
            for key,entry in read_patch(path).entries.items():
                assert key not in seen, ('Duplicate runtime resource',key)
                seen.add(key)
                if entry.type_id==ANIMATION_TYPE_ID:
                    assert struct.unpack_from('<I',entry.toc_data,4)[0]==report['driver_bones']+len(sources)
                    clips.add(str(entry.file_id))
                elif entry.type_id==BONE_TYPE_ID:
                    bones=BonesData.parse(entry.toc_data)
                    assert bones.hashes[-len(sources):]==[b['hash'] for b in sources]
                    assert bones.names[-len(sources):]==[b['name'] for b in sources]
                    skeletons+=1
                elif entry.type_id==UNIT_TYPE_ID:
                    unit=UnitData.parse(entry.toc_data)
                    assert unit.name_hashes==manifest['driverHashes']+[b['hash'] for b in sources]
                    skeletons+=1
        assert skeletons==2
        assert clips=={a['id'] for a in report['animations']}
        assert len(clips)==report['expected_animations']
        result.update(animations=len(clips),additive=sum(a['additive'] for a in report['animations']),
            runtime_resources=len(seen),runtime_bytes=sum(f['bytes'] for f in report['files']),
            max_sampled_bone_length_error=max(a['max_bone_length_error'] for a in report['animations']))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--models',type=Path)
    parser.add_argument('--animations',type=Path)
    parser.add_argument('--game-data',type=Path)
    parser.add_argument('--cache',type=Path)
    parser.add_argument('--smoke-fixture',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    result=smoke_fixture(args.game_data,args.smoke_fixture,manifest,args.cache) if args.smoke_fixture else verify(args.models,args.animations,manifest)
    if args.game_data and args.animations and not args.smoke_fixture:
        report=json.loads((args.animations/'build-report.json').read_text(encoding='utf-8-sig'))
        store=PackageStore(args.game_data)
        wanted={}
        for clip in report['animations']:
            wanted.setdefault(clip['package'],set()).add(int(clip['id']))
        checked=0
        for package,ids in wanted.items():
            header=store.load_toc_header(package)
            types,count=struct.unpack_from('<II',header,4)
            for i in range(count):
                offset=72+types*32+i*80
                file_id,type_id=struct.unpack_from('<QQ',header,offset)
                if type_id==ANIMATION_TYPE_ID and file_id in ids:
                    assert not any(struct.unpack_from('<II',header,offset+60)), 'External animation payload was omitted'
                    checked+=1
        assert checked==report['expected_animations']
        result['original_animation_external_payloads_checked']=checked
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
