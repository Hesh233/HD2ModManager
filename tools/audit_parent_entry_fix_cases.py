"""Independent raw parent/matrix, Lua entry and blend-mask audit of suite cases."""
import hashlib
import json
import struct
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID,STATE_MACHINE_TYPE_ID
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.native_skeleton import source_blend_mask_owners
from verify_test04_lua_entry import exercise
from audit_attachment_routes import audit as route_audit


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def archive(p):
    p=Path(p)
    return TocArchive.parse_parts(p.read_bytes(),load_external_data=False)
def table(raw):
    offset=struct.unpack_from('<I',raw,52)[0];n=struct.unpack_from('<I',raw,offset)[0];at=offset+16+128*n
    return offset,n,[struct.unpack_from('<HH',raw,at+4*i) for i in range(n)]


def audit_case(folder,game):
    folder=Path(folder);flow=read(folder/'import-regression.json');model=Path(flow['model'])
    manifest=read(model/'vpk2patch/source-skeleton.json');mounts=manifest['sourceAttachmentShadows'];added=len(mounts)
    assert added==21
    units=[]
    for path in sorted(model.rglob('*.patch_*')):
        if not path.suffix.rsplit('_',1)[-1].isdigit():continue
        a=archive(path)
        for e in a.entries_of_type(UNIT_TYPE_ID):
            raw=bytes(e.toc_data);u=UnitData.parse(raw)
            if not all(r['hash'] in u.name_hashes for r in mounts):continue
            offset,n,records=table(raw)
            assert all(p<n for _,p in records),'AQ parent list index would exceed node count'
            before_count=n-added;hashes=struct.pack(f'<{before_count}I',*u.name_hashes[:before_count])
            # Calibration can relocate a same-sized table before mounts are added.
            # The LAST preceding matching table is the actual append input.
            original_at=raw.rfind(hashes,0,offset)-16-132*before_count
            assert original_at>=0 and struct.unpack_from('<I',raw,original_at)[0]==before_count
            old_parent_at=original_at+16+128*before_count
            old_records=raw[old_parent_at:old_parent_at+4*before_count]
            assert old_records==raw[offset+16+128*n:offset+16+128*n+4*before_count]
            assert raw[original_at+16:original_at+16+64*before_count]==raw[offset+16:offset+16+64*before_count]
            assert raw[original_at+16+64*before_count:original_at+16+128*before_count]==raw[offset+16+64*n:offset+16+64*n+64*before_count]
            for row in mounts:
                index=u.name_hashes.index(row['hash']);parent=u.name_hashes.index(row['sourceAnchorHash'])
                assert records[index]==(1,parent)
            units.append({'resource':f'{e.file_id:016x}','nodes':n,'existingParentRecordsPreserved':before_count,'rawMatricesPreserved':True})
    attachment=read(next((folder/'attachment').rglob('attachment-build-report.json')))
    expected=set(attachment['modelResources'])
    assert expected<={r['resource'] for r in units},'Missing a registered Source model Unit'
    assert units
    runtime=next((folder/'animations/runtime').glob('*.patch_2'));a=archive(runtime)
    avatar=a.entries_of_type(UNIT_TYPE_ID)[0];_,n,records=table(avatar.toc_data)
    assert all(p<n for _,p in records),'Avatar parent table is invalid'
    lua_files=[p for p in (folder/'attachment').rglob('*.lua') if p.read_text(encoding='utf-8-sig').startswith('-- HD2-Addon:')]
    assert len(lua_files)==1
    lua=exercise(lua_files[0].read_text(encoding='utf-8-sig'))
    assert lua['started'] and lua['version']=='1.0.9' and lua['closed']==1 and lua['writes']==0
    events=[json.loads(l[l.index('{'):].strip()) for l in lua['logs']]
    loaded=next(e for e in events if e['event']=='loaded')
    # The generated standalone Lua package also carries its avatar override.
    lua_package=next(p for p in folder.iterdir() if p.is_dir() and p.name.startswith('[骨骼挂点修正]'))
    lua_avatars=[e for q in lua_package.glob('*.patch_*') if q.suffix.rsplit('_',1)[-1].isdigit() for e in archive(q).entries_of_type(UNIT_TYPE_ID) if e.file_id==0x4d1c334d294dfa97]
    assert len(lua_avatars)==1
    _,lua_n,lua_records=table(lua_avatars[0].toc_data)
    assert all(p<lua_n for _,p in lua_records)
    # The established Lua package adds five unanimated reference/output nodes
    # and overrides the animation package's smaller avatar, by design.
    assert loaded['rigExpectedNodes']==lua_n and any(e['event']=='complete' for e in events)
    # Compare all masks to the original native input bytes, not generator output alone.
    inputs=ROOT/'outputs/attachment-root-mask-fix-20261106/inputs'
    original=(inputs/'state-machine.toc').read_bytes();bones=BonesData.parse((inputs/'bones.toc').read_bytes())
    m=read(folder/'animations/source-skeleton.json');owners=source_blend_mask_owners(bones,m)
    patched=bytes(a.entries_of_type(STATE_MACHINE_TYPE_ID)[0].toc_data)
    count,old_at=struct.unpack_from('<II',original,28);new_count,new_at=struct.unpack_from('<II',patched,28)
    assert new_count==count;mask_checks=0
    for i in range(count):
        old=old_at+struct.unpack_from('<I',original,old_at+4+4*i)[0]
        new=new_at+struct.unpack_from('<I',patched,new_at+4+4*i)[0]
        native=struct.unpack_from('<I',original,old)[0]
        weights=struct.unpack_from(f'<{native}f',original,old+4)
        assert struct.unpack_from('<I',patched,new)[0]==native+len(owners)
        assert original[old+4:old+4+4*native]==patched[new+4:new+4+4*native]
        appended=struct.unpack_from(f'<{len(owners)}f',patched,new+4+4*native)
        assert all(w==weights[j] for w,j in zip(appended,owners));mask_checks+=len(owners)
    routes=route_audit(folder,game)
    report={'status':'PASS','model':Path(flow['vpk']).stem,'scale':flow['scale'],'units':units,
            'unitCount':len(units),'sourceBones':len(manifest['bones']),'avatarNodes':lua_n,'animationAvatarNodes':n,
            'oldRawParentAndMatrixBytesPreserved':True,'aqParentBoundsValid':True,
            'luaEntryStartedAndStopped':True,'luaVersion':lua['version'],'simulatedEmptyWorlds':True,
            'masks':count,'maskOwnerChecks':mask_checks,'routeChecks':routes['checks'],
            'maxNativeChannelError':routes['maxNativeChannelError'],'sampleAnimations':flow['samples'],
            'gameTested':False,'blenderLiveTested':False,'modelUnchangedByBuild':flow['protectedModelUnchanged']}
    (folder/'parent-entry-mask-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','model','unitCount','sourceBones','maskOwnerChecks','routeChecks','maxNativeChannelError')}),flush=True)
    return report

if __name__=='__main__':
    for folder in sys.argv[2:]:audit_case(folder,sys.argv[1])
