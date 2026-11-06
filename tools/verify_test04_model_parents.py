"""Forensic byte audit of deployed test04 Units and isolated re-serialization only."""
import hashlib
import json
import struct
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.constants import UNIT_TYPE_ID
from anim_batch_mod.formats import UnitData
from anim_batch_mod.attachment_skeleton import append_model_source_mounts


def table(raw):
    off=struct.unpack_from('<I',raw,52)[0];n=struct.unpack_from('<I',raw,off)[0]
    at=off+16+128*n
    return off,n,[struct.unpack_from('<HH',raw,at+4*i) for i in range(n)]


def main():
    base=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7/test-library/[原比例模型]test04'
    out=ROOT/'outputs/test04-live-crash-audit-20261106/evidence';candidate=out/'isolated-unit-candidates';candidate.mkdir(parents=True,exist_ok=True)
    mp=base/'vpk2patch/source-skeleton.json';manifest=json.loads(mp.read_text(encoding='utf-8-sig'));added=len(manifest['sourceAttachmentShadows'])
    rows=[];sources=[]
    for folder in ('vpk2patch','Overwrite'):
        for path in sorted((base/folder).glob('*.patch_*')):
            if not path.suffix.rsplit('_',1)[-1].isdigit():continue
            data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
            sources.append({'path':str(path),'bytes':len(data),'sha256':digest})
            archive=TocArchive.parse_parts(data,load_external_data=False)
            for entry in archive.entries.values():
                if entry.type_id!=UNIT_TYPE_ID:continue
                raw=bytes(entry.toc_data);unit=UnitData.parse(raw)
                if not all(r['hash'] in unit.name_hashes for r in manifest['sourceAttachmentShadows']):continue
                new,n,records=table(raw)
                oldn=n-added;pattern=struct.pack(f'<{oldn}I',*unit.name_hashes[:oldn])
                found=raw.find(pattern,0,new);old=found-16-132*oldn
                assert old>=0 and struct.unpack_from('<I',raw,old)[0]==oldn
                # Relocation leaves the pre-append block and mesh payload intact.
                # This restores that pointer in an isolated buffer, not the live file.
                original=bytearray(raw[:new]);struct.pack_into('<I',original,52,old)
                _,_,oldrecords=table(original)
                changes=[{'node':i,'before':list(a),'deployed':list(b)} for i,(a,b) in enumerate(zip(oldrecords,records[:oldn])) if a!=b]
                bad=[i for i,(flags,parent) in enumerate(records) if flags and parent>=n]
                corrected=append_model_source_mounts(original,manifest);co,cn,cr=table(corrected)
                assert cn==n and cr[:oldn]==oldrecords
                assert not any(flags and parent>=cn for flags,parent in cr)
                assert all(parent<cn for flags,parent in cr) # AQ LOD0 direct indexing is now safe.
                assert corrected[co+16:co+16+64*oldn]==original[old+16:old+16+64*oldn]
                assert corrected[co+16+64*cn:co+16+64*cn+64*oldn]==original[old+16+64*oldn:old+16+128*oldn]
                prefix=bytearray(corrected[:new]);prefix[52:56]=original[52:56];assert prefix==original
                target=candidate/(folder+'-'+f'{entry.file_id:016x}'+'.toc');target.write_bytes(corrected)
                rows.append({'path':str(path),'resource':f'{entry.file_id:016x}','count':n,'preAppendCount':oldn,
                             'oldTransformOffset':old,'deployedTransformOffset':new,'parentChanges':changes,
                             'invalidParentNodes':bad,'decodedParentsComparisonMissesBug':UnitData.parse(original).parents==unit.parents[:oldn],
                             'candidate':str(target),'oldRecordsAndMatricesByteIdentical':True,'candidateParentBoundsValid':True})
            assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    report={'status':'PASS','model':'test04','sourceManifest':str(mp),'modelScale':manifest.get('modelScale'),
            'affectedUnits':len(rows),'corruptedParentRecords':sum(len(r['parentChanges']) for r in rows),
            'units':rows,'sources':sources,'gameOrLibraryModified':False,'blenderLiveTested':False,
            'aqImportEvidence':'unit.py L3336 indexes bones[ParentBone]; deployed ParentBone=65535 for a 261-node Unit.'}
    (out/'model-parent-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','affectedUnits','corruptedParentRecords','gameOrLibraryModified','blenderLiveTested')}))

if __name__=='__main__':main()
