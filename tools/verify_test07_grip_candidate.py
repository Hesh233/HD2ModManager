"""Check actual test07 resources and current Core-composed entry, plus Chef 1.4.1."""
import hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from verify_test04_lua_entry import exercise
import audit_native_v31_b23_chef as chef
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from anim_batch_mod.native_skeleton import bone_name_hash
OUT=ROOT/'outputs/test07-sidearm-fix-111-20261106'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    candidate=OUT/'candidate-111';source=(candidate/'hd2attachmentfix.lua').read_text(encoding='utf-8')
    for name in ('native_grip_transfer_test.lua','attachment_fix_runtime.lua'):
        assert (ROOT/'HD2PhysBoneCompat/src'/name).read_text(encoding='utf-8').strip() in source,name
    r=exercise(source);assert r['started'] and r['version']=='1.0.11' and r['writes']==0 and r['closed']==1
    (OUT/'entry-verification.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    profile=json.loads((OUT/'attachment-profile.json').read_text(encoding='utf-8'))
    rig=TocArchive.parse_parts((candidate/'9ba626afa44a3aa3.patch_1').read_bytes(),load_external_data=False)
    u=UnitData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==UNIT_TYPE_ID))
    rows=list(profile['avatar']['nodes'])+profile['leftGrip']['nodes']+profile['leftGrip']['outputs']+profile['rightGrip']['nodes']+profile['rightGrip']['outputs']+[profile['sourceRightMount']]
    for row in profile['attachments']:rows += [row[x] for x in ('node','source','native','reference','sourceMount') if row.get(x)]
    for row in profile['bodySync']['outputs']:rows += [row[x] for x in ('node','native','reference','positionParent')]
    for row in rows:
        assert u.name_hashes[row['index']]==bone_name_hash(row['name']),row
        if row.get('parent') is not None:assert u.parents[row['index']]==row['parent'],row
    model=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/test-library/[原比例模型]test07';units={}
    for folder in ('vpk2patch','Overwrite'):
        for p in (model/folder).glob('*.patch_*'):
            if not p.suffix.rsplit('_',1)[-1].isdigit():continue
            a=TocArchive.parse_parts(p.read_bytes(),load_external_data=False)
            for e in a.entries.values():
                if e.type_id==UNIT_TYPE_ID:units[f'{e.file_id:016x}']=UnitData.parse(e.toc_data)
    for rid,spec in profile['models'].items():
        unit=units[rid];assert len(unit.parents)==spec['count'],rid
        for n in spec['nodes']:
            assert unit.name_hashes[n['index']]==bone_name_hash(n['name']),(rid,n)
            assert unit.parents[n['index']]==n['parent'],(rid,n)
    # Preserve all existing animation slot indices and every body Unit signature.
    from anim_batch_mod.constants import BONE_TYPE_ID
    from anim_batch_mod.formats import BonesData
    original=ROOT/'outputs/test07-grip-fix-20261106/candidate'
    oldArchive=TocArchive.parse_parts((original/'9ba626afa44a3aa3.patch_1').read_bytes(),load_external_data=False)
    oldUnit=UnitData.parse(next(e.toc_data for e in oldArchive.entries.values() if e.type_id==UNIT_TYPE_ID))
    oldBone=BonesData.parse(next(e.toc_data for e in oldArchive.entries.values() if e.type_id==BONE_TYPE_ID))
    newBone=BonesData.parse(next(e.toc_data for e in rig.entries.values() if e.type_id==BONE_TYPE_ID))
    assert oldUnit.parents[:107]==u.parents[:107] and oldUnit.name_hashes[:107]==u.name_hashes[:107]
    assert [oldUnit.name_hashes.index(h) for h in oldBone.hashes]==[u.name_hashes.index(h) for h in newBone.hashes]
    oldProfile=json.loads((original/'attachment-profile.json').read_text(encoding='utf-8'))
    assert oldProfile['leftGrip']==profile['leftGrip'] and oldProfile['bodySync']==profile['bodySync']
    # Underbarrel selection/intent prefix is exactly the accepted 1.0.10 implementation.
    oldCode=(original/'hd2attachmentfix.lua').read_text(encoding='utf-8')
    a=oldCode.index('    local function plan_left(');b=oldCode.index('        local function pose(m)',a)
    x=source.index('    local function plan_left(');y=source.index('        local result=solve_source_arm',x)
    assert oldCode[a:b]==source[x:y],'Proven underbarrel/left intent prefix changed'
    build=json.loads((candidate/'attachment-build-report.json').read_text(encoding='utf-8'))
    assert build['avatarNodes']==248 and build['pipelineVersion']=='1.0.15'
    project=ROOT/'projects/test01-native-grip';spec=json.loads((project/'project.json').read_text(encoding='utf-8'))
    for release in spec['releases']:assert digest(project/release['path'])==release['sha256']
    work=OUT/'chef-harness'
    for folder in ('runtime','physics-companion','native-parenting'):(work/folder).mkdir(parents=True,exist_ok=True)
    shutil.copy2(candidate/'hd2attachmentfix.lua',work/'hd2attachmentfix-B23.lua')
    shutil.copy2(candidate/'9ba626afa44a3aa3.patch_0',work/'runtime/9ba626afa44a3aa3.patch_4')
    shutil.copy2(ROOT/'outputs/native-v34-b23-integrated-20261105/physics-companion/9ba626afa44a3aa3.patch_3',work/'physics-companion/9ba626afa44a3aa3.patch_3')
    target=work/'native-parenting/9ba626afa44a3aa3.patch_5'
    if not target.exists():shutil.copy2(candidate/'9ba626afa44a3aa3.patch_1',target)
    assert digest(target)==digest(candidate/'9ba626afa44a3aa3.patch_1')
    chef.W=work;chef.main(version='1.0.11')
    staged=ROOT/'tools/native-python/anim_batch_mod';info=json.loads((staged/'build-info.json').read_text(encoding='utf-8-sig'))
    for f in info['files']:
        assert digest(staged/f['name']).upper()==f['sha256'].upper(),f['name']
        assert (staged/f['name']).read_bytes()==(ROOT.parent/f['name']).read_bytes(),f['name']
    assert info['luaVersion']=='1.0.11' and (staged/'presets/native-v15/grip-fixes-1.0.11.json').is_file()
    result=dict(status='PASS',avatarNodes=len(u.parents),avatarNamedRows=len(rows),modelBindings=len(profile['models']),
                composedEntryStarted=r['started'],luaVersion=r['version'],embeddedRuntimeMatchesSource=True,
                frozen108ReleasesUnchanged=True,stagedPythonMatchesRoot=True,acceptedLeftPrefixUnchanged=True,animationSlotIndicesPreserved=True,actualChefParserSandbox=True,gameTested=False)
    (OUT/'real-layout-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
