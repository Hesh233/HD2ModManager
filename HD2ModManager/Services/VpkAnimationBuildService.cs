using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using HD2ModCore.Infrastructure;

namespace HD2ModManager.Services;

/// <summary>
/// 为一个已入库的原骨架模型 Mod 全量生成配套骨架动画。
/// <para>
/// 走的是「原生骨架转换」已验证的动画链路：读模型里的 <c>source-skeleton.json</c> 清单，
/// 调随包 Python 运行时跑 <c>anim_batch_mod/main.py native-project</c>，把游戏全部第三人称
/// 动画逐条重定向到来源骨架，产出单一 patch 的 <c>runtime/</c> 目录。
/// 清单不存在、运行时缺失或报告不完整都直接抛错——动画半套上线等于进游戏动作错乱。
/// </para>
/// </summary>
internal static class VpkAnimationBuildService
{
    /// <summary>随包 Python 运行时与脚本是否齐全——缺了就不该问"是否生成动画"。</summary>
    internal static bool IsRuntimeAvailable()
        => File.Exists(Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "runtime", "python.exe"))
        && File.Exists(Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "main.py"));

    internal static async Task<string> BuildAttachmentFixAsync(string modDirectory, string outputRoot,
        CancellationToken cancellationToken, string? configPath = null)
    {
        var manifest = FindManifest(modDirectory);
        var runner = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "runtime", "python.exe");
        var script = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "main.py");
        if (!IsRuntimeAvailable()) throw new FileNotFoundException("缺少挂点修正配置生成器，请更新完整管理器。");
        var gameData = SettingsService.GetGameDataFolder();
        if (string.IsNullOrWhiteSpace(gameData) || !Directory.Exists(gameData))
            throw new InvalidOperationException("请先配置 HD2 游戏 data 目录。");
        Directory.CreateDirectory(outputRoot);
        var snapshot = configPath ?? Path.Combine(outputRoot, "config.toml");
        if (configPath is null) await WriteConfigSnapshotAsync(snapshot, ReadManifestScale(manifest), modDirectory, cancellationToken);
        await PrepareNativeModelAsync(modDirectory, snapshot, cancellationToken);
        var calibration = Path.Combine(outputRoot, "calibration");
        var result = await Hd2ModProcess.RunAsync(runner,
            ["-X", "utf8", script, "attachment-runtime", "--manifest", manifest,
             "--model-directory", Path.GetDirectoryName(manifest)!, "--game-data", gameData,
             "--output", calibration, "--config", snapshot], cancellationToken).ConfigureAwait(false);
        if (result.ExitCode != 0) throw new InvalidOperationException(Hd2ModProcess.Explain(result, "挂点修正生成"));
        using var report = JsonDocument.Parse(await File.ReadAllTextAsync(
            Path.Combine(calibration, "attachment-build-report.json"), cancellationToken));
        if (report.RootElement.GetProperty("status").GetString() != "complete")
            throw new InvalidDataException("挂点修正骨架报告不完整。");
        var profile = await File.ReadAllTextAsync(Path.Combine(calibration, "attachment-profile.lua"), cancellationToken);
        var feature = LuaAddonCatalog.AttachmentFix(profile) with
        {
            Title = VpkImportService.NativeGripFixPrefix + Path.GetFileName(modDirectory),
            ModGuid = new Guid(System.Security.Cryptography.MD5.HashData(
                Encoding.UTF8.GetBytes("attachment-fix:" + Path.GetFileName(modDirectory) + ":" +
                    report.RootElement.GetProperty("modelScale").ToString()))).ToString()
        };
        var exported = LuaAddonPackageExport.Export(outputRoot, feature);
        var patches = Path.Combine(exported, "patch版");
        foreach (var path in Directory.EnumerateFiles(patches, "*.patch_0*").ToArray())
            File.Move(path, path.Replace(".patch_0", ".patch_4", StringComparison.Ordinal));
        foreach (var path in Directory.EnumerateFiles(Path.Combine(calibration, "native-parenting")))
            File.Copy(path, Path.Combine(patches, Path.GetFileName(path)));
        File.Copy(Path.Combine(calibration, "attachment-build-report.json"), Path.Combine(patches, "attachment-build-report.json"));
        return exported;
    }

    internal static async Task<string> BuildAsync(
        string modDirectory,
        string outputRoot,
        Action<string, int, int, string>? onProgress,
        CancellationToken cancellationToken, int? sampleCount = null)
    {
        var manifest = FindManifest(modDirectory);
        var runner = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "runtime", "python.exe");
        var script = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "main.py");
        if (!File.Exists(runner) || !File.Exists(script))
            throw new FileNotFoundException("发布包缺少原生骨架转换的 Python 运行时或源码，无法生成骨架动画。");
        var gameData = SettingsService.GetGameDataFolder();
        if (string.IsNullOrWhiteSpace(gameData) || !Directory.Exists(gameData))
            throw new InvalidOperationException("请先在设置中配置 HD2 游戏 data 目录。");

        var working = Path.Combine(Path.GetTempPath(), "hd2anim-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(working);
        try
        {
            if (Directory.Exists(outputRoot) && Directory.EnumerateFileSystemEntries(outputRoot).Any())
                throw new IOException("动画输出目录必须为空，不覆盖已有工程。");
            var snapshot = Path.Combine(working, "config.toml");
            await WriteConfigSnapshotAsync(snapshot, ReadManifestScale(manifest), modDirectory, cancellationToken);
            await PrepareNativeModelAsync(modDirectory, snapshot, cancellationToken);
            var arguments = new List<string>
            {
                "-X", "utf8", script, "native-project",
                "--manifest", manifest,
                "--config", snapshot,
                "--game-data", gameData,
                "--output", outputRoot,
            };
            if (sampleCount is not null) arguments.AddRange(["--sample-count", sampleCount.Value.ToString(CultureInfo.InvariantCulture)]);
            var result = await Hd2ModProcess.RunAsync(runner, arguments, cancellationToken, onProgress)
                .ConfigureAwait(false);
            if (result.ExitCode != 0)
                throw new InvalidOperationException(Hd2ModProcess.Explain(result, "骨架动画生成"));
            VerifyReport(Path.Combine(outputRoot, "build-report.json"));
            var runtimeDirectory = Path.Combine(outputRoot, "runtime");
            WriteAnimationIdentity(runtimeDirectory, Path.GetFileName(modDirectory));
            File.Copy(snapshot, Path.Combine(runtimeDirectory, "config.toml"), true);
            File.Copy(Path.ChangeExtension(snapshot, ".provenance.json"), Path.Combine(runtimeDirectory, "config.provenance.json"), true);
            File.Copy(Path.Combine(outputRoot, "build-report.json"), Path.Combine(runtimeDirectory, "build-report.json"), true);
            return Path.Combine(outputRoot, "runtime");
        }
        finally
        {
            try { Directory.Delete(working, recursive: true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
        }
    }

    /// <summary>转换产物里的骨架清单：优先 <c>vpk2patch/</c> 载荷目录，其次 Mod 根。</summary>
    private static string FindManifest(string modDirectory)
    {
        foreach (var directory in new[]
        {
            Path.Combine(modDirectory, ModNodePayloadLayout.VpkPatchDirectoryName),
            modDirectory,
        })
        {
            if (!Directory.Exists(directory)) continue;
            var found = Directory.GetFiles(directory, "source-skeleton.json", SearchOption.TopDirectoryOnly);
            if (found.Length != 0) return found[0];
        }

        throw new FileNotFoundException("模型 Mod 里没有 source-skeleton.json：它不是原骨架转换产物，无法生成配套动画。");
    }

    private static double ReadManifestScale(string manifestPath)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(manifestPath, Encoding.UTF8));
        if (!document.RootElement.TryGetProperty("modelScale", out var value)) return 1;
        double scale;
        if (value.TryGetDouble(out var parsed)) scale = parsed;
        else if (value.ValueKind == JsonValueKind.String
            && double.TryParse(value.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var text)) scale = text;
        else return 1;
        return scale > 0 && scale <= 10 ? scale : 1;
    }

    /// <summary>
    /// 取与「原生骨架转换」同源的 config.toml，并把 <c>native_skeleton.model_scale</c>
    /// 强制对齐到清单里模型实际用的倍率——Python 侧两边不一致会直接拒绝构建。
    /// <c>attachment_swap</c> 缺键时强制补 true：ResolveConfig 优先读 Mod 目录自带的旧快照，
    /// 缺键会静默跳过挂点骨骼交换，让原比例模型与同步动作的挂点行为分叉；显式 false 仍然尊重。
    /// </summary>
    internal static async Task WriteConfigSnapshotAsync(string snapshotPath, double modelScale, string modDirectory,
        CancellationToken cancellationToken, string? sourceConfig = null)
    {
        var source = sourceConfig ?? NativeSkeletonProjectService.ResolveConfig(modDirectory);
        var runner = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "runtime", "python.exe");
        var script = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "main.py");
        var result = await Hd2ModProcess.RunAsync(runner,
            ["-X", "utf8", script, "prepare-config", "--config", source, "--output", snapshotPath,
             "--model-scale", modelScale.ToString("R", CultureInfo.InvariantCulture), "--manifest", FindManifest(modDirectory)], cancellationToken);
        if (result.ExitCode != 0) throw new InvalidDataException(Hd2ModProcess.Explain(result, "校准配置快照"));
    }

    internal static async Task PrepareNativeModelAsync(string modDirectory, string configPath, CancellationToken cancellationToken)
    {
        var manifest = FindManifest(modDirectory);
        var runner = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "runtime", "python.exe");
        var script = Path.Combine(AppContext.BaseDirectory, "anim_batch_mod", "main.py");
        var result = await Hd2ModProcess.RunAsync(runner,
            ["-X", "utf8", script, "prepare-native-model", "--manifest", manifest,
             "--model-directory", Path.GetDirectoryName(manifest)!, "--config", configPath], cancellationToken);
        if (result.ExitCode != 0) throw new InvalidDataException(Hd2ModProcess.Explain(result, "原武器骨准确握点重算"));
    }

    internal static void WriteAnimationIdentity(string directory, string modelName)
    {
        var name = VpkImportService.NativeAnimationName(modelName);
        var guid = new Guid(System.Security.Cryptography.MD5.HashData(Encoding.UTF8.GetBytes("native-animation:" + name)));
        File.WriteAllText(Path.Combine(directory, "manifest.json"), JsonSerializer.Serialize(new
        {
            Version = 1, Guid = guid.ToString(), Name = name, Description = "[全量动作文件]"
        }, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
    }

    internal static string EnsureAttachmentSwapDefault(string text)
        => Regex.IsMatch(text, @"(?m)^\s*attachment_swap\s*=") ? text
            : Regex.IsMatch(text, @"(?m)^\s*\[native_skeleton\]")
                ? Regex.Replace(text, @"(?m)^(\s*\[native_skeleton\][^\n]*)$", "$1\nattachment_swap = true")
                : text + "\n[native_skeleton]\nattachment_swap = true\n";

    private static void VerifyReport(string reportPath)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(reportPath, Encoding.UTF8));
        var root = document.RootElement;
        var complete = root.TryGetProperty("status", out var status) && status.GetString() == "complete";
        var built = root.TryGetProperty("animations", out var animations) ? animations.GetArrayLength() : -1;
        var expected = root.TryGetProperty("expected_animations", out var count) && count.TryGetInt32(out var parsed)
            ? parsed
            : -1;
        if (!complete || expected <= 0 || built != expected)
            throw new InvalidDataException($"骨架动画报告不完整（{built}/{expected} 条），动画 Mod 不能产出。");
    }
}
