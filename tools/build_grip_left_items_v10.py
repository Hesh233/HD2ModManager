"""Isolated V10 left-held and carried-equipment test builder; no deployment."""
from pathlib import Path
import sys,json,copy,uuid,struct,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_detailed_grip_test as b
import survey_native_weapon_grips as sv
from anim_batch_mod.formats import UnitData,BonesData
from anim_batch_mod.constants import UNIT_TYPE_ID,BONE_TYPE_ID
from prepare_native_v31_b23 import compose_source
from lupa.lua51 import LuaRuntime
VERSION='1.0.18-test.items.10';OUT=ROOT/'outputs/grip-left-items-test-20261109-v10';BASE=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';ANALYSIS=ROOT/'outputs/grip-left-items-analysis-20261109'
REVISION=10
TAG='LEFT_ITEMS_V10'
def configure_revision(revision):
 global REVISION,VERSION,OUT,TAG
 assert revision in (10,11,12)
 REVISION=revision;VERSION=f'1.0.18-test.items.{revision}';TAG=f'LEFT_ITEMS_V{revision}'
 OUT=ROOT/'outputs/grip-left-items-test-20261109-v10'
 if revision>=11:OUT=OUT/f'v{revision}'
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
V12_MELEE={'792d5d2a340fd6e6':'Machete','e3b6aedd07fcb464':'Stun Lance','5f3ec9bda2bd8553':'Breaching Hammer','b0f1b354ba1d38d8':'One True Flag'}
V12_EXACT=set(V12_MELEE)|{'1a437158e1b8d2a1','005c2262f672caf4','03e67a19b07c6523','07d605bd50c98461','2e9d0bdc48b09e60','503c0e01fbafa86a'}
def inventory():
 old=ROOT/'outputs/grip-equipment-perf-test-20261108-v9';fixtures=b.load(old/'equipment-fixtures.json');specs=b.load(old/'verified-component-specs.json');prov=b.load(old/'component-provenance.json')
 raw=b.load(ANALYSIS/'v10-equipment-fixtures.json');meta=b.load(ANALYSIS/'archive-inventory.json');fixtures.update(raw)
 sv.INDEX=BASE/'data/indexes/asset-index.sqlite';q=sv.Survey();names=dict(q.bone_names);wanted=set(b.load(old/'test06/B23-profile.json')['gripFixes']['sidearms'])|{'43b2d7766120203b','8a307bd1811a5fe9','94bd931b5fb4ee95','d54b9505c0f72873','6cfcc7f8801a0266','25aa2fd4643cf4ee'};candidates={}
 if REVISION>=12:wanted.update(V12_EXACT)
 for rid in wanted:
  for aid in q.unit_archives.get(int(rid,16),[])[:1]:
   ar=q.archive(aid)
   shared=sum(e.type_id==UNIT_TYPE_ID for e in ar.entries.values())>40
   for e in ar.entries.values():
    if e.type_id==BONE_TYPE_ID:
     try:bn=BonesData.parse(e.toc_data);names.update(zip(bn.hashes,bn.names))
     except Exception:pass
   for e in ar.entries.values():
    if e.type_id!=UNIT_TYPE_ID:continue
    id=f'{e.file_id:016x}'
    if shared and id!=rid:continue
    u=UnitData.parse(e.toc_data);fixtures[id]=dict(resource=id,count=len(u.parents),hashes=u.name_hashes,parents=u.parents,matrices=b.matrices(u))
    ns={names.get(h):i for i,h in enumerate(u.name_hashes) if h in names}
    if 'game_mesh' not in ns or len(u.parents)>60 or any(n in ns for n in ('l_hand','r_hand','hips','spine1')):continue
    if id==rid or ('IK_right' not in ns and ('IK_left' not in ns or id=='72fe4b13f726c344')):
     if REVISION<12 or rid not in V12_EXACT or id in V12_EXACT or id in specs:candidates[id]=str(aid)
 q.db.close()
 # Keep only exact original equipment identities; no world props or thrown projectile whitelist.
 for id in ['819ec78bcaf69c49','612f7f6193fb1b2b','076692fd83a83c5c','48fd06b465e8b681','16051937941bb709','7b153e02ad22d12c','72fe4b13f726c344','d5cb9b5401b261f9','1b1fcc0e025c1f7d','7372947782b91123','c891acf9e8dbda97','5f4b129d947d79d7','6e165f05a49233f6','1ec5f54265a91c83']:
  candidates.setdefault(id,meta['units'][id]['archive'])
 def make(id,kind=None):
  f=fixtures[id];available={b.bone_name_hash(n):n for n in ['StingrayEntityRoot','FbxAxisSystem_ConvertNode','skeleton','root','boss','game_mesh','IK_left','IK_right','bullet_01','g_mag','muzzle','laser','attach_offset','pivot','shadow_mesh','attach_mag','attach_ammo','attach_underbarrel','attach_muzzle','attach_optic']}
  nodes=[dict(name=available[h],index=i,parent=f['parents'][i]) for i,h in enumerate(f['hashes']) if h in available];n={v['name']:v['index'] for v in nodes}
  root=n.get('skeleton',n.get('root',n.get('game_mesh')))
  # Unknown external root indices are verified via named child parent relationships, not raw hash API calls.
  external=f['parents'][n['game_mesh']]
  roots=[]
  if external is not None and external>=2:roots.append(external)
  for name in ('skeleton','root','boss','game_mesh','pivot'):
   if name in n and n[name] not in roots:roots.append(n[name])
  eligible=(REVISION>=12 and id=='503c0e01fbafa86a') or id in {'819ec78bcaf69c49','612f7f6193fb1b2b','076692fd83a83c5c','48fd06b465e8b681','d5cb9b5401b261f9','c891acf9e8dbda97','5f4b129d947d79d7'} or 'bullet_01' in n or 'g_mag' in n
  if id in specs:
   spec=specs[id];spec['heldRoots']=roots;spec['leftHeldEligible']=eligible
   return spec
  kind=kind or ('weapon' if 'IK_right' in n else 'weapon_grip' if 'IK_left' in n else 'weapon_magazine' if eligible else 'weapon_component')
  spec=dict(kind=kind,resource=id,count=f['count'],nodes=nodes,root=root,heldRoots=roots,order=0 if kind=='weapon' else 1 if kind=='weapon_grip' else 2,verifiedComponent=True,repairFamily='EQUIPMENT_V10',leftHeldEligible=eligible)
  specs[id]=spec;return spec
 for id,archive in candidates.items():
  make(id);prov[id]=dict(source='read-only original weapon archive',archive=archive,repair='exact carried component / alternate graph anchor')
 throwables=meta['throwables']
 for id in throwables:make(id,'held_throwable')['leftHeldEligible']=True
 make(b.BEACON)['leftHeldEligible']=True
 # The Stoker linked subweapon must update before its magazine/muzzle consumers.
 specs['72fe4b13f726c344']['order']=1
 if REVISION>=11:
  # V10's existing-spec early return left the Reprimand muzzle outside the new anchor fallback.
  specs['16051937941bb709']['repairFamily']='EQUIPMENT_V10'
 if REVISION>=12:
  for rid,spec in specs.items():
   if spec['kind']=='weapon_magazine':
    f=fixtures[rid];assert f['hashes'][0]==b.bone_name_hash('StingrayEntityRoot') and f['parents'][0] is None
    for name,index in (('StingrayEntityRoot',0),('FbxAxisSystem_ConvertNode',1)):
     assert f['hashes'][index]==b.bone_name_hash(name)
     if not any(n['index']==index for n in spec['nodes']):spec['nodes'].append(dict(name=name,index=index,parent=f['parents'][index]))
    spec['heldRoots']=[0]+[i for i in spec.get('heldRoots',[spec['root']]) if i!=0];spec['leftHeldEligible']=True
  for rid in V12_MELEE:
   spec=specs[rid];spec.update(kind='weapon',order=0,verifiedComponent=True,repairFamily='MELEE_V12',leftHeldEligible=False)
   if 0 not in spec['heldRoots']:spec['heldRoots'].insert(0,0)
  specs['503c0e01fbafa86a'].update(kind='weapon_magazine',verifiedComponent=True,repairFamily='EQUIPMENT_V10',leftHeldEligible=True)
 return specs,fixtures,prov,throwables

