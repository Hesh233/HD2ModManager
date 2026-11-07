"""One HD2 skeleton pipeline. Reuses the original batch processor and patch writer.

VPK models are converted by vpk2patch --single-hd2-skeleton, never --source-skeleton. No Source
channels, B23 parenting, native-v15 arm archive, swaps or attachment Lua enter
this route. The batch configuration is derived from this model's HD2 bind.
"""
from pathlib import Path
import argparse,copy,hashlib,json,math,struct,sys,tomllib
from types import SimpleNamespace
from .archive import PackageStore,ResourceIndex,TocArchive
from .constants import UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID
from .formats import UnitData,BonesData
from .playback_reference import NormalPlaybackReference,PLAYBACK_REVISION,FRAME_TIME_POLICY
from .processor import ModConfig
from .batch import discover_batch_jobs,build_batch_entries
from .cli import parse_thread_count,calculate_bone_offsets,calculate_bone_rotation_compensations,write_generated_config,write_output_patch,verify_patch

REFERENCE_UNIT=0x4d1c334d294dfa97
REFERENCE_ARCHIVE='18235e0c9ec0e636'
PIPELINE_VERSION='1.0.20'
PROCESSING_PROFILE='standard-single-v3-normal-reference'
BIND_POLICY='hd2-source-sized-shared-bind-v1'
CONTROL_MARKERS={'attach_hand_l','attach_hand_r','weapon_aim','attach_weapon','aim_weapon','head_aim','boss_aim'}


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
    # Versions 2/3 describe a valid shared MESH bind, even though their cached
    # animation policy is obsolete. Re-derive calibration; never execute it.
    folder=Path(folder)
    if (folder/'source-skeleton.json').exists() or marker.get('sourceRigRetained') is True:
        raise ValueError('Single HD2 route cannot consume a dual Source rig')
    if marker.get('version') not in (2,3,4) or marker.get('bindPolicy')!=BIND_POLICY:
        raise ValueError('Legacy single model has no shared bind: reimport the VPK and rebuild both packages')
    if marker.get('attachmentLua') is True or marker.get('attachmentSwap') is True:
        raise ValueError('Single HD2 model cannot include a dual attachment policy')
    certificate=folder/'single-hd2-bind.json'
    if not certificate.exists() or hashlib.sha256(certificate.read_bytes()).hexdigest()!=marker.get('bindSha256'):
        raise ValueError('Single model bind certificate changed: reimport the VPK')
    if _model_files(folder)!=marker.get('modelFiles'):
        raise ValueError('Single model payload changed since calibration: reimport the VPK')
    _validate_bind(folder,list(model_units(folder)))


def _read_standard_config(config_path=None):
    candidates=[Path(config_path)] if config_path else [Path(__file__).resolve().parent.parent/'config.toml',Path(__file__).with_name('config.toml')]
    path=next((p.resolve() for p in candidates if p.is_file()),None)
    if path is None:raise FileNotFoundError('Standard config.toml is required for single HD2 animation')
    raw=path.read_bytes();data=tomllib.loads(raw.decode('utf-8-sig'))
    options=dict(rotate_multipliers=True,rotation_compensation=False,ik_correction=True,allow_additive=True,source_arm_constraints=True)
    supplied=data.get('single_skeleton',{})
    if not isinstance(supplied,dict) or set(supplied)-set(options) or any(not isinstance(v,bool) for v in supplied.values()):
        raise ValueError('Invalid single_skeleton processing switches')
    options.update(supplied)
    raw_chains=data.get('ik_chains')
    if not isinstance(raw_chains,dict):raise ValueError('Standard [ik_chains] must be present; no invented arm targets')
    from .processor import IKChainConfig
    chains={}
    for name,row in raw_chains.items():
        if not isinstance(row,dict) or not isinstance(row.get('chain'),list):raise ValueError('Invalid standard IK chain')
        if row.get('policy','fk-target')!='fk-target':raise ValueError('Single HD2 uses standard IK, not experimental/dual policies')
        chains[str(name)]=IKChainConfig(row['chain'],row.get('target_multiplier',1.0))
    return dict(path=path,raw=raw,data=data,options=options,chains=chains,sha256=hashlib.sha256(raw).hexdigest())


