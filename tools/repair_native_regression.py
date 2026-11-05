"""Repair existing native clips without resampling the Source motion tested in game."""
import copy, hashlib, json, shutil, sys
from pathlib import Path
from collections import OrderedDict
sys.path.append(str(Path(__file__).resolve().parents[3]))
from anim_batch_mod.archive import PackageStore, TocArchive
from anim_batch_mod.constants import ANIMATION_TYPE_ID, UNIT_TYPE_ID, BONE_TYPE_ID
from anim_batch_mod.native_animation import preserve_driver_channels, read_blocks
from anim_batch_mod.native_skeleton import load_manifest, append_unit, append_bones, animation_nodes
from anim_batch_mod.formats import UnitData, BonesData

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'outputs/native-fix-20261103'
WORK=ROOT/'outputs/native-regression-20261103'

def patch(path):
    return TocArchive.parse_parts(path.read_bytes(),*(Path(str(path)+s).read_bytes() for s in ('.gpu_resources','.stream')))

def digest(path):
    with path.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def run():
    project=WORK/'project'
    if not project.exists(): shutil.copytree(ROOT/'outputs/native-manual-20261103/project',project)
    manifest=load_manifest(project/'models/test01/source-skeleton.json')
    for p in project.rglob('source-skeleton.json'):
        p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    runtime=project/'animations/runtime'; runtime.mkdir(exist_ok=True)
    if any(runtime.iterdir()): raise FileExistsError(runtime)
    build=json.loads((project/'animations/build-report.json').read_text(encoding='utf-8'))
    lookup={int(e['id']):e['package'] for e in build['animations']}
    store=PackageStore(Path(r'E:\Steam\steamapps\common\Helldivers 2\data'))
    cache=OrderedDict()
    def original(fid):
        name=lookup[fid]
        if name not in cache:
            if len(cache)>=2: cache.popitem(last=False)
            cache[name]=TocArchive.load_toc_only(store,name)
        cache.move_to_end(name)
        return cache[name].entries[(fid,ANIMATION_TYPE_ID)].toc_data
    report=dict(status='building',animations=0,original_driver_bytes_changed_in_previous_package=0,
                original_driver_bytes_preserved=True,source_channel_bytes_preserved=True,
                physics_nodes=sum(n.get('physics',False) for n in manifest['bones']),game_tested=False)
    for p in sorted((OLD/'project/animations/runtime').glob('*.patch_*'),key=lambda p:p.name):
        if p.suffix in ('.stream','.gpu_resources'): continue
        ar=patch(p)
        for entry in ar.entries.values():
            if entry.type_id==ANIMATION_TYPE_ID:
                base=original(entry.file_id); previous=entry.toc_data
                try: repaired=preserve_driver_channels(base,previous)
                except Exception as error: raise ValueError(f'{entry.file_id} {p.name}: {error}') from error
                changed=False
                for a,b,c in zip(read_blocks(base),read_blocks(previous),read_blocks(repaired)):
                    count=len(a.states); assert count==90
                    native=lambda block:[e for e in block.entries if e[1] is None or e[1]<count]
                    source=lambda block:[e for e in block.entries if e[1] is not None and e[1]>=count]
                    assert a.states==c.states[:count] and a.flags==c.flags[:count*3]
                    assert native(a)==native(c) and a.hash_floats==c.hash_floats
                    assert b.states[count:]==c.states[count:] and b.flags[count*3:]==c.flags[count*3:]
                    assert source(b)==source(c)
                    changed |= a.states!=b.states[:count] or native(a)!=native(b)
                report['original_driver_bytes_changed_in_previous_package']+=int(changed)
                report['animations']+=1
                entry.toc_data=bytearray(repaired)
            elif entry.type_id==UNIT_TYPE_ID:
                entry.toc_data=append_unit((OLD/'avatar.toc').read_bytes(),manifest)
                unit=UnitData.parse(entry.toc_data)
                assert not {n['hash'] for n in manifest['bones'] if n.get('physics')} & set(unit.name_hashes)
            elif entry.type_id==BONE_TYPE_ID:
                entry.toc_data=append_bones((OLD/'bones.toc').read_bytes(),manifest)
                bones=BonesData.parse(entry.toc_data)
                assert bones.hashes[-89:]==[n['hash'] for n in animation_nodes(manifest)]
        paths=ar.write_patch(runtime/p.name,list(ar.entries.values()))
        reread=patch(runtime/p.name)
        assert reread.entries.keys()==ar.entries.keys()
        assert all(reread.entries[k].toc_data==e.toc_data for k,e in ar.entries.items())
        print(f"Verified {report['animations']}/3180 animations: {p.name}",flush=True)
    assert report['animations']==3180
    report['status']='PASS'
    (WORK/'reports/animation-physics-isolation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    build.update(retarget_version='preserved-drivers-unlinked-physics-v3',driver_channels_preserved=True,
                 physics_unlinked_nodes=report['physics_nodes'],source_motion_reused=True)
    build['files']=[dict(path='runtime/'+p.name,bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(runtime.iterdir())]
    (project/'animations/build-report.json').write_text(json.dumps(build,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__': run()
