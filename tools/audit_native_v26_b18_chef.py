"""Check exact AIM/PARTS contents using the shipped Chef parser and sandbox."""
from pathlib import Path

source = Path(__file__).with_name('audit_native_v20_b12_chef.py').read_text(encoding='utf-8')
for old, new in (
    ('native-v20-b12-20261104', 'native-v26-b18-20261105'),
    ('B12', 'B18'), ("('A','B','ALL')", "('AIM','PARTS')"), ("reports['A']", "reports['AIM']"),
):
    assert old in source, old
    source = source.replace(old, new)
marker = "assert(p.attachmentProbe.variant==expected_profile.attachmentProbe.variant)"
extra = """local expectedSimple,actualSimple=0,0
for resource,spec in pairs(expected_profile.simpleWeaponComponents or {})do
 expectedSimple=expectedSimple+1
 local actual=assert(p.simpleWeaponComponents and p.simpleWeaponComponents[resource])
 assert(actual.count==spec.count and actual.markerIndex==spec.markerIndex and #actual.signature==#spec.signature)
 for i,row in ipairs(spec.signature)do assert(actual.signature[i].name==row.name and actual.signature[i].index==row.index)end
end
for _ in pairs(p.simpleWeaponComponents or {})do actualSimple=actualSimple+1 end
assert(expectedSimple==actualSimple)
"""
assert marker in source
source = source.replace(marker, extra + marker)
exec(compile(source, __file__, 'exec'), dict(__file__=__file__, __name__='__main__'))
