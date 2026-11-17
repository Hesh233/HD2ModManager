# 骨架测试版管理器打包工具（schema 2，2026-11-15）

本目录是固定安装目录 `非运行文件/打包工具` 的可维护源码，不是另一个管理器发布目录。

## 构建与同步

在管理器仓库根目录执行（只编译打包辅助程序，不重编译/安装 Core、GUI 或任何 Lua 资源）：

```powershell
dotnet build tools/ManagerPackageSupport/ManagerPackageSupport.csproj -c Release -p:NuGetAudit=false
python tools/manager-packaging/test_packaging.py
& .\tools\manager-packaging\Sync-ManagerPackaging.ps1 -Apply
```

同步器默认指向 `outputs/native-v34-b23-integrated-20261105/manager-1.0.7`，可用 `-InstallationRoot` 指定实际安装。省略 `-Apply` 只列计划，不写目标目录。现在同时同步根目录 BAT 入口，并按**实际 GUI 程序集＋本安装 build-info**生成打包清单版本/物理分支元数据，避免 GUI 升级后仍因旧1.5.15清单报错。普通后端不继承测试版的 direct-v1 元数据；Full 的版本、Core/Python、生产policy、真实模板及完整配置SHA门禁仍保留。

默认只同步入口/打包工具，保留已有 `生成链版本.txt`，不把源码说明反向盖到不同后端。只有明确需要静态说明同步时才使用 `-IncludeStaticSupport`。所有源文件和目标/备份路径预检通过后才写入；不复制 Core/GUI、根/随包 config、settings、骨骼开关、用户库或任何模型 profile。旧打包文件按内容哈希备份到既有 `验证记录`；可传 `-BackupRoot` 指定一个已存在的独立备份目录。

```powershell
& .\tools\manager-packaging\Sync-ManagerPackaging.ps1 -InstallationRoot "实际管理器目录" -Apply -BackupRoot "已存在的备份目录"
```


## 实际使用

`Package-HD2ModManager.bat` 现在有对应源码模板，定位自己的安装目录，不受当前工作目录、空格/中文/!影响；传参和退出码保留。默认 Full；`-CheckOnly` 不写 ZIP；`-Mode Startup` 是不含 CLI/动画模板/物理 ZIP 的启动依赖诊断版，不是完整发布版。

当前 GUI 基准1.5.17，骨架修复版1.01；首页列出1.01修复说明、设置显示“骨架修复1.01”，程序自更新继续停用。上游基准取实际程序集，骨架修复版取配套skeletonRepairVersion元数据。新装骨架询问/双骨架开关默认关闭。输出文件名包含实际GUI版本与 skeleton-test，不把历史目录名当版本。

Full = 122 个白名单载荷（含 B3 模型校准生成器、生产 repair policy/profile 和生成链版本说明） + 新装 settings/README/LICENSE + **1 个独立正式物理 ZIP**。

```text
HD2ModManager/
  原管理器运行文件与工具链…
  运行时配套/
    物理运行时.zip
      manifest.json
      9ba626afa44a3aa3.patch_0
      9ba626afa44a3aa3.patch_0.stream
      9ba626afa44a3aa3.patch_0.gpu_resources
```

物理 ZIP 每次由**本次待打包安装 DLL**的 `PhysBoneLuaPackageExport.Export` 生成；不从测试包寻找、复制或改名。验证正式 owner/GUID、语义版本、Lua 资源 owner hash、TOC/正文、根目录四项及压缩后逐字节回读；最终校验生成配套的 Core/GameItemAssets SHA-256 和包内 DLL 相同。报告 `productionArtifacts` 保存版本、来源与全部哈希。当前安装 runtime 2.3.6 / compat 1.3.6（保留test16已验收数学及严格身份/bind闸；新增多人发现/调度修正尚待实机验证）。

需要兼容共享加载器及带物理参数的角色 patch。将内层 ZIP 导入管理器，启用一份物理运行时，重新部署并完全重启游戏；内置/外置物理二选一，不重复加载。新装设置仍默认关闭内置物理；打包不会自动安装或部署。

Full 已包含 B3 1.0.19 / 第一人称 Source 1.0.1 正式生成器。多骨骼模型出包/导入时，按当前模型自动校准并生成“基础运行时 ZIP＋开关面板 ZIP”，不是把某个 test06 ZIP 改名。Full 不携带模型专属测试 ZIP；第一人称骨架三件套仅属于面板第一项，TP 挂点按当前 bones 顺序独立勾选。物理 ZIP 仍独立。

Full 预检调用待打包 Core 的 `companion-check`，同时核对 8 个生产 Lua 资源、Python 生成器和版本元数据；旧 Core 或不完整 Python 包不能冒充 B3 发布版。更改选项后重新部署并完全重启游戏，基础运行时始终单独启用。

## 验证

可使用 `-OutputDirectory "独立输出目录"` 把新ZIP和临时物理工作目录写到指定位置（默认仍为安装目录的 `非运行文件/打包输出`），检查全部目录祖先不是链接，且仅清理本轮 `.physics-GUID`。`-CheckOnly` 即使提供此参数也不创建目录。

```powershell
python tools/manager-packaging/verify_manager_package.py "完整包绝对路径.zip" --report "验证报告绝对路径.json"
```

可增加 `--protected` 指向本次打包前记录的 `{绝对路径: SHA-256}` 字典。验证外层所有 CRC/长度/SHA-256、内层全部内容、来源对应及新装路径清空。回归覆盖静态文件缺失补齐、源缺失拒绝、旧文件哈希备份、二次同步零改写，以及完整包、Startup、CheckOnly、重复/越界/测试路径、缺辅助程序/物理声明/许可、错误 Core、配套与包内 DLL 不一致等。

原安装内 `分析依赖.py`、`生成打包说明.py` 是 schema 1 整理记录工具，**不要用它们重建 schema 2 清单或覆盖最新说明**；更新以本目录源码、同步器和本轮报告为准。
