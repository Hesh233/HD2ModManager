"""Adapt retained v12 regression fixtures without writing their reports."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
T=ROOT/'tools'

def main():
    for name in ('animations','chef','runtime'):
        if (T/f'audit_native_v13_{name}.py').exists():
            continue  # Keep subsequent v13-specific invariants and diagnostics.
        source=(T/f'audit_native_v12_{name}.py').read_text(encoding='utf-8')
        source=source.replace("W=ROOT/'outputs/native-v12-20261104'", "W=ROOT/'outputs/native-v13-20261104'")
        if name=='runtime':
            source=source.replace(";P=W/'project'", ";P=ROOT/'outputs/native-v12-20261104/project'")
            source=source.replace("(W/'source-before/native_attachments.lua')", "(ROOT/'outputs/native-v12-20261104/source-before/native_attachments.lua')")
            marker="(W/'attachment-runtime-audit.json').write_text"
            extra='''current=json.loads((W/'project/attachment-profile.json').read_text(encoding='utf-8'))
assert not current['armSync']
current_check=run(current,fixture,source,prefix+"tick(3);return {active=runtime.stats.active,gun=A.written[33]==true,sling=A.written[28]==true}")
assert current_check=={'active':1,'gun':False,'sling':False},current_check
result.update(v13Baseline=current_check,armSyncExperimental=True)
'''
            source=source.replace(marker,extra+marker)
        if name=='chef':
            source=source.replace("a.version=='2.1.7'", "a.version=='2.1.8'")
            source=source.replace('blended==24','blended==23')
            source=source.replace('assert(count==5)',"assert(count==5 and p.armSync==false and #p.armChains==2)")
        (T/f'audit_native_v13_{name}.py').write_text(source,encoding='utf-8')
    print('v13 audit entry points prepared')

if __name__=='__main__':main()
