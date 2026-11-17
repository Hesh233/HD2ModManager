"""Export and verify A22 with the actual frozen application exporter, isolated only.
A22 = A21 projection/dispatch reuse + non-writing health sampling. Test candidate ONLY."""
from pathlib import Path
import base64, hashlib, json, struct, sys, zipfile, shutil
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'outputs/physics-A22-health-sampling-candidate-20261117'
OUT=LAB/'release-candidate'
from analyze_a19_hotpath_candidates import replace_once, protected_files
from finalize_single_loader_accepted import check_config, validate_evidence

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    frozen=json.loads((LAB/'protected-before.json').read_text('utf-8'))
    assert protected_files()==frozen
    assert not OUT.exists(), 'Keep exports write-once'
    config=check_config()
    evidence=validate_evidence() # rehash CURRENT real bind/config and old full-FK evidence, not a fresh FK run
    (LAB/'baseline-consumer-and-config-revalidation.json').write_text(json.dumps(dict(configuration=config,acceptedEvidenceRevalidated=evidence,freshFullFkRun=False),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    s=(ROOT/'tools/export_single_consumers_formal.py').read_text('utf-8-sig')
    s=replace_once(s,"for variant in ['A','B']:","for variant in ['A']:")
    s=replace_once(s,"ROOT/'HD2PhysBoneCompat/src/production/single_remote_release_manifest.json'", "ROOT/'outputs/physics-A22-health-sampling-candidate-20261117/candidate-manifest.json'")
    # The accepted normal Core evolved since A21 (ce3a3c40/19802 methods/39 resources ->
    # 575e97b5/19281 methods/42 resources) and now already embeds compat 1.3.13, so a
    # physics candidate changes only the runtime resource. Pin the CURRENT baseline
    # dynamically instead of the obsolete literal; the real gate (identity unchanged,
    # zero IL method/constant/reference edits, only physics resources touched) is kept.
    s=replace_once(s,"assert audit['methodsBefore']==audit['methodsAfter']==19802",
        "assert audit['methodsBefore']==audit['methodsAfter'] and audit['resourcesBefore']==audit['resourcesAfter']")
    s=replace_once(s,"assert audit['changedResources']==['HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua']",
        "assert set(audit['changedResources'])<={'HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua'} and 'HD2ModCore.PhysBone.physbone_runtime.lua' in audit['changedResources']")
    (LAB/'exporter-runner-snapshot.py').write_text(s,encoding='utf-8')
    sys.argv=['actual-export','--output',str(OUT),'--source-root',str(LAB)]
    exec(compile(s,str(ROOT/'tools/export_single_consumers_formal.py'),'exec'),{'__file__':str(ROOT/'tools/export_single_consumers_formal.py'),'__name__':'a22_isolated_export'})
    manifest=json.loads((LAB/'candidate-manifest.json').read_text('utf-8-sig'))
    entry=manifest['sources'][0];export=OUT/'A-export';proof=json.loads((export/'physics-provenance.json').read_text('utf-8-sig'))
    NORMAL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
    audit=json.loads((OUT/'A-core-audit.json').read_text('utf-8-sig'))
    normal_sha=sha(NORMAL/'HD2ModCore.dll')
    assert audit['beforeSha256'].lower()==normal_sha, 'export baseline must be the current pinned normal Core'
    assert audit['identityUnchanged'] and not audit['changedMethods'] and not audit['changedConstants'] and not audit['changedReferences']
    assert proof['runtimeVersion']=='2.3.22' and proof['compatVersion']=='1.3.13'
    assert proof['owner']=='mods/hd2modmanager/physbone' and proof['guid']=='7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01'
    package=export/'physics-runtime.zip';assert sha(package)==proof['zipSha256']
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()))==4
        for row in proof['entries']:
            b=z.read(row['path']);assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
        b=z.read('9ba626afa44a3aa3.patch_0')
    at=struct.unpack_from('<Q',b,120)[0];size=struct.unpack_from('<I',b,160)[0]
    assert size<=4194304 and len(b[at+8:at+size])+8==size
    addon=b[at+8:at+size].decode('utf-8').replace('\r\n','\n')
    assert hashlib.sha256(addon.encode()).hexdigest()==proof['sourceSha256']
    extracted=OUT/'A-extracted';extracted.mkdir()
    # Current accepted manager Core wraps the runtime resource as SkeletonRuntime and
    # routes via PhysicsRoutes.new(PhysBoneCompat, SkeletonRuntime, DirectCompat,
    # DirectRuntime); the skeleton branch is the single-skeleton A22 runtime. Compat
    # keeps the PhysBoneCompat wrapper. Both blocks must equal the candidate source.
    for name,label in [('physbone_runtime.lua','SkeletonRuntime'),('physbone_compat.lua','PhysBoneCompat')]:
        wanted=(LAB/'A-source'/name).read_text('utf-8-sig')
        marker='local '+label+' = (function()\n';start=addon.index(marker)+len(marker)
        assert addon[start:start+len(wanted)]==wanted and addon[start+len(wanted):].startswith('\nend)()')
        (extracted/name).write_text(wanted,encoding='utf-8',newline='\n')
        assert sha(extracted/name)==(entry['runtimeSha256'] if 'runtime' in name else entry['compatSha256'])
    assert sha(extracted/'physbone_compat.lua')==sha(ROOT/'HD2PhysBoneCompat/src/production/single_remote_compat.lua')
    (OUT/'A-addon.lua').write_text(addon,encoding='utf-8',newline='\n')
    receipt=dict(status='PASS_ACTUAL_A22_EXPORT_CRC_SHA_SIZE_AND_SOURCE_EXTRACTION_NOT_GAME_FPS',runtimeVersion='2.3.22',compatVersion='1.3.13',luaResourceBytes=size,chefMaxBytes=4194304,chefHeadroomBytes=4194304-size,zipBytes=package.stat().st_size,zipSha256=sha(package),runtimeSha256=entry['runtimeSha256'],compatSha256=entry['compatSha256'],frozenNormalCoreCodeChanged=False,compatByteIdentical=True,freshFullFkRun=False,rootConfigPreserved=True,productionSourceChanged=False,healthSamplingSafetyGapDisclosed=True,normalCoreSha256=normal_sha,coreMethods=audit['methodsBefore'],coreResources=audit['resourcesBefore'],coreChangedResources=audit['changedResources'],addonRuntimeWrapper='SkeletonRuntime',addonRouting='PhysicsRoutes.new(PhysBoneCompat,SkeletonRuntime,DirectCompat,DirectRuntime); skeleton branch is the A22 single-skeleton runtime, routing/direct components unchanged from normal Core',compatAlreadyEmbeddedInNormalCore=('HD2ModCore.PhysBone.physbone_compat.lua' not in audit['changedResources']),normalCoreBaselineShiftSinceA21=True,normalCoreBaselineNote='A21 exported against ce3a3c40/19802 methods/39 resources; current accepted manager Core is 575e97b5/19281 methods/42 resources and already embeds compat 1.3.13, so only the runtime resource changes. Delivered ZIP addon is source-Lua determined, independent of Core IL.')
    (OUT/'export-verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Local Chef copies for the established runner; originals remain untouched.
    old=ROOT/'outputs/physics-single-loader-size-fix-20261117'
    for name in ['actual-chef-bit-shim.lua','actual-chef-core-1.lua']:
        shutil.copyfile(old/name,LAB/name)
    assert protected_files()==frozen
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__': main()