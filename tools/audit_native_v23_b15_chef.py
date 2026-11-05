"""Shipped Chef parser and profiles for the two B14-A subsets."""
from pathlib import Path
source=Path(__file__).with_name('audit_native_v20_b12_chef.py').read_text(encoding='utf-8')
source=source.replace('native-v20-b12-20261104','native-v23-b15-20261105').replace('B12','B15')
source=source.replace("('A','B','ALL')","('A1','A2')")
source=source.replace("reports['A']","reports['A1']")
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
