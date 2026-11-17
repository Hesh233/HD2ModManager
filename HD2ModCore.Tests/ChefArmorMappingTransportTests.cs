using System.Text;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class ChefArmorMappingTransportTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "hd2-chef-transport-" + Guid.NewGuid().ToString("N"));
    [Fact]
    public void Projection_IsFlatAtomicUtf8_AndKeepsRevisionAndDisable()
    {
        var text = "schema=3\nrevision=4\nenabled=true\nlink=4718af954e550001,4718af954e550002\n";
        var path = ChefArmorMappingTransport.WriteProjection(root, text);
        Assert.Equal(Path.Combine(root, "codex_runtime_armor_registry.links.dat"), path);
        Assert.Equal(Encoding.UTF8.GetBytes(text), File.ReadAllBytes(path));
        Assert.False(File.ReadAllBytes(path).AsSpan().StartsWith(new byte[] { 0xef, 0xbb, 0xbf }));
        var stopped = "schema=3\nrevision=5\nenabled=false\nmode=apply\n";
        ChefArmorMappingTransport.WriteProjection(root, stopped);
        Assert.Equal(stopped, File.ReadAllText(path));
        Assert.Single(Directory.GetFiles(root));
    }
    [Fact]
    public void OversizedProjection_IsRejectedBeforeChangingExistingFile()
    {
        var path = ChefArmorMappingTransport.WriteProjection(root, "old");
        Assert.Throws<InvalidDataException>(() => ChefArmorMappingTransport.WriteProjection(root, new string('a', 4 * 1024 * 1024 + 1)));
        Assert.Equal("old", File.ReadAllText(path)); Assert.Single(Directory.GetFiles(root));
    }
    [Fact]
    public void CustomRegistryRoot_DoesNotPublishToRealUserFolders()
    {
        ChefArmorMappingTransport.PublishCanonical(Path.Combine(root, "wardrobe.links"), "not-production");
        Assert.False(Directory.Exists(root));
    }
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Stop_ReplacesExistingCanonicalButDoesNotCreateMissingOne(bool enabled)
    {
        Directory.CreateDirectory(root); var path = Path.Combine(root, "wardrobe.links");
        File.WriteAllText(path, "schema=3\nrevision=3\nlink=0000000000000001,0000000000000002\n");
        ChefArmorMappingTransport.PublishStopIfNeeded(root, new RuntimeArmorRegistryDocument(4, enabled, []));
        var text = File.ReadAllText(path);
        Assert.Contains("revision=4", text); Assert.DoesNotContain("link=", text);
        Assert.Contains(enabled ? "enabled=true" : "enabled=false", text);
        File.Delete(path);
        ChefArmorMappingTransport.PublishStopIfNeeded(root, new RuntimeArmorRegistryDocument(5, enabled, []));
        Assert.False(File.Exists(path));
    }
    [Fact]
    public void ActiveMapping_DoesNotReplaceCanonicalInStopPath()
    {
        Directory.CreateDirectory(root); var path = Path.Combine(root, "wardrobe.links"); File.WriteAllText(path, "active");
        ChefArmorMappingTransport.PublishStopIfNeeded(root, new RuntimeArmorRegistryDocument(4, true, [new RuntimeArmorRegistryMapping(10, 20)]));
        Assert.Equal("active", File.ReadAllText(path));
    }
    [Fact]
    public void MirrorFailure_IsNotSilentlySwallowed_OrdinaryFailureIsUnchanged()
    {
        ChefArmorMappingTransport.RethrowIfMirrorFailure(new IOException("ordinary"));
        var failure = new IOException("projection failure"); failure.Data["HD2ModManager.ChefArmorMirrorFailure"] = true;
        Assert.Same(failure, Assert.Throws<IOException>(() => ChefArmorMappingTransport.RethrowIfMirrorFailure(failure)));
    }
    public void Dispose()
    {
        var resolved = Path.GetFullPath(root);
        var temp = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        if (!resolved.StartsWith(temp, StringComparison.OrdinalIgnoreCase) || !Path.GetFileName(resolved).StartsWith("hd2-chef-transport-", StringComparison.Ordinal))
            throw new InvalidOperationException("Fixture cleanup escaped its temporary root.");
        if (Directory.Exists(resolved)) Directory.Delete(resolved, true);
    }
}
