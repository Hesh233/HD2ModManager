using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace HD2ModCore.Infrastructure;

/// <summary>Publishes both model-calibrated B3 packages together, never a half-completed delivery.</summary>
public static class NativeRuntimeCompanionPackageExport
{
    public const string PackagesDirectoryName = "packages";
    public const string BaseDirectoryName = "基础运行时";
    public const string PanelDirectoryName = "开关面板";
    public const string Schema = "hd2-grip-switches-v1";
    public const string RuntimeVersion = "1.0.19";
    public const string FirstPersonSourceVersion = "1.0.1";
    private static readonly UTF8Encoding Utf8 = new(false, true);
    private static readonly string[] ProfileNames =
        ["attachment-profile.json", "attachment-profile.lua", "first-person-source-profile.json", "attachment-fix.json"];
    private static readonly HashSet<string> CanonicalBones = new(StringComparer.Ordinal)
    {
        "attach_hand_r", "attach_hand_l", "attach_weapon", "attach_samplepouch", "attach_intelpad",
        "target_designator", "attach_knife", "sling", "backpack", "support_mg", "support",
        "cape1", "cape2", "cape3", "cape4", "cape5", "cape6", "cape7", "cape8", "hellpad_socket", "pistol",
    };
    public sealed record Result(string Directory, string BaseZip, string PanelZip, string Report);
    private sealed record VerifiedFile(string Name, byte[] Bytes, string Sha256);
    private sealed record Option(string Key, string Owner, string Folder, string Label, string Description);

