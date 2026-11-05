"""Read supplied attachment catalog and the delivered test01 manifest."""
import json, zipfile, xml.etree.ElementTree as E
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'outputs/native-manual-20261103/project'
W=ROOT/'outputs/native-v11-20261104'
W.mkdir(exist_ok=True)
ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(P.parent/'Helldivers 2 Archive Labeling.xlsx') as z:
    strings=[''.join(e.itertext()) for e in E.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si',ns)]
    book=E.fromstring(z.read('xl/workbook.xml'))
    rels={r.attrib['Id']:r.attrib['Target'] for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    sheets={s.attrib['name']:rels[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']] for s in book.find('s:sheets',ns)}
    print('SHEETS',sheets)
    found=[]
    for name,target in sheets.items():
        target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        rows=[]
        for row in E.fromstring(z.read(target)).findall('.//s:row',ns):
            cells={}
            for c in row.findall('s:c',ns):
                v=c.find('s:v',ns)
                value=(v.text or '') if v is not None else ''.join(c.find('s:is',ns).itertext()) if c.find('s:is',ns) is not None else ''
                if c.attrib.get('t')=='s': value=strings[int(value)]
                if value: cells[c.attrib['r']]=value
            if name=='Weapon to Avatar Bones' or any(k in str(cells).lower() for k in ('attach_hand','attach_weapon','aim_weapon','camera','hand_twist','smg-72')):
                rows.append(cells)
        found.append(dict(sheet=name,rows=rows))
        if rows and name in ('Weapon to Avatar Bones','Weapons & Attachment IDs'): print(name, json.dumps(rows,ensure_ascii=False))
    (W/'spreadsheet-extract.json').write_text(json.dumps(found,ensure_ascii=False,indent=2),encoding='utf-8')
m=json.loads((P/'source-skeleton.json').read_text(encoding='utf-8-sig'))
print('MANIFEST',[(k,len(v) if isinstance(v,(dict,list)) else v) for k,v in m.items() if k!='bones'])
print('BONES',[(i,n['sourceName'],n['parent'],n['driver']) for i,n in enumerate(m['bones']) if not n['physics']])
p=json.loads((P/'attachment-profile.json').read_text())
print('PROFILE',[(r['index'],r['standardName'],r['policy'],r.get('configuredAnchorIndex'),r.get('sourceAnchorIndex')) for r in p['vpk']])
