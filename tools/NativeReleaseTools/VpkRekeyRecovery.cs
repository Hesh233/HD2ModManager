using System.Diagnostics;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;

// Recovery/verification harness: invoke the published GUI service, not a second rekey implementation.
internal static class VpkRekeyRecovery
{
    public static async Task RunAsync(string[] args)
    {
        if (args.Length != 5) throw new ArgumentException("--rekey-existing-vpk <published> <new-report-directory> <mod-guid> <target-archive>");
        foreach (var processName in new[] { "HD2ModManager", "helldivers2" })
        {
            var processes = Process.GetProcessesByName(processName);
            try { if (processes.Length != 0) throw new InvalidOperationException($"Close {processName} before recovery."); }
            finally { foreach (var process in processes) process.Dispose(); }
        }
        var published = Path.GetFullPath(args[1]);
        var output = Path.GetFullPath(args[2]);
        if (Directory.Exists(output)) throw new IOException("Choose a new report directory.");
        Directory.CreateDirectory(output);
        AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY", published);
        AssemblyLoadContext.Default.Resolving += (_, name) =>
        {
            var candidate = Path.Combine(published, name.Name + ".dll");
            return File.Exists(candidate) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(candidate) : null;
        };
        var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(published, "HD2ModManager.dll"));
        var settings = assembly.GetType("HD2ModManager.Services.SettingsService", true)!;
        var paths = (StoragePaths)settings.GetMethod("CreateStoragePaths")!.Invoke(null, null)!;
        var snapshot = await new JsonModLibraryStore(paths, allowLegacyMigration: false).TryLoadAsync()
            ?? throw new InvalidDataException("Library snapshot missing.");
        var id = new ModNodeId(Guid.Parse(args[3]));
        var node = snapshot.Nodes[id];
        var directory = Path.GetFullPath(Path.Combine(paths.ModsDirectory, node.RelativePath));
        if (!directory.StartsWith(Path.GetFullPath(paths.ModsDirectory).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
            StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Mod directory escapes library.");
        var source = Path.Combine(directory, "vpk2patch");
        var before = HashTree(source);
        foreach (var file in new[] { "wardrobe.json" })
        {
            var path = Path.Combine(directory, file);
            if (File.Exists(path)) File.Copy(path, Path.Combine(output, file + ".before"));
        }
        if (Directory.Exists(Path.Combine(directory, "Overwrite")))
            throw new IOException("Existing Overwrite must be backed up explicitly before this recovery harness is used.");
        var wardrobe = assembly.GetType("HD2ModManager.Services.VpkModWardrobeService", true)!;
        var read = (Task)wardrobe.GetMethod("ReadAsync")!.Invoke(null, [directory, CancellationToken.None])!;
        await read;
        var state = read.GetType().GetProperty("Result")!.GetValue(read)!;
        var disabled = state.GetType().GetProperty("State")!.GetValue(state)!;
        disabled = disabled.GetType().GetProperty("Disabled")!.GetValue(disabled)!;
        var headMerge = (bool)state.GetType().GetProperty("HeadMergeIntoBody")!.GetValue(state)!;
        var rekey = assembly.GetType("HD2ModManager.Services.VpkRekeyService", true)!;
        var task = (Task)rekey.GetMethod("RunAsync")!.Invoke(null,
            [id.Value.ToString("N"), directory, new[] { args[4] }, disabled,
                (Action<string>)(stage => Console.WriteLine(stage)), CancellationToken.None, headMerge])!;
        await task;
        var result = task.GetType().GetProperty("Result")!.GetValue(task)!;
        await File.WriteAllTextAsync(Path.Combine(output, "gui-service-result.json"),
            JsonSerializer.Serialize(result, result.GetType(), new JsonSerializerOptions { WriteIndented = true }));
        if (!(bool)result.GetType().GetProperty("Ok")!.GetValue(result)!) throw new InvalidDataException("Rekey failed; see gui-service-result.json.");
        var after = HashTree(source);
        if (before.Count != after.Count || before.Any(pair => !after.TryGetValue(pair.Key, out var value) || pair.Value != value))
            throw new InvalidDataException("Source files/attributes changed during rekey.");
        var savedTask = (Task)wardrobe.GetMethod("ReadAsync")!.Invoke(null, [directory, CancellationToken.None])!;
        await savedTask;
        var saved = savedTask.GetType().GetProperty("Result")!.GetValue(savedTask)!;
        var target = (string?)saved.GetType().GetProperty("TargetArmorArchiveId")!.GetValue(saved);
        if (!string.Equals(target, args[4], StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Wardrobe target did not persist.");
        await File.WriteAllTextAsync(Path.Combine(output, "verification.json"), JsonSerializer.Serialize(new
        {
            publishedGuiServiceInvoked = true, mod = id.Value, directory, target,
            sourceFilesUnchanged = before.Count, headMerge, sourceFiles = before,
            overwriteFiles = Directory.GetFiles(Path.Combine(directory, "Overwrite")).Select(Path.GetFileName),
            deployed = false,
        }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"Rekey succeeded; saved target {target}; {before.Count} source files unchanged. Not deployed.");
    }

    private static Dictionary<string, string> HashTree(string directory) => Directory.GetFiles(directory, "*", SearchOption.AllDirectories)
        .ToDictionary(path => Path.GetRelativePath(directory, path),
            path => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))) + ":" + File.GetAttributes(path));
}
