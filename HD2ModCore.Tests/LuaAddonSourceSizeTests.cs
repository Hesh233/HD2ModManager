using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class LuaAddonSourceSizeTests
{
    [Fact]
    public void ResourceEnvelopeCountsTowardInclusiveLimit()
    {
        var max = LuaAddonPatchBuilder.MaxLoaderResourceBytes - 8;
        LuaAddonPatchBuilder.ValidateSourceSize(new string('a', max));
        Assert.Throws<InvalidDataException>(() => LuaAddonPatchBuilder.ValidateSourceSize(new string('a', max + 1)));
    }

    [Fact]
    public void LimitCountsUtf8BytesNotCharacters()
    {
        var count = (LuaAddonPatchBuilder.MaxLoaderResourceBytes - 8) / 3;
        LuaAddonPatchBuilder.ValidateSourceSize(new string('中', count));
        Assert.Throws<InvalidDataException>(() => LuaAddonPatchBuilder.ValidateSourceSize(new string('中', count + 1)));
    }

    [Fact]
    public void RejectedExportPreservesExistingPackage()
    {
        var root = Path.Combine(Path.GetTempPath(), "hd2-size-" + Guid.NewGuid().ToString("N"));
        var folder = Path.Combine(root, "physics");
        Directory.CreateDirectory(folder);
        var marker = Path.Combine(folder, "preserve.txt");
        File.WriteAllText(marker, "existing user package");
        var feature = new LuaAddonPackageExport.Feature("physics", "size-test", "mods/test/size", Guid.NewGuid().ToString(), "size.lua", new string('a', LuaAddonPatchBuilder.MaxLoaderResourceBytes));
        Assert.Throws<InvalidDataException>(() => LuaAddonPackageExport.Export(root, feature));
        Assert.Equal("existing user package", File.ReadAllText(marker));
        Assert.Single(Directory.EnumerateFiles(folder));
    }

    [Fact]
    public void RejectedPatchCreatesNoDirectory()
    {
        var folder = Path.Combine(Path.GetTempPath(), "hd2-size-reject-" + Guid.NewGuid().ToString("N"));
        Assert.Throws<InvalidDataException>(() => LuaAddonPatchBuilder.Write(folder, "mods/test/size", new string('a', LuaAddonPatchBuilder.MaxLoaderResourceBytes)));
        Assert.False(Directory.Exists(folder));
    }
}
