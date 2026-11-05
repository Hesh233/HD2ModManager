"""Capture B13-0's clean exit separately from its failed probe validation."""
import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path
from package_native_v12 import ROOT,load,save_json

W=ROOT/'outputs/native-v22-b14-20261104';OUT=W/'evidence'
GAME=Path.home()/'AppData/Roaming/Arrowhead/Helldivers2'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    path=GAME/'hd2physbone.log';data=path.read_bytes();text=data.decode('utf-8',errors='replace')
    at=text.rfind('[attach_probe] variant=0 event=loaded version=1.1.0')
    assert at>=0
    start=text.rfind('\n',0,at)+1;session=text[start:];probe=[r for r in session.splitlines()if '[attach_probe]'in r]
    assert len(probe)==3 and 'name=boss_aim'in probe[1]and 'event=disabled'in probe[2]
    assert not any('event=validated'in r or 'event=applied'in r for r in probe)
    (OUT/'B13-0-probe-excerpt.log').write_text('\n'.join(probe)+'\n',encoding='utf-8')
    loader=GAME/'chef_loader.log';loader_data=loader.read_bytes()
    loader_rows=[r for r in loader_data.decode('utf-8',errors='replace').splitlines()if '23:38:14'<=r[:8]<='23:40:49']
    assert any('shutdown (clean)'in r for r in loader_rows)
    (OUT/'B13-0-loader-excerpt.log').write_text('\n'.join(loader_rows)+'\n',encoding='utf-8')
    def meta(p,d):return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest(),modified=datetime.fromtimestamp(p.stat().st_mtime).isoformat())
    source=ROOT/'outputs/native-v21-b13-20261104/evidence/stingray-idstring32.html'
    body=source.read_bytes();markup=body.decode('utf-8-sig');plain=html.unescape(re.sub('<[^>]+>',' ',markup));plain=' '.join(plain.split())
    begin=plain.index('A hashed string value.');end=plain.index('Constructors and accessors',begin)
    excerpt=plain[begin:end]
    assert 'IdString32 objects are temporary' in excerpt and 'frame in which they were generated'in excerpt
    (OUT/'stingray-idstring32.html').write_bytes(body)
    (OUT/'idstring32-lifetime-excerpt.txt').write_text(excerpt+'\n',encoding='utf-8')
    save_json(OUT/'idstring32-api-source.json',dict(url='https://help.autodesk.com/cloudhelp/ENU/Stingray-Help/lua_ref/obj_stingray_IdString32.html',
        proxy='http://127.0.0.1:7890',**meta(source,body),scope='Official Stingray API lifetime contract; game outcome requires test.'))
    report=dict(status='ANALYZED',variant='B13-0',userReportedNoCrash=True,cleanShutdown=True,
        probeValidationPassed=False,validatedEvents=0,appliedEvents=0,disabledEvents=1,
        stoppedAt=dict(name='boss_aim',expectedIndex=9,stage='name_query',reason='avatar_layout_changed',frame=1210),
        sources=[meta(path,data),meta(loader,loader_data)],
        conclusion='No crash; probe disabled at first name query. Cached ID lifetime is a confirmed code defect; actual query cause still needs fresh-ID runtime verification.',
        next='B14-0 only; require validated=23 without disabled before A/B displacement.')
    save_json(OUT/'B13-0-game-result.json',report)
    feedback=load(W/'feedback.json');feedback['B13_0']=report;save_json(W/'feedback.json',feedback)
    print('B13-0 recorded: clean exit, first name query rejected, zero validated/applied events. Official temporary-ID contract saved.')


if __name__=='__main__':main()
