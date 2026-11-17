"""Current accepted A19/B20 release/archive/analysis verifier; candidate-only tools remain historical."""
from pathlib import Path
import json, zipfile, struct
from finalize_single_loader_accepted import ROOT, OUT, LAB, GATE, PROD, NORMAL, read, sha, require, snapshot, json_new, check_config, validate_evidence

def main():
    release=read(OUT/'formal-release.json');delivery=read(OUT/'delivery.json');m=read(PROD/'single_remote_release_manifest.json')
    require(m['realGameAcceptanceStatus']=='user-accepted-A19-B20-formal-not-controlled-multiplayer-FPS','Stale production status')
    require(m['formalRelease']['sha256']==sha(OUT/'formal-release.json') and m['formalRelease']['packages']==release['packages']==delivery['packages'],'Stale formal manifest')
    old=read(OUT/'before/HD2PhysBoneCompat/src/production/single_remote_release_manifest.json'); allowed={'realGameAcceptanceStatus','acceptedFeedback','formalRelease'}
    require({k:v for k,v in m.items() if k not in allowed}=={k:v for k,v in old.items() if k not in allowed},'Unauthorized production metadata drift')
    require(sha(OUT/'user-acceptance.json')==release['acceptanceSha256'],'Acceptance drift')
    inputs=read(GATE/'gate-run.json')['inputs']; sizes={}
    for row in release['packages']:
        v=row['variant'];s=next(x for x in m['sources'] if x['variant']==v)
        require(sha(s['runtimePath'])==s['runtimeSha256']==inputs[v+'Runtime'] and sha(m['compatPath'])==s['compatSha256']==inputs[v+'Compat'],'Lua/manifest/gate source drift')
        require(sha(row['path'])==row['sha256']==sha(LAB/'release-candidate'/(v+'-export/physics-runtime.zip')),'Formal/accepted candidate byte mismatch')
        with zipfile.ZipFile(row['path']) as z:
            require(z.testzip() is None and len(z.namelist())==4,'Formal CRC/member failure')
            b=z.read('9ba626afa44a3aa3.patch_0');at=struct.unpack_from('<Q',b,120)[0];size=struct.unpack_from('<I',b,160)[0]
            require(size<=4194304 and len(b[at+8:at+size])+8==size,'Chef resource size failure');sizes[v]=size
    require(validate_evidence()==release['gates'],'Consumer/FK/runtime evidence failure')
    require(sha(NORMAL/'HD2ModCore.dll')==release['normalCoreSha256'] and sha(NORMAL/'config.toml')==release['rootConfigSha256'],'Normal Core/root config changed')
    require(snapshot(read(OUT/'protected-before.json').keys())==read(OUT/'protected-before.json'),'Protected user files changed')
    configs=check_config()
    ar=delivery['archive'];require(sha(ar['path'])==ar['sha256'] and Path(ar['path']).stat().st_size==ar['bytes'],'Sealed archive changed')
    with zipfile.ZipFile(ar['path']) as z:
        require(z.testzip() is None and len(z.namelist())==ar['entries'],'Sealed archive CRC/member failure')
    analyses=[]
    for name in ['physics-A19-one-vs-four-analysis-20261117','physics-A19-one-vs-four-analysis-20261117-identity-watch']:
        p=ROOT/'outputs'/name/'result.json';a=read(p)
        require(a['status']=='PASS_A19_REAL_MODEL_CHEF_ONE_FOUR_ONE_STRUCTURAL_COMPARISON_NOT_FPS' and a['runtimeSha256']==inputs['ARuntime'] and a['actualChefPatchSha256']==release['packages'][0]['sha256'] and a['fixtureSourceSha256']==sha(ROOT/'HD2PhysBoneCompat/test/single-consumer-runtime-test.py'),'Analysis runtime/fixture drift')
        require([r['players']for r in a['phases']]==[1,4,1] and all(r['localSolverCalls']==1800 and r['remoteSolverCalls']==r['remoteSuccessfulBoneWrites']==r['fpQueryDelta']==0 for r in a['phases']),'Analysis exclusion/cadence failure')
        analyses.append({'path':str(p),'sha256':sha(p),'status':a['status'],'notFps':True})
    result={'status':'PASS_FORMAL_ARCHIVE_AND_A19_STRUCTURAL_ANALYSIS_CURRENT_USER_STATE_PRESERVED','packages':release['packages'],'archive':ar,'luaResourceBytes':sizes,'gates':release['gates'],'configuration':configs,'protectedPaths':len(read(OUT/'protected-before.json')),'protectedChanges':[],'analysis':analyses,'onlyNewDeliveryDocsToolsAndReleaseMetadataWritten':True,'gameOrManagerLaunched':False,'automaticallyImportedOrDeployed':False}
    json_new(OUT/'final-verification.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
