"""B14 exact shipped Chef sandbox/profile verification."""
from pathlib import Path
source=Path(__file__).with_name('audit_native_v21_b13_chef.py').read_text(encoding='utf-8')
source=source.replace('native-v21-b13-20261104','native-v22-b14-20261104').replace('B13','B14')
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
