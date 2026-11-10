using System.IO.Compression;
using System.Text.Json;
using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class ArsenalPhysicsPackageLayoutTests
{
    [Fact]
    public void PhysicsHasRootManifestAndExactlyOnePatchTriplet()
    {
        InTemp(root =>
        {
            var feature = LuaAddonCatalog.Physics();
            var folder = LuaAddonPackageExport.Export(root, feature);
            Assert.True(File.Exists(Path.Combine(folder, "manifest.json")));
            Assert.False(Directory.Exists(Path.Combine(folder, "patch版")));
            Assert.Equal(3, Directory.EnumerateFiles(folder, "*.patch_0*", SearchOption.TopDirectoryOnly).Count());
            Assert.Equal(3, Directory.EnumerateFiles(folder, "*.patch_0*", SearchOption.AllDirectories).Count());
            using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "manifest.json")));
            Assert.Equal(feature.ModGuid, manifest.RootElement.GetProperty("Guid").GetString());
            Assert.Equal(feature.Title, manifest.RootElement.GetProperty("Name").GetString());
            Assert.False(manifest.RootElement.TryGetProperty("Options", out _));
            Assert.Equal(feature.Source, File.ReadAllText(Path.Combine(folder, "lua版", feature.LuaFileName)));
        });
    }

    [Fact]
    public void PhysicalPayloadIsByteIdenticalToExistingPatchBuilder()
    {
        InTemp(root =>
        {
            var feature = LuaAddonCatalog.Physics();
            var folder = LuaAddonPackageExport.Export(Path.Combine(root, "export"), feature);
            var baseline = LuaAddonPatchBuilder.Write(Path.Combine(root, "reference"), feature.AddonId, feature.Source);
            foreach (var suffix in new[] { "", ".stream", ".gpu_resources" })
                Assert.Equal(File.ReadAllBytes(baseline + suffix),
                    File.ReadAllBytes(Path.Combine(folder, Path.GetFileName(baseline)) + suffix));
        });
    }

    [Fact]
    public void BothFlatAndSingleFeatureWrapperZipsExposeDirectPatchFiles()
    {
        InTemp(root =>
        {
            var exports = Path.Combine(root, "exports");
            var folder = LuaAddonPackageExport.Export(exports, LuaAddonCatalog.Physics());
            var flat = Path.Combine(root, "flat.zip");
            var wrapped = Path.Combine(root, "wrapped.zip");
            ZipFile.CreateFromDirectory(folder, flat);
            ZipFile.CreateFromDirectory(exports, wrapped);
            using var z1 = ZipFile.OpenRead(flat);
            using var z2 = ZipFile.OpenRead(wrapped);
            Assert.NotNull(z1.GetEntry("manifest.json"));
            Assert.Equal(3, z1.Entries.Count(e => !e.FullName.Contains('/') && e.Name.Contains(".patch_0", StringComparison.Ordinal)));
            // Arsenal's inferred Include="physbone" sees these direct children without recursion.
            Assert.Equal(3, z2.Entries.Count(e => e.FullName.StartsWith("physbone/", StringComparison.Ordinal)
                && e.FullName.Count(c => c == '/') == 1 && e.Name.Contains(".patch_0", StringComparison.Ordinal)));
        });
    }

    [Fact]
    public void ReExportRemovesLegacyNestedPhysicalPatchWithoutDuplication()
    {
        InTemp(root =>
        {
            var feature = LuaAddonCatalog.Physics();
            var oldFolder = Path.Combine(root, feature.Key);
            LuaAddonPatchBuilder.Write(Path.Combine(oldFolder, "patch版"), feature.AddonId, feature.Source);
            File.WriteAllText(Path.Combine(oldFolder, "stale.txt"), "legacy");
            var folder = LuaAddonPackageExport.Export(root, feature);
            Assert.False(Directory.Exists(Path.Combine(folder, "patch版")));
            Assert.False(File.Exists(Path.Combine(folder, "stale.txt")));
            Assert.Equal(3, Directory.EnumerateFiles(folder, "*.patch_0*", SearchOption.AllDirectories).Count());
            Assert.Contains("Arsenal", File.ReadAllText(Path.Combine(folder, LuaAddonPackageExport.ReadmeFileName)), StringComparison.Ordinal);
        });
    }

    [Fact]
    public void PhysicalWrapperUsesAddonIdentityNotFeatureDirectoryName()
    {
        InTemp(root =>
        {
            var folder = PhysBoneLuaPackageExport.Export(Path.Combine(root, "physics-runtime"));
            Assert.True(File.Exists(Path.Combine(folder, "manifest.json")));
            Assert.True(File.Exists(Path.Combine(folder, "9ba626afa44a3aa3.patch_0")));
            Assert.False(Directory.Exists(Path.Combine(folder, "patch版")));
        });
    }

    [Fact]
    public void OtherFeatureLayoutsRemainUnchanged()
    {
        InTemp(root =>
        {
            foreach (var feature in new[] { LuaAddonCatalog.Wardrobe(), LuaAddonCatalog.AttachmentFix("return {testProfile=true}") })
            {
                var folder = LuaAddonPackageExport.Export(root, feature);
                Assert.False(File.Exists(Path.Combine(folder, "manifest.json")));
                Assert.True(File.Exists(Path.Combine(folder, "patch版", "manifest.json")));
                Assert.Equal(3, Directory.EnumerateFiles(Path.Combine(folder, "patch版"), "*.patch_0*", SearchOption.TopDirectoryOnly).Count());
            }
        });
    }

    private static void InTemp(Action<string> test)
    {
        var root = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "hd2-arsenal-flat-" + Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(root);
        try { test(root); }
        finally { Directory.Delete(root, recursive: true); }
    }
}
