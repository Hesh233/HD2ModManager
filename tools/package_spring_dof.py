"""Package the existing physical export and verify raw LUA resource readback."""
from pathlib import Path
import hashlib,json,struct,zipfile
from lupa.lua51 import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
install=ROOT/'outputs/native-v34-b23-integrated-20261105/manager-1.0.7'
export=ROOT/'tmp/lua-boot/physics130-export'
package=install/'非运行文件/测试包/物理运行时-弹簧自由度补全-1.3.0-待测试.zip'
assert package.parent.is_dir() and not package.exists()
source=(ROOT/'HD2PhysBoneCompat/src/physbone_compat.lua').read_bytes().replace(b'\r\n',b'\n')
runtime=(ROOT/'HD2PhysBoneCompat/src/physbone_runtime.lua').read_bytes().replace(b'\r\n',b'\n')
lua=(export/'lua版/hd2physbone.lua').read_bytes();patch=(export/'patch版/9ba626afa44a3aa3.patch_0').read_bytes()
assert source in lua.replace(b'\r\n',b'\n') and runtime in lua.replace(b'\r\n',b'\n')
assert b'M.version = "1.3.0"' in lua and b'M.VERSION = "2.3.0"' in lua
vm=LuaRuntime();vm.eval('function(s)local f,e=loadstring(s);assert(f,e);return true end')(lua.decode('utf-8'))
nt,n=struct.unpack_from('<II',patch,4);assert n==1
record=struct.unpack_from('<QQQQQQQIIIIII',patch,72+32*nt)
payload=patch[record[2]:record[2]+record[7]]
assert struct.unpack_from('<II',payload)==(len(lua),2) and payload[8:]==lua
for suffix in ['gpu_resources','stream']:assert (export/f'patch版/9ba626afa44a3aa3.patch_0.{suffix}').stat().st_size==0
manifest=json.loads((export/'patch版/manifest.json').read_text('utf-8-sig'))
old=install/'test-library/物理运行时-VRD排除手腕-1.2.4-待测试-patch版/manifest.json'
assert old.exists()
old_manifest=json.loads(old.read_text('utf-8-sig'));assert manifest['Guid']==old_manifest['Guid']
files=[p for p in export.rglob('*') if p.is_file()]
proof=dict(status='PASS_OFFLINE_NOT_GAME_ACCEPTANCE',compatVersion='1.3.0',runtimeVersion='2.3.0',
 exactCoreSource=True,patchPayloadEqualsLua=True,luaHeaderVersion=2,zipCrc=True,emptySidecars=True,stableGuid=True,manifest=manifest,
 memberSha256={str(p.relative_to(export)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
readme='''# 弹簧自由度补全 1.3.0 / runtime 2.3.0（待实机）

只选择 lua版 或 patch版一种安装形态，停用旧外置物理包并重启游戏。不要把两种形态同时启用。

新增：按 0x40 求解根部 base_spring；无 0x20 定长标志时保留轴向积分及 along 刚度/阻尼；0x01/0x02 区分柔性/刚性，纯 base_spring 不驱动尖端。保持原角限、VRD腕排除和前裙锚点策略。

非定长改变的是尖端动力学，不会直接缩放网格；纯轴向输入且零重力时，最终旋转可能仍为零，这是 Valve 原变换语义。base_spring 才会输出根部位移。

当前含物理参数的模型无需重新导入、重绑或重烘动画。管理器 Core 已仅替换两个物理 Lua 资源；更新工具不等于旧外置包自动更新。

14项Lua harness（含35组新自由度检查）、21真实Unit/93442断言、VRD 15709、腕排除293、前裙6595及Core 1125通过/1既有跳过。未进行新游戏视觉验收。
'''
with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 root='物理运行时-弹簧自由度补全-1.3.0/'
 for p in files:z.write(p,root+p.relative_to(export).as_posix())
 z.writestr(root+'本轮说明.md',readme)
 z.writestr(root+'版本与校验.json',json.dumps(proof,ensure_ascii=False,indent=2))
with zipfile.ZipFile(package) as z:assert z.testzip() is None and len(z.infolist())==8
proof.update(package=str(package),bytes=package.stat().st_size,sha256=hashlib.sha256(package.read_bytes()).hexdigest())
(ROOT/'outputs/vrd-analysis-20261107/spring-dof-package-20261108.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(package=str(package),bytes=proof['bytes'],sha256=proof['sha256'],status=proof['status']),ensure_ascii=False))
