from pathlib import Path
import json,hashlib,datetime,zipfile,shutil,os
root=Path.cwd();install=root/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7';audit=root/'outputs/vrd-analysis-20261107';archive=install/'归档'
for p in [archive,archive/'测试报告',archive/'测试日志',install/'说明文档']:assert p.is_dir(),p
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
before=json.loads((audit/'accepted-archive-protected-before.json').read_text(encoding='utf8'))
changes=[p for p,h in before['hashes'].items() if not Path(p).exists() or sha(p)!=h]
assert not changes,changes
source_before=json.loads((audit/'accepted-source-before.json').read_text(encoding='utf8'))
assert all(sha(root/n)==h for n,h in source_before.items())
sync=json.loads((audit/'accepted-code-sync.json').read_text(encoding='utf-8-sig'))
assert sync['status']=='PASS' and all(sha(r['source']).upper()==r['sourceSha256']==sha(r['target']).upper() for r in sync['files'])
model=install/'test-library/[单骨架模型]test01/vpk2patch';anim=install/'test-library/[单骨架动画](test01)'
model_manifest=json.loads((model/'single-skeleton.json').read_text(encoding='utf-8-sig'));anim_manifest=json.loads((anim/'single-skeleton.json').read_text(encoding='utf-8-sig'))
assert model_manifest['bindSha256']==anim_manifest['bindSha256']
log=Path(os.environ['APPDATA'])/'Arrowhead/Helldivers2/hd2physbone_compact.log';log_dst=archive/'测试日志/单骨架VRD物理-1.2.1-用户验收.log';shutil.copyfile(log,log_dst)
package=json.loads((audit/'single-vrd-package-audit.json').read_text(encoding='utf8'))
for p in package['packages']:assert sha(install/p['name'])==p['sha256']
record={'status':'ACCEPTED_AND_ARCHIVED','version':'1.2.1','archivedAt':now,'userFeedback':'表现良好，归档并同步代码','acceptanceBasis':'用户本轮实机试用反馈；未提供逐动作穷举清单，不扩展成全动作/长期/所有模型保证','functionalCodeChangeThisTurn':False,'currentRetainedModel':{'name':'test01','modelScale':model_manifest['modelScale'],'bindSha256':model_manifest['bindSha256'],'configSha256':model_manifest['configSha256'],'playbackRevision':anim_manifest['playbackRevision']},'offlinePackageModelScale':1.1,'offlinePackageScope':'此前1.1成套包保留原字节，不能混称为本次当前留存1.05模型的实机包','latestSessionLog':{'path':str(log_dst),'sha256':sha(log_dst),'firstLine':log_dst.read_text(encoding='utf-8-sig').splitlines()[0]},'deploymentSnapshotTiming':'当前activation-state为验收后现状，只保留不改，不宣称它就是23:03会话配置','protectedFilesVerified':len(before['hashes']),'changedProtectedFiles':[],'tests':{'dotnetPassed':1844,'dotnetSkipped':2,'luaHarnessesPassed':12,'driverAssertionsPassed':15709},'packages':package['packages'],'codeSync':sync}
record_path=archive/'测试报告/单骨架VRD物理-1.2.1-已验收归档.json';record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
(audit/'accepted-archive-final.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
text=f'''# 单骨架 VRD / 物理 1.2.1 · 已验收封档

状态：**用户实机反馈良好，已接受并归档**。\n用户原话：“表现良好，归档并同步代码”。\n归档时间：{now}（Asia/Shanghai）。

## 冻结范围
- 修复编号重叠、错父链/权重、最终骨轴下固定bind、触发区回位、单骨架v3时间平滑与极端跳变护栏。
- 多骨架v1/v2、原物理参数、挂点/握持实现及R2播放策略保持；本轮不再调参或重烘。
- 当前留存test01模型/动画清单倍率 **{model_manifest['modelScale']}**，bind一致，R2。此前1.1离线成套包保留原名及SHA，不据此扩张实机覆盖范围。
- 保存最近23:03会话compact日志及当前清单；验收后配置revision193现状保留，不擅自重部署。

## 代码同步
源码未再做功能修改。重新Release完整编译后，三程序集身份、方法体、常量与嵌入资源全部一致；构建元数据导致文件哈希不同，不是功能变化（Core16744方法/567常量/31资源，SourceModel908方法/101常量/0资源，Migration2585方法/184常量/11资源）。仅同步这组等价DLL/PDB到固定manager和已有staging，12个目标逐哈希核对。原目录内.before-accepted-vrd-code-sync.bak保存被替换版本。开发构建产物与固定目录已对齐，不新建发布目录。

## 复核
.NET 1844通过/2既有跳过；12 Lua harness、15709 driver断言通过。{len(before['hashes'])}个当前配置、库文件、索引、部署状态、多骨架源码及正常Python资源哈希保持。没有重新导入用户模型、重生成动画或修改游戏data。

## 已验收基线
归档下“单骨架VRD物理-1.2.1-已验收-源码与二进制.zip”冻结本轮源码、测试、同步工具、当前DLL/PDB及同步前已验收Migration恢复副本。测试报告保存文件SHA；原交付ZIP保留原名字和字节，避免历史导入链接失效。后续若改动单骨架，必须继续以本基线与多骨架字节保护为回归门禁。

用户反馈证明本轮试用效果良好；不将其改写成逐动作、全部模型、长期多人测试的穷尽保证。
'''
(archive/'单骨架VRD物理-1.2.1-已验收-封档.md').write_text(text,encoding='utf8')
(install/'说明文档/单骨架VRD物理-1.2.1-已验收-封档.md').write_text(text,encoding='utf8')
p=install/'单骨架VRD物理-1.2.1-修复与验收.md';s=p.read_text(encoding='utf8');s=s.replace('代码、固定管理器同步及离线验证完成；**尚未游戏视觉验收**，不能把“3180条动画构建通过”当作“全部动作自然”已被实机证实。','**用户本轮实机反馈“表现良好”，已接受并归档。** 代码已同步并冻结；验收范围以用户反馈为准，不扩展成穷尽的全动作/全部模型/长期保证。当前留存模型/动画清单倍率1.05，历史1.1离线包另行保留。').replace('最终ZIP需要CRC及Lua/patch内嵌一致检查通过','最终ZIP CRC及Lua/patch内嵌一致检查通过');s+='\n\n## 验收归档更新\n已于本轮用户确认后封档并复核代码同步，当前正常配置无需再次重导或部署。详情见说明文档/单骨架VRD物理-1.2.1-已验收-封档.md。\n';p.write_text(s,encoding='utf8')
for d in [install,root/'outputs/single-hd2-fix-20261106/manager']:
 p=d/'生成链版本.txt';s=p.read_text(encoding='utf-8-sig')
 if 'VRD/物理1.2.1已验收归档' not in s:s+='\nVRD/物理1.2.1已验收归档：用户反馈表现良好；代码等价同步；当前正常配置、多骨架与R2不再改动。\n';p.write_text(s,encoding='utf8')
p=install/'更新记录.json';j=json.loads(p.read_text(encoding='utf-8-sig'));j['acceptedVrdPhysicsRepair']={'version':'1.2.1','status':'ACCEPTED_AND_ARCHIVED','archivedAt':now,'userFeedback':record['userFeedback'],'report':str(record_path),'codeSync':str(audit/'accepted-code-sync.json'),'preservedAcceptedBehavior':True};p.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf8')
p=root/'AGENTS.md';s=p.read_text(encoding='utf8');note='- 2026-11-07 用户实机确认单骨架VRD/物理1.2.1“表现良好，归档并同步代码”：已验收封档冻结。当前留存test01模型/动画清单倍率1.05、bind一致、R2；不要把历史1.1离线包误标为该实机包。重新Release编译三程序集方法/常量/资源/身份完全一致（仅构建元数据hash差异），12DLL/PDB目标对齐固定manager与已有staging，同目录.bak。1844 .NET通过/2skip，12Lua、15709断言复核；13368当前库/设置/索引/部署/Python/多骨架保护文件哈希不变。不再重烘或部署当前正常配置；多骨架及已接受R2继续冻结。已有归档目录内源码+二进制ZIP/用户日志/验收JSON与封档说明，原待测ZIP名字及字节保留避免失效链接。反馈覆盖本轮试用，不扩张为全动作/全部模型/长期多人穷尽验收。证据outputs/vrd-analysis-20261107/accepted-archive-final.json；固定目录归档/单骨架VRD物理-1.2.1-已验收-封档.md。\n\n'
if '用户实机确认单骨架VRD/物理1.2.1' not in s:s=s.replace('# 项目协作记忆\n','# 项目协作记忆\n\n'+note,1)
s=s.replace('库/配置/游戏/多骨架源码与输出保护哈希保持；尚未游戏视觉验收。','库/配置/游戏/多骨架源码与输出保护哈希保持；后续用户本轮实机已接受，最新验收与冻结边界见上条。');p.write_text(s,encoding='utf8')
p=root/'docs/vrd-single-skeleton-20261107-封档.md';s=p.read_text(encoding='utf-8-sig');s+='\n\n## 用户验收结案（2026-11-07）\n用户反馈：“表现良好，归档并同步代码”。1.2.1本轮实机试用已接受并冻结；当前正常模型/动画/游戏配置不再改动。代码重新编译等价核验与固定manager/staging同步完成；多骨架保持。当前留存test01清单为1.05/R2，历史1.1离线包不扩张为实机验收。详细封档、哈希和源码二进制基线在固定目录“归档/单骨架VRD物理-1.2.1-已验收-封档.md”。\n';p.write_text(s,encoding='utf8')
source_files=list(source_before)+['HD2ModCore/Infrastructure/PhysBoneLuaSource.cs','HD2ModCore/Infrastructure/PhysBoneLuaPackageExport.cs','tools/Audit-SingleVrd.ps1','tools/Sync-SingleVrdRuntime.ps1','tools/package_single_vrd_fix.py','tools/Audit-AcceptedVrdCode.ps1','tools/Sync-AcceptedVrdCode.ps1']
archive_zip=archive/'单骨架VRD物理-1.2.1-已验收-源码与二进制.zip';members=[]
with zipfile.ZipFile(archive_zip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for name in source_files:
  p=root/name;arc='源码/'+name;z.write(p,arc);members.append({'name':arc,'sha256':sha(p)})
 for name in ['HD2ModCore.dll','HD2ModCore.pdb','HD2SourceModel.dll','HD2SourceModel.pdb','HD2SourceMigration.dll','HD2SourceMigration.pdb']:
  p=install/name;arc='已同步二进制/'+name;z.write(p,arc);members.append({'name':arc,'sha256':sha(p)})
 for name in ['HD2ModCore.dll','HD2ModCore.pdb','HD2SourceModel.dll','HD2SourceModel.pdb','HD2SourceMigration.dll','HD2SourceMigration.pdb']:
  p=install/(name+'.before-accepted-vrd-code-sync.bak')
  if p.exists():z.write(p,'同步前验收二进制/'+name)
 for p,arc in [(model/'single-skeleton.json','验收现场/当前留存模型清单.json'),(anim/'single-skeleton.json','验收现场/当前留存动画清单.json'),(log_dst,'验收现场/用户会话.log'),(record_path,'验收记录.json'),(archive/'单骨架VRD物理-1.2.1-已验收-封档.md','封档说明.md')]:z.write(p,arc)
 for name in ['accepted-code-equivalence.json','accepted-code-sync.json','accepted-driver-tests.log','accepted-lua-tests.log','accepted-model-tests.log','accepted-migration-tests.log','accepted-core-tests.log','accepted-cli-tests.log']:
  z.write(audit/name,'校验/'+name)
 z.writestr('源码与二进制SHA256.json',json.dumps(members,ensure_ascii=False,indent=2))
with zipfile.ZipFile(archive_zip) as z:assert z.testzip() is None
record['sourceBinaryArchive']={'path':str(archive_zip),'sha256':sha(archive_zip),'bytes':archive_zip.stat().st_size}
record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8');(audit/'accepted-archive-final.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
print('ACCEPTED_AND_ARCHIVED; protected unchanged='+str(len(before['hashes']))+'; archive='+str(archive_zip)+'; bytes='+str(archive_zip.stat().st_size))
