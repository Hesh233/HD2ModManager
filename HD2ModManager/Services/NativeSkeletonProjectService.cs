using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using HD2ModCore.Infrastructure;

namespace HD2ModManager.Services;

/// <summary>Build in a new export directory; publish completion only after both model and animations succeed.</summary>
internal static class NativeSkeletonProjectService
{
    internal static string ResolveConfig(string modDirectory)
    {
        var paths = new[] { Path.Combine(modDirectory, "config.toml"),
            Path.Combine(AppContext.BaseDirectory, "config.toml"),
            Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "config.toml") };
        return paths.FirstOrDefault(File.Exists)
            ?? throw new FileNotFoundException("找不到 config.toml：放在 Mod 根目录或管理器程序旁边后重试。");
    }

    internal static async Task<string> BuildAsync(string modDirectory, string? targetArchive,
        Action<string> stage, CancellationToken cancellationToken)
    {
        var config = ResolveConfig(modDirectory);
        var cli = Hd2ModCliLocator.TryResolve() ?? throw new FileNotFoundException("找不到 hd2mod.exe。");
        var runner = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "runtime", "python.exe");
        var script = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "main.py");
        if (!File.Exists(runner) || !File.Exists(script))
            throw new FileNotFoundException("发布包缺少原生骨架转换的 Python 运行时或源码。");
        var gameData = SettingsService.GetGameDataFolder();
        if (string.IsNullOrWhiteSpace(gameData) || !Directory.Exists(gameData))
            throw new InvalidOperationException("请先在设置中配置 HD2 游戏 data 目录。");
        var sources = VpkRebuildService.FindSourceVpks(modDirectory);
        if (sources.Count == 0) throw new FileNotFoundException("Mod 根目录没有来源 VPK。");
        var paths = SettingsService.CreateStoragePaths();
        var oldReport = VpkConversionReport.TryRead(modDirectory);
        var materials = new List<string>(sources);
        if (oldReport?.IdNamespace is { Length: > 0 } ns)
            materials.AddRange(VpkRebuildService.FindSiblingVpks(paths.ModsRootDirectory, modDirectory, ns, []));
        var project = Path.Combine(SettingsService.GetResolvedDefaultExportPath(), "NativeSkeleton",
            DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(project);
        var snapshot = Path.Combine(project, "config.toml");
        File.Copy(config, snapshot);
        var materialList = Path.Combine(project, "material-sources.txt");
        await File.WriteAllLinesAsync(materialList, materials.Distinct(), new UTF8Encoding(false), cancellationToken);
        var sourceList = Path.Combine(project, "source-vpks.txt");
        await File.WriteAllLinesAsync(sourceList, sources, new UTF8Encoding(false), cancellationToken);
        try
        {
            var savedScale = oldReport?.Settings.ModelScale ?? 1;
            var scaleResult = await Hd2ModProcess.RunAsync(runner, ["-c", """
import sys,tomllib,math,re
from pathlib import Path
p=Path(sys.argv[1]); text=p.read_text(encoding='utf-8-sig'); d=tomllib.loads(text)
native=d.get('native_skeleton',{}); scale=native.get('model_scale',float(sys.argv[2]))
if isinstance(scale,bool) or not isinstance(scale,(int,float)) or not math.isfinite(scale) or not 0<scale<=10:
    raise ValueError('native_skeleton.model_scale must be in (0,10]')
if 'model_scale' not in native:
    header=re.search(r'^\s*\[native_skeleton\][^\n]*$',text,re.M)
    if header:
        text=text[:header.end()]+'\nmodel_scale = '+repr(scale)+text[header.end():]
    else:
        text+='\n[native_skeleton]\nmodel_scale = '+repr(scale)+'\n'
    p.write_text(text,encoding='utf-8')
print(scale)
""", snapshot, savedScale.ToString("R", System.Globalization.CultureInfo.InvariantCulture)], cancellationToken);
            if (scaleResult.ExitCode != 0) throw new InvalidDataException(Hd2ModProcess.Explain(scaleResult, "模型倍率配置"));
            // 与 WriteConfigSnapshot 同源：旧快照缺 attachment_swap 键时强制补 true，
            // 保证挂点骨骼交换与同步动作一致（显式 false 尊重原配置）。
            File.WriteAllText(snapshot, VpkAnimationBuildService.EnsureAttachmentSwapDefault(
                File.ReadAllText(snapshot, Encoding.UTF8)), new UTF8Encoding(false));
            var modelScale = double.Parse(scaleResult.Output.Trim(), System.Globalization.CultureInfo.InvariantCulture);
            stage("正在保留来源骨架并转换模型");
            var args = new List<string> { "vpk2patch", "--vpk-list", sourceList,
                "--material-source-list", materialList, "--output", Path.Combine(project, "models"),
                "--manager-root", paths.AppRootDirectory, "--library", Path.Combine(project, "workspace"),
                "--game-data", gameData, "--source-skeleton", "--json" };
            var conversionSettings = oldReport is { HasSettings: true } ? oldReport.Settings
                : new VpkConversionSettings("merge", "metal", null, null, null);
            args.AddRange((conversionSettings with { ModelScale = modelScale }).ToArguments());
            if (oldReport?.IdNamespace is { Length: > 0 } token) args.AddRange(["--id-namespace-token", token]);
            var result = await Hd2ModProcess.RunAsync(cli, args, cancellationToken,
                (_, _, _, text) => stage(text)).ConfigureAwait(false);
            await File.WriteAllTextAsync(Path.Combine(project, "conversion.json"), result.Output, cancellationToken);
            if (result.ExitCode != 0) throw new InvalidOperationException(Hd2ModProcess.Explain(result, "模型转换"));
            var manifests = Directory.GetFiles(Path.Combine(project, "models"), "source-skeleton.json", SearchOption.AllDirectories);
            if (manifests.Length != 1) throw new InvalidDataException("一个原生骨架工程必须恰好有一个角色模型；请分别转换多个角色。");
            var modelDirectory = Path.GetDirectoryName(manifests[0])!;
            var physics = await Hd2ModProcess.RunAsync(cli, ["physbone", "embed-mod", modelDirectory, "--json"], cancellationToken);
            await File.WriteAllTextAsync(Path.Combine(project, "physics.json"), physics.Output, cancellationToken);
            if (physics.ExitCode != 0) throw new InvalidDataException(Hd2ModProcess.Explain(physics, "物理参数封包"));
            PhysBoneLuaPackageExport.Export(Path.Combine(project, "physics-runtime"));
            foreach (var file in Directory.EnumerateFiles(Path.Combine(project, "physics-runtime", "patch版"), "*.patch_0*"))
                File.Move(file, file.Replace(".patch_0", ".patch_3", StringComparison.Ordinal));
            // 挂点对调（2026-11-05）：原生骨架工程同时产出 [骨骼挂点修正] 独立 lua 包。
            // patch_4 高于物理包的 patch_3，避免同一补丁家族里互相覆盖。
            var attachmentFix = Path.Combine(project, "attachment-fix-runtime");
            stage("正在生成本模型的挂点配置与配套骨架");
            await VpkAnimationBuildService.BuildAttachmentFixAsync(modelDirectory, attachmentFix, cancellationToken, snapshot);
            stage("正在批量生成配套动画");
            var animation = await Hd2ModProcess.RunAsync(runner,
                ["-X", "utf8", script, "native-project", "--manifest", manifests[0], "--config", snapshot,
                 "--game-data", gameData, "--output", Path.Combine(project, "animations")], cancellationToken,
                (_, _, _, text) => stage(text)).ConfigureAwait(false);
            await File.WriteAllTextAsync(Path.Combine(project, "animation-output.json"), animation.Output, cancellationToken);
            if (animation.ExitCode != 0) throw new InvalidOperationException(Hd2ModProcess.Explain(animation, "配套动画"));
            using (var report = JsonDocument.Parse(await File.ReadAllTextAsync(
                Path.Combine(project, "animations", "build-report.json"), cancellationToken)))
            {
                var root = report.RootElement;
                if (root.GetProperty("status").GetString() != "complete"
                    || root.GetProperty("animations").GetArrayLength() != root.GetProperty("expected_animations").GetInt32())
                    throw new InvalidDataException("配套动画报告不完整，工程不能用于测试。");
            }
            // Retain the original material options as separate choices; avoid merging conflicting variants.
            var materialDirectories = materials.Select(Path.GetDirectoryName).Where(d => d is not null)
                .Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
            var materialIndex = 0;
            foreach (var directory in materialDirectories)
            {
                var payload = Path.Combine(directory!, "vpk2patch");
                if (!Directory.Exists(payload) || File.Exists(Path.Combine(payload, "sections.json"))) continue;
                var destination = Path.Combine(project, "material-options", (++materialIndex).ToString("D3"));
                Directory.CreateDirectory(destination);
                foreach (var file in Directory.EnumerateFiles(payload, "*.patch_*"))
                    File.Copy(file, Path.Combine(destination, Path.GetFileName(file)));
            }
            var readme = "原生骨架人工测试工程\n\n"
                + "模型材质.zip：导入时自动登记原生素体，再到护甲映射选择测试护甲；models 保留转换中间文件。\n"
                + "配套动画.zip：作为单独 Mod 导入，与模型同时启用。全部第三人称动画、avatar Unit、Bones 和扩展骨骼混合遮罩整合为一个 patch；模型包不含 StateMachine。\n"
                + "physics-runtime：物理运行时。管理器内置物理与外置 Lua 加载器方案任选其一，勿重复加载。\n"
                + "attachment-fix-runtime：[骨骼挂点修正] 本模型的 Lua patch_4 和配套骨架 patch_5；一并启用，物理包独立。头部子节点不修正。\n"
                + "material-options：沿用原 Mod 的材质选项，只选与原来一致的一组。\n"
                + "config.toml：本次配置快照；修改后从原 Mod 再点原生骨架转换生成新工程。\n"
                + "此补丁替换共享的第三人称动画，一次只测试一个原生骨架角色。第一人称手臂与物理动力学尚未验证。\n"
                + "自定义骨名统一为 hd2n 前缀；source-skeleton.json 保存原名映射。保留父子关系和 bind 轴，保留源原点并统一缩放网格与骨架。权重受 HD2 half 格式量化。\n"
                + "两套骨架采用相同浮点采样时间；标准挂点名称保留，Mod 手臂通过 IK 对齐，超出臂长的动作仍需检查握持距离。\n"
                + "检查待机、行走、冲刺、蹲伏、趴下、瞄准、换弹、手指与脚底。结束后整套停用。\n"
                + $"界面选择的目标护甲：{targetArchive ?? "自定义素体"}\n游戏内验收：待人工测试。\n";
            await File.WriteAllTextAsync(Path.Combine(project, "人工测试说明.txt"), readme, cancellationToken);
            stage("正在打包模型与全部配套动画");
            cancellationToken.ThrowIfCancellationRequested();
            ZipFile.CreateFromDirectory(Path.Combine(project, "models"), Path.Combine(project, "模型材质.zip"), CompressionLevel.Fastest, false);
            ZipFile.CreateFromDirectory(Path.Combine(project, "animations", "runtime"), Path.Combine(project, "配套动画.zip"), CompressionLevel.Fastest, false);
            cancellationToken.ThrowIfCancellationRequested();
            await File.WriteAllTextAsync(Path.Combine(project, "project.json"), JsonSerializer.Serialize(new
                { status = "complete", source = modDirectory, targetArchive, config, gameTested = false },
                new JsonSerializerOptions { WriteIndented = true }), cancellationToken);
            return project;
        }
        catch (Exception error)
        {
            await File.WriteAllTextAsync(Path.Combine(project, "FAILED.txt"), error.Message, CancellationToken.None);
            throw new InvalidOperationException($"{error.Message}\n未完成的工程与日志保留在：{project}", error);
        }
    }
}
