"""One HD2 skeleton pipeline. Reuses the original batch processor and patch writer.

VPK models are converted by vpk2patch --single-hd2-skeleton, never --source-skeleton. No Source
channels, B23 parenting, native-v15 arm archive, swaps or attachment Lua enter
this route. The batch configuration is derived from this model's HD2 bind.
"""
from pathlib import Path
import argparse,copy,hashlib,json,math,sys,tomllib
from types import SimpleNamespace
from .archive import PackageStore,ResourceIndex,TocArchive
from .constants import UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID
from .formats import UnitData,BonesData
from .processor import ModConfig
from .batch import discover_batch_jobs,build_batch_entries
from .cli import parse_thread_count,calculate_bone_offsets,calculate_bone_rotation_compensations,write_generated_config,write_output_patch,verify_patch

REFERENCE_UNIT=0x4d1c334d294dfa97
REFERENCE_ARCHIVE='18235e0c9ec0e636'
PIPELINE_VERSION='1.0.17'
ARM_POLICY='bind-relative-arm-v1'
BIND_POLICY='hd2-source-sized-shared-bind-v1'


def _progress(phase,done,total,message):
    # Same live protocol as mixed/native packaging. stdout is the final JSON report;
    # Hd2ModProcess consumes only stderr line-by-line while the child is running.
    text=str(message).replace('\r',' ').replace('\n',' ').strip()
    print(f'#progress {phase} {done} {total} {text}',file=sys.stderr,flush=True)


def model_units(folder):
    for path in sorted(Path(folder).glob('*.patch_*')):
        if not path.suffix.rsplit('_',1)[-1].isdigit():continue
        side=lambda s:Path(str(path)+s).read_bytes() if Path(str(path)+s).exists() else b''
        archive=TocArchive.parse_parts(path.read_bytes(),side('.gpu_resources'),side('.stream'))
        for entry in archive.entries.values():
            if entry.type_id==UNIT_TYPE_ID:yield entry.file_id,UnitData.parse(entry.toc_data)



