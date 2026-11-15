using System;
using System.Collections.Generic;

namespace HD2ModManager.Services;

/// <summary>A companion build failure may delete this batch's new nodes, never an existing model update.</summary>
internal static class VpkImportRollbackPolicy
{
    internal static string[] NewlyCreatedModGuids(IEnumerable<string> imported, IReadOnlySet<Guid> existing)
    {
        var seen = new HashSet<Guid>();
        var result = new List<string>();
        foreach (var text in imported)
            if (Guid.TryParse(text, out var id) && id != Guid.Empty && !existing.Contains(id) && seen.Add(id))
                result.Add(id.ToString("N"));
        return result.ToArray();
    }
}
