using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class NativeRuntimeCompanionPackageTests
{
    private const string Identity = "aaaaaaaaaaaaaaaaaaaa";

    [Fact]
    public void ProducesIndependentBaseAndPanelWithFpOnlyInFirstOption() => InTemp(root =>
    {
        var result = Export(root);
        using var b = ZipFile.OpenRead(result.BaseZip);
        using var panel = ZipFile.OpenRead(result.PanelZip);
        Assert.Contains(b.Entries, e => e.FullName == "manifest.json");
        Assert.Contains(b.Entries, e => e.FullName == "9ba626afa44a3aa3.patch_4");
        Assert.Contains(b.Entries, e => e.FullName == "9ba626afa44a3aa3.patch_5");
        Assert.DoesNotContain(b.Entries, e => e.FullName.Contains("patch_6", StringComparison.Ordinal));
        Assert.DoesNotContain(panel.Entries, e => e.FullName.Contains("patch_4", StringComparison.Ordinal));
        Assert.Contains(panel.Entries, e => e.FullName == "options/00-fp-arms/9ba626afa44a3aa3.patch_6");
        Assert.Equal(1, panel.Entries.Count(e => e.FullName.EndsWith(".patch_6", StringComparison.Ordinal)));
        Assert.Contains(b.Entries, e => e.FullName == "attachment-profile.lua");
        using var m = Manifest(result.PanelZip);
        Assert.Equal(3, m.RootElement.GetProperty("Options").GetArrayLength());
        Assert.Equal("options/00-fp-arms", m.RootElement.GetProperty("Options")[0].GetProperty("Include")[0].GetString());
        using var report = JsonDocument.Parse(File.ReadAllText(result.Report));
        Assert.Equal("complete", report.RootElement.GetProperty("status").GetString());
        Assert.True(report.RootElement.GetProperty("publishedTogether").GetBoolean());
        Assert.False(report.RootElement.GetProperty("gameTested").GetBoolean());
        Assert.Empty(Directory.GetDirectories(Path.GetDirectoryName(result.Directory)!, ".runtime-companions-*"));
    });

    [Fact]
    public void ProductionComposerIsCompleteAndIndependentFromPhysics()
    {
        var source = PhysBoneLuaSource.ComposeB3AttachmentFixPackage("return {runtimeCompanionVersion='1.0.19'}");
        Assert.StartsWith("-- HD2-Addon: mods/hd2modmanager/attachment_fix\n", source, StringComparison.Ordinal);
        Assert.DoesNotContain("-- INSERT ", source, StringComparison.Ordinal);
        Assert.Contains("local OptionSwitches=", source, StringComparison.Ordinal);
        Assert.Contains("local FirstPersonSource=", source, StringComparison.Ordinal);
        Assert.Contains("local HiddenFirstPerson=", source, StringComparison.Ordinal);
        Assert.Contains("local testRun=false", source, StringComparison.Ordinal);
        Assert.DoesNotContain("local PhysBoneRuntime", source, StringComparison.Ordinal);
        Assert.DoesNotContain("1.0.19-test", source, StringComparison.Ordinal);
    }

    [Fact]
    public void TestProfilesAreRejectedBeforeAnyPackageCreation() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        EditJson(c, "attachment-profile.json", p => p["testRepairs"] = new JsonObject { ["enabled"] = true });
        RefreshProfileHashes(c);
        AssertRejected(root, c);
    });

    [Fact]
    public void MissingFpTripletCannotProduceCompletedZip() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        File.Delete(Path.Combine(c, "first-person-parenting", "9ba626afa44a3aa3.patch_6.stream"));
        Assert.Throws<FileNotFoundException>(() => NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "output"), c, "Example"));
        Assert.False(Directory.Exists(Path.Combine(root, "output")));
    });

    [Fact]
    public void CalibrationHashMismatchIsRejectedBeforeWriting() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        File.AppendAllText(Path.Combine(c, "native-parenting", "9ba626afa44a3aa3.patch_5"), "corruption");
        AssertRejected(root, c);
    });

    [Fact]
    public void JsonAndLuaCalibrationHashMismatchIsRejected() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        File.AppendAllText(Path.Combine(c, "attachment-profile.lua"), "-- stale\n");
        AssertRejected(root, c);
    });

    [Fact]
    public void DifferentModelsHaveDifferentPackageGuids() => InTemp(root =>
    {
        var a = NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "a"), Fixture(Path.Combine(root, "a-cal"), Identity), "A");
        var b = NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "b"), Fixture(Path.Combine(root, "b-cal"), "bbbbbbbbbbbbbbbbbbbb"), "B");
        Assert.NotEqual(GuidOf(a.BaseZip), GuidOf(b.BaseZip));
        Assert.NotEqual(GuidOf(a.PanelZip), GuidOf(b.PanelZip));
        Assert.NotEqual(GuidOf(a.BaseZip), GuidOf(a.PanelZip));
    });

    [Fact]
    public void RebuildDoesNotOverwritePreviousCompanions() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        var result = NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "output"), c, "Example");
        var hash = Hash(File.ReadAllBytes(result.BaseZip));
        Assert.Throws<IOException>(() => NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "output"), c, "Example"));
        Assert.Equal(hash, Hash(File.ReadAllBytes(result.BaseZip)));
    });

    [Fact]
    public void PackageGuidsRemainStableAcrossNewCalibrationIdentities() => InTemp(root =>
    {
        var a = NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "a"), Fixture(Path.Combine(root, "a-cal"), Identity), "A");
        var b = NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "b"), Fixture(Path.Combine(root, "b-cal"), "bbbbbbbbbbbbbbbbbbbb", modelIdentity: Identity), "A changed scale/armor");
        Assert.Equal(GuidOf(a.BaseZip), GuidOf(b.BaseZip));
        Assert.Equal(GuidOf(a.PanelZip), GuidOf(b.PanelZip));
        using var za = ZipFile.OpenRead(a.PanelZip);
        using var zb = ZipFile.OpenRead(b.PanelZip);
        Assert.Contains("m" + Identity + "/fp_arms", PatchText(za, "options/00-fp-arms/9ba626afa44a3aa3.patch_0"));
        Assert.Contains("mbbbbbbbbbbbbbbbbbbbb/fp_arms", PatchText(zb, "options/00-fp-arms/9ba626afa44a3aa3.patch_0"));
    });

    [Fact]
    public void SemanticOptionGuidsSurviveBoneListReordering() => InTemp(root =>
    {
        var a = Export(Path.Combine(root, "a"));
        var b = NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "b", "output"),
            Fixture(Path.Combine(root, "b"), Identity, ["attach_hand_l", "attach_hand_r"]), "Example");
        using var ma = Manifest(a.PanelZip);
        using var mb = Manifest(b.PanelZip);
        string NodeGuid(JsonDocument d, string name) => d.RootElement.GetProperty("Nodes").EnumerateArray()
            .Single(n => n.GetProperty("Name").GetString() == name).GetProperty("Guid").GetString()!;
        foreach (var bone in new[] { "attach_hand_l", "attach_hand_r" }) Assert.Equal(NodeGuid(ma, bone), NodeGuid(mb, bone));
        Assert.Equal(3, mb.RootElement.GetProperty("Options").GetArrayLength());
    });

    [Theory]
    [InlineData("phase", "test-source")]
    [InlineData("animationChannels", 48)]
    [InlineData("animationChannelsAdded", 1)]
    [InlineData("originalNativeIndicesPreserved", false)]
    [InlineData("modelChanged", true)]
    [InlineData("physicsNodesDriven", true)]
    public void BrokenFpContractsAreRejected(string key, object value) => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        EditJson(c, "first-person-source-profile.json", p => p[key] = JsonSerializer.SerializeToNode(value));
        var fp = JsonNode.Parse(File.ReadAllText(Path.Combine(c, "first-person-source-profile.json")))!;
        EditJson(c, "attachment-profile.json", p => p["firstPersonSource"] = fp.DeepClone());
        RefreshProfileHashes(c);
        AssertRejected(root, c);
    });

    [Fact]
    public void IndependentFpJsonMustMatchEmbeddedFpContract() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        EditJson(c, "first-person-source-profile.json", p => p["animationChannels"] = 48);
        RefreshProfileHashes(c);
        AssertRejected(root, c);
    });

    [Fact]
    public void ForeignMarkerOwnerIsRejected() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        EditJson(c, "attachment-profile.json", p => p["optionSwitches"]!["specs"]![0]!["owner"] = "mods/foreign/fp_arms");
        RefreshProfileHashes(c);
        AssertRejected(root, c);
    });

    [Fact]
    public void HeadOrUnknownAttachmentCannotBeReleased() => InTemp(root => AssertRejected(root, Fixture(root, Identity, ["attach_head"])));

    [Fact]
    public void DuplicateOrEscapingReportPathsAreRejected() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        EditJson(c, "attachment-build-report.json", p => p["runtimeCompanions"]!["profileFiles"]![0]!["name"] = "../outside.json");
        AssertRejected(root, c);
    });

    [Fact]
    public void MalformedCalibrationIsReportedAsInvalidData() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        EditJson(c, "attachment-build-report.json", p => p.AsObject().Remove("runtimeCompanions"));
        AssertRejected(root, c);
    });

    [Fact]
    public void CancellationCannotPublishEitherZip() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        using var cancel = new CancellationTokenSource();
        cancel.Cancel();
        Assert.Throws<OperationCanceledException>(() => NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "output"), c, "Example", cancel.Token));
        Assert.False(Directory.Exists(Path.Combine(root, "output")));
    });

    [Fact]
    public void WriteFailureCleansStagingAndCanBeRetried() => InTemp(root =>
    {
        var c = Fixture(root, Identity);
        var output = Path.Combine(root, "output");
        Assert.ThrowsAny<IOException>(() => NativeRuntimeCompanionPackageExport.Export(output, c, new string('x', 600)));
        Assert.False(Directory.Exists(Path.Combine(output, NativeRuntimeCompanionPackageExport.PackagesDirectoryName)));
        Assert.Empty(Directory.GetDirectories(output, ".runtime-companions-*"));
        Assert.True(File.Exists(NativeRuntimeCompanionPackageExport.Export(output, c, "Retry").PanelZip));
    });

    [Fact]
    public async Task GeneratedZipPairImportsAsIndependentRootsWithFpPayloadOnlyOnFpOption()
    {
        var root = NewTemp();
        try
        {
            var result = Export(root);
            var paths = new StoragePaths(Path.Combine(root, "app"));
            Directory.CreateDirectory(paths.AppRootDirectory);
            var importer = new ModLibraryImporter(paths, new ObjectTreeImporter(new PatchFileNameParser()),
                new ArchiveObjectTreeImporter(new ObjectTreeImporter(new PatchFileNameParser())), new JsonModLibraryStore(paths));
            await importer.ImportArchiveAsync(result.BaseZip);
            var imported = await importer.ImportArchiveAsync(result.PanelZip);
            var standards = imported.Snapshot.Nodes.Values.Where(n => n.Metadata.Kind == ModNodeKind.Standard).ToArray();
            var options = imported.Snapshot.Nodes.Values.Where(n => n.Metadata.Kind == ModNodeKind.Option).ToArray();
            Assert.Equal(2, standards.Length);
            Assert.Equal(3, options.Length);
            var baseNode = Assert.Single(standards, n => n.Metadata.Name!.StartsWith("[基础运行时", StringComparison.Ordinal));
            var panelNode = Assert.Single(standards, n => n.Metadata.Name!.StartsWith("[开关面板", StringComparison.Ordinal));
            Assert.Equal(GuidOf(result.BaseZip), baseNode.Id.Value.ToString());
            Assert.Equal(GuidOf(result.PanelZip), panelNode.Id.Value.ToString());
            Assert.Equal(2, baseNode.PatchGroups.Count);
            Assert.Single(panelNode.PatchGroups);
            var fpNode = Assert.Single(options, n => n.Metadata.Name == "开启第一人称手臂");
            Assert.Equal(2, fpNode.PatchGroups.Count);
            Assert.All(options, n => Assert.Equal(panelNode.Id.Value.ToString("N"), Assert.Single(n.Metadata.HostModGuids!)));
            Assert.All(options.Where(n => n.Id != fpNode.Id), n => Assert.Single(n.PatchGroups));
            var fpFiles = Directory.GetFiles(paths.ModsDirectory, "*.patch_*", SearchOption.AllDirectories)
                .Where(f => File.ReadAllBytes(f).SequenceEqual(new byte[] { 6, 2, 3 })).ToArray();
            Assert.Equal(Path.Combine(paths.ModsDirectory, fpNode.RelativePath), Path.GetDirectoryName(Assert.Single(fpFiles)));
            var activations = new OptionActivationStore(Path.Combine(root, "option-activations.json"));
            await new OptionActivationDefaultInitializer().InitializeMissingStatesAsync(imported.Snapshot, activations, [panelNode.Id]);
            await activations.SetEnabledAsync(fpNode.Id.Value.ToString("N"), panelNode.Id.Value.ToString("N"), false);
            await new OptionActivationDefaultInitializer().InitializeMissingStatesAsync(imported.Snapshot, activations, [panelNode.Id]);
            Assert.False(activations.CreateSnapshot().IsEnabled(fpNode.Id.Value.ToString("N"), panelNode.Id.Value.ToString("N")));
            Assert.All(options.Where(n => n.Id != fpNode.Id), n => Assert.True(activations.CreateSnapshot().IsEnabled(n.Id.Value.ToString("N"), panelNode.Id.Value.ToString("N"))));
        }
        finally { DeleteTemp(root); }
    }

    private static NativeRuntimeCompanionPackageExport.Result Export(string root) =>
        NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "output"), Fixture(root, Identity), "Example");
    private static void AssertRejected(string root, string calibration)
    {
        Assert.Throws<InvalidDataException>(() => NativeRuntimeCompanionPackageExport.Export(Path.Combine(root, "output"), calibration, "Example"));
        Assert.False(Directory.Exists(Path.Combine(root, "output")));
    }
    private static JsonDocument Manifest(string path) { using var z = ZipFile.OpenRead(path); return JsonDocument.Parse(z.GetEntry("manifest.json")!.Open()); }
    private static string GuidOf(string path) { using var m = Manifest(path); return m.RootElement.GetProperty("Guid").GetString()!; }
    private static string PatchText(ZipArchive z, string name) { using var s = z.GetEntry(name)!.Open(); using var r = new StreamReader(s); return r.ReadToEnd(); }
    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes));
    private static void Json(string path, object value) => File.WriteAllText(path, JsonSerializer.Serialize(value), new UTF8Encoding(false));
    private static void EditJson(string calibration, string name, Action<JsonNode> edit)
    {
        var path = Path.Combine(calibration, name); var node = JsonNode.Parse(File.ReadAllText(path))!;
        edit(node); File.WriteAllText(path, node.ToJsonString(), new UTF8Encoding(false));
    }
    private static void RefreshProfileHashes(string c) => EditJson(c, "attachment-build-report.json", b =>
        b["runtimeCompanions"]!["profileFiles"] = JsonSerializer.SerializeToNode(new[]
        { "attachment-profile.json", "attachment-profile.lua", "first-person-source-profile.json", "attachment-fix.json" }
            .Select(name => new { name, sha256 = Hash(File.ReadAllBytes(Path.Combine(c, name))) }).ToArray()));
    private static string Fixture(string root, string id, string[]? bones = null, string? modelIdentity = null)
    {
        var c = Path.Combine(root, "calibration"); Directory.CreateDirectory(c);
        object[] Patches(string folder, string patch)
        {
            var directory = Path.Combine(c, folder); Directory.CreateDirectory(directory);
            return new[] { "", ".stream", ".gpu_resources" }.Select(s =>
            {
                var name = "9ba626afa44a3aa3.patch_" + patch + s;
                var path = Path.Combine(directory, name); File.WriteAllBytes(path, s.Length == 0 ? [(byte)int.Parse(patch), 2, 3] : []);
                return (object)new { name, sha256 = Hash(File.ReadAllBytes(path)) };
            }).ToArray();
        }
        var tpFiles = Patches("native-parenting", "5"); var fpFiles = Patches("first-person-parenting", "6");
        bones ??= ["attach_hand_r", "attach_hand_l"];
        var specs = new[] { new { key = "fp_arms", label = "开启第一人称手臂", folder = "options/00-fp-arms", description = "FP", owner = "mods/hd2modmanager/grip_switches/m" + id + "/fp_arms", bone = "" } }
            .Concat(bones.Select((bone, i) => new { key = "bone:" + bone, label = bone, folder = "options/" + (i + 1).ToString("D2") + "-" + bone, description = bone, owner = "mods/hd2modmanager/grip_switches/m" + id + "/bone_" + bone, bone })).ToArray();
        var settings = new { version = 1, enabled = true, bones, excludeHeadDescendants = true };
        var source = new[] { new { index = 64, parent = 63 }, new { index = 65, parent = 64 } };
        var entry = new { index = 63, parent = 7 };
        var fpContract = new { version = "1.0.1", phase = "production-b3", side = "both", entry, sourceNodes = source,
            avatar = new { resource = "d0cf4d493ca08bed", nativeCount = 63, count = 66, outputs = new object[] { entry, source[0], source[1] }, nativeGraph = Enumerable.Range(0, 63).Select(index => new { index }).ToArray() },
            animationChannels = 47, animationChannelsAdded = 0, originalNativeIndicesPreserved = true, modelChanged = false, physicsNodesDriven = false };
        Json(Path.Combine(c, "attachment-profile.json"), new { runtimeCompanionVersion = "1.0.19", optionSwitches = new { schema = "hd2-grip-switches-v1", identity = id, modelIdentity = modelIdentity ?? id, enabled = true, bones, specs }, firstPersonSource = fpContract, attachmentFixSettings = settings });
        Json(Path.Combine(c, "first-person-source-profile.json"), fpContract); Json(Path.Combine(c, "attachment-fix.json"), settings);
        File.WriteAllText(Path.Combine(c, "attachment-profile.lua"), "return {runtimeCompanionVersion='1.0.19'}\n", new UTF8Encoding(false));
        Json(Path.Combine(c, "attachment-build-report.json"), new { status = "complete", files = tpFiles,
            runtimeCompanions = new { version = "1.0.19", identity = id, optionCount = specs.Length, fpAvatarCount = 66, nativeFpCount = 63, fpAnimationChannels = 47, fpFiles, profileFiles = Array.Empty<object>() } });
        var profilePath = Path.Combine(c, "attachment-profile.json");
        var p = JsonNode.Parse(File.ReadAllText(profilePath))!.AsObject();
        var shared = JsonNode.Parse(AttachmentRepairProfileContract.SharedPolicyBytes())!.AsObject();
        var repair = shared["settings"]!.DeepClone().AsObject();
        repair["enabled"] = true; repair["schema"] = AttachmentRepairProfileContract.Schema;
        repair["revision"] = AttachmentRepairProfileContract.Revision; repair["version"] = "1.0.19";
        repair["sharedPolicySha256"] = AttachmentRepairProfileContract.SharedPolicySha256;
        var contacts = JsonSerializer.SerializeToNode(new { left = new { native = new[] { .05, .01, .01 }, source = new[] { .06, .01, .01 } }, right = new { native = new[] { .05, .01, .01 }, source = new[] { .06, .01, .01 } } })!;
        repair["contacts"] = contacts;
        var contactText = "{\"left\":{\"native\":[0.05,0.01,0.01],\"source\":[0.06,0.01,0.01]},\"right\":{\"native\":[0.05,0.01,0.01],\"source\":[0.06,0.01,0.01]}}";
        repair["calibration"] = JsonSerializer.SerializeToNode(new { @namespace = "hd2n_fixture", modelSpecific = true, nativeBindSha256 = new string('a',64), sourceBindsSha256 = new string('b',64), avatarBindSha256 = new string('c',64), contactsSha256 = Hash(Encoding.UTF8.GetBytes(contactText)).ToLowerInvariant() });
        repair["sourceFkRefresh"] = JsonSerializer.SerializeToNode(new { enabled = true, levels = new[] { new[] { new { name = "hd2n_fixture_neck", index = 1 }, new { name = "hd2n_fixture_l_clavicle", index = 2 }, new { name = "hd2n_fixture_r_clavicle", index = 3 } } } });
        p["repairPolicy"] = repair; p["consumers"] = shared["fixedConsumers"]!.DeepClone(); p["allowedConsumers"] = shared["allowedConsumers"]!.DeepClone();
        var weapon = shared["weaponPolicies"]!.AsObject(); var weaponTargets = new JsonObject();
        foreach (var item in weapon["leftPolicies"]!.AsObject()) weaponTargets[item.Key] = new JsonObject { ["leftPolicy"] = item.Value!.DeepClone() };
        foreach (var item in weapon["nativeRightTargets"]!.AsObject())
        {
            var target = item.Value!.DeepClone().AsObject(); target["rootToIKRight"] = new JsonArray(1,0,0,0,1,0,0,0,1,0,0,0); weaponTargets[item.Key] = target;
        }
        p["gripFixes"] = new JsonObject { ["sidearms"] = weapon["sidearms"]!.DeepClone() };
        p["leftGrip"] = new JsonObject { ["weaponTargets"] = weaponTargets, ["intent"] = new JsonObject { ["weaponThresholds"] = weapon["intentWeaponThresholds"]!.DeepClone() } };
        p["variant"] = "hd2n_fixture-production-b3-1.0.19"; p["avatar"] = new JsonObject { ["count"] = 100 };
        File.WriteAllText(profilePath, p.ToJsonString());
        using (var profileDocument = JsonDocument.Parse(p.ToJsonString()))
            File.WriteAllText(Path.Combine(c, "attachment-profile.lua"), AttachmentRepairProfileContract.ProfileToLua(profileDocument.RootElement), new UTF8Encoding(false));
        RefreshProfileHashes(c);
        return c;
    }
    [Theory]
    [InlineData("missing-policy")]
    [InlineData("missing-consumer")]
    [InlineData("missing-allow")]
    [InlineData("contact-tamper")]
    [InlineData("wrong-fk-model")]
    [InlineData("stale-lua")]
    [InlineData("missing-stock-policy")]
    [InlineData("missing-c4")]
    public void ProductionRepairAndLuaGapsFailBeforePublication(string mutation) => InTemp(root =>
    {
        var c = Fixture(root, Identity); var path = Path.Combine(c, "attachment-profile.json");
        var p = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        switch (mutation)
        {
            case "missing-policy": p.Remove("repairPolicy"); break;
            case "missing-consumer": p["consumers"]!.AsObject().Remove("503c0e01fbafa86a"); break;
            case "missing-allow": p["allowedConsumers"]!.AsObject().Remove("16051937941bb709"); break;
            case "contact-tamper": p["repairPolicy"]!["contacts"]!["left"]!["source"]![0] = .08; break;
            case "wrong-fk-model": p["repairPolicy"]!["sourceFkRefresh"]!["levels"]![0]![0]!["name"] = "another_model_neck"; break;
            case "missing-stock-policy": p["leftGrip"]!["weaponTargets"]!["027dec442cc26a90"]!["leftPolicy"] = "aim_only"; break;
            case "missing-c4": p["gripFixes"]!["sidearms"]!.AsObject().Remove("51f50d6321f52f3d"); break;
            case "stale-lua": File.WriteAllText(Path.Combine(c, "attachment-profile.lua"), "return {}\n"); break;
        }
        File.WriteAllText(path, p.ToJsonString()); RefreshProfileHashes(c); AssertRejected(root, c);
    });

    private static string NewTemp()
    {
        var root = Path.Combine(Path.GetTempPath(), "hd2-b3-production-tests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root); return root;
    }
    private static void InTemp(Action<string> test) { var root = NewTemp(); try { test(root); } finally { DeleteTemp(root); } }
    private static void DeleteTemp(string root)
    {
        var full = Path.GetFullPath(root);
        if (!string.Equals(Path.GetDirectoryName(full), Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.GetTempPath())), StringComparison.OrdinalIgnoreCase)
            || !Path.GetFileName(full).StartsWith("hd2-b3-production-tests-", StringComparison.Ordinal)) throw new IOException("Unsafe test cleanup");
        foreach (var file in Directory.EnumerateFiles(full, "*", SearchOption.AllDirectories)) File.SetAttributes(file, FileAttributes.Normal);
        Directory.Delete(full, recursive: true);
    }
}
