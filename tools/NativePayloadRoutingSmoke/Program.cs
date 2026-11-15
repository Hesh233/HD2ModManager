using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using System.Text.Json;

var candidate = Path.GetFullPath(args[0]);
var output = Path.GetFullPath(args[1]);
Directory.CreateDirectory(output);
var context = new AssemblyLoadContext("native-payload-routing", isCollectible: false);
context.Resolving += (_, name) =>
{
    var path = Path.Combine(candidate, name.Name + ".dll");
    return File.Exists(path) ? context.LoadFromAssemblyPath(path) : null;
};
var gui = context.LoadFromAssemblyPath(Path.Combine(candidate, "HD2ModManager.dll"));
var core = context.LoadFromAssemblyPath(Path.Combine(candidate, "HD2ModCore.dll"));
var find = gui.GetType("HD2ModManager.Services.VpkAnimationBuildService", true)!
    .GetMethod("FindManifest", BindingFlags.NonPublic | BindingFlags.Static)!;
var converted = gui.GetType("HD2ModManager.Services.VpkImportService", true)!
    .GetMethod("IsConvertedPackage", BindingFlags.NonPublic | BindingFlags.Static)!;
var plan = core.GetType("HD2ModCore.Infrastructure.NativeSkeletonRebuildPlan", true)!;
var fromPayload = plan.GetMethod("FromPayload", BindingFlags.Public | BindingFlags.Static)!;
var cases = new List<object>();
var checks = 0;
foreach (var layout in new[] { "flat", "vpk2patch", "sectional" })
{
    var root = Path.Combine(output, "fixtures", layout);
    var payload = layout == "flat" ? root : Path.Combine(root, layout);
    Directory.CreateDirectory(payload);
    var expected = Path.Combine(payload, "source-skeleton.json");
    File.WriteAllText(expected, "{\"modelScale\":1,\"version\":3}");
    var resolved = (string)find.Invoke(null, [root])!;
    if (!string.Equals(expected, resolved, StringComparison.OrdinalIgnoreCase))
        throw new Exception($"{layout}: native manifest resolved to {resolved}, expected {expected}");
    checks++;
    var route = fromPayload.Invoke(null, [payload])!;
    var kind = plan.GetProperty("Kind")!.GetValue(route)!.ToString();
    if (kind != "DualSkeletonWithLua") throw new Exception($"{layout}: route silently changed to {kind}");
    checks++;
    if (layout != "flat")
    {
        if (!(bool)converted.Invoke(null, [root])!)
            throw new Exception($"{layout}: converted library model not recognized");
        checks++;
    }
    cases.Add(new { layout, expectedManifest = expected, actualManifest = resolved, route = kind });
}
gui.GetType("HD2ModManager.Services.SettingsService", true)!
    .GetMethod("ApplyToVpkBuild", BindingFlags.Public | BindingFlags.Static)!.Invoke(null, null);
var callback = core.GetType("HD2ModCore.Infrastructure.VpkRebuildService", true)!
    .GetProperty("PrepareNativeSkeletonAsync", BindingFlags.Public | BindingFlags.Static)!.GetValue(null);
if (callback is null) throw new Exception("Desktop startup did not register the staged native rebuild adapter");
checks++;
File.WriteAllText(Path.Combine(output, "native-payload-routing.json"), JsonSerializer.Serialize(
    new { status = "PASS_CURRENT_LEGACY_FLAT_NATIVE_ROUTING", checks, cases, desktopStagingCallbackRegistered = true,
        modelsImported = false, modelOrAnimationBakesRun = false, installedLibraryOrGameWritten = false },
    new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"PASS native payload routing: {checks} checks; flat, vpk2patch, sectional and desktop staging callback");

