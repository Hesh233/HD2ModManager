"""B14 keeps B13's scope and resolves frame-temporary name IDs on demand."""
from pathlib import Path
source=Path(__file__).with_name('prepare_native_v21_b13.py').read_text(encoding='utf-8')
for old,new in (
    ('native-v21-b13-20261104','native-v22-b14-20261104'),
    ("baseline['revision']=='native-v20'", "baseline['revision']=='native-v21'"),
    ("R/'project/diagnostics/B12'", "R/'project/diagnostics/B13'"),
    ("local M={VERSION='0.11.1'}", "local M={VERSION='0.11.2'}"),
    ("local M={VERSION='0.11.0'}", "local M={VERSION='0.11.1'}"),
    ('native-v21-B13','native-v22-B14'),('test01-v21-B13','test01-v22-B14'),
    ('v21-B13','v22-B14'),("control='v20-B12'", "control='v21-B13'"),
    ('B13','B14'),
):
    assert old in source,old
    source=source.replace(old,new)
# The chained label change must not change the source baseline directory.
source=source.replace("R/'project/diagnostics/B14'", "R/'project/diagnostics/B13'")
source=source.replace("control='v21-B14'", "control='v21-B13'")
source=source.replace("print('B14 prepared:", "print('B14 immediate-ID revision prepared:")
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