def _validate_standard_chains(standard,bone_count):
    if bone_count==90 and not {'l_hand','r_hand','l_foot','r_foot'}.issubset(standard['chains']):
        raise ValueError('Standard single HD2 config must provide both hand and foot IK chains')


def _derive_calibration(units,original,bones):
    candidates=[u for _,u in units if set(bones.hashes).issubset(u.name_hashes)]
    if not candidates:raise ValueError('Converted model lacks the complete HD2 animation skeleton')
    base=candidates[0]
    for u in candidates:
        for h in bones.hashes:
            a,b=base.transforms[base.name_hashes.index(h)],u.transforms[u.name_hashes.index(h)]
            if math.dist(a.position,b.position)>1e-5 or abs(sum(x*y for x,y in zip(a.rotation,b.rotation)))<1-1e-5 or max(abs(x-y) for x,y in zip(a.scale,b.scale))>1e-5:
                raise ValueError('Single model variants have incompatible HD2 binds')
    projected=copy.deepcopy(original)
    for i,h in enumerate(original.name_hashes):
        if h not in base.name_hashes:raise ValueError('Model is missing an original HD2 node')
        bi=base.name_hashes.index(h);bp=base.parents[bi];op=original.parents[i]
        if (None if bp is None else base.name_hashes[bp])!=(None if op is None else original.name_hashes[op]):
            raise ValueError('Single HD2 topology differs from the original batch skeleton')
        if max(abs(a-b) for a,b in zip(original.transforms[i].scale,base.transforms[bi].scale))>1e-5:
            raise ValueError('Single animation cannot compensate changed node scale')
        if h not in bones.hashes and (math.dist(original.transforms[i].position,base.transforms[bi].position)>1e-5 or abs(sum(a*b for a,b in zip(original.transforms[i].rotation,base.transforms[bi].rotation)))<1-1e-6):
            raise ValueError('Single batch cannot change an unanimated HD2 helper local bind')
        projected.transforms[i]=copy.deepcopy(base.transforms[bi])
    for name,h in zip(bones.names,bones.hashes):
        if name not in CONTROL_MARKERS:continue
        i=original.name_hashes.index(h);a,b=original.transforms[i],projected.transforms[i]
        if math.dist(a.position,b.position)>2e-5 or abs(sum(x*y for x,y in zip(a.rotation,b.rotation)))<1-1e-6:
            raise ValueError(f'Single HD2 control marker {name} has an incompatible local bind: reimport the VPK with the control-safe converter')
        projected.transforms[i]=copy.deepcopy(a)
    for side in ('l','r'):
        for name in (side+'_elbow',side+'_hand'):
            if name not in bones.names:continue
            i=original.name_hashes.index(bones.hashes[bones.names.index(name)])
            a,b=original.transforms[i].position,projected.transforms[i].position
            length=math.sqrt(sum(v*v for v in a)*sum(v*v for v in b))
            if length<1e-10 or sum(x*y for x,y in zip(a,b))/length<1-1e-6:
                raise ValueError(f'Single HD2 arm {name} is off the native animation axis: reimport the VPK with the axis-safe converter')
    offsets,deltas=calculate_bone_offsets(projected,bones,original,bones,1e-6)
    rotations=calculate_bone_rotation_compensations(projected,bones,original,bones,1e-6)
    return offsets,deltas,rotations


def _compose_config(calibration,standard,original,bones):
    offsets,deltas,rotations=calibration;offsets=copy.deepcopy(offsets);deltas=copy.deepcopy(deltas)
    data=standard['data'];names=set(bones.names)
    required=str(data.get('filter',{}).get('required_bone','cape4'))
    if required not in names:raise ValueError('Standard required_bone is not in the single HD2 skeleton')
    distances=data.get('bone_distance_multipliers',{});rotates=data.get('bone_rotate_multipliers',{})
    if not isinstance(distances,dict) or not isinstance(rotates,dict):raise ValueError('Invalid standard multipliers')
    if (set(distances)|set(rotates))-names:raise ValueError('Single HD2 multipliers reference non-HD2 bones')
    for n in distances:
        offsets.setdefault(n,[0.,0.,0.]);deltas.setdefault(n,[0.,0.,0.])
    indices={n:original.name_hashes.index(h) for n,h in zip(bones.names,bones.hashes)}
    _validate_standard_chains(standard,len(bones.names))
    for target,chain in standard['chains'].items():
        if not set([target,*chain.chain]).issubset(names):raise ValueError('Standard IK references a missing single HD2 bone')
        r,m,h=[indices[n] for n in [*chain.chain,target]]
        if original.parents[m]!=r or original.parents[h]!=m:raise ValueError('Standard IK must be a direct two-bone HD2 chain')
    config=ModConfig(offsets,required_bone=required,distance_multipliers=dict(distances),rotate_multipliers=dict(rotates),rotation_compensations=rotations,ik_chains=copy.deepcopy(standard['chains']))
    return config,deltas