    public static Result Export(string outputRoot, string calibrationDirectory, string modelName,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(outputRoot);
        ArgumentException.ThrowIfNullOrWhiteSpace(calibrationDirectory);
        ArgumentException.ThrowIfNullOrWhiteSpace(modelName);
        cancellationToken.ThrowIfCancellationRequested();
        var root = Path.GetFullPath(outputRoot);
        var calibration = Path.GetFullPath(calibrationDirectory);
        var delivery = Path.Combine(root, PackagesDirectoryName);
        if (Directory.Exists(delivery) || File.Exists(delivery))
            throw new IOException("不覆盖已有配套：" + delivery);
        var safeName = string.Concat(modelName.Select(c => Path.GetInvalidFileNameChars().Contains(c) ? '_' : c))
            .Trim().TrimEnd('.');
        if (string.IsNullOrWhiteSpace(safeName)) throw new InvalidDataException("模型名称无效。");

        // Snapshot and validate every calibration input before writing any package. A missing or
        // concurrently edited sidecar must not leave a completed base ZIP beside a broken panel.
        var buildBytes = File.ReadAllBytes(Path.Combine(calibration, "attachment-build-report.json"));
        VerifiedFile[] profiles, thirdPerson, firstPerson;
        string identity, modelIdentity;
        string[] bones;
        Option[] options;
        int fpCount;
        try
        {
            using var build = JsonDocument.Parse(buildBytes);
            var b = build.RootElement;
            var generated = b.GetProperty("runtimeCompanions");
            if (b.GetProperty("status").GetString() != "complete"
                || generated.GetProperty("version").GetString() != RuntimeVersion)
                throw new InvalidDataException("需要完整的生产 B3 模型校准，不接受旧版/测试报告。");
            profiles = ReadVerifiedFiles(calibration, ProfileNames, generated.GetProperty("profileFiles"), cancellationToken);
            using var document = JsonDocument.Parse(profiles.Single(f => f.Name == "attachment-profile.json").Bytes);
            using var fpDocument = JsonDocument.Parse(profiles.Single(f => f.Name == "first-person-source-profile.json").Bytes);
            using var settingsDocument = JsonDocument.Parse(profiles.Single(f => f.Name == "attachment-fix.json").Bytes);
            var p = document.RootElement;
            var fp = fpDocument.RootElement;
            var settings = settingsDocument.RootElement;
            if (p.TryGetProperty("testRepairs", out _) || fp.TryGetProperty("testRepairs", out _)
                || p.GetProperty("runtimeCompanionVersion").GetString() != RuntimeVersion
                || fp.GetProperty("version").GetString() != FirstPersonSourceVersion
                || fp.GetProperty("phase").GetString() != "production-b3"
                || !SameJson(p.GetProperty("firstPersonSource"), fp)
                || !SameJson(p.GetProperty("attachmentFixSettings"), settings))
                throw new InvalidDataException("B3 JSON、FP Source 与挂点设置不是同一份正式校准。");
            AttachmentRepairProfileContract.ValidateProfile(p);
            if (Utf8.GetString(profiles.Single(f => f.Name == "attachment-profile.lua").Bytes).Replace("\r\n", "\n", StringComparison.Ordinal) != AttachmentRepairProfileContract.ProfileToLua(p))
                throw new InvalidDataException("B3 Lua/profile JSON configuration mismatch.");
            var switches = p.GetProperty("optionSwitches");
            identity = switches.GetProperty("identity").GetString()!;
            modelIdentity = switches.GetProperty("modelIdentity").GetString()!;
            if (switches.GetProperty("schema").GetString() != Schema
                || !Regex.IsMatch(identity, "^[a-f0-9]{20}$") || !Regex.IsMatch(modelIdentity, "^[a-f0-9]{20}$")
                || generated.GetProperty("identity").GetString() != identity
                || settings.GetProperty("version").GetInt32() != 1
                || !settings.GetProperty("excludeHeadDescendants").GetBoolean()
                || switches.GetProperty("enabled").GetBoolean() != settings.GetProperty("enabled").GetBoolean()
                || !SameJson(switches.GetProperty("bones"), settings.GetProperty("bones")))
                throw new InvalidDataException("B3 模型标记、骨骼集合或开关设置不一致。");
            bones = switches.GetProperty("bones").EnumerateArray().Select(x => x.GetString()!).ToArray();
            var specs = switches.GetProperty("specs").EnumerateArray().ToArray();
            if (bones.Any(x => !CanonicalBones.Contains(x)) || bones.Distinct(StringComparer.Ordinal).Count() != bones.Length
                || specs.Length != bones.Length + 1 || specs.Length != generated.GetProperty("optionCount").GetInt32())
                throw new InvalidDataException("B3 选项数量、骨骼名称或顺序不一致。");
            options = specs.Select((spec, i) =>
            {
                var key = i == 0 ? "fp_arms" : "bone:" + bones[i - 1];
                var folder = "options/" + i.ToString("D2") + "-" + (i == 0 ? "fp-arms" : bones[i - 1]);
                var owner = "mods/hd2modmanager/grip_switches/m" + identity + "/" + key.Replace(':', '_');
                var label = spec.GetProperty("label").GetString();
                if (spec.GetProperty("key").GetString() != key || spec.GetProperty("folder").GetString() != folder
                    || spec.GetProperty("owner").GetString() != owner || string.IsNullOrWhiteSpace(label)
                    || i > 0 && spec.GetProperty("bone").GetString() != bones[i - 1])
                    throw new InvalidDataException("B3 选项目录、owner 或骨骼顺序无效。");
                return new Option(key, owner, folder, label!, spec.GetProperty("description").GetString() ?? "");
            }).ToArray();
            fpCount = fp.GetProperty("avatar").GetProperty("count").GetInt32();
            if (fp.GetProperty("side").GetString() != "both"
                || fp.GetProperty("avatar").GetProperty("resource").GetString() != "d0cf4d493ca08bed"
                || fp.GetProperty("avatar").GetProperty("nativeCount").GetInt32() != 63
                || generated.GetProperty("nativeFpCount").GetInt32() != 63
                || fp.GetProperty("animationChannels").GetInt32() != 47
                || generated.GetProperty("fpAnimationChannels").GetInt32() != 47
                || fp.GetProperty("animationChannelsAdded").GetInt32() != 0 || fpCount < 65
                || fpCount != generated.GetProperty("fpAvatarCount").GetInt32()
                || fp.GetProperty("sourceNodes").GetArrayLength() != fpCount - 64
                || fp.GetProperty("avatar").GetProperty("outputs").GetArrayLength() != fpCount - 63
                || fp.GetProperty("avatar").GetProperty("nativeGraph").GetArrayLength() != 63
                || fp.GetProperty("entry").GetProperty("index").GetInt32() != 63
                || fp.GetProperty("entry").GetProperty("parent").GetInt32() != 7
                || !fp.GetProperty("originalNativeIndicesPreserved").GetBoolean()
                || fp.GetProperty("modelChanged").GetBoolean() || fp.GetProperty("physicsNodesDriven").GetBoolean())
                throw new InvalidDataException("FP63/47 原生输入与独立 Source 输出契约不完整。");
            thirdPerson = ReadVerifiedFiles(Path.Combine(calibration, "native-parenting"), PatchNames("5"), b.GetProperty("files"), cancellationToken);
            firstPerson = ReadVerifiedFiles(Path.Combine(calibration, "first-person-parenting"), PatchNames("6"), generated.GetProperty("fpFiles"), cancellationToken);
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or InvalidOperationException
            or FormatException or ArgumentNullException or DecoderFallbackException)
        {
            throw new InvalidDataException("生产 B3 校准格式不完整或损坏。", error);
        }
        var source = PhysBoneLuaSource.ComposeB3AttachmentFixPackage(Utf8.GetString(profiles.Single(f => f.Name == "attachment-profile.lua").Bytes));
        cancellationToken.ThrowIfCancellationRequested();
        Directory.CreateDirectory(root);
        var staging = Path.Combine(root, ".runtime-companions-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        var baseName = safeName + "-基础运行时.zip";
        var panelName = safeName + "-开关面板.zip";
        const string reportName = "runtime-companions.json";
        try
        {
            var baseDirectory = Path.Combine(staging, BaseDirectoryName);
            var panelDirectory = Path.Combine(staging, PanelDirectoryName);
            Directory.CreateDirectory(baseDirectory);
            Directory.CreateDirectory(panelDirectory);
            LuaAddonPatchBuilder.Write(baseDirectory, LuaAddonCatalog.AttachmentFixAddonId, source);
            foreach (var file in Directory.GetFiles(baseDirectory, "*.patch_0*"))
                File.Move(file, file.Replace(".patch_0", ".patch_4", StringComparison.Ordinal));
            WriteFiles(baseDirectory, thirdPerson, cancellationToken);
            var baseGuid = StableGuid("base:" + modelIdentity);
            var baseTitle = "[基础运行时·必须启用]" + modelName;
            WriteJson(Path.Combine(baseDirectory, "manifest.json"), new
            {
                Version = 1, Guid = baseGuid, Name = baseTitle,
                Description = "生产 B3 " + RuntimeVersion + "；本模型基础始终独立启用，与模型、配套动画和开关面板配合。一次只启用一个 attachment_fix，物理独立。",
                Nodes = new[] { new { RelativePath = "", Guid = baseGuid, Name = baseTitle } },
            });
            WriteFiles(baseDirectory, profiles, cancellationToken);
            File.WriteAllBytes(Path.Combine(baseDirectory, "attachment-build-report.json"), buildBytes);
            var manifestOptions = new List<object>();
            var nodes = new List<object>();
            var panelGuid = StableGuid("panel:" + modelIdentity);
            var panelTitle = "[开关面板·FP与" + bones.Length + "骨]" + modelName;
            nodes.Add(new { RelativePath = "", Guid = panelGuid, Name = panelTitle });
            for (var i = 0; i < options.Length; i++)
            {
                cancellationToken.ThrowIfCancellationRequested();
                var option = options[i];
                var directory = Path.Combine(panelDirectory, option.Folder.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(directory);
                LuaAddonPatchBuilder.Write(directory, option.Owner,
                    "-- HD2-Addon: " + option.Owner + "\nreturn {version='1.0.0',schema='" + Schema + "',key='" + option.Key + "',enabled=true}\n");
                if (i == 0) WriteFiles(directory, firstPerson, cancellationToken);
                manifestOptions.Add(new { Name = option.Label, Description = option.Description, Include = new[] { option.Folder } });
                // Preserve semantic option identity when the author's canonical bone list is reordered.
                nodes.Add(new { RelativePath = option.Folder, Guid = StableGuid("option:" + modelIdentity + ":" + option.Key), Name = option.Label });
            }
            var panelOwner = "mods/hd2modmanager/grip_switches_panel/m" + identity;
            LuaAddonPatchBuilder.Write(panelDirectory, panelOwner,
                "-- HD2-Addon: " + panelOwner + "\nreturn {version='1.0.0',schema='hd2-grip-switches-panel-v1',panel=true}\n");
            WriteJson(Path.Combine(panelDirectory, "manifest.json"), new
            {
                Version = 1, Guid = panelGuid, Name = panelTitle,
                Description = "必须另启用本模型基础运行时。第一项控制 FP 双臂，后续按本模型 bones 顺序；TP 总设置不影响 FP 选项。更改后部署并完全重启。",
                Options = manifestOptions, Nodes = nodes,
            });
            var readme = "生产 B3 配套\n\n1. 分别导入本模型基础运行时 ZIP 与开关面板 ZIP，基础始终独立启用。\n"
                + "2. 面板第一项控制第一人称双臂，后续按本模型 bones 顺序控制 TP 挂点；首次导入核对所需选项。\n"
                + "3. 同时启用本模型与对应配套动画；基础运行时的 TP 骨架必须在动画之后胜出。一次只启用一个 attachment_fix。\n"
                + "4. 使用 Chef Shared Loader；选项在首次回调读取，修改后重新部署并完全重启游戏。\n"
                + "FP 关闭仅隐藏唯一原生匹配双臂并恢复原 mesh mask，不构造 Source 求解器，不写 Source pose 或相关刷新；FP 与 TP 开关独立。\n"
                + "物理运行时另为独立 ZIP，内置/外置二选一，不重复加载。生成与校准离线验证不等于本模型全部动作和游戏视觉已验收。\n";
            File.WriteAllText(Path.Combine(baseDirectory, "如何安装.txt"), readme, Utf8);
            File.WriteAllText(Path.Combine(panelDirectory, "如何安装.txt"), readme, Utf8);
            var baseEntries = BuildAndVerifyZip(baseDirectory, Path.Combine(staging, baseName), cancellationToken);
            var panelEntries = BuildAndVerifyZip(panelDirectory, Path.Combine(staging, panelName), cancellationToken);
            WriteJson(Path.Combine(staging, reportName), new
            {
                status = "complete", version = RuntimeVersion, firstPersonSourceVersion = FirstPersonSourceVersion,
                identity, modelIdentity, modelName, optionCount = options.Length, boneOrder = bones,
                firstPersonSourceCount = fpCount, gameTested = false,
                runtimeSourceSha256 = Hash(Utf8.GetBytes(source)),
                calibrationFiles = profiles.Select(f => new { name = f.Name, sha256 = f.Sha256 }),
                basePackage = new { directory = BaseDirectoryName, file = baseName, sha256 = FileHash(Path.Combine(staging, baseName)), entries = baseEntries },
                panelPackage = new { directory = PanelDirectoryName, file = panelName, sha256 = FileHash(Path.Combine(staging, panelName)), entries = panelEntries },
                physicalRuntimeEmbedded = false, fpGraphOnlyInFpOption = true, oneTransferRuntime = true,
                publishedTogether = true, markerIdentityBoundToCalibration = true,
            });
            cancellationToken.ThrowIfCancellationRequested();
            // Same-parent directory rename is the publication boundary for both ZIPs and their report.
            Directory.Move(staging, delivery);
            return new(delivery, Path.Combine(delivery, baseName), Path.Combine(delivery, panelName), Path.Combine(delivery, reportName));
        }
        catch
        {
            DeleteOwnStaging(root, staging);
            throw;
        }
    }

    private static VerifiedFile[] ReadVerifiedFiles(string directory, string[] names, JsonElement expected, CancellationToken token)
    {
        var records = expected.EnumerateArray().ToArray();
        if (records.Length != names.Length || records.Select(x => x.GetProperty("name").GetString()).Distinct(StringComparer.Ordinal).Count() != names.Length
            || records.Any(x => !names.Contains(x.GetProperty("name").GetString(), StringComparer.Ordinal)))
            throw new InvalidDataException("校准文件清单不完整、重复或含外部路径。");
        return names.Select(name =>
        {
            token.ThrowIfCancellationRequested();
            var bytes = File.ReadAllBytes(Path.Combine(directory, name));
            var sha = Hash(bytes);
            if (bytes.Length == 0 && !name.EndsWith(".stream", StringComparison.Ordinal) && !name.EndsWith(".gpu_resources", StringComparison.Ordinal)
                || !sha.Equals(records.Single(x => x.GetProperty("name").GetString() == name).GetProperty("sha256").GetString(), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("B3 校准内容发生变化：" + name);
            return new VerifiedFile(name, bytes, sha);
        }).ToArray();
    }
    private static string[] PatchNames(string number) =>
        [LuaAddonPatchBuilder.ArchiveId + ".patch_" + number, LuaAddonPatchBuilder.ArchiveId + ".patch_" + number + ".stream", LuaAddonPatchBuilder.ArchiveId + ".patch_" + number + ".gpu_resources"];
    private static void WriteFiles(string directory, VerifiedFile[] files, CancellationToken token)
    {
        foreach (var file in files) { token.ThrowIfCancellationRequested(); File.WriteAllBytes(Path.Combine(directory, file.Name), file.Bytes); }
    }
    private static bool SameJson(JsonElement a, JsonElement b) => JsonNode.DeepEquals(JsonNode.Parse(a.GetRawText()), JsonNode.Parse(b.GetRawText()));
    private static void WriteJson(string path, object value) => File.WriteAllText(path,
        JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }), Utf8);
    private static string StableGuid(string seed) => new Guid(MD5.HashData(Utf8.GetBytes("hd2-b3:" + seed))).ToString();
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static string FileHash(string path) { using var stream = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant(); }
    private static object[] BuildAndVerifyZip(string source, string path, CancellationToken token)
    {
        var files = Directory.GetFiles(source, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal).ToArray();
        var entries = files.Select(f => new { path = Path.GetRelativePath(source, f).Replace('\\', '/'), size = new FileInfo(f).Length, sha256 = FileHash(f) }).ToArray();
        using (var zip = ZipFile.Open(path, ZipArchiveMode.Create))
            for (var i = 0; i < files.Length; i++) { token.ThrowIfCancellationRequested(); zip.CreateEntryFromFile(files[i], entries[i].path, CompressionLevel.Optimal); }
        using (var zip = ZipFile.OpenRead(path))
        {
            if (zip.Entries.Count != entries.Length) throw new InvalidDataException("配套 ZIP 条目数不一致。");
            foreach (var item in entries)
            {
                token.ThrowIfCancellationRequested();
                var entry = zip.GetEntry(item.path) ?? throw new InvalidDataException("缺 ZIP 条目。");
                using var stream = entry.Open();
                if (entry.Length != item.size || !Convert.ToHexString(SHA256.HashData(stream)).Equals(item.sha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("配套 ZIP 回读失败：" + item.path);
            }
        }
        return entries;
    }
    private static void DeleteOwnStaging(string root, string staging)
    {
        if (!string.Equals(Path.GetDirectoryName(Path.GetFullPath(staging)), root, StringComparison.OrdinalIgnoreCase)
            || !Path.GetFileName(staging).StartsWith(".runtime-companions-", StringComparison.Ordinal))
            throw new IOException("拒绝清理工作区以外的临时配套目录。");
        if (Directory.Exists(staging)) Directory.Delete(staging, recursive: true);
    }
}
