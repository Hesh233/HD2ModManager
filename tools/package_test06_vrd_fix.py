"""Package the existing Core physical export; never install/deploy or alter models."""
from pathlib import Path
import hashlib,json,struct,zipfile,sys
sys.dont_write_bytecode=True
from lupa.lua51 import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
if ROOT.name == 'HD2ModManager_main': ROOT = ROOT.parent
INSTALL=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
OUT=ROOT/'outputs/test06-vrd-skirt-analysis-20261109'
EXPORT=ROOT/'tmp/lua-boot/physics131-test06-export'
PACKAGE=INSTALL/'非运行文件/测试包/物理运行时-test06-VRD骨轴与bind修正-1.3.1-待测试.zip'
assert PACKAGE.parent.is_dir() and not PACKAGE.exists(), 'preserve existing releases'
compat=(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua').read_bytes().replace(b'\r\n',b'\n')
runtime=(ROOT/'HD2PhysBoneCompat/src/physbone_runtime.lua').read_bytes().replace(b'\r\n',b'\n')
lua=(EXPORT/'lua版/hd2physbone.lua').read_bytes();normal=lua.replace(b'\r\n',b'\n')
assert compat in normal and runtime in normal
assert b'M.version = "1.3.1"' in lua and b'M.VERSION = "2.3.1"' in lua
assert lua.startswith(b'-- HD2-Addon: mods/hd2modmanager/physbone\n')
LuaRuntime().eval('function(s)local f,e=loadstring(s);assert(f,e);return true end')(lua.decode('utf-8'))
patch=(EXPORT/'patch版/9ba626afa44a3aa3.patch_0').read_bytes();nt,n=struct.unpack_from('<II',patch,4);assert n==1
row=struct.unpack_from('<QQQQQQQIIIIII',patch,72+32*nt);payload=patch[row[2]:row[2]+row[7]]
assert struct.unpack_from('<II',payload)==(len(lua),2) and payload[8:]==lua
for suffix in ('gpu_resources','stream'):assert (EXPORT/f'patch版/9ba626afa44a3aa3.patch_0.{suffix}').stat().st_size==0
manifest=json.loads((EXPORT/'patch版/manifest.json').read_text(encoding='utf-8-sig'))
old=INSTALL/'test-library/物理运行时-弹簧自由度补全-1.3.0-待测试-物理运行时-弹簧自由度补全-1.3.0-patch版/manifest.json'
assert manifest['Guid']==json.loads(old.read_text(encoding='utf-8-sig'))['Guid']
reg=json.loads((OUT/'fix-test06-bind-regression.json').read_text(encoding='utf-8'))
assert reg['status']=='PASS_OFFLINE_NOT_GAME_ACCEPTANCE' and reg['scopedHelperIndices']==[73,74,76,89,91]
assert reg['maxWorldErrorDegrees']<.001 and reg['uncoveredV2BehaviorDeliberatelyUnchanged']
assert len(reg['legacyRigs'])==5 and all(v['numericTraceExact'] for v in reg['legacyRigs'])
files=[p for p in EXPORT.rglob('*') if p.is_file()];assert len(files)==6
readme='''# test06 VRD 骨轴与 bind 参考修正 1.3.1 / runtime 2.3.1（待实机）

## 使用
1. 保留现有模型、材质、混合动画和挂点 Lua；仅停用旧的外置物理运行时（如 1.3.0）。
2. 本包只选 lua版 或 patch版一种形态。推荐成套导入 patch版；不要同时启用两种或两份物理运行时。
3. 重新应用你的配置并完全重启游戏，再自行切到 test06 做短跑/原地抬腿测试。

不需要重导模型，不需要重烘动画。本轮代理没有切换当前配置、导入库或部署游戏，也没有更新安装版管理器 DLL；请使用这个明确的 1.3.1 测试包，而不是让旧安装版重新导出 1.3.0。

## 严格范围
只命中当前 test06 原比例/native v2 的 hd2n_e6dc84f05416 命名空间、完整七 driver 契约和已校验规则。只修五根裙骨 73/74/76/89/91；手腕两根依旧主动排除。

- 控制参考改用发货 canonical bind，不再用首个动画姿态。
- 父骨空间旋转增量正确换算到骨 bind 局部空间，并一次识别实际 localPose 表达。未知 bind 表达拒绝驱动并记录原因。
- 模型、权重、骨架、v2 sidecar、动画、弹簧参数、角限、前裙特判均不改。
- 没有顺带修改无覆盖区回位策略；仍保留该 v2 旧行为，没有新增碰撞。
- test01/test07 的实际 native v1/v2 和 single v3 五种 rig 各240帧写入/四元数/去重/恢复逐值一致。

## 日志核对
应出现运行时 2.3.1，以及每实例类似：
[test06-vrd] canonicalBind=5 boneLocalDelta=5 completeLocal=0 rejected=0 profile=test06-native-v2-bind-v1

completeLocal=5 也表示一种已识别的完整 localPose 表达；如 rejected 非零，请回传日志，不要盲调裙摆参数。其他模型不会出现这个限定修复标签。

## 验证与边界
26575 限定修复断言；7真实模型、不同首帧、fast/matrix 两路、缓存实例、9负控；21真实Unit/93442弹簧回归、VRD15709、腕排除270、前裙3352；14项独立Lua harness（多人壳按其文档使用LuaJIT）；Core1126通过、1既有资源测试跳过。Lua语法/内嵌两源码/patch正文/owner与GUID/空配套/ZIP CRC精确回读通过。

1107个历史骨图用于识别实际 bind/local 表达并做5535次骨轴部分重放；旧日志缺控制权重，未假称完整逐帧规则求解实测。所有数值验证均为离线，不代表当前跑步视觉或GPU蒙皮已通过。需用户进行本轮实机验收。
'''
proof=dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',compatVersion='1.3.1',runtimeVersion='2.3.1',
 profile='test06-native-v2-bind-v1',helperIndices=reg['scopedHelperIndices'],exactCurrentCoreSource=True,
 patchPayloadEqualsLua=True,luaHeaderVersion=2,stableOwner='mods/hd2modmanager/physbone',stableGuid=True,
 emptySidecars=True,modelOrAnimationRebuildRequired=False,gameDeployed=False,gameTested=False,managerInstallationUpdated=False,
 v2UncoveredPolicyUnchanged=True,manifest=manifest,legacyNumericTraceExact=True,
 sourceSha256={'compat':hashlib.sha256(compat).hexdigest(),'runtime':hashlib.sha256(runtime).hexdigest()},
 memberSha256={str(p.relative_to(EXPORT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
with zipfile.ZipFile(PACKAGE,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 prefix='物理运行时-test06-VRD骨轴与bind修正-1.3.1/'
 for p in files:z.write(p,prefix+p.relative_to(EXPORT).as_posix())
 z.writestr(prefix+'本轮说明.md',readme)
 z.writestr(prefix+'版本与校验.json',json.dumps(proof,ensure_ascii=False,indent=2))
with zipfile.ZipFile(PACKAGE) as z:
 assert z.testzip() is None and len(z.infolist())==8
 assert z.read(next(n for n in z.namelist() if n.endswith('hd2physbone.lua')))==lua
proof.update(zipCrc=True,package=str(PACKAGE),bytes=PACKAGE.stat().st_size,sha256=hashlib.sha256(PACKAGE.read_bytes()).hexdigest())
(OUT/'fix-package-readback.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
(INSTALL/'非运行文件/说明文档/test06-VRD骨轴与bind参考修正-1.3.1-说明.md').write_text(readme,encoding='utf-8')
print(json.dumps({k:proof[k] for k in ['status','package','bytes','sha256','compatVersion','runtimeVersion']},ensure_ascii=False,indent=2))