def _write_effective_config(path,config,deltas):
    if config.offsets or config.rotation_compensations:
        write_generated_config(path,config.offsets,deltas,distance_multipliers=config.distance_multipliers,rotation_compensations=config.rotation_compensations)
        text=path.read_text(encoding='utf-8').replace('required_bone = "cape4"','required_bone = '+json.dumps(config.required_bone))
    else:text='[filter]\nrequired_bone = '+json.dumps(config.required_bone)+'\n[bone_offsets]\n[bone_distance_multipliers]\n'
    for target,chain in sorted(config.ik_chains.items()):
        text+='\n[ik_chains.'+json.dumps(target)+']\nchain = '+json.dumps(chain.chain)+'\ntarget_multiplier = '+json.dumps(chain.target_multiplier)+'\n'
    if config.rotate_multipliers:
        text+='\n[bone_rotate_multipliers]\n'
        for name,value in sorted(config.rotate_multipliers.items()):text+=json.dumps(name)+' = '+repr(value)+'\n'
    path.write_text(text,encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chain_rows(config):
    return {n:dict(chain=c.chain,target_multiplier=c.target_multiplier) for n,c in sorted(config.ik_chains.items())}


def _standard_manifest(folder,certificate,units,bones,config,standard,config_sha):
    return dict(version=4,bindPolicy=BIND_POLICY,modelFingerprint='toc-and-referenced-payloads-v1',modelScale=certificate['modelScale'],
        bindSha256=hashlib.sha256((Path(folder)/'single-hd2-bind.json').read_bytes()).hexdigest(),modelFiles=_model_files(folder),
        pipelineVersion=PIPELINE_VERSION,processingProfile=PROCESSING_PROFILE,skeleton='hd2',sourceRigRetained=False,
        referenceUnit=f'0x{REFERENCE_UNIT:016x}',referenceArchive=REFERENCE_ARCHIVE,modelResources=[f'{i:016x}' for i,_ in units],
        boneCount=len(bones.names),config='single-config.toml',configSha256=config_sha,options=standard['options'],
        standardConfigPath=str(standard['path']),standardConfigSha256=standard['sha256'],ikChains=_chain_rows(config),
        preserveHandBendFrame=False,preserveSourceKeyTimes=False,preserveUnchangedBytes=True,preserveUnmodifiedChannels=False,preservePlaybackTiming=False,preserveReferencePlayback=True,playbackRevision=PLAYBACK_REVISION,frameTimePolicy=FRAME_TIME_POLICY,controlMarkerPolicy="original-hd2-local-v1",attachmentLua=False,attachmentSwap=False,configOrigin='model-bind-plus-standard-processing')


def prepare_model(folder,game_data,config_path=None):
    folder=Path(folder)
    if (folder/'source-skeleton.json').exists():raise ValueError('Single HD2 route cannot consume a dual Source rig')
    units=list(model_units(folder))
    if not units:raise ValueError('No converted HD2 model Units')
    certificate=_validate_bind(folder,units);standard=_read_standard_config(config_path)
    store=PackageStore(Path(game_data));index=ResourceIndex(store,folder/'single-resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID})
    try:
        index.load_or_build();_,entry=index.resolve(REFERENCE_UNIT,UNIT_TYPE_ID);original=UnitData.parse(entry.toc_data)
        _,entry=index.resolve(original.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(entry.toc_data)
        config,deltas=_compose_config(_derive_calibration(units,original,bones),standard,original,bones)
        digest=_write_effective_config(folder/'single-config.toml',config,deltas)
        marker=_standard_manifest(folder,certificate,units,bones,config,standard,digest)
        (folder/'single-skeleton.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding='utf-8')
        return marker
    finally:
        index.close()
        for suffix in ('','-wal','-shm'):(folder/('single-resource-index.sqlite3'+suffix)).unlink(missing_ok=True)


def build_project(folder,game_data,output,sample_count=None,threads=2,config_path=None):
    _progress('prepare',0,0,'正在校验单骨架绑定及标准IK配置')
    folder=Path(folder);output=Path(output)
    marker=json.loads((folder/'single-skeleton.json').read_text(encoding='utf-8-sig'))
    _validate_prepared_model(folder,marker)
    standard=_read_standard_config(config_path);_validate_standard_chains(standard,marker.get('boneCount'))
    if output.exists() and any(output.iterdir()):raise FileExistsError('Single animation output must be empty')
    output.mkdir(parents=True,exist_ok=True)
    store=PackageStore(Path(game_data));index=ResourceIndex(store,output/'resource-index.sqlite3',{UNIT_TYPE_ID,BONE_TYPE_ID,STATE_MACHINE_TYPE_ID,ANIMATION_TYPE_ID})
    playback=None
    report=dict(status='building',pipelineVersion=PIPELINE_VERSION,processingProfile=PROCESSING_PROFILE,skeleton='hd2',processor='anim_batch_mod.batch.build_batch_entries',
        standardConfigPath=str(standard['path']),standardConfigSha256=standard['sha256'],options=standard['options'],
        preserveHandBendFrame=False,preserveSourceKeyTimes=False,preserveUnchangedBytes=True,preserveUnmodifiedChannels=False,preservePlaybackTiming=False,preserveReferencePlayback=True,playbackRevision=PLAYBACK_REVISION,frameTimePolicy=FRAME_TIME_POLICY,controlMarkerPolicy="original-hd2-local-v1",attachmentLua=False,attachmentSwap=False,sourceRigRetained=False,
        inputModelManifestVersion=marker['version'],legacyModelConfigurationIgnored=marker['version']<4,animations=[],gameTested=False,progressProtocol='stderr-v1')
    try:
        _progress('index',0,1,'读取游戏资源索引')
        index.load_or_build(lambda done,total,label:_progress('index',done,total,f'读取游戏资源索引 {done}/{total}') if done%250==0 or done==total else None)
        _progress('index',1,1,'游戏资源索引已就绪')
        _,entry=index.resolve(REFERENCE_UNIT,UNIT_TYPE_ID);original=UnitData.parse(entry.toc_data)
        _,entry=index.resolve(original.bones_ref,BONE_TYPE_ID);bones=BonesData.parse(entry.toc_data)
        units=list(model_units(folder));config,deltas=_compose_config(_derive_calibration(units,original,bones),standard,original,bones)
        effective=output/'effective-single-config.toml';digest=_write_effective_config(effective,config,deltas)
        config=ModConfig.load(effective)
        report.update(configSha256=digest,ikChains=_chain_rows(config),boneCount=len(bones.names))
        _progress('discover',0,0,'正在收集原生单骨架动画')
        discovery=discover_batch_jobs(store,index,[REFERENCE_ARCHIVE],config,requested_unit_id=REFERENCE_UNIT,include_ik_bones=standard['options']['ik_correction'],
            progress=lambda phase,done,total,label:_progress('discover',0,0,f'正在收集单骨架动画：{label}'))
        if discovery.fatal_issues:raise ValueError('Single animation discovery failed: '+repr(discovery.fatal_issues))
        jobs=discovery.jobs;report['available_animations']=len(jobs)
        playback=NormalPlaybackReference.bundled()
        playback.validate_ids([j.animation_id for j in jobs])
        report.update(playback.report())
        if sample_count is not None:
            if not 1<=sample_count<=len(jobs):raise ValueError('Invalid sample count')
            jobs=jobs[:sample_count];report['sampleOnly']=True
        report['expected_animations']=len(jobs);report['threads']=threads;report['executor']='process' if threads>1 else 'serial'
        _progress('animation',0,len(jobs),f'单骨架动画 0/{len(jobs)}')
        def progress(phase,done,total,label):_progress(phase,done,total,f'单骨架动画 {done}/{total}')
        o=standard['options']
        # The template overrides these native sparse/timing switches for normal
        # clips. Keep them enabled for the accepted additive byte-passthrough path.
        build=build_batch_entries(index,jobs,config,allow_additive=o['allow_additive'],progress=progress,apply_rotate_multipliers=o['rotate_multipliers'],
            apply_rotation_compensations=o['rotation_compensation'],apply_ik_correction=o['ik_correction'],add_unit=False,threads=threads,use_processes=True,
            preserve_hand_bend_frame=False,preserve_source_key_times=True,preserve_unmodified_channels=True,source_arm_constraints=o['source_arm_constraints'],preserve_playback_timing=True,preserve_unchanged_bytes=True,playback_reference_loader=playback.read)
        if build.fatal_issues or len(build.animations)!=len(jobs):raise ValueError('Incomplete single batch build: '+repr(build.fatal_issues))
        _progress('package',0,0,'正在写入单骨架动画包')
        staging=output/'runtime-incomplete';staging.mkdir()
        paths=write_output_patch(store,SimpleNamespace(output=staging,patch_index=2,force=False),build.entries)
        _progress('verify',0,0,'正在校验单骨架动画包')
        ids=[r.animation_id for r in build.animations];verify_patch(paths[0],ids)
        counts={struct.unpack_from('<I',e.toc_data,4)[0] for e in build.entries if e.type_id==ANIMATION_TYPE_ID}
        if counts!={len(bones.names)}:raise ValueError('Single batch changed HD2 channel count')
        (staging/'single-config.toml').write_bytes(effective.read_bytes());(staging/'standard-input.toml').write_bytes(standard['raw'])
        certificate=json.loads((folder/'single-hd2-bind.json').read_text(encoding='utf-8-sig'))
        runtime_marker=_standard_manifest(folder,certificate,units,bones,config,standard,digest)
        runtime_marker.update(playback.report())
        runtime_marker.update(inputModelManifestVersion=marker['version'],inputModelConfigSha256=marker.get('configSha256'),legacyModelConfigurationIgnored=marker['version']<4)
        (staging/'single-skeleton.json').write_text(json.dumps(runtime_marker,ensure_ascii=False,indent=2),encoding='utf-8')
        staging.rename(output/'runtime')
        report.update(status='complete',armTargetProjections=sum(r.modification.arm_target_projections for r in build.animations),
            armRequestedTargetMaxDistance=max((r.modification.arm_requested_target_max_distance for r in build.animations),default=0),
            armTargetPolicy='source-angle-standard-ray-v1' if o['source_arm_constraints'] else 'legacy-world',ikEvaluations=sum(r.modification.ik_evaluations for r in build.animations),ikCorrections=sum(r.modification.ik_corrections for r in build.animations),
            ikMaxErrorBefore=max((r.modification.ik_max_error_before for r in build.animations),default=0),ikMaxErrorAfter=max((r.modification.ik_max_error_after for r in build.animations),default=0),
            animations=[dict(id=f'{i:016x}') for i in ids],files=[dict(name=p.name,sha256=hashlib.sha256((output/'runtime'/p.name).read_bytes()).hexdigest()) for p in paths])
        return report
    except BaseException as error:
        report.update(status='failed',error=str(error));raise
    finally:
        if playback is not None:playback.archive.close()
        index.close();(output/'build-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if report['status']=='complete':_progress('complete',1,1,'单骨架动画打包完成')


def main(argv=None):
    p=argparse.ArgumentParser(description='Standard anim_batch_mod single HD2 skeleton packaging')
    p.add_argument('action',choices=['prepare-model','build']);p.add_argument('--model-directory',required=True,type=Path)
    p.add_argument('--game-data',required=True,type=Path);p.add_argument('--config',type=Path);p.add_argument('--output',type=Path);p.add_argument('--sample-count',type=int)
    p.add_argument('--threads',type=parse_thread_count,default=2)
    a=p.parse_args(argv)
    if a.action=='prepare-model':report=prepare_model(a.model_directory,a.game_data,a.config)
    else:
        if a.output is None:p.error('build requires --output')
        report=build_project(a.model_directory,a.game_data,a.output,a.sample_count,a.threads,config_path=a.config)
    print(json.dumps(report,ensure_ascii=False));return 0
