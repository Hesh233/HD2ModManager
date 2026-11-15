"""Create a flat Arsenal TEST physics package; never import/deploy/update production."""
from __future__ import annotations
import argparse,hashlib,json,struct,sys,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT.parents[1]))
import audit_test06_vrd_skirt as a
from lupa.lua51 import LuaRuntime
from build_test09_axis_test import OUT,INSTALL,PROFILE,COMPAT_VERSION,RUNTIME_VERSION,sha,save
NAME='物理运行时-test09_chr654-源骨参考轴修正-axis1-待测试'
PACKAGE=INSTALL/'非运行文件/测试包'/(NAME+'.zip')
OWNER='mods/hd2modmanager/physbone'

def prepare():
    build=json.loads((OUT/'build-report.json').read_text('utf8'))
    base=Path(build['baselinePackage']);raw=base.read_bytes();assert sha(base)==build['baselinePackageSha256']
    nt,n=struct.unpack_from('<II',raw,4);assert nt==n==1
    at=72+nt*32;row=struct.unpack_from('<QQQQQQQIIIIII',raw,at)
    code=(OUT/'hd2physbone-test09.lua').read_bytes();assert code.startswith(('-- HD2-Addon: '+OWNER+'\n').encode())
    LuaRuntime().eval('function(s)local f,e=loadstring(s);assert(f,e);return true end')(code.decode('utf8'))
    payload=struct.pack('<II',len(code),2)+code
    result=bytearray(raw[:row[2]]);struct.pack_into('<I',result,at+56,len(payload))
    result+=payload;result+=bytes((-len(result))%16)
    directory=OUT/'patch';directory.mkdir(exist_ok=True)
    target=directory/'9ba626afa44a3aa3.patch_0';target.write_bytes(result)
    for suffix in ['stream','gpu_resources']:Path(str(target)+'.'+suffix).write_bytes(b'')
    manifest=json.loads((base.parent/'manifest.json').read_text('utf8'))
    manifest.update(Name=NAME,Description=f'TEST ONLY {RUNTIME_VERSION}/{COMPAT_VERSION}; {PROFILE}; 22 skirt frames, no model/animation rebuild; not game accepted.')
    save(directory/'manifest.json',manifest)
    parsed=a.patch_rows(target);assert len(parsed)==1 and parsed[0][0:2]==row[0:2]
    actual=a.payload(target,parsed[0]);assert actual==payload
    save(OUT/'patch-prepare-report.json',dict(status='PREPARED_TEST_ONLY',stableOwner=OWNER,stableGuid=manifest['Guid'],
        resourceId=f'{row[0]:016x}',luaHeaderRevision=2,patchPayloadEqualsLua=True,emptySidecars=True,
        patchSha256=sha(target),luaSha256=sha(OUT/'hd2physbone-test09.lua'),members={p.name:sha(p) for p in directory.iterdir() if p.is_file()}))
    print('Prepared flat TEST patch',target)

def publish():
    regression=json.loads((OUT/'test09-axis-regression.json').read_text('utf8'))
    suite=json.loads((OUT/'test09-axis-suite.json').read_text('utf8'))
    assert regression['status']==suite['status']=='PASS_OFFLINE_NOT_GAME_ACCEPTANCE'
    assert len(regression['legacyRigs'])==5 and all(x['numericTraceExact'] for x in regression['legacyRigs'])
    assert regression['gpuResults']['fixed']['edgeStretchMax']<1.21 and regression['test09HairNumericallyUnchanged']
    protected=json.loads((OUT/'protected-before.json').read_text('utf8'));after={p:sha(p) for p in protected};assert after==protected
    prepare()
    manifest=json.loads((OUT/'patch/manifest.json').read_text('utf8'));members=list((OUT/'patch').iterdir())
    assert len(members)==4 and all(p.is_file() for p in members)
    assert not PACKAGE.exists(),'preserve earlier released test package'
    with zipfile.ZipFile(PACKAGE,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(members):z.write(p,p.name)
    with zipfile.ZipFile(PACKAGE) as z:
        assert z.testzip() is None and len(z.infolist())==4
        for p in members:assert z.read(p.name)==p.read_bytes()
        assert json.loads(z.read('manifest.json'))['Guid']==manifest['Guid']
    evidence=dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',package=str(PACKAGE),bytes=PACKAGE.stat().st_size,sha256=sha(PACKAGE),
        compatVersion=COMPAT_VERSION,runtimeVersion=RUNTIME_VERSION,profile=PROFILE,sourceFrames=22,zipCrc=True,
        flatRootManifestAndThreePatchFiles=True,stableOwner=OWNER,stableGuid=manifest['Guid'],
        modelReimportRequired=False,animationRebakeRequired=False,managerInstallationUpdated=False,
        gameDeployed=False,gameTested=False,protectedFilesUnchanged=len(protected),regressionChecks=regression['checks'],
        patchMembers={p.name:sha(p) for p in members},sourceSha256=dict(compat=sha(OUT/'physbone_compat-test09.lua'),runtime=sha(OUT/'physbone_runtime-test09.lua')))
    save(OUT/'package-report.json',evidence)
    save(OUT/'protected-after.json',after)
    print(json.dumps(evidence,ensure_ascii=False,indent=2))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf8');p=argparse.ArgumentParser();p.add_argument('--publish',action='store_true');args=p.parse_args()
    publish() if args.publish else prepare()
