"""Shared native model calibration preset and TOML snapshot materialization."""
from pathlib import Path
import argparse,hashlib,json,re,tomllib

PIPELINE_VERSION='1.0.9'

def preset_root():
    here=Path(__file__).resolve().parent
    for p in [here/'presets/native-v15',here/'HD2ModManager/tools/native-python/anim_batch_mod/presets/native-v15']:
        if (p/'preset.json').is_file():return p
    raise FileNotFoundError('Native v15 preset missing; rebuild the complete bundled runtime/templates')

def resolve_native_config(path,manifest=None,managed_defaults=False):
    path=Path(path).resolve();d=tomllib.loads(path.read_text(encoding='utf-8-sig'));n=d.setdefault('native_skeleton',{})
    if managed_defaults:
        for key,value in dict(calibration_preset='native-v15',runtime_policy='b23-1.0.8',calibrate_weapon_bones=True,use_model_preset=True,preserve_arm_reference_clavicles=True).items():n.setdefault(key,value)
    if n.get('calibration_preset'):
        if n['calibration_preset']!='native-v15':raise ValueError('Unknown native calibration preset')
        root=preset_root();preset=json.loads((root/'preset.json').read_text(encoding='utf-8-sig'))
        n.setdefault('arm_reference_archive',str(root/preset['armReference']))
        n.setdefault('avatar_template',str(root/preset['avatarTemplate']))
        n.setdefault('preserve_arm_reference_clavicles',True)
        if manifest and n.get('use_model_preset',False):
            values=preset.get('models',{}).get(manifest.get('boneNamespace'),{})
            if 'foot_y_degrees' in values:n['foot_y_degrees']=values['foot_y_degrees']
    for key in ['arm_reference_archive','avatar_template']:
        if key in n:
            p=Path(n[key]);p=p if p.is_absolute() else path.parent/p
            p=p.resolve()
            if not p.is_file():raise FileNotFoundError(f'{key} unavailable: {p}')
            if key=='avatar_template':
                for suffix in ['.gpu_resources','.stream']:
                    if not Path(str(p)+suffix).is_file():raise FileNotFoundError('Avatar template sidecar missing: '+str(p)+suffix)
            n[key]=p.as_posix()
    return d

def _value(value):
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,str):return json.dumps(value,ensure_ascii=False)
    if isinstance(value,dict):return '{ '+', '.join(k+' = '+_value(v) for k,v in value.items())+' }'
    return repr(value)

def write_snapshot(source,output,model_scale=None,manifest=None):
    source=Path(source);output=Path(output);d=resolve_native_config(source,manifest,managed_defaults=True);n=d['native_skeleton']
    if model_scale is not None:n['model_scale']=model_scale
    n.setdefault('attachment_swap',True)
    text=source.read_text(encoding='utf-8-sig')
    header=re.search(r'^\[native_skeleton\][^\r\n]*',text,re.M)
    if not header:text+='\n[native_skeleton]\n';header=re.search(r'^\[native_skeleton\][^\r\n]*',text,re.M)
    end=re.search(r'^\[',text[header.end():],re.M);stop=header.end()+end.start() if end else len(text)
    section=text[header.end():stop]
    for key,value in n.items():
        pattern=r'(?m)^[ \t]*'+re.escape(key)+r'[ \t]*=.*$'
        line=key+' = '+_value(value)
        if re.search(pattern,section):section=re.sub(pattern,lambda _:line,section)
        else:section+='\n'+line+'\n'
    text=text[:header.end()]+section+text[stop:]
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(text.encode('utf-8'))
    checked=tomllib.loads(text);assert checked['native_skeleton']==n
    provenance={'pipelineVersion':PIPELINE_VERSION,'configSource':str(source.resolve()),'configSnapshot':str(output.resolve()),
        'configSha256':hashlib.sha256(output.read_bytes()).hexdigest(),'modelScale':n.get('model_scale'),
        'calibrationPreset':n.get('calibration_preset'),'runtimePolicy':n.get('runtime_policy'),
        'references':{k:{'path':n[k],'sha256':hashlib.sha256(Path(n[k]).read_bytes()).hexdigest()} for k in ['arm_reference_archive','avatar_template'] if k in n}}
    output.with_suffix('.provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    return provenance

def apply_runtime_policy(cfg,version='b23-1.0.8'):
    if version!='b23-1.0.8':raise ValueError('Unsupported runtime policy: '+str(version))
    policy=json.loads((preset_root()/'runtime-policy.json').read_text(encoding='utf-8-sig'))
    for key in ['performance','previewGuard','allowedConsumers','diagnostics']:cfg[key]=policy[key]
    cfg['leftGrip']['intent']=policy['intent'];cfg['consumers'].update(policy['fixedConsumers'])
    cfg['sync']['enabled']=False;cfg['logSeconds']=1.;cfg['maxRecords']=5000
    cfg['runtimePolicyVersion']=version
    return cfg

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--config',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--model-scale',type=float);p.add_argument('--manifest',type=Path)
    a=p.parse_args(argv);m=json.loads(a.manifest.read_text(encoding='utf-8-sig')) if a.manifest else None
    print(json.dumps(write_snapshot(a.config,a.output,a.model_scale,m)));return 0
