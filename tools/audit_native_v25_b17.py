"""Run affine, rollback, lifecycle and paired-control cases on L/R profiles."""
from pathlib import Path

source = Path(__file__).with_name('audit_native_v23_b15.py').read_text(encoding='utf-8')
for old, new in (
    ('native-v23-b15-20261105', 'native-v25-b17-20261105'),
    ('B15', 'B17'), ("('A1','A2')", "('L','R')"), ('A1/A2 subsets', 'L/R subsets'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, __file__, 'exec'), dict(__file__=__file__, __name__='__main__'))
