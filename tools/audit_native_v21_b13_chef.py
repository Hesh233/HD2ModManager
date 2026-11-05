"""Run the shipped Chef parser for B13 0/A/B/ALL, including exact profiles."""
from pathlib import Path
source=(Path(__file__).with_name('audit_native_v20_b12_chef.py')).read_text(encoding='utf-8')
source=source.replace('native-v20-b12-20261104','native-v21-b13-20261104').replace('B12','B13')
source=source.replace("('A','B','ALL')", "('0','A','B','ALL')")
source=source.replace('assert(p.attachmentProbe.variant==expected_profile.attachmentProbe.variant)',
    'assert(p.attachmentProbe.variant==expected_profile.attachmentProbe.variant)\nassert(p.attachmentProbe.validationOnly==expected_profile.attachmentProbe.validationOnly)')
exec(compile(source,__file__,'exec'),dict(__file__=__file__,__name__='__main__'))
