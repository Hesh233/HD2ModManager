using System.Buffers.Binary;
using System.Text.Json;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;

namespace HD2ModCore.Tests;

public sealed class CustomModelSourceDeploymentTests : IDisposable
{
    private const string Name = "9ba626afa44a3aa3.patch_0";
    private const ulong CustomUnit = 0x4718af954e550001;
    private const ulong TargetUnit = 0xa152e9ef3754a3d0;
    private readonly string root = Path.Combine(Path.GetTempPath(), "hd2-custom-source-" + Guid.NewGuid().ToString("N"));
    private readonly ModNodeId id = ModNodeId.New();
    private string Mod => Path.Combine(root, "model");
    private string Overwrite => Path.Combine(Mod, "Overwrite");
    private string Payload(string layout) => Path.Combine(Mod, layout);
    private LibrarySnapshot Snapshot => new(1, DateTimeOffset.UtcNow,
        new Dictionary<ModNodeId, ModNode> { [id] = new(id, "model", new("model", null, DateTimeOffset.UtcNow, null), [], []) }, []);
    private static RuntimeArmorRegistryModel Model => new("custom-test", null,
        [new RuntimeArmorRegistryModelPiece(3, "4718af954e550001", 0, 0, 0)], "model");

    [Theory]
    [InlineData("sectional")]
    [InlineData("vpk2patch")]
    public async Task Rekey_PreservesSourceBeforeEffectivePayload_AndMappingWorks(string layout)
    {
        Setup(layout);
        var before = Directory.GetFiles(Mod, "*", SearchOption.AllDirectories).ToDictionary(p => p, File.ReadAllBytes);
        var index = await new PatchFileIndexBuilder(new PatchFileNameParser()).BuildAsync(Snapshot, root);
        Assert.Empty(index.Issues);
        var files = index.FilesByNode[id];
        Assert.Equal(4, files.Count);
        Assert.All(files.Where(f => f.FilePath.StartsWith(Payload(layout), StringComparison.Ordinal)), f => Assert.True(f.NormalizedOrder < 0 && f.DeployOrder < 0));
        var data = Path.Combine(root, "data"); Directory.CreateDirectory(data);
        var profile = new Profile(ProfileId.New(), "test", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, [new ProfileEntry(id, 0, DateTimeOffset.UtcNow)], 1);
        var plan = await new ApplyPlanner(new PatchFileNameParser()).BuildPlanAsync(profile, Snapshot, index, data);
        var bases = plan.PatchMappings.Where(m => m.SidecarKind == PatchSidecarKind.Base).ToArray();
        Assert.Equal(Path.Combine(Payload(layout), Name), bases[0].SourcePath);
        Assert.Equal(Path.Combine(Overwrite, Name), bases[1].SourcePath);
        // Isolated copy of the plan, never an actual game deployment.
        foreach (var mapping in plan.PatchMappings) File.Copy(mapping.SourcePath, mapping.TargetPath);
        var available = await RuntimeArmorResourceFilter.ReadDeployedUnitsAsync(data);
        Assert.Contains(CustomUnit, available); Assert.Contains(TargetUnit, available);
        var desired = new RuntimeArmorRegistryDocument(1, true, [new RuntimeArmorRegistryMapping(123, null, Model.Key)], [Model]);
        Assert.Single(RuntimeArmorResourceFilter.Compile(desired, available).Mappings);
        Assert.Throws<InvalidDataException>(() => RuntimeArmorResourceFilter.Compile(desired, new HashSet<ulong>()));
        foreach (var pair in before) Assert.Equal(pair.Value, File.ReadAllBytes(pair.Key));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task NoRekeyOrSelfTarget_DoesNotAddDuplicateSource(bool selfTarget)
    {
        Setup("sectional", selfTarget ? CustomUnit : TargetUnit);
        if (!selfTarget) File.Delete(Path.Combine(Overwrite, ".hd2-vpk-rekey-overwrite"));
        var files = (await new PatchFileIndexBuilder(new PatchFileNameParser()).BuildAsync(Snapshot, root)).FilesByNode[id];
        Assert.Equal(2, files.Count); Assert.All(files, f => Assert.True(f.NormalizedOrder >= 0));
    }

    [Theory]
    [InlineData("missing-gpu")]
    [InlineData("wrong-unit")]
    [InlineData("truncated")]
    public async Task BrokenSource_FailsClosedWithoutWriting(string failure)
    {
        Setup("sectional");
        var source = Path.Combine(Payload("sectional"), Name);
        if (failure == "missing-gpu") File.Delete(source + ".gpu_resources");
        if (failure == "wrong-unit") WritePatch(source, TargetUnit);
        if (failure == "truncated") File.WriteAllBytes(source, [1, 2]);
        var index = await new PatchFileIndexBuilder(new PatchFileNameParser()).BuildAsync(Snapshot, root);
        Assert.Contains(index.Issues, i => i.Code == "CustomModelSourceDeploymentInvalid" && i.Severity == CoreIssueSeverity.Error);
        Assert.All(index.FilesByNode[id], f => Assert.StartsWith(Overwrite, f.FilePath, StringComparison.Ordinal));
    }

    [Fact]
    public void FileFactsGeneration_RetiresLegacyCacheWithoutDeletingIt()
    {
        var empty = new LibrarySnapshot(1, DateTimeOffset.UtcNow, new Dictionary<ModNodeId, ModNode>(), []);
        var method = typeof(ModInformationCenter).GetMethod("ComputeFileGeneration", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!;
        var result = (string)method.Invoke(null, [empty, root])!;
        var expected = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes("filefacts-custom-namespace-r1\n"))).ToLowerInvariant();
        Assert.Equal(expected, result);
        Assert.NotEqual(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData([])).ToLowerInvariant(), result);
        Assert.False(Directory.Exists(root));
    }

    [Fact]
    public async Task SourceDependencyGroups_PrecedeBothEffectiveGroups()
    {
        Setup("sectional");
        var extra = Name.Replace("patch_0", "patch_1");
        WritePatch(Path.Combine(Payload("sectional"), extra), CustomUnit);
        WritePatch(Path.Combine(Overwrite, extra), TargetUnit);
        var index = await new PatchFileIndexBuilder(new PatchFileNameParser()).BuildAsync(Snapshot, root);
        var profile = new Profile(ProfileId.New(), "test", DateTimeOffset.UtcNow, null, [new ProfileEntry(id, 0)]);
        var plan = await new ApplyPlanner(new PatchFileNameParser()).BuildPlanAsync(profile, Snapshot, index, Path.Combine(root, "not-created"));
        var bases = plan.PatchMappings.Where(m => m.SidecarKind == PatchSidecarKind.Base).ToArray();
        Assert.Equal(4, bases.Length);
        Assert.All(bases.Take(2), m => Assert.StartsWith(Payload("sectional"), m.SourcePath, StringComparison.Ordinal));
        Assert.All(bases.Skip(2), m => Assert.StartsWith(Overwrite, m.SourcePath, StringComparison.Ordinal));
        Assert.Equal([0, 1, 2, 3], bases.Select(m => m.TargetPatchIndex).ToArray());
    }

    private void Setup(string layout, ulong target = TargetUnit)
    {
        Directory.CreateDirectory(Payload(layout)); Directory.CreateDirectory(Overwrite);
        File.WriteAllText(Path.Combine(Overwrite, ".hd2-vpk-rekey-overwrite"), "managed");
        File.WriteAllText(Path.Combine(Payload(layout), "custom-model.json"), JsonSerializer.Serialize(Model, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        WritePatch(Path.Combine(Payload(layout), Name), CustomUnit);
        WritePatch(Path.Combine(Overwrite, Name), target);
    }
    private static void WritePatch(string path, ulong unit)
    {
        var bytes = new byte[180];
        BinaryPrimitives.WriteUInt32LittleEndian(bytes, 0xf0000011);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(4), 1);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(8), 1);
        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(68), PatchUnitMeshReader.UnitTypeId);
        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(76), 1);
        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(92), unit);
        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(100), PatchUnitMeshReader.UnitTypeId);
        BinaryPrimitives.WriteUInt64LittleEndian(bytes.AsSpan(108), 176);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(148), 4);
        BinaryPrimitives.WriteUInt32LittleEndian(bytes.AsSpan(156), 8);
        File.WriteAllBytes(path, bytes); File.WriteAllBytes(path + ".gpu_resources", new byte[8]);
    }
    public void Dispose() { if (Directory.Exists(root)) Directory.Delete(root, true); }
}
