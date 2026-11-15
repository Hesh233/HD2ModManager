"""Offline production-B3 module checks using the frozen accepted replay fixtures.
No game/GUI deployment, no changes to the accepted B3 packages or input logs.
"""
from pathlib import Path
import argparse
import copy
import io
import contextlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
sys.path.insert(0,str(ROOT/'tools'))
from lupa.lua51 import LuaRuntime
from audit_native_b23_107_issues import plain


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--calibration',type=Path,default=ROOT/'tmp/b3-production-test06-calibration2')
    parser.add_argument('--out',type=Path,default=ROOT/'tmp/b3-production-fp-validation');args=parser.parse_args()
    calibration=args.calibration.resolve();output=args.out.resolve();output.mkdir(parents=True,exist_ok=True)
    profile=json.loads((calibration/'attachment-profile.json').read_text(encoding='utf-8'))
    production=ROOT/'HD2PhysBoneCompat/src/production'
    vm=LuaRuntime(unpack_returned_tuples=True)
    compile_checks=0
    for f in production.glob('*.lua'):
        ok,why=vm.eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(f.read_text(encoding='utf-8'))
        assert ok,(f.name,why);compile_checks+=1
    module=vm.execute((production/'attachment_option_switches.lua').read_text(encoding='utf-8'))
    specs=profile['optionSwitches']['specs'];schema=profile['optionSwitches']['schema'];selector_checks=0
    for disabled in [None,*[s['key'] for s in specs],'all']:
        markers={s['owner']:s for s in specs if disabled not in ('all',s['key'])}
        def lookup(owner):
            if owner not in markers:return None
            return vm.table_from(dict(schema=schema,key=markers[owner]['key'],enabled=True))
        state=module.resolve(vm.table_from(profile,recursive=True),lookup)
        result=plain(module.apply(vm.table_from(profile,recursive=True),state));state=plain(state)
        expected={s['bone'] for s in specs if 'bone' in s and disabled not in ('all',s['key'])}
        assert state['activeBoneCount']==len(expected);selector_checks+=1
        assert state['fpArms']==(disabled not in ('all','fp_arms'));selector_checks+=1
        assert {r['node']['name'] for r in result['attachments']}=={r['node']['name'] for r in profile['attachments'] if r['node']['name'] in expected};selector_checks+=1
        assert result['rightAttachmentEnabled']==('attach_hand_r' in expected);selector_checks+=1
        assert result['leftGrip']['enabled']==('attach_hand_l' in expected);selector_checks+=1
        assert result['allAttachmentBonesOff']==(not expected);selector_checks+=1
        assert result['firstPersonSource']['runtimeEnabled']==state['fpArms'];selector_checks+=1
        assert result['firstPersonSource']['hiddenOnly']==(not state['fpArms']);selector_checks+=1
        for key in ['models','consumers','rightAxes','leftAxes','bodySync']:
            assert result[key]==plain(vm.table_from(profile,recursive=True))[key];selector_checks+=1
    for value in [None,{'schema':'foreign-model','key':'fp_arms','enabled':True},{'schema':schema,'key':'wrong','enabled':True}]:
        state=plain(module.resolve(vm.table_from(profile,recursive=True),lambda owner:vm.table_from(value) if value else None))
        assert not state['fpArms'];selector_checks+=1
    # Run the historical acceptance replay code with new production sources/calibration.
    # Only output paths and fixture inputs are redirected; never overwrite historical results.
    for name in ['verify_fp_enabled.py','verify_fp_disabled.py']:
        original=ROOT/'outputs/grip-b3-options-20261110'/name;s=original.read_text(encoding='utf-8')
        start=s.index('O=Path(__file__).parent;');end=s.index('\nh=',start)
        initial=f"""out=Path({str(output)!r});out.mkdir(exist_ok=True)
c=b.load(Path({str(calibration/'first-person-source-profile.json')!r}))
all_models=c['models']
c['models']=[next(m for m in all_models if m['resource']=='e6980827cce04d17'),next(m for m in all_models if m['resource']=='4c28e97d1bf51e2b')]
c['models'] += [m for m in all_models if m['resource'] not in ('e6980827cce04d17','4c28e97d1bf51e2b')]
c['logSeconds']=0;c['diagnosticSeconds']=0
from anim_batch_mod.archive import TocArchive
fp_patch=Path({str(calibration/'first-person-parenting/9ba626afa44a3aa3.patch_6')!r})
fp=b.UnitData.parse(next(iter(TocArchive.parse_parts(fp_patch.read_bytes(),load_external_data=False).entries.values())).toc_data)
fixtures=R/'outputs/grip-b3-options-20261110/b3'
model=b.UnitData.parse((fixtures/'fp-model-unit.toc').read_bytes());left=b.UnitData.parse((fixtures/'fp-left-model-unit.toc').read_bytes())
source=(R/'HD2PhysBoneCompat/src/production/first_person_source.lua').read_text(encoding='utf-8')"""
        s=s[:start]+initial+s[end:]
        s=s.replace("(out/'src/native_first_person_guard.lua').read_text(encoding='utf-8')","(R/'HD2PhysBoneCompat/src/production/native_first_person_guard.lua').read_text(encoding='utf-8')")
        s=s.replace("(out/'src/fp_arm_hidden_mode.lua').read_text(encoding='utf-8')","(R/'HD2PhysBoneCompat/src/production/fp_arm_hidden_mode.lua').read_text(encoding='utf-8')")
        s=s.replace("(out/'fp-native-unit.toc').read_bytes()","(fixtures/'fp-native-unit.toc').read_bytes()")
        if name=='verify_fp_enabled.py':
            extra=r'''
-- Alternative receiver resources are valid, but two same-side native matches are ambiguous.
view=false;rt:tick('update',4000,110);view=true
local originalResource=model.resource;model.resource='c19ad4635cf57c68';refresh(model)
local before=rt.stats.writes;rt:tick('render',4001,110.1)
check(rt.stats.writes>before and rt.pending.modelSpec.resource==model.resource,'alternate right resource did not drive its own contract')
view=false;rt:tick('update',4002,110.2);check(not rt.pending,'alternate resource restore failed');view=true
model.resource=originalResource;refresh(model)
local alternate=make(model_fixture);alternate.resource='c19ad4635cf57c68';alternate.nativeReceiver=true;refresh(alternate)
groups[2]={fp,model,left,alternate};before=rt.stats.writes;rt:tick('render',4003,110.3)
check(rt.stats.writes==before,'ambiguous different-resource right receivers were driven')
groups[2]={fp,model,left};view=false;rt:tick('update',4004,110.4)
'''
            s=s.replace("rt:stop();check(nativeWrites==0",extra+"\nrt:stop();check(nativeWrites==0",1)
        with contextlib.redirect_stdout(io.StringIO()):
            exec(compile(s,str(original)+' [production]','exec'),{'__file__':str(original),'__name__':'__main__'})
    enabled=json.loads((output/'fp-enabled-validation.json').read_text(encoding='utf-8'))
    disabled=json.loads((output/'fp-disabled-validation.json').read_text(encoding='utf-8'))
    native=json.loads((output/'fp-disabled-native63-validation.json').read_text(encoding='utf-8'))
    result=dict(status='PASS_OFFLINE_PRODUCTION_B3',moduleCompilationChecks=compile_checks,selectorChecks=selector_checks,
                fpEnabledChecks=enabled['checks'],actualReplaySamples=enabled['actualSamples'],fpDisabledChecks=disabled['checks'],native63DisabledChecks=native['checks'],
                nativePoseWrites=enabled['nativeWrites'],modelPoseWrites=enabled['modelWrites'],alternateReceiverPositiveAndAmbiguityNegative=True,
                maxContactErrorMetres=enabled['maximumContactErrorMetres'],maxTwistMatrixError=enabled['maximumTwistMatrixError'],gameDeployed=False)
    (output/'production-b3-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