def _model_files(folder):
    # Import appends a PhysBone compatibility trailer to GPU files after staging.
    # Fingerprint the actual referenced resource bytes, not that runtime metadata.
    files=[]
    for path in sorted(Path(folder).glob('*.patch_*')):
        if not path.suffix.rsplit('_',1)[-1].isdigit():continue
        side=lambda suffix:Path(str(path)+suffix).read_bytes() if Path(str(path)+suffix).exists() else b''
        archive=TocArchive.parse_parts(path.read_bytes(),side('.gpu_resources'),side('.stream'))
        files.append(dict(name=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        entries=sorted(archive.entries.values(),key=lambda e:(e.file_id,e.type_id))
        for suffix,attribute in [('.gpu_resources','gpu_data'),('.stream','stream_data')]:
            external=Path(str(path)+suffix)
            if external.exists():
                digest=hashlib.sha256()
                for entry in entries:digest.update(getattr(entry,attribute))
                files.append(dict(name=external.name,sha256=digest.hexdigest()))
    return files


def _validate_bind(folder,units):
    from .processor import _calculate_world_transforms
    from .math3d import matrix3_columns_to_quaternion
    path=Path(folder)/'single-hd2-bind.json'
    if not path.exists():
        raise ValueError('Legacy single model has no shared mesh/skeleton bind: reimport the VPK')
    bind=json.loads(path.read_text(encoding='utf-8-sig'))
    if bind.get('version')!=1 or bind.get('policy')!=BIND_POLICY or bind.get('meshOnlyPostprocessing') is not False:
        raise ValueError('Unsupported single HD2 mesh/skeleton bind policy: reimport the VPK')
    scale=bind.get('modelScale')
    if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or not 0<scale<=10:
        raise ValueError('Invalid single HD2 model scale')
    hashes=bind.get('driverHashes',[]);matrices=bind.get('driverWorld',[])
    if not hashes or len(set(hashes))!=len(hashes) or len(hashes)!=len(matrices):
        raise ValueError('Invalid single HD2 bind certificate')
    expected={}
    for h,row in zip(hashes,matrices):
        if len(row)!=16 or any(not math.isfinite(v) for v in row):raise ValueError('Non-finite single bind')
        columns=[row[0:3],row[4:7],row[8:11]]
        scales=[math.sqrt(sum(v*v for v in c)) for c in columns]
        if any(v<1e-8 for v in scales):raise ValueError('Singular single bind scale')
        expected[h]=(row[12:15],matrix3_columns_to_quaternion([[v/s for v in c] for c,s in zip(columns,scales)]),scales)
    for resource,u in units:
        if len(set(u.name_hashes))!=len(u.name_hashes):raise ValueError('Duplicate model node hashes')
        if not set(hashes).issubset(u.name_hashes):raise ValueError(f'Model {resource:016x} lacks the shared HD2 bind')
        if any(any(not math.isfinite(v) for v in t.position+t.rotation+t.scale) or
               any(v<=0 for v in t.scale) for t in u.transforms):
            raise ValueError('Single HD2 model contains non-finite or singular bone scale')
        worlds=_calculate_world_transforms(u.transforms,u.parents)
        for h,(position,rotation,scale) in expected.items():
            world=worlds[u.name_hashes.index(h)]
            if math.dist(position,world.position)>2e-5 or abs(sum(a*b for a,b in zip(rotation,world.rotation)))<1-1e-6 or max(abs(a-b) for a,b in zip(scale,world.scale))>1e-4:
                raise ValueError(f'Model {resource:016x} bind differs from the converted mesh at {h:08x}')
    return bind


def _validate_prepared_model(folder,marker):
    if marker.get('version')!=3 or marker.get('bindPolicy')!=BIND_POLICY:
        raise ValueError('Legacy single model/animation config: reimport the VPK and rebuild both packages')
    certificate=Path(folder)/'single-hd2-bind.json'
    if not certificate.exists() or hashlib.sha256(certificate.read_bytes()).hexdigest()!=marker.get('bindSha256'):
        raise ValueError('Single model bind certificate changed: reimport the VPK')
    if _model_files(folder)!=marker.get('modelFiles'):
        raise ValueError('Single model payload changed since animation configuration: reimport the VPK')
    _validate_bind(folder,list(model_units(folder)))


def prepare_model(folder,game_data,config_path=None):
    folder=Path(folder)
    if (folder/'source-skeleton.json').exists():raise ValueError('Single HD2 route cannot consume a dual Source rig')
    units=list(model_units(folder))
    if not units:raise ValueError('No converted HD2 model Units')
    certificate=_validate_bind(folder,units)
    store=PackageStore(Path(game_data));index=ResourceIndex(store,folder/'single-resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID})
    try:
        index.load_or_build();_,original_entry=index.resolve(REFERENCE_UNIT,UNIT_TYPE_ID)
        original=UnitData.parse(original_entry.toc_data);_,bones_entry=index.resolve(original.bones_ref,BONE_TYPE_ID)
        bones=BonesData.parse(bones_entry.toc_data)
        candidates=[u for _,u in units if set(bones.hashes).issubset(u.name_hashes)]
        if not candidates:raise ValueError('Converted model lacks the complete HD2 animation skeleton')
        base=candidates[0]
        for u in candidates:
            # Body parts/variants must describe the SAME bind, not silently pick one.
            for h in bones.hashes:
                a,b=base.transforms[base.name_hashes.index(h)],u.transforms[u.name_hashes.index(h)]
                if max(abs(x-y) for x,y in zip(a.position,b.position))>1e-5 or abs(sum(x*y for x,y in zip(a.rotation,b.rotation)))<1-1e-5 or max(abs(x-y) for x,y in zip(a.scale,b.scale))>1e-5:
                    raise ValueError('Single model variants have incompatible HD2 binds')
        # Model Units may contain appended unanimated physics helpers. Project ONLY
        # the HD2 driver hashes into the original order, as the old batch codec requires.
        projected=copy.deepcopy(original)
        for i,h in enumerate(original.name_hashes):
            if h not in base.name_hashes:raise ValueError('Model is missing an original HD2 node')
            bi=base.name_hashes.index(h);bp=base.parents[bi];op=original.parents[i]
            if (None if bp is None else base.name_hashes[bp])!=(None if op is None else original.name_hashes[op]):
                raise ValueError('Single HD2 driver topology differs from the original batch skeleton')
            if max(abs(a-b) for a,b in zip(original.transforms[i].scale,base.transforms[bi].scale))>1e-5:
                raise ValueError('Single animation cannot compensate changed node scale')
            if h not in bones.hashes and (math.dist(original.transforms[i].position,base.transforms[bi].position)>1e-5 or
                abs(sum(a*b for a,b in zip(original.transforms[i].rotation,base.transforms[bi].rotation)))<1-1e-6):
                raise ValueError('Single batch cannot change an unanimated HD2 helper local bind')
            projected.transforms[i]=copy.deepcopy(base.transforms[bi])
        base=projected
        offsets,deltas=calculate_bone_offsets(base,bones,original,bones,1e-6)
        rotations=calculate_bone_rotation_compensations(base,bones,original,bones,1e-6)
        output=folder/'single-config.toml'
        if offsets or rotations:write_generated_config(output,offsets,deltas,rotation_compensations=rotations)
        else:output.write_text('[filter]\nrequired_bone = "l_pinky_finger3"\n[bone_offsets]\nboss = [0.0, 0.0, 0.0] # identity correction for an unchanged HD2 bind\n[bone_distance_multipliers]\n',encoding='utf-8')
        # Original batch flags, configurable independently from the dual-rig preset.
        cfg=tomllib.loads(Path(config_path).read_text(encoding='utf-8-sig')) if config_path else {}
        options=cfg.get('single_skeleton',{})
        allowed={'rotate_multipliers','rotation_compensation','ik_correction','allow_additive'}
        if set(options)-allowed or any(not isinstance(v,bool) for v in options.values()):raise ValueError('Invalid single_skeleton options')
        for k,v in {'rotate_multipliers':True,'rotation_compensation':True,'ik_correction':True,'allow_additive':True}.items():options.setdefault(k,v)
        # Old manager presets explicitly disabled this for the old identity bind.
        # A shared non-identity bind requires it, regardless of that legacy default.
        adjusted=bool(rotations) and not options['rotation_compensation']
        if rotations:options['rotation_compensation']=True
        arm_targets=[]
        arm_names={side+'_'+part for side in ('l','r') for part in ('shoulder','elbow','hand')}
        if arm_names.intersection(bones.names):
            if not arm_names.issubset(bones.names):raise ValueError('Incomplete single HD2 arm skeleton')
            if not options['ik_correction']:raise ValueError('Single HD2 arm retargeting requires ik_correction=true')
            with output.open('a',encoding='utf-8') as stream:
                for side in ('l','r'):
                    target=side+'_hand';arm_targets.append(target)
                    stream.write('\n[ik_chains.'+target+']\nchain = ["'+side+'_shoulder", "'+side+'_elbow"]\n'
                                 'target_multiplier = [1.0, 1.0, 1.0]\npolicy = "'+ARM_POLICY+'"\n')
        marker=dict(version=3,bindPolicy=BIND_POLICY,modelFingerprint='toc-and-referenced-payloads-v1',modelScale=certificate['modelScale'],
            bindSha256=hashlib.sha256((folder/'single-hd2-bind.json').read_bytes()).hexdigest(),modelFiles=_model_files(folder),
            pipelineVersion=PIPELINE_VERSION,skeleton='hd2',sourceRigRetained=False,
            referenceUnit=f'0x{REFERENCE_UNIT:016x}',referenceArchive=REFERENCE_ARCHIVE,modelResources=[f'{i:016x}' for i,_ in units],
            boneCount=len(bones.names),config='single-config.toml',configSha256=hashlib.sha256(output.read_bytes()).hexdigest(),
            armRetargetPolicy=ARM_POLICY,armIKChains=arm_targets,options=options,requiredRotationCompensation=bool(rotations),legacyRotationOptionAdjusted=adjusted,attachmentLua=False,attachmentSwap=False,configOrigin='converted-model-hd2-bind')
        (folder/'single-skeleton.json').write_text(json.dumps(marker,indent=2),encoding='utf-8')
        return marker
    finally:
        index.close()
        # This staging-only cache is not a distributable model resource.
        for suffix in ('','-wal','-shm'):(folder/('single-resource-index.sqlite3'+suffix)).unlink(missing_ok=True)


def build_project(folder,game_data,output,sample_count=None,threads=2):
    if isinstance(threads,bool) or not isinstance(threads,int) or not 1<=threads<=16:
        raise ValueError("threads must be an integer between 1 and 16")
    _progress('prepare',0,0,'正在校验单骨架模型与动画配置')
    folder=Path(folder);output=Path(output)
    marker=json.loads((folder/'single-skeleton.json').read_text(encoding='utf-8-sig'))
    if marker.get('skeleton')!='hd2' or marker.get('sourceRigRetained') is not False or marker.get('attachmentSwap') is not False or marker.get('attachmentLua') is not False:
        raise ValueError('Not a single HD2 skeleton model')
    _validate_prepared_model(folder,marker)
    path=folder/marker['config']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=marker['configSha256']:raise ValueError('Model/animation config mismatch: reimport after changing configuration')
    config=ModConfig.load(path)
    targets=marker.get('armIKChains')
    if marker.get('armRetargetPolicy')!=ARM_POLICY or not isinstance(targets,list):
        raise ValueError('Legacy single arm animation contract: reimport the VPK and rebuild both packages')
    if marker.get('boneCount')==90 and set(targets)!={'l_hand','r_hand'}:
        raise ValueError('Single HD2 arm contract must include both hands')
    if set(config.ik_chains)!=set(targets) or any(config.ik_chains[n].policy!=ARM_POLICY or
        config.ik_chains[n].chain!=[n[0]+'_shoulder',n[0]+'_elbow'] for n in targets):
        raise ValueError('Single HD2 arm IK configuration is empty or incompatible')
    if targets and not marker['options']['ik_correction']:
        raise ValueError('Single HD2 arm retargeting requires ik_correction=true')
    if config.rotation_compensations and not marker['options']['rotation_compensation']:
        raise ValueError('Single bind axis compensation is required')
    if output.exists() and any(output.iterdir()):raise FileExistsError('Single animation output must be empty')
    output.mkdir(parents=True,exist_ok=True)
    _progress('index',0,1,'读取游戏 bundle 映射')
    store=PackageStore(Path(game_data))
    index=ResourceIndex(store,output/'resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID})
    report=dict(status='building',pipelineVersion=PIPELINE_VERSION,skeleton='hd2',processor='anim_batch_mod.batch.build_batch_entries',
        configSha256=marker['configSha256'],attachmentLua=False,attachmentSwap=False,sourceRigRetained=False,animations=[],gameTested=False,progressProtocol='stderr-v1')
    try:
        index.load_or_build(lambda done,total,label: _progress('index',done,total,
            f'读取游戏资源索引 {done}/{total}') if done % 250 == 0 or done == total else None)
        _progress('index',1,1,'游戏资源索引已就绪')
        _progress('discover',0,0,'正在收集单骨架动画')
        discovery=discover_batch_jobs(store,index,[REFERENCE_ARCHIVE],config,requested_unit_id=REFERENCE_UNIT,
            include_ik_bones=marker['options']['ik_correction'],
            progress=lambda phase,done,total,label: _progress('discover',0,0,f'正在收集单骨架动画：{label}'))
        if discovery.fatal_issues:raise ValueError('Single animation discovery failed: '+repr(discovery.fatal_issues))
        jobs=discovery.jobs;report['available_animations']=len(jobs)
        if sample_count is not None:
            if not 1<=sample_count<=len(jobs):raise ValueError('Invalid sample count')
            jobs=jobs[:sample_count];report['sampleOnly']=True
        report['expected_animations']=len(jobs);report['threads']=threads
        _progress('animation',0,len(jobs),f'单骨架动画 0/{len(jobs)}')
        def progress(phase,done,total,label):_progress(phase,done,total,f'单骨架动画 {done}/{total}')
        o=marker['options']
        build=build_batch_entries(index,jobs,config,allow_additive=o['allow_additive'],progress=progress,
            apply_rotate_multipliers=o['rotate_multipliers'],apply_rotation_compensations=o['rotation_compensation'],apply_ik_correction=o['ik_correction'],add_unit=False,threads=threads)
        if build.fatal_issues or len(build.animations)!=len(jobs):raise ValueError('Incomplete single batch build: '+repr(build.fatal_issues))
        _progress('package',0,0,'正在写入单骨架动画包')
        staging=output/'runtime-incomplete';staging.mkdir()
        paths=write_output_patch(store,SimpleNamespace(output=staging,patch_index=2,force=False),build.entries)
        _progress('verify',0,0,'正在校验单骨架动画包')
        ids=[r.animation_id for r in build.animations];verify_patch(paths[0],ids)
        # Original batch keeps one HD2 channel layout and does not append Source tracks.
        from .formats import AnimationData
        counts={len(AnimationData.parse(e.toc_data).initial_bone_states) for e in build.entries if e.type_id==ANIMATION_TYPE_ID}
        if counts!={marker['boneCount']}:raise ValueError('Single batch changed HD2 channel count')
        (staging/'single-config.toml').write_bytes(path.read_bytes())
        (staging/'single-skeleton.json').write_text(json.dumps(marker,indent=2),encoding='utf-8')
        staging.rename(output/'runtime')
        report.update(status='complete',armRetargetPolicy=ARM_POLICY,armIKChains=targets,
            armRetargetSamples=sum(r.modification.arm_retargets for r in build.animations),
            animations=[dict(id=f'{i:016x}') for i in ids],boneCount=marker['boneCount'],
            files=[dict(name=p.name,sha256=hashlib.sha256((output/'runtime'/p.name).read_bytes()).hexdigest()) for p in paths])
        return report
    except BaseException as e:
        report.update(status='failed',error=str(e));raise
    finally:
        index.close();(output/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if report['status']=='complete':_progress('complete',1,1,'单骨架动画打包完成')


def main(argv=None):
    p=argparse.ArgumentParser(description='Original anim_batch_mod single HD2 skeleton packaging')
    p.add_argument('action',choices=['prepare-model','build']);p.add_argument('--model-directory',required=True,type=Path)
    p.add_argument('--game-data',required=True,type=Path);p.add_argument('--config',type=Path);p.add_argument('--output',type=Path);p.add_argument('--sample-count',type=int)
    p.add_argument('--threads',type=parse_thread_count,default=2,help='Animation threads (1..16, default: 2)')
    a=p.parse_args(argv)
    if a.action=='prepare-model':report=prepare_model(a.model_directory,a.game_data,a.config)
    else:
        if a.output is None:p.error('build requires --output')
        report=build_project(a.model_directory,a.game_data,a.output,a.sample_count,a.threads)
    print(json.dumps(report,ensure_ascii=False));return 0
