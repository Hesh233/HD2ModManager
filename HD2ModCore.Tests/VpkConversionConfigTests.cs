using HD2ModCore.Infrastructure;
namespace HD2ModCore.Tests;
public sealed class VpkConversionConfigTests
{
    [Theory]
    [InlineData("", false)]
    [InlineData("[native_skeleton]\nmerge_wrist_weights=true", false)]
    [InlineData("[vpk_conversion]\nmerge_wrist_weights=false", false)]
    [InlineData("[vpk_conversion]\nmerge_wrist_weights=true", true)]
    [InlineData("\uFEFF [vpk_conversion] # hi\r\n merge_wrist_weights = true # yes", true)]
    [InlineData("[\"vpk_conversion\"]\n'merge_wrist_weights'=true", true)]
    [InlineData("vpk_conversion.merge_wrist_weights = true", true)]
    [InlineData("# [vpk_conversion]\n# merge_wrist_weights=true", false)]
    [InlineData("[vpk_conversion.other]\nmerge_wrist_weights=true", false)]
    [InlineData("[[vpk_conversion.other]]\nmerge_wrist_weights=true", false)]
    [InlineData("text=\"\"\"\n[vpk_conversion]\nmerge_wrist_weights=true\n\"\"\"\n[other]", false)]
    [InlineData("text='''\n[vpk_conversion]\nmerge_wrist_weights=true\n'''\n[vpk_conversion]\nmerge_wrist_weights=false", false)]
    [InlineData("[vpk_conversion]\nnote=\"abc # not comment\"\nmerge_wrist_weights=true", true)]
    public void ReadsOnlyActiveOptIn(string text,bool expected) => Assert.Equal(expected,VpkConversionConfig.Parse(text));
    [Theory]
    [InlineData("[vpk_conversion]\nmerge_wrist_weights=\"true\"")]
    [InlineData("[vpk_conversion]\nmerge_wrist_weights=1")]
    [InlineData("[[vpk_conversion]]\nmerge_wrist_weights=true")]
    [InlineData("[vpk_conversion]\nmerge_wrist_weights=TRUE")]
    [InlineData("[vpk_conversion]\nmerge_wrist_weights=true\nmerge_wrist_weights=false")]
    [InlineData("[vpk_conversion]\n[vpk_conversion]")]
    [InlineData("vpk_conversion={ merge_wrist_weights=true }")]
    public void InvalidOrDuplicateSettingDoesNotSilentlyEnable(string text) => Assert.Throws<InvalidDataException>(()=>VpkConversionConfig.Parse(text));
    [Fact] public void RootConfigIsAuthoritativeAndMissingDefaultsOff()
    {
        var dir=Path.Combine(Path.GetTempPath(),"wrist-config-"+Guid.NewGuid().ToString("N")); Directory.CreateDirectory(dir);
        try {
            Assert.False(VpkConversionConfig.Load(dir));
            Directory.CreateDirectory(Path.Combine(dir,"anim_batch_mod"));
            File.WriteAllText(Path.Combine(dir,"anim_batch_mod","config.toml"),"[vpk_conversion]\nmerge_wrist_weights=true");
            Assert.True(VpkConversionConfig.Load(dir));
            File.WriteAllText(Path.Combine(dir,"config.toml"),"[native_skeleton]\nfps=30");
            Assert.False(VpkConversionConfig.Load(dir));
            File.WriteAllText(Path.Combine(dir,"config.toml"),"[vpk_conversion]\nmerge_wrist_weights=true");
            Assert.True(VpkConversionConfig.Load(dir));
            File.WriteAllText(Path.Combine(dir,"config.toml"),"[vpk_conversion]\nmerge_wrist_weights=false");
            Assert.False(VpkConversionConfig.Load(dir));
        } finally {
            if (!Path.GetFullPath(dir).StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Unsafe test cleanup path.");
            Directory.Delete(dir,true);
        }
    }
}
