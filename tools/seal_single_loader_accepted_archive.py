"""Seal accepted A19/B20 and evidence by copying; never delete originals."""
from pathlib import Path
import hashlib, json, zipfile
from finalize_single_loader_accepted import ROOT, LAB, OUT, NORMAL, PROD, GATE, read, sha, snapshot, require, json_new, validate_evidence

def main():
    release=read(OUT/'formal-release.json');manifest=read(PROD/'single_remote_release_manifest.json')
    require(manifest['realGameAcceptanceStatus']=='user-accepted-A19-B20-formal-not-controlled-multiplayer-FPS','Stale acceptance metadata')
    require(manifest['formalRelease']['sha256']==sha(OUT/'formal-release.json'),'Stale formalRelease SHA')
    old=read(OUT/'before/HD2PhysBoneCompat/src/production/single_remote_release_manifest.json')
    allowed={'realGameAcceptanceStatus','acceptedFeedback','formalRelease'}
    require({k:v for k,v in old.items() if k not in allowed}=={k:v for k,v in manifest.items() if k not in allowed},'Non-acceptance production metadata changed')
    require(snapshot(read(OUT/'protected-before.json').keys())==read(OUT/'protected-before.json'),'Protected user state changed')
    require(validate_evidence()==release['gates'],'Fresh gate verification mismatch')
    inputs={}
    omitted=[]
    def add(p,name):
        p=Path(p);require(p.is_file(),'Missing archive source '+str(p));require(name not in inputs,'Duplicate member '+name);inputs[name]=p
    suffixes={'.json','.lua','.in','.py','.cs','.md','.log','.txt','.trx','.toml','.bin','.zip'}
    for base,label in [(LAB,'candidate-evidence'),(OUT,'formal-evidence')]:
        for p in sorted(base.rglob('*')):
            if not p.is_file():continue
            rel=p.relative_to(base);parts=set(rel.parts)
            selected=not (parts & {'data','payload-cache','dotnet-temp','obj','bin','gates'}) and p.suffix.lower() in suffixes
            if selected:add(p,label+'/'+rel.as_posix())
            else:omitted.append({'source':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'reason':'duplicate real model/synthetic payload or compiled/intermediate artifact; original remains at source'})
    for p in PROD.iterdir():
        if p.is_file():add(p,'production/'+p.name)
    for t in read(GATE/'gate-run.json')['tests']:
        p=Path(t['command'][3]);name='verification-source/'+p.relative_to(ROOT).as_posix()
        if name not in inputs:add(p,name)
    for p in [Path(__file__), ROOT/'tools/finalize_single_loader_accepted.py',ROOT/'tools/verify_single_consumers_ship_fix.py',ROOT/'tools/run_single_consumers_ship_fix_gates.py',ROOT/'HD2PhysBoneCompat/test/single-consumer-fk-test.py',ROOT/'HD2SourceMigration/VpkConversion/PhysicsConsumerManifestBuilder.cs',ROOT/'tools/check_animation_config.py',ROOT/'AGENTS.md',ROOT/'docs/agent/physics-single-loader-accepted-formal-20261117.md']:
        name='source/'+p.relative_to(ROOT).as_posix();add(p,name)
    for model in read(PROD/'single_consumer_catalog.json')['models']:
        folder=NORMAL/'test-library'/model['modelName']/'sectional'
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in {'.json','.toml','.bin','.lua'}:add(p,'actual-model-bind-config/'+model['modelName']+'/'+p.name)
    for p in [ROOT.parent/'config.toml',ROOT/'tools/native-python/anim_batch_mod/config.toml',NORMAL/'config.toml',NORMAL/'anim_batch_mod/build-info.json',NORMAL/'HD2ModCore.dll']:
        add(p,'normal-baseline/'+p.relative_to(ROOT.parent).as_posix())
    for row in release['packages']:add(Path(row['path']),'formal-packages/'+Path(row['path']).name)
    for row in read(OUT/'user-acceptance.json')['packages']:add(Path(row['path']),'accepted-candidates/'+Path(row['path']).name)
    entries=[{'member':n,'source':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in sorted(inputs.items())]
    index={'schema':'hd2-accepted-A19-B20-archive-v1','date':'2026-11-17','timezone':'Asia/Shanghai','status':'SEALED_COPY_NO_ORIGINAL_DELETION','userAcceptanceSha256':sha(OUT/'user-acceptance.json'),'formalReleaseSha256':sha(OUT/'formal-release.json'),'entries':entries,'omittedButRetainedAtOriginalSource':omitted,'notFullGameDataBackup':True}
    archive=NORMAL/'非运行文件/归档/单骨架物理AB-Chef加载上限修复-2.3.19-2.3.20-正式源码证据日志-20261117-封档.zip'
    require(not archive.exists(),'Do not replace an existing seal')
    require(archive.resolve().is_relative_to((NORMAL/'非运行文件/归档').resolve()),'Unsafe archive target')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(inputs.items()):z.write(p,name)
        z.writestr('archive-manifest.json',(json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    with zipfile.ZipFile(archive) as z:
        require(z.testzip() is None and len(z.namelist())==len(entries)+1 and len(set(z.namelist()))==len(z.namelist()),'Archive CRC/names fail')
        for row in entries:
            with z.open(row['member']) as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            require(z.getinfo(row['member']).file_size==row['bytes'] and digest==row['sha256'] and sha(row['source'])==row['sha256'],'Archive member/original changed '+row['member'])
    require(snapshot(read(OUT/'protected-before.json').keys())==read(OUT/'protected-before.json'),'Protected original changed while sealing')
    result={'status':'TWO_USER_ACCEPTED_FORMAL_PACKAGES_DELIVERED_AND_SEALED','packages':release['packages'],'archive':{'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'entries':len(entries)+1,'omittedRetainedFiles':len(omitted),'allMemberSizesHashesAndCrcVerified':True,'originalsDeleted':False},'gates':release['gates'],'protectedPaths':len(read(OUT/'protected-before.json')),'protectedChanges':[],'currentUserLibraryPreserved':True,'gameOrManagerLaunched':False,'automaticallyImportedOrDeployed':False,'controlledMultiplayerFpsMeasured':False}
    json_new(OUT/'delivery.json',result)
    json_new(archive.with_suffix('.zip.sha256.json'),{'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'entries':len(entries)+1,'crcAndMemberHashesPassed':True})
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()

