"""Build opt-in three-line Lua TEST/DETAILED packages. Never installs or deploys.
Uses existing model-specific B23 profile/Avatar companion and shared runtime.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,math,sqlite3,struct,sys,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]))
sys.path.insert(0,str(ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'))
import lz4
sys.modules['utils.lz4_311']=lz4
from lupa.lua51 import LuaRuntime
from prepare_native_v31_b23 import compose_source,matrices,lua
from anim_batch_mod.archive import TocArchive
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from anim_batch_mod.processor import _calculate_world_transforms
from anim_batch_mod.math3d import quat_rotate,quat_inverse
from anim_batch_mod.native_skeleton import bone_name_hash
import survey_native_weapon_grips as survey
VERSION='1.0.18-test.detailed.7'
DEFAULT_OUTPUT=ROOT/'outputs/grip-rollback-ragdoll-test-20261108-v7'
BEACON='16f397ca5f51f271'
STOCK=('027dec442cc26a90','0b882808c6f498e8','9eb160830321bfd6')
def sha(data):return hashlib.sha256(data).hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def resources(p):
    with Path(p).open('rb') as f:
        h=f.read(72);nt,n=struct.unpack_from('<II',h,4);f.seek(72+nt*32)
        rows=[struct.unpack('<QQQQQQQIIIIII',f.read(80)) for _ in range(n)]
        out=[]
        for r in rows:
            if r[1] not in (UNIT_TYPE_ID,BONE_TYPE_ID):continue
            f.seek(r[2]);out.append((r[0],r[1],f.read(r[7])))
        return out

def component_inventory(manager,weapon_ids):
    survey.INDEX=manager/'data/indexes/asset-index.sqlite'
    s=survey.Survey();specs={};fixtures={};provenance={};seen=set()
    try:
        for rid in sorted(weapon_ids):
            for aid in s.unit_archives.get(int(rid,16),[])[:1]:
                if aid in seen:continue
                seen.add(aid);a=s.archive(aid)
                for e in a.entries.values():
                    if e.type_id!=UNIT_TYPE_ID:continue
                    u=UnitData.parse(e.toc_data);id=f'{e.file_id:016x}'
                    fixtures[id]=dict(resource=id,count=len(u.parents),hashes=u.name_hashes,parents=u.parents,matrices=matrices(u))
                    idx={n:u.name_hashes.index(bone_name_hash(n)) for n in ('skeleton','game_mesh','IK_right','IK_left','bullet_01','attach_offset','laser','muzzle','boss','root') if bone_name_hash(n) in u.name_hashes}
                    if not (3<=len(u.parents)<=192 and 'skeleton' in idx and 'game_mesh' in idx) or 'IK_right' in idx or 'IK_left' in idx:continue
                    marker=next((n for n in ('bullet_01','attach_offset','laser','muzzle') if n in idx),None)
                    # Only verified component signatures, never arbitrary scene Units.
                    if not marker:continue
                    kind={'bullet_01':'weapon_magazine','attach_offset':'weapon_optic','laser':'weapon_underbarrel','muzzle':'weapon_muzzle'}[marker]
                    names=['skeleton','game_mesh',marker]
                    # Include the internal root/boss chain; native external links stay read-only.
                    for n in ('root','boss'):
                        if n in idx:names.append(n)
                    nodes=[dict(name=n,index=idx[n],parent=u.parents[idx[n]],hash=bone_name_hash(n)) for n in names]
                    spec=dict(kind=kind,resource=id,count=len(u.parents),nodes=nodes,root=idx['skeleton'],order=1,verifiedComponent=True)
                    if id in specs:assert specs[id]==spec
                    specs[id]=spec;provenance[id]=dict(archive=aid,weapon=rid,sourceUnitSha256=sha(e.toc_data))
    finally:s.db.close()
    return specs,fixtures,provenance

def contact_rows(manager,name,profile):
    md=manager/f'test-library/[原比例模型]{name}/vpk2patch'
    m=load(md/'source-skeleton.json')
    sr=resources(md/'9ba626afa44a3aa3.patch_0');s=UnitData.parse(next(d for _,t,d in sr if t==UNIT_TYPE_ID))
    nr=resources(manager/f'test-library/[原比例混合动画]({name})/9ba626afa44a3aa3.patch_0')
    n=UnitData.parse(next(d for _,t,d in nr if t==UNIT_TYPE_ID));b=BonesData.parse(next(d for _,t,d in nr if t==BONE_TYPE_ID))
    sw=_calculate_world_transforms(s.transforms,s.parents);nw=_calculate_world_transforms(n.transforms,n.parents)
    si={x['driver']:s.name_hashes.index(x['hash']) for x in m['bones'] if x['driver']}
    ni={name:n.name_hashes.index(h) for name,h in zip(b.names,b.hashes) if h in n.name_hashes}
    contacts={}
    for side,label in [('l','left'),('r','right')]:
        def point(w,idx):
            h=idx[side+'_hand'];points=[]
            for finger in ('index','middle'):
                i=idx[f'{side}_{finger}_finger1'];points.append(quat_rotate(quat_inverse(w[h].rotation),[w[i].position[j]-w[h].position[j] for j in range(3)]))
            return [sum(v[j] for v in points)/len(points) for j in range(3)]
        contacts[label]=dict(native=point(nw,ni),source=point(sw,si),units='metres_already_model_scaled',quality='skeleton_proxy_not_mesh_surface')
    ar=resources(manager/f'test-library/[骨骼挂点修正]{name}/9ba626afa44a3aa3.patch_1')
    avatar=UnitData.parse(next(d for _,t,d in ar if t==UNIT_TYPE_ID));byhash={h:i for i,h in enumerate(avatar.name_hashes)}
    probes=[]
    for x in m['bones']:
        if x['driver'] in ('l_hand','r_hand','l_elbow','r_elbow') or 'handtwist' in x['name'].lower() or 'wrist' in x.get('sourceName','').lower():
            i=byhash[x['hash']];probes.append(dict(name=x['name'],index=i,parent=avatar.parents[i],hash=x['hash']))
    return contacts,probes

SG225=('46183b50961d1328','6228d0242bde56b6','c12a34f375bd5a87')
SG225_EXTRA={'3ddb9d36da22555d':'weapon_magazine','68b8d040421e8a49':'weapon_magazine','b7cd78c71e0a48ed':'weapon_rigid_part'}
SG225_MUZZLES=('cdf733b0106a23c3','8cd335a5f711bb59','d8cf7fe059b4bf1e')
def add_sg225_components(specs,fixtures,provenance):
    for rid,kind in SG225_EXTRA.items():
        f=fixtures[rid];names=[]
        for name in ('StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','game_mesh','collision','shells_drum','spindle','follower','shell_breach'):
            h=bone_name_hash(name)
            if h in f['hashes']:
                i=f['hashes'].index(h);names.append(dict(name=name,index=i,parent=f['parents'][i],hash=h))
        idx={n['name']:n['index'] for n in names}
        assert 'game_mesh' in idx
        specs[rid]=dict(kind=kind,resource=rid,count=f['count'],nodes=names,
            root=idx.get('skeleton',idx['game_mesh']),order=1,verifiedComponent=True,repairFamily='SG225')
        provenance[rid]=dict(source='verified SG225/SG225SP/SG225IE shared-archive Unit',reason='magazines lack bullet_01; rigid piece lacks skeleton/pivot',roleConfirmed=kind!='weapon_rigid_part')
    for rid in SG225_MUZZLES:
        assert rid in specs;specs[rid]['repairFamily']='SG225'

RELOAD_WEAPONS=('2152d5147b0ac418','8645f167b3c813a2','c85f576d5e086147','27ee1ed8f6fb6356','295beb26dc4f8ff1','7e3145a5baa4b948')
RELOAD_PARTS={'b7cd35e0edc15cd7':'hmg_belt_box','e3541de70b7ec1c0':'laser_battery_medium','50cd7e9f909fe5a1':'laser_heatsink','6600b5e755a21f1f':'laser_heatsink','80e8335ab4042fcf':'laser_reload_module','d44c25420aa3e2ff':'laser_reload_module'}
def add_reload_components(specs,fixtures,provenance):
    for rid,role in RELOAD_PARTS.items():
        f=fixtures[rid];nodes=[]
        for name in ('StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','root','boss','game_mesh','g_mag','belt_01','belt_08','bullet_01'):
            h=bone_name_hash(name)
            if h in f['hashes']:
                i=f['hashes'].index(h);nodes.append(dict(name=name,index=i,parent=f['parents'][i],hash=h))
        idx={n['name']:n['index'] for n in nodes};assert 'game_mesh' in idx
        specs[rid]=dict(kind='weapon_magazine',resource=rid,count=f['count'],nodes=nodes,
            root=idx.get('root',idx.get('skeleton',idx['game_mesh'])),order=1,verifiedComponent=True,
            repairFamily='HMG_LAS',componentRole=role)
        provenance[rid]=dict(source='verified handheld HMG/laser weapon archive Unit',reason='reload component may lack skeleton/pivot/bullet_01; use exact layout',role=role)

def beacon_configuration(fixture):
    assert fixture['count']==37
    names=('StingrayEntityRoot','FbxAxisSystem_ConvertNode','locator_beacon','skeleton','root','boss','game_mesh')
    nodes=[]
    for name in names:
        h=bone_name_hash(name);i=fixture['hashes'].index(h)
        nodes.append(dict(name=name,index=i,parent=fixture['parents'][i],hash=h))
    link=next(n for n in nodes if n['name']=='skeleton')
    probe=copy.deepcopy(nodes)
    for i in (35,36):probe.append(dict(name=f'raw_hash_{fixture["hashes"][i]:08x}',index=i,hash=fixture['hashes'][i]))
    policy=dict(enabled=True,resource=BEACON,count=37,linkNode=link,linkMetres=.04,linkDegrees=15,
        probeNodes=probe,policy='native_path_custom_hand_only',neverWriteBeaconOrEffects=True)
    spec=dict(kind='held_beacon',resource=BEACON,count=37,nodes=nodes,root=link['index'],order=2,verifiedComponent=True)
    return policy,spec

def prepare_profile(profile,contacts,probes,specs,name,lines=None):
    p=copy.deepcopy(profile);lines=lines or dict(handContact=True,stockPolicy=True,components=True)
    p['testRepairs']=dict(enabled=True,version=VERSION,modelLabel=name,lines=lines,contacts=contacts,poseProbes=probes,
        anchorKind='knuckle-contact-proxy',maxReachCorrection=.025,notProduction=True)
    p['variant']+='-TEST-DETAILED-THREE-LINES';p['packageName']=f'{name}-握持回退与布娃娃骨图排查-测试用详细日志-{VERSION}.zip'
    p['logging']=dict(compact=False,detailed=True,recordSeconds=3600,maxBytes=536870912,segmentBytes=16777216,exceptionIntervalSeconds=.25)
    p['logSeconds']=.25;p['maxRecords']=1000000
    p['sidearmDiagnostics']=dict(p.get('sidearmDiagnostics',{}),enabled=True,intervalSeconds=.25,maxSamplesPerPath=20000,
        resources={rid:True for rid in p['leftGrip']['weaponTargets']})
    if lines['stockPolicy']:
        for id in STOCK:
            if id in p['leftGrip']['weaponTargets']:p['leftGrip']['weaponTargets'][id]['leftPolicy']='always'
    if lines['components']:
        for id,spec in specs.items():p['allowedConsumers'][id]=True;p['consumers'][id]=copy.deepcopy(spec)
    return p

def build(manager,out,name,specs,fixtures,provenance,lines):
    base=manager/f'test-library/[骨骼挂点修正]{name}'
    original=load(base/'attachment-profile.json');contacts,probes=contact_rows(manager,name,original)
    p=prepare_profile(original,contacts,probes,specs,name,lines)
    beacon,beacon_spec=beacon_configuration(fixtures[BEACON])
    p['testRepairs']['beacon']=beacon
    p['testRepairs']['logTag']='ROLLBACK_RAGDOLL_V7'
    p['testRepairs']['reloadParts']=dict(enabled=lines['components'],families=list(RELOAD_WEAPONS),resources=list(RELOAD_PARTS))
    p['testRepairs']['sg225Parts']=dict(enabled=lines['components'],families=list(SG225),extraResources=list(SG225_EXTRA),muzzleResources=list(SG225_MUZZLES))
    p['testRepairs']['aimDiagnostics']=dict(enabled=True,intervalSeconds=.05,readOnly=True)
    avatar=UnitData.parse(next(d for _,t,d in resources(base/'9ba626afa44a3aa3.patch_1') if t==UNIT_TYPE_ID))
    byhash={h:i for i,h in enumerate(avatar.name_hashes)}
    aims={}
    for key,name0 in [('nativeLeftRoot','l_shoulder'),('nativeRightRoot','r_shoulder'),('nativeLeftClavicle','l_clavicle'),('nativeRightClavicle','r_clavicle'),('weaponAim','weapon_aim'),('nativeSpine2','spine2'),('nativeChest','chest')]:
        h=bone_name_hash(name0);i=byhash[h];aims[key]=dict(name=name0,index=i,parent=avatar.parents[i],hash=h)
    for side,key in [('left','Left'),('right','Right')]:
        c=p[side+'Grip'];aims['source'+key+'Parent']=copy.deepcopy(c['nodes'][0]);aims['source'+key+'RootRef']=copy.deepcopy(c['nodes'][1]);aims['source'+key+'RootOutput']=copy.deepcopy(c['outputs'][0])
    p['testRepairs']['aimNodes']=aims
    p['testRepairs']['poseProbes']+=list(aims.values())
    # Only observe the exact P/40-K; do not change hand position/orientation authority.
    source_meta=load(manager/f'test-library/[原比例模型]{name}/vpk2patch/source-skeleton.json')
    source_by_driver={x['driver']:x for x in source_meta['bones'] if x.get('driver')}
    def tracking_node(node_name,node_hash):
        i=avatar.name_hashes.index(node_hash)
        return dict(name=node_name,hash=node_hash,index=i,parent=avatar.parents[i])
    actor_nodes={};source_tracking=[]
    for key,driver in [('Hand','r_hand'),('Elbow','r_elbow'),('IndexBase','r_index_finger1'),('MiddleBase','r_middle_finger1'),('ThumbBase','r_thumb_finger1')]:
        x=source_by_driver[driver];node=tracking_node(x['name'],x['hash'])
        actor_nodes['source'+key]=node;source_tracking.append(node)
        actor_nodes['native'+key]=tracking_node(driver,bone_name_hash(driver))
    actor_nodes['sourceHandReference']=copy.deepcopy(p['rightGrip']['nodes'][3])
    actor_nodes['nativeHandTwist']=tracking_node('r_hand_twist',bone_name_hash('r_hand_twist'))
    for j,node in enumerate(probes):
        if 'handtwist_r' in node['name'].lower() or ('wrist' in node['name'].lower() and '_r' in node['name'].lower()):
            actor_nodes['sourceWristAux'+str(j)]=copy.deepcopy(node);source_tracking.append(node)
    p['testRepairs']['gripTracking']=dict(enabled=True,readOnly=True,intervalSeconds=.10,
        resources={'dbb6c961c59fadc1':True},actorNodes=actor_nodes,
        stages=['final_output','next_render_input'],solverUnchangedFromV4=True,
        skinSurfaceObserved=False)

    p['testRepairs']['reverseExperimentRemoved']=True
    p['testRepairs']['bodyDiagnostics']=dict(enabled=True,intervalSeconds=.25,
        bypassNoAnimationStateMachine=True,requireObservedStateMachinePresent=True,readOnly=True,ragdollStateDirectlyObserved=False,
        skinStages=['next_render_input','final_output','inactive_after_restore','native_only_observer'],
        maxUnownedModels=6,unownedProbeRadius=4,
        pairs=copy.deepcopy([pair for pair in p['sync']['pairs'] if '_finger' not in pair['name']]),
        stages=['update_input','next_render_input','before_write','after_body_sync','final_output','inactive_after_restore','native_only_observer'])
    bone_rows=resources(base/'9ba626afa44a3aa3.patch_1')
    bones=BonesData.parse(next(data for _,typ,data in bone_rows if typ==BONE_TYPE_ID))
    names_by_hash=dict(zip(bones.hashes,bones.names));names_by_hash.update({x['hash']:x['name'] for x in source_meta['bones']})
    skin_audit_root=ROOT/'outputs/grip-ragdoll-followup-20261108'
    skin_rows={}
    for part in ('vpk','overwrite'):
        for row in load(skin_audit_root/f'{name}-skin-{part}.json')['rows']:skin_rows[row['resource']]=row['weightedNodes']
    p['variant']+='-ROLLBACK-RAGDOLL-V7'
    p['allowedConsumers'][BEACON]=True;p['consumers'][BEACON]=beacon_spec
    p['sidearmDiagnostics']['resources'][BEACON]=True
    model_units={}
    for part in ('vpk2patch','Overwrite'):
        for file in (manager/f'test-library/[原比例模型]{name}'/part).glob('*.patch_*'):
            if not file.suffix.rsplit('_',1)[-1].isdigit():continue
            for rid,typ,data in resources(file):
                if typ==UNIT_TYPE_ID:model_units[f'{rid:016x}']=UnitData.parse(data)
    for rid,spec in p['models'].items():
        u=model_units[rid];nodes=[]
        for probe in probes:
            if 'handtwist' not in probe['name'].lower() and 'wrist' not in probe['name'].lower():continue
            i=u.name_hashes.index(probe['hash'])
            nodes.append(dict(name=probe['name'],hash=probe['hash'],index=i,parent=u.parents[i]))
        spec['testWristProbes']=nodes
        spec['testSkinProbes']=[]
        for row in skin_rows[rid]:
            assert u.name_hashes[row['index']]==row['hash']
            node_name=names_by_hash[row['hash']]
            spec['testSkinProbes'].append(dict(name=node_name,hash=row['hash'],index=row['index'],
                parent=u.parents[row['index']],weightedVertices=row['weightedVertices'],
                avatarSameHashAvailable=row['hash'] in avatar.name_hashes,
                kind='model_physics_bone' if '_phys_' in node_name else 'weighted_skeleton_node'))
        spec['testGripProbes']=[]
        for probe in source_tracking:
            i=u.name_hashes.index(probe['hash'])
            spec['testGripProbes'].append(dict(name=probe['name'],hash=probe['hash'],index=i,parent=u.parents[i]))

    folder=out/name;folder.mkdir(parents=True,exist_ok=True)
    code=compose_source(p);assert '-- INSERT ' not in code
    ok,error=LuaRuntime().eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(code);assert ok,error
    body=code.encode('utf-8');raw=(base/'9ba626afa44a3aa3.patch_0').read_bytes();header=raw[:192]
    assert struct.unpack_from('<I',header)[0]==0xf0000011 and struct.unpack_from('<Q',header,120)[0]==192
    payload=struct.pack('<II',len(body),2)+body;patch=bytearray(header)+payload;patch.extend(bytes(-len(patch)%16))
    struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
    parsed=TocArchive.parse_parts(patch,load_external_data=False);assert len(parsed.entries)==1
    assert bytes(next(iter(parsed.entries.values())).toc_data)==payload
    manifest=load(base/'manifest.json');manifest.update(Guid=str(uuid.uuid4()),Name=f'[测试用·详细日志·握持回退与布娃娃骨图排查]{name}',
        Description=f'TEST ONLY / DETAILED LOG {VERSION}. 撤回V6原生右臂对齐，恢复V4握持；只读全身/实际蒙皮骨/动画状态/帧交接诊断，未宣称布娃娃拉伸已修复；SG225配件覆盖/缓存修复；只读瞄准同步排查，不宣称高度修好；保留已验收朝向及战备球、原模型/动画/VRD。日志4Hz完整矩阵及10Hz枪坐标/手指/模型双阶段观测，1小时/512MiB上限，16MiB分段。不可与原挂点包同时启用。')
    note=f'''# {name} P/40-K俯仰握持排查【测试用 / 详细日志版】\n\n版本：{VERSION}。回退与诊断版：V6原生右臂对齐已移除，恢复V4握持；新增全身关键骨、实际蒙皮骨和动画状态分阶段观测；没有全局缩放或物理改写，布娃娃拉伸未宣称修复。\n\n三线开关：{json.dumps(lines,ensure_ascii=False)}\n1. 左右手：骨架掌心代理校准，手腕朝向取同一avatar原生post-IK手；左手重定基到最终枪握点。不是网格掌面拟合。\n2. P-44/P-35/GP-20按双手持握代理处理，换弹/收枪仍有原生接触门禁。\n3. 真实弹匣/瞄具等图签名覆盖与枪→配件刷新，含AR-61标准弹匣89cce4d15db88aa8；不写配件local、不重挂。\n4. 保留已验收战备球修复。追加SG225无bullet_01弹匣和已核对的刚性部件；缓存根远但网格近时允许受限刷新。新增20Hz相机/肩根/锁骨只读同步日志；本版不盲改手臂长度或已正确右手方向。追加重机枪弹链箱、激光电池/散热器的精确布局与多锚点缓存刷新；新增最终接触日志，补偿前后误差分开。\n\n只使用与本模型名称匹配的一个测试包。保留同模型【原比例模型】、【原比例混合动画】及原物理包。停用原【骨骼挂点修正】和其它同名测试挂点包，再导入本ZIP并启用；按原配套顺序置于模型/动画后。完全重启游戏。不要同时启用test01与test06挂点。\n\n日志：%APPDATA%\\Arrowhead\\Helldivers2\\hd2_grip_TEST_DETAILED_{name}_ROLLBACK_RAGDOLL_V7_日期时间.partNN.log。保留所有part。不会覆盖hd2_grip_b23_compact.log。完整矩阵约4Hz；新增枪坐标、指根和模型双阶段约10Hz，最多1小时/512MiB，每16MiB分段；达到上限只停记录，不停握持。测试版会增加CPU/磁盘开销。\n\n检查加载版本{VERSION}，日志行含TEST_ONLY_DETAILED、testOnly=true。记录before_write、after_right_ik、after_mount_refresh、final_output、左右接触误差、程序腕骨节点/可见模型姿态、配件原生父级/刷新阶段。GPU skin矩阵与VRD内部状态未直接观测，不伪称通过。\n\n重点：P/40-K依次左右转动、仅上下转动、单持和双手瞄准、换弹切枪；同帧test_grip_tracking_probe含IK_right/腕/指根/模型与相机。两阶段为final_output和next_render_input，仍未读取GPU皮肤矩阵。本版撤回原生右臂写入；新增test_body_lifecycle_probe与test_actor_lifecycle；记录update_input/next_render_input/before_write/after_body_sync/final_output；已观测有动画状态机后确认丢失时仅恢复旧写入，不继续握持/上身驱动；临时布娃娃状态仍待日志证实；保留其它武器与所有已验收修复。回滚：停用本测试包、启用原挂点包并重启游戏；模型/动画/物理无需替换。\n'''
    artifact={};companions={}
    zipname=p['packageName']
    with zipfile.ZipFile(out/zipname,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('9ba626afa44a3aa3.patch_0',patch)
        for suffix in ('.gpu_resources','.stream'):z.writestr('9ba626afa44a3aa3.patch_0'+suffix,b'')
        for suffix in ('','.gpu_resources','.stream'):
            file='9ba626afa44a3aa3.patch_1'+suffix;data=(base/file).read_bytes();companions[file]=sha(data);z.writestr(file,data);(folder/file).write_bytes(data)
        z.writestr('attachment-profile.json',json.dumps(p,ensure_ascii=False,indent=2))
        z.writestr('attachment-fix.json',(base/'attachment-fix.json').read_bytes())
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2));z.writestr('测试用详细日志版说明.md',note)
    with zipfile.ZipFile(out/zipname) as z:
        assert z.testzip() is None
        for file,h in companions.items():assert sha(z.read(file))==h
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'测试说明.md').write_text(note,encoding='utf-8')
    (folder/'hd2attachmentfix-B23.lua').write_bytes(body);(folder/'B23-profile.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'container-header.bin').write_bytes(header)
    (folder/'native-parenting.json').write_text(json.dumps(dict(files=[dict(name=n,sha256=h) for n,h in companions.items()]),indent=2),encoding='utf-8')
    (folder/'测试用详细日志版说明.md').write_text(note,encoding='utf-8')
    artifact=dict(model=name,package=str(out/zipname),sha256=sha((out/zipname).read_bytes()),luaSha256=sha(body),avatarNodes=p['avatar']['count'],models=len(p['models']),companionHashes=companions,testVersion=VERSION,
        newComponents=len(specs),repairLines=lines,gameTested=False,gameDeployed=False)
    (folder/'package-validation.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    return artifact

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manager-root',type=Path,default=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7')
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    parser.add_argument('--models',nargs='+',default=['test01','test06'])
    for n in ('contact','stock','components'):parser.add_argument('--no-'+n,action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    ids=set()
    for name in args.models:ids.update(load(args.manager_root/f'test-library/[骨骼挂点修正]{name}/attachment-profile.json')['leftGrip']['weaponTargets'])
    ids.add(BEACON)
    ids.update(RELOAD_WEAPONS)
    specs,fixtures,provenance=component_inventory(args.manager_root,ids)
    add_sg225_components(specs,fixtures,provenance)
    add_reload_components(specs,fixtures,provenance)
    (args.output/'verified-component-specs.json').write_text(json.dumps(specs,indent=2),encoding='utf-8')
    (args.output/'equipment-fixtures.json').write_text(json.dumps(fixtures,indent=2),encoding='utf-8')
    (args.output/'component-provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    lines=dict(handContact=not args.no_contact,stockPolicy=not args.no_stock,components=not args.no_components)
    results=[build(args.manager_root,args.output,name,specs,fixtures,provenance,lines) for name in args.models]
    (args.output/'build-report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False,indent=2))
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
