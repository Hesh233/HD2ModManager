using HD2ModManager.Services;

namespace HD2ModCore.Tests;

public sealed class VpkImportRollbackPolicyTests
{
    [Fact]
    public void ExistingModelUpdatesAreNeverDeletedByCompanionFailure()
    {
        var existing = Guid.NewGuid(); var created = Guid.NewGuid();
        var ids = VpkImportRollbackPolicy.NewlyCreatedModGuids([existing.ToString("D"), created.ToString("N")], new HashSet<Guid> { existing });
        Assert.Equal([created.ToString("N")], ids);
    }
    [Fact]
    public void RootAndOptionIdsAreDeduplicatedAcrossGuidFormats()
    {
        var root = Guid.NewGuid(); var option = Guid.NewGuid();
        var ids = VpkImportRollbackPolicy.NewlyCreatedModGuids([root.ToString("D"), root.ToString("N"), option.ToString("D"), "bad", Guid.Empty.ToString()], new HashSet<Guid>());
        Assert.Equal([root.ToString("N"), option.ToString("N")], ids);
    }
    [Fact]
    public void NothingNewMeansNoRollbackDeletion()
    {
        var existing = Guid.NewGuid();
        Assert.Empty(VpkImportRollbackPolicy.NewlyCreatedModGuids([existing.ToString("N"), "not-a-guid"], new HashSet<Guid> { existing }));
    }
}
