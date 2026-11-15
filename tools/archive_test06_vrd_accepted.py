"""Archive the user-accepted test06 physical fix. No model baking or game deployment."""
from pathlib import Path
import datetime,hashlib,json,shutil,zipfile,re,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
if ROOT.name=='HD2ModManager_main':ROOT=ROOT.parent
OUT=ROOT/'outputs/test06-vrd-skirt-analysis-20261109'
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
ARCHIVE=INSTALL/'非运行文件/归档'
GUIDE=INSTALL/'非运行文件/说明文档/test06-VRD骨轴与bind参考-1.3.1-已验收-封档.md'

def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
 assert ARCHIVE.is_dir() and not GUIDE.exists()
 proof=json.loads((OUT/'fix-package-readback.json').read_text(encoding='utf-8'))
 sync=json.loads((OUT/'accepted-code-sync.json').read_text(encoding='utf-8-sig'))
 installed=json.loads((OUT/'accepted-installed-resource-check.json').read_text(encoding='utf-8-sig'))
 source_sync=json.loads((OUT/'accepted-source-metadata-sync.json').read_text(encoding='utf-8'))
 feedback=json.loads((OUT/'accepted-user-feedback-20261109.json').read_text(encoding='utf-8'))
 assert sync['mode']=='apply' and sync['coreCodeIdentical'] and sync['coreMethodsExact']==16752 and sync['coreConstantsExact']==569
 assert set(sync['changedResources'])=={'HD2ModCore.PhysBone.physbone_compat.lua','HD2ModCore.PhysBone.physbone_runtime.lua'}
 assert installed['status']=='PASS' and installed['exportedFromActualInstalledCore']
 for p in sync['plan']:assert sha(p['target']).upper()==p['sourceHash']
 for name in ['accepted-root-regression.json','accepted-mirror-regression.json']:
  reg=json.loads((OUT/name).read_text(encoding='utf-8'));assert reg['status']=='PASS_OFFLINE_NOT_GAME_ACCEPTANCE' and reg['checks']==26575
 # Installed exporter must reproduce the accepted source after platform newline normalization.
 package=Path(proof['package']);assert sha(package)==proof['sha256']
 with zipfile.ZipFile(package) as z:
  accepted_lua=z.read(next(n for n in z.namelist() if n.endswith('hd2physbone.lua')))
 assert accepted_lua.replace(b'\r\n',b'\n')==(OUT/'accepted-installed-standalone.lua').read_bytes().replace(b'\r\n',b'\n')
 accepted_package=ARCHIVE/'test06-VRD骨轴与bind参考-1.3.1-已验收-20261109.zip'
 assert not accepted_package.exists();shutil.copyfile(package,accepted_package);assert sha(accepted_package)==proof['sha256']
 # A live log snapshot is evidence of module/bind activation, not a complete visual trace.
 live=Path(r'C:\Users\Administrator\AppData\Roaming\Arrowhead\Helldivers2\hd2physbone_compact.log')
 raw=live.read_bytes();log=OUT/'accepted-physical-session-20261109.log';log.write_bytes(raw)
 text=raw.decode('utf-8-sig',errors='replace')
 markers=re.findall(r'canonicalBind=(\d+) boneLocalDelta=(\d+) completeLocal=(\d+) rejected=(\d+)',text)
 assert '运行时 2.3.1' in text and markers and all(v==('5','5','0','0') for v in markers)
 now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
 record=dict(feedback,status='ACCEPTED_AND_CODE_SYNCED_ARCHIVE_PENDING',synchronizedAt=now,
  installedCoreSha256=sha(INSTALL/'HD2ModCore.dll'),sourceMirrorSynced=True,
  coreMethodsPreserved=16752,coreConstantsPreserved=569,resourcesPreserved=29,
  physicalResourcesReplaced=2,modelAnimationOrGameDeploymentChangedByTask=False,
  originalTestPackageRetained=True,acceptedPackage=dict(path=str(accepted_package),sha256=sha(accepted_package)),
  logSnapshot=dict(path=str(log),sha256=sha(log),firstLine=text.splitlines()[0],bindings=markers,
    limit='No frame-by-frame visual or GPU acceptance inferred from this log; acceptance comes from the user feedback.'),
  binarySyncReport=str(OUT/'accepted-code-sync.json'),sourceSyncReport=str(OUT/'accepted-source-metadata-sync.json'))
 description=f'''# test06 VRD 1.3.1 已验收封档（2026-11-09）

用户反馈：**“表现正常，同步代码并归档”**。据此将本轮 test06 原比例/native v2 五根裙骨的骨轴与发货 bind 参考修复记为实机验收通过并冻结。

验收仅覆盖用户本轮反馈；不是全部模型/动作/长期多人局穷尽验收。手腕排除、其他模型、single v3、原弹簧/角限/前裙策略保持；无覆盖区回位策略和碰撞没有修改。

## 同步已完成

- compat **1.3.1** / runtime **2.3.1** 物理 Lua 主源码与镜像对齐。
- 固定安装目录 `manager-1.0.7/HD2ModCore.dll` 与已有 `outputs/single-hd2-fix-20261106/manager` staging 同步，未新建发布版。
- 使用既有资源隔离编译流程：**16752 方法体、569 常量、程序集身份保持**；31资源中只替换两个物理Lua，其他29资源逐字节不变。没有带入并行握持/布娃娃源码改动。
- 原恢复DLL保留在既有 `非运行文件/归档/旧版备份`。没有补回此前清理掉的PDB。
- 物理版本元数据定向更新，保留单链1.0.21/R2/轨道编码及全部其他字段。
- 主源码与镜像各26575限定回归通过；实际安装Core导出物理Lua与验收包按LF规范化后完整一致。

**不需要重导模型或重烘动画，也没有重新应用配置/部署游戏。** 若管理器在更新时仍开着，关闭后重新启动即可使用新版导出；游戏内本轮正常的1.3.1包无需再次更换。

## 归档与回退

原测试ZIP保留原文件名和字节，避免历史链接失效。“待测试”名字是历史交付命名，不再代表最新验收状态。归档副本字节与原ZIP完全相同：

`{accepted_package}`

SHA-256：`{proof['sha256']}`

另有源码/同步后二进制/恢复基线/规则与发货bind参考/回归/日志/版本记录的源码与二进制ZIP。原图形模型、动画和大素材不重复封装；原库和源VPK由保护清单/hash引用。

本次日志快照记录 runtime2.3.1 和 canonicalBind5/boneLocalDelta5/rejected0；不把此快照当完整GPU/视觉轨迹。验收依据为用户反馈。

详细记录位于 `{OUT}`，最终文件为 `accepted-archive-final.json`。
'''
 GUIDE.write_text(description,encoding='utf-8')
 source_files=[
 'HD2PhysBoneCompat/src/physbone_compat.lua','HD2PhysBoneCompat/src/physbone_runtime.lua',
 'HD2PhysBoneCompat/test/test06-native-vrd-bind-test.py','HD2PhysBoneCompat/test/fixtures/test06-native-vrd-bind.json',
 'HD2PhysBoneCompat/test/driver-update-test.py','HD2PhysBoneCompat/test/driver-wrist-exclusion-test.py',
 'HD2PhysBoneCompat/test/single-front-skirt-test.py','HD2PhysBoneCompat/test/single-vrd-bind-test.py','HD2PhysBoneCompat/test/spring-dof-model-test.py',
 'HD2ModCore.Tests/LuaAddonPackageTests.cs','HD2ModCore/Infrastructure/PhysBoneLuaSource.cs','HD2ModCore/Infrastructure/PhysBoneLuaPackageExport.cs',
 'tools/Prepare-Test06AcceptedCore.ps1','tools/Sync-SingleVrdRuntime.ps1','tools/BuildNativeRuntime.ps1',
 'tools/audit_test06_vrd_skirt.py','tools/package_test06_vrd_fix.py','tools/archive_test06_vrd_accepted.py',
 'docs/test06-vrd-scoped-fix-20261109.md','docs/test06-vrd-skirt-analysis-20261109.md']
 files={str(ROOT/p):'源码/'+p for p in source_files}
 files[str(INSTALL/'HD2ModCore.dll')]='同步后二进制/HD2ModCore.dll'
 files[str(ROOT/'tmp/lua-boot/physics131-isolated-core/HD2ModCore.pdb')]='构建符号（未安装）/HD2ModCore.pdb'
 files[str(INSTALL/'非运行文件/归档/旧版备份/HD2ModCore.dll.before-test06-vrd-131-accepted-20261109.bak')]='同步前恢复基线/HD2ModCore.dll'
 for p in OUT.glob('fix-*'):
  if p.is_file():files[str(p)]='修复验证/'+p.name
 for p in OUT.glob('accepted-*'):
  if p.is_file():files[str(p)]='验收与同步/'+p.name
 for p in (OUT/'fix-dotnet').glob('*.trx'):files[str(p)]='修复验证/dotnet/'+p.name
 for p in [OUT/'fix-baseline-physbone_compat.lua',OUT/'fix-baseline-physbone_runtime.lua']:
  if p.exists():files[str(p)]='修复前Lua/'+p.name
 model=INSTALL/'test-library/[原比例模型]test06/vpk2patch'
 for name in ['source-skeleton.json','physbone-driver-rig.bin','physbone-rig.bin','config.toml']:
  files[str(model/name)]='发货参考（不含图形模型）/'+name
 for p in [ROOT/'tools/native-python/anim_batch_mod/build-info.json',INSTALL/'anim_batch_mod/build-info.json']:
  files[str(p)]='版本元数据/'+('源码-' if p.parts[-4]=='tools' else '安装-')+p.name
 files[str(GUIDE)]='封档说明.md'
 archive=ARCHIVE/'test06-VRD骨轴与bind参考-1.3.1-已验收-源码与二进制-20261109.zip'
 assert not archive.exists()
 members={name:sha(path) for path,name in files.items()}
 with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for path,name in files.items():z.write(path,name)
  z.writestr('源码与二进制SHA256.json',json.dumps(members,ensure_ascii=False,indent=2))
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 record['status']='ACCEPTED_SYNCED_AND_ARCHIVED'
 record['sourceBinaryArchive']=dict(path=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,members=len(members))
 record['freezeSource']=dict(compatNormalizedSha256=proof['sourceSha256']['compat'],runtimeNormalizedSha256=proof['sourceSha256']['runtime'])
 save(OUT/'accepted-archive-final.json',record)
 print(json.dumps({'status':record['status'],'archive':str(archive),'bytes':archive.stat().st_size,'acceptedPackage':str(accepted_package),'guide':str(GUIDE)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