def main():
 OUT.mkdir(parents=True,exist_ok=True);specs,fixtures,prov,throws=inventory();b.VERSION=VERSION
 save(OUT/'verified-component-specs.json',specs);save(OUT/'equipment-fixtures.json',fixtures);save(OUT/'component-provenance.json',prov);save(OUT/'throwables.json',throws)
 rows=[];assembly=OUT/'assembly';assembly.mkdir(exist_ok=True)
 for name in ('test01','test06'):
  row=b.build(BASE,assembly,name,copy.deepcopy(specs),fixtures,prov,dict(handContact=True,stockPolicy=True,components=True));folder=OUT/name;folder.mkdir(exist_ok=True)
  p=b.load(assembly/name/'B23-profile.json');p['testRepairs']['version']=VERSION;p['testRepairs']['logTag']=TAG;p['variant']+=f'-LEFT-ITEMS-V{REVISION}'
  for rid,spec in specs.items():p['consumers'][rid]=copy.deepcopy(spec);p['allowedConsumers'][rid]=True
  p['testRepairs']['leftHeldItems']=dict(enabled=True,magazines=True,linkMetres=.012,linkDegrees=3,neverWriteItemOrEffects=True)
  p['testRepairs']['equipmentV10']=dict(enabled=True,carryMounts={k:True for k in ('pistol','sling','support','support_mg','attach_weapon','attach_hand_l','backpack')})
  if REVISION>=11:
   p['testRepairs']['leftHeldItems'].update(recoverLocalOffset=True,reloadComponentsOnly=True,requireExternalParent=True,candidateRadius=1.5,probeResources={rid:True for rid in ('7372947782b91123','1ec5f54265a91c83','1b1fcc0e025c1f7d','d5cb9b5401b261f9')})
   p['testRepairs']['equipmentV10'].update(alternateLinkedRoots=True,probeLinks={'16051937941bb709':dict(parentResource='94bd931b5fb4ee95',mount='attach_muzzle')})
  if REVISION>=12:
   p['testRepairs']['leftHeldItems'].update(unitRootComposeOnly=True,probeResources={rid:True for rid,spec in specs.items() if spec['kind']=='weapon_magazine'})
   p['testRepairs']['equipmentV10']['probeLinks']['503c0e01fbafa86a']=dict(parentResource='2e9d0bdc48b09e60',mount='attach_mag')
   for rid,label in V12_MELEE.items():
    spec=specs[rid];marker=next((n for n in spec['nodes'] if n['name']=='IK_left'),None)
    p['testRepairs']['heldEquipment']['rigidRight'][rid]=dict(rootIndices=spec['heldRoots'],allowWeaponMount=True,linkMetres=.012,linkDegrees=3,
     itemType='melee',recoverLocalOffset=True,requireExternalParent=True,unitRootComposeOnly=True,leftMarker=marker,leftContactMetres=.14,designation=label)
  for rid in throws:
   spec=specs[rid];p['testRepairs']['heldEquipment']['rigidRight'][rid]=dict(rootIndices=spec['heldRoots'],allowWeaponMount=True,linkMetres=.012,linkDegrees=3,itemType='throwable')
  p['logging']['maxBytes']=16*1024*1024;p['packageName']=f'{name}-左手与随身装备修复-测试用低负载日志-{VERSION}.zip'
  code=compose_source(p);ok,err=LuaRuntime().eval('function(s)local f,e=loadstring(s);return f~=nil,e end')(code);assert ok,err
  body=code.encode('utf-8');header=(assembly/name/'container-header.bin').read_bytes();payload=struct.pack('<II',len(body),2)+body;patch=bytearray(header)+payload;patch.extend(bytes(-len(patch)%16));struct.pack_into('<Q',patch,32,len(patch));struct.pack_into('<I',patch,160,len(payload))
  note=f'''# {name} V{REVISION}【测试用·低负载日志】\n\n版本 {VERSION}。保留V9已验收C4、导弹标记器及榴弹发射器、普通握持及双骨骼原布娃娃处理。\n\n新增原生左手物品挂持检测：左手战备球/换弹组件仅确认既有挂点位置及角度后，Source左手跟随原生手掌，保留物品挂点。23种已核对投掷物按当前手枪手掌代理跟随，不写抛出物local/链接。组件新增无skeleton罐体/电池/弹药、司炉者下挂、训斥枪口及有配件手枪；刷新范围包含角色腿挂/背挂节点，仍不认领远处装备。\n\n停用V9同名挂点，仅启用本模型V10，保留模型/动画/物理，重启游戏。\n日志 hd2_grip_TEST_PERF_{name}_{TAG}_日期时间.partNN.log，TEST_ONLY_PERF；约1Hz，16MiB上限。本版未实机验收。\n\n单骨骼test01观测包独立，只记录布娃娃数据，不修复且不写任何骨骼。不要给单骨骼安装此双骨骼握持包。\n'''
  if REVISION>=11:
   note=note.replace('停用V9同名挂点，仅启用本模型V10',f'停用V9/V10/V11等旧挂点，仅启用本模型V{REVISION}')
   note+=f'\nV11增量：左手检测按 world=原生左挂点×当前物品local 核对非零局部偏移，限定外链父、唯一候选，不归零物品local。训斥枪口补进精确备用根刷新；仅增加约1Hz弹夹候选和枪口before/final/restore矩阵，16MiB上限。已修好的常规持握及其它枪口保留，不加通用横移。该版未实机验收。单骨骼诊断改用独立S2，不安装本双骨骼包。\n'
  if REVISION>=12:
   note+='\nV12：换弹沿精确Unit根(0)当前local复合核对，不把内部骨根的父索引当成外链。新增P113/R63对应弹夹及磁轨炮503c...精确图；砍刀/晕眩长矛/破门锤/唯一真旗仅已确认原生手链接时，复用原生持物路径与Source手代理，脱手/腰挂不驱动，不虚构IK_right。训斥枪口V11已验收修复保留。单骨骼启动诊断替换为独立S3，不安装此双骨骼包。\n'
  manifest=b.load(assembly/name/'manifest.json');manifest.update(Guid=str(uuid.uuid4()),Name=f'[测试用·低负载·左手与随身装备]{name}',Description=f'TEST ONLY / {VERSION}. Left-held items and carried components; no game verification.')
  dest=OUT/p['packageName']
  with zipfile.ZipFile(row['package']) as z,zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as w:
   for info in z.infolist():
    if info.filename in ('9ba626afa44a3aa3.patch_0','attachment-profile.json','manifest.json') or info.filename.endswith('.md'):continue
    data=z.read(info);w.writestr(info.filename,data)
    if info.filename.startswith('9ba626afa44a3aa3.patch_1'):(folder/info.filename).write_bytes(data)
   w.writestr('9ba626afa44a3aa3.patch_0',patch);w.writestr('attachment-profile.json',json.dumps(p,ensure_ascii=False,indent=2));w.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2));w.writestr('测试说明.md',note)
  (folder/'hd2attachmentfix-B23.lua').write_bytes(body);save(folder/'B23-profile.json',p);save(folder/'manifest.json',manifest);(folder/'container-header.bin').write_bytes(header);(folder/'测试说明.md').write_text(note,encoding='utf-8')
  row.update(package=str(dest),sha256=b.sha(dest.read_bytes()),luaSha256=b.sha(body),testVersion=VERSION);rows.append(row)
 save(OUT/'build-report.json',rows);print(json.dumps(rows,ensure_ascii=False,indent=2))
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,choices=(10,11,12),default=10)
 configure_revision(parser.parse_args().revision);sys.stdout.reconfigure(encoding='utf-8');main()
