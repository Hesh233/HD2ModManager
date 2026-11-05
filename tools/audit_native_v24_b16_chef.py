"""Check H/W through the shipped Chef sandbox with exact profile contents."""
from pathlib import Path
source=Path(__file__).with_name('audit_native_v23_b15_chef.py').read_text(encoding='utf-8')
source=source.replace('native-v23-b15-20261105','native-v24-b16-20261105').replace('B15','B16')
source=source.replace("('A1','A2')","('H','W')").replace("reports['A1']","reports['H']")
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
