using Xunit;

namespace HD2ModCli.Tests;

public sealed class VpkRekeyTargetKitTests
{
    private const string B08Armor = "dfa7c28c3b490a8c";
    private const string B08Helmet = "7805dbf6f83b09ba";
    private const string Fs38Armor = "813da450b8029cb2";
    private const string Fs38Helmet = "0290d8011fce62ef";

    [Theory]
    [InlineData(B08Armor, B08Helmet)]
    [InlineData(B08Helmet, B08Armor)]
    [InlineData(Fs38Armor, Fs38Helmet)]
    [InlineData(Fs38Helmet, Fs38Armor)]
    public void ExpandsOnlyTheMatchingDlcAndOppositeCategory(string selected, string counterpart)
    {
        var kits = new[]
        {
            Kit(B08Armor, "Armor", 3715278879, 3794083209),
            Kit(B08Helmet, "Helmet", 3715278879, 3794083209),
            Kit(Fs38Armor, "Armor", 4143618132, 3794083209),
            Kit(Fs38Helmet, "Helmet", 4143618132, 3794083209),
        };

        Assert.Equal([selected, counterpart], CliVpkRekey.ExpandTargetKit(kits, selected));
    }

    [Fact]
    public void NeverAddsAnotherArmorEvenWithTheSameDlcAndSet()
    {
        var kits = new[] { Kit(B08Armor, "Armor"), Kit(Fs38Armor, "Armor"), Kit(B08Helmet, "Helmet") };
        Assert.Equal([B08Armor, B08Helmet], CliVpkRekey.ExpandTargetKit(kits, B08Armor));
    }

    [Fact]
    public void DuplicateFactsDoNotDuplicateThePairedArchive()
    {
        var helmet = Kit(B08Helmet, "Helmet");
        Assert.Equal([B08Armor, B08Helmet], CliVpkRekey.ExpandTargetKit(
            [Kit(B08Armor, "Armor"), helmet, helmet with { ArchiveId = B08Helmet.ToUpperInvariant() }], B08Armor));
    }

    [Fact]
    public void AmbiguousCounterpartsRequireExplicitArchives()
    {
        var exception = Assert.Throws<CliUserException>(() => CliVpkRekey.ExpandTargetKit(
            [Kit(B08Armor, "Armor"), Kit(B08Helmet, "Helmet"), Kit(Fs38Helmet, "Helmet")], B08Armor));
        Assert.Contains("TargetKitAmbiguous", exception.Code);
    }

    [Fact]
    public void AmbiguousSelectedEquipmentIdentityIsNotGuessed()
    {
        Assert.Throws<CliUserException>(() => CliVpkRekey.ExpandTargetKit(
            [Kit(B08Armor, "Armor", 1), Kit(B08Armor, "Armor", 2), Kit(B08Helmet, "Helmet", 1)], B08Armor));
    }

    [Fact]
    public void MissingPairNeverFallsBackToAnotherDlc()
    {
        Assert.Equal([B08Armor], CliVpkRekey.ExpandTargetKit(
            [Kit(B08Armor, "Armor", 1), Kit(Fs38Helmet, "Helmet", 2)], B08Armor));
    }

    [Fact]
    public void UnknownArchiveAndUnsetSetIdAreNotAutoPaired()
    {
        Assert.Equal([B08Armor], CliVpkRekey.ExpandTargetKit([], B08Armor));
        Assert.Equal([B08Armor], CliVpkRekey.ExpandTargetKit(
            [Kit(B08Armor, "Armor", set: 0), Kit(B08Helmet, "Helmet", set: 0)], B08Armor));
    }

    private static CliEquipmentFactKit Kit(string archive, string category, uint dlc = 1, uint set = 2)
        => new(1, dlc, set, category, archive, archive, []);
}
