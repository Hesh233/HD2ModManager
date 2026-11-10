# HD2ModManager

Helldivers 2 mod management and patch adaptation tools.

This project is licensed under the GNU General Public License, version 3 (GPLv3). See [LICENSE.txt](LICENSE.txt).

## 上游与许可 / Upstream & License

本项目基于 [AssestinaR/HD2ModManager](https://github.com/AssestinaR/HD2ModManager)(GPL-3.0)深度修改与扩展:新增单骨架转换路线、native-v15 校准预设、内嵌 Python 工具链与 VRD/握持修复工作流;上游原有的 mod 管理核心继续沿用。按 GPLv3 要求,本仓库同样以 GPL-3.0 发布(见 [LICENSE.txt](LICENSE.txt))。

This repository is a heavily modified derivative of [AssestinaR/HD2ModManager](https://github.com/AssestinaR/HD2ModManager) (GPL-3.0) and is distributed under the same license.


## 可复现工程归档

- [test01 原生挂点工程（B23-LR-M 1.0.8）](projects/test01-native-grip/README.md)：固定配置/输入、共享实现、不可变发布包和可重建工作目录。
- 一键重新打包：`projects/test01-native-grip/build.ps1`；不自动重烘动作或部署游戏。
- 完整动作仅保留必要依赖，不放入每个握持运行时工程；归档及清理记录见 `outputs/project-archive-cleanup-20261105/归档与清理报告.md`。

### VPK腕权重配置（2026-11-08）

管理器根目录 `config.toml` 中使用 `[vpk_conversion]` / `merge_wrist_weights = false`，默认不合并；设为true仅转移程序腕辅助骨权重到下臂，保留骨骼与VRD。两种骨架路线共用，初次界面不再询问，重构建以当前配置为准而不是旧报告。单骨架臂段归一化已修正手掌/手指联动；已有模型/动画须重新生成。详见固定manager的说明文档/腕权重配置与手部联动修复-20261108.md。


## Arsenal 物理包兼容修复（2026-11-10）

物理外置包改为功能根 manifest＋patch 三件套，修复旧外层选项可能“部署成功但复制 0 文件”的问题；保留已验收 VRD 1.3.1/runtime 2.3.1 数学与其它功能布局。详见 [平铺导出及验收范围](docs/arsenal-physics-flat-export-20261110.md)。
