using System.Runtime.ExceptionServices;
using System.Text;

namespace HD2ModCore.Infrastructure;

// A projection of wardrobe.links, not a second authoritative workspace. Chef
// permits flat .dat/.log files in its settings folder, not ArmorRegistry/Logs.
internal static class ChefArmorMappingTransport
{
    internal const string LinksFileName = "codex_runtime_armor_registry.links.dat";
    private const string FailureKey = "HD2ModManager.ChefArmorMirrorFailure";
    private const int MaximumBytes = 4 * 1024 * 1024;

    public static void PublishCanonical(string path, string text)
    {
        // Isolated/custom registry roots must never write the user's profile.
        if (!string.Equals(Path.GetFullPath(path),
            Path.Combine(RuntimeArmorRegistryService.ResolveRegistryRoot(), "wardrobe.links"),
            StringComparison.OrdinalIgnoreCase)) return;
        var preferred = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Arrowhead", "Helldivers2");
        try { WriteProjection(preferred, text); }
        catch (Exception first) when (first is IOException or InvalidDataException or UnauthorizedAccessException)
        {
            // Chef itself falls back to LOCALAPPDATA if its settings folder
            // cannot be written. Match that policy, without relaxing sandbox IO.
            try { WriteProjection(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), text); }
            catch (Exception second) when (second is IOException or InvalidDataException or UnauthorizedAccessException)
            {
                var failure = new IOException("Chef 护甲映射镜像写入失败，未能发布外置映射：" + second.Message, new AggregateException(first, second));
                failure.Data[FailureKey] = true;
                throw failure;
            }
        }
    }

    internal static string WriteProjection(string directory, string text)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(directory);
        var bytes = new UTF8Encoding(false).GetBytes(text);
        if (bytes.Length > MaximumBytes) throw new InvalidDataException("Chef 护甲映射镜像超过 4 MiB 上限。");
        Directory.CreateDirectory(directory);
        var target = Path.Combine(Path.GetFullPath(directory), LinksFileName);
        var temporary = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(flushToDisk: true); }
            File.Move(temporary, target, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
        return target;
    }

    public static void PublishStopIfNeeded(string registryRoot, HD2ModCore.Domain.RuntimeArmorRegistryDocument document)
    {
        if (document.Enabled && document.Mappings.Count != 0) return;
        var path = Path.Combine(registryRoot, "wardrobe.links");
        var text = "schema=3\nrevision=" + document.Revision.ToString(System.Globalization.CultureInfo.InvariantCulture)
            + "\nenabled=" + (document.Enabled ? "true" : "false") + "\nmode=apply\n";
        // Do not create a missing canonical links file just to clear it. This
        // also repairs the old normal build's zero-link early-out on disable.
        if (File.Exists(path))
        {
            var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                { stream.Write(new UTF8Encoding(false).GetBytes(text)); stream.Flush(flushToDisk: true); }
                File.Move(temporary, path, overwrite: true);
            }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
        }
        // The projection can exist even if an older canonical file was removed.
        // Explicit disable/clear must replace that projection as well.
        PublishCanonical(path, text);
    }

    public static void RethrowIfMirrorFailure(Exception exception)
    {
        // The legacy links compiler catches IO failures. Do not silently report
        // success if the Chef projection specifically failed to publish.
        if (exception.Data.Contains(FailureKey)) ExceptionDispatchInfo.Capture(exception).Throw();
    }
}
