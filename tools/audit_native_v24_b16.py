"""Run paired-control, affine, lifecycle and ID-lifetime cases for H/W."""
from pathlib import Path
source=Path(__file__).with_name('audit_native_v23_b15.py').read_text(encoding='utf-8')
source=source.replace('native-v23-b15-20261105','native-v24-b16-20261105').replace('B15','B16')
source=source.replace("('A1','A2')","('H','W')")
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
