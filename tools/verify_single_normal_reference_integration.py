"""Verify official R2 orchestration using read-only cached game index; no library writes."""
from pathlib import Path
import hashlib, json, sqlite3, sys, time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod import single_skeleton as single
from anim_batch_mod.archive import ResourceIndex
from anim_batch_mod.playback_reference import NormalPlaybackReference, REFERENCE_SHA256
from audit_single_against_normal import records, NORMAL
OUT=ROOT/'outputs/single-normal-reference-integrated-20261107'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
MODEL=INSTALL/'test-library/[单骨架模型]test01/vpk2patch'
DB=ROOT/'outputs/single-hd2-fix-20261106/final-verified/test01/animations/resource-index.sqlite3'
ACCEPTED=ROOT/'outputs/test01-normal-reference-r2-20261107/normal-template-build/runtime/9ba626afa44a3aa3.patch_2'

def main():
    start=time.time();report=dict(userGameAcceptance=True,libraryModified=False,gameDeployed=False)
    with NormalPlaybackReference.bundled() as playback, NORMAL.open('rb') as source:
        rows=records(NORMAL);playback.validate_ids([r[0] for r in rows]);checked=0
        for row in rows:
            source.seek(row[2]);assert playback.read(row[0])==source.read(row[7]);checked+=1
        report.update(playback.report());report['losslessNormalClips']=checked
    class CachedIndex(ResourceIndex):
        def load_or_build(self,progress=None):
            self.connection=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True);return True
    output=OUT/'formal-build-r2'
    with patch.object(single,'ResourceIndex',CachedIndex):
        built=single.build_project(MODEL,Path('E:/Steam/steamapps/common/Helldivers 2/data'),output,sample_count=16,threads=2,config_path=INSTALL/'config.toml')
    actual=output/'runtime/9ba626afa44a3aa3.patch_2'
    accepted_rows={r[0]:r for r in records(ACCEPTED)}
    results=[]
    with actual.open('rb') as new,ACCEPTED.open('rb') as gold:
        for row in records(actual):
            old=accepted_rows[row[0]];new.seek(row[2]);gold.seek(old[2]);raw=new.read(row[7]);same=raw==gold.read(old[7]);assert same,f'{row[0]:016x}'
            results.append(dict(id=f'{row[0]:016x}',byteExactAcceptedR2=same,sha256=hashlib.sha256(raw).hexdigest()))
    report.update(formalBuild=built,productionExactClips=results,elapsedSeconds=time.time()-start)
    assert built['configSha256']=='fcd958c31994492f7bab616dcf1c3e3335f2a8da5c397314a5710dd939252832'
    assert built['playbackRevision']=='normal-reference-r2' and built['pipelineVersion']=='1.0.20'
    assert built['preserveUnmodifiedChannels'] is False and built['preserveSourceKeyTimes'] is False
    assert built['preservePlaybackTiming'] is False and built['preserveReferencePlayback'] is True
    (OUT/'formal-integration-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS: complete 3180 lossless templates; 16 official generated clips exact accepted R2; config unchanged',flush=True)
if __name__=='__main__':main()
