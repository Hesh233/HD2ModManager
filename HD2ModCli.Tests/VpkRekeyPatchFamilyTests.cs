using Xunit;

namespace HD2ModCli.Tests;

public sealed class VpkRekeyPatchFamilyTests
{
    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void CopiesSidecarsOrMaterializesExplicitEmptyFiles(bool hasSidecars)
    {
        var root = Path.Combine(Path.GetTempPath(), "hd2-rekey-family-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var source = Path.Combine(root, "source.patch_0");
            var destination = Path.Combine(root, "output.patch_0");
            File.WriteAllBytes(source, [1, 2]);
            File.WriteAllBytes(destination + ".stream", [9]);
            if (hasSidecars)
            {
                File.WriteAllBytes(source + ".gpu_resources", [3, 4]);
                File.WriteAllBytes(source + ".stream", [5, 6]);
            }
            CliVpkRekey.CopyPatchFamily(source, destination);
            Assert.Equal(new byte[] { 1, 2 }, File.ReadAllBytes(destination));
            Assert.Equal(hasSidecars ? new byte[] { 3, 4 } : [], File.ReadAllBytes(destination + ".gpu_resources"));
            Assert.Equal(hasSidecars ? new byte[] { 5, 6 } : [], File.ReadAllBytes(destination + ".stream"));
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
