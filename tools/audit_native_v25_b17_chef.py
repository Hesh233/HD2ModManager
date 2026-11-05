"""Check exact L/R contents using the shipped Chef parser and sandbox."""
from pathlib import Path

source = Path(__file__).with_name('audit_native_v20_b12_chef.py').read_text(encoding='utf-8')
for old, new in (
    ('native-v20-b12-20261104', 'native-v25-b17-20261105'),
    ('B12', 'B17'), ("('A','B','ALL')", "('L','R')"), ("reports['A']", "reports['L']"),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, __file__, 'exec'), dict(__file__=__file__, __name__='__main__'))
