from pathlib import Path
import hashlib,json,struct,zipfile
root=Path.cwd();audit=root/'outputs/vrd-analysis-20261107';install=root/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
model=audit/'e2e-test01-single/test01';anim=root/'tmp/single-vrd-fix-build/runtime';export=audit/'lua-package/exported'
prep=json.loads((model/'single-skeleton.json').read_text(encoding='utf-8-sig'))
marker=json.loads((anim/'single-skeleton.json').read_text(encoding='utf-8-sig'))
assert prep['bindSha256']==marker['bindSha256'] and prep['configSha256']==marker['inputModelConfigSha256']
marker['modelFiles']=prep['modelFiles'];(anim/'single-skeleton.json').write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding='utf8')
carrier=(model/'9ba626afa44a3aa3.patch_0.gpu_resources').read_bytes()
assert carrier[-56:-48]==b'HD2PBFT1'
length=struct.unpack_from('<Q',carrier,len(carrier)-40)[0];container=carrier[-length:]
count=struct.unpack_from('<I',container,40)[0];at=48;records={}
for _ in range(count):
 name_len=struct.unpack_from('<H',container,at)[0];off,size=struct.unpack_from('<QQ',container,at+4)
 name=container[at+56:at+56+name_len].decode();records[name]=container[off:off+size];at+=56+name_len
assert records['hd2_driver_rig.bin']==(model/'physbone-driver-rig.bin').read_bytes()
assert struct.unpack_from('<I',records['hd2_driver_rig.bin'],8)[0]==3
assert records['hd2_spring_rig.bin']==(model/'physbone-rig.bin').read_bytes()
physical=install/'物理运行时-VRD驱动-1.2.1-待测试.zip'
with zipfile.ZipFile(physical,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name in ['lua版/hd2physbone.lua','patch版/9ba626afa44a3aa3.patch_0','patch版/9ba626afa44a3aa3.patch_0.gpu_resources','patch版/9ba626afa44a3aa3.patch_0.stream','patch版/manifest.json','如何安装.txt']:
  p=export/name;assert p.exists(),p;z.write(p,'物理运行时-VRD驱动-1.2.1-physbone/'+name)
with zipfile.ZipFile(physical) as z:
 assert len(z.infolist())==6
 lua=z.read(next(n for n in z.namelist() if n.endswith('hd2physbone.lua')))
 patch=z.read(next(n for n in z.namelist() if n.endswith('.patch_0')))
 assert b'M.version = "1.2.1"' in lua and lua in patch
report=json.loads((root/'tmp/single-vrd-fix-build/build-report.json').read_text())
assert report['status']=='complete' and report['expected_animations']==3180
compound=install/'test01-单骨架-VRD物理修复-1.2.1-成套待测试.zip'
with zipfile.ZipFile(compound,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in model.iterdir():
  if p.is_file() and (p.name.startswith('9ba626afa44a3aa3.patch_') and not p.name.endswith('.bak') or p.name in ['custom-model.json','physbone-driver-rig.bin','physbone-rig.bin','sections.json','single-hd2-bind.json','single-config.toml','single-skeleton.json']):
   z.write(p,'[单骨架模型]test01/vpk2patch/'+p.name)
 oldmodel=install/'test-library/[单骨架模型]test01'
 z.write(oldmodel/'vpk2patch.json','[单骨架模型]test01/vpk2patch.json');z.write(root/'testVPK/test01.vpk','[单骨架模型]test01/test01.vpk')
 for p in anim.iterdir():
  if p.is_file():z.write(p,'[单骨架动画](test01)/'+p.name.replace('.patch_2','.patch_0'))
 z.write(install/'test-library/[单骨架动画](test01)/manifest.json','[单骨架动画](test01)/manifest.json')
 z.write(root/'tmp/single-vrd-fix-build/build-report.json','[单骨架动画](test01)/build-report.json')
 z.writestr('安装说明.txt','仅单骨架test01，倍率1.1，沿用当前材质namespace及金属设置。管理器已更新：推荐重启后正常重新导入test01.vpk（单骨架），让原目标护甲Overwrite重新编译；不要复制旧Overwrite。物理运行时另导入1.2.1并只启用这一份。成套动画3180条、R2播放字节保持。多骨架无需重导/更换。尚未游戏视觉验收。')
with zipfile.ZipFile(compound) as z:
 assert z.testzip() is None
 embedded=z.read('[单骨架模型]test01/vpk2patch/9ba626afa44a3aa3.patch_0.gpu_resources')
 assert embedded==carrier and records['hd2_driver_rig.bin'] in embedded
assert hashlib.sha256((anim/'9ba626afa44a3aa3.patch_2').read_bytes()).hexdigest()==hashlib.sha256((install/'test-library/[单骨架动画](test01)/9ba626afa44a3aa3.patch_0').read_bytes()).hexdigest()
proof={'status':'PASS_OFFLINE_NOT_GAME_ACCEPTANCE','animations':3180,'animationBytesUnchanged':True,'modelScale':1.1,'modelNamespace':'vpk-678e82d907d3e6e7','embeddedDriverVersion':3,'embeddedRecords':list(records),'physicalPackageEntries':6,'gameTested':False,'packages':[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [physical,compound]]}
(audit/'single-vrd-package-audit.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(proof,ensure_ascii=False))
