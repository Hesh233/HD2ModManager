using System.Linq.Expressions;
using System.Reflection;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;
using HD2ModCore.Infrastructure;
using Microsoft.Data.Sqlite;

// Exercise the published GUI conversion service and the real importer's read-only commit boundary.
// Never deploy, map armor, open the WPF window, or mutate the user's library/settings.
internal static class VpkImportSimulation
{
    internal static async Task RunAsync(string[] args, bool single = false, string? targetArchive = null)
    {
        var published = Path.GetFullPath(args[1]);
        var output = Path.GetFullPath(args[2]);
        if (Hash(typeof(StoragePaths).Assembly.Location) != Hash(Path.Combine(published, "HD2ModCore.dll")))
            throw new InvalidDataException("Simulation Core DLL differs from the published Core; rebuild NativeReleaseTools first.");
        var gameData = Path.GetFullPath(args[3]);
        var samples = int.Parse(args[4]);
        if (Directory.Exists(output)) throw new IOException("Use a new isolated test directory.");
        if (samples < 1 || samples > 32 || args.Length < 7 || (args.Length - 5) % 2 != 0)
            throw new ArgumentException("Expected published output game-data samples (vpk scale)...");
        Directory.CreateDirectory(output);
        var paths = new StoragePaths(Path.Combine(output, "isolated-manager"), Path.Combine(output, "isolated-library"));
        Directory.CreateDirectory(paths.IndexDirectory);
        // SQLite backup rather than copying a database with a potentially live WAL.
        using (var source = new SqliteConnection($"Data Source={Path.Combine(published, "data", "indexes", "asset-index.sqlite")};Mode=ReadOnly"))
        using (var target = new SqliteConnection($"Data Source={paths.DbPath}"))
        { source.Open(); target.Open(); source.BackupDatabase(target); }
        AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY", published);
        AssemblyLoadContext.Default.Resolving += (_, name) =>
        {
            var candidate = Path.Combine(published, name.Name + ".dll");
            return File.Exists(candidate) ? AssemblyLoadContext.Default.LoadFromAssemblyPath(candidate) : null;
        };
        var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(published, "HD2ModManager.dll"));
        var settings = assembly.GetType("HD2ModManager.Services.SettingsService", true)!;
        var configuredGame = (string)settings.GetMethod("GetGameDataFolder")!.Invoke(null, null)!;
        if (!Path.GetFullPath(configuredGame).Equals(gameData, StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Published game-data setting must match test input; settings were not changed.");
        var buildService = assembly.GetType("HD2ModManager.Services.VpkAnimationBuildService", true)!;
        var convertService = assembly.GetType("HD2ModManager.Services.VpkImportService", true)!;
        var decisionType = assembly.GetType("HD2ModManager.Services.VpkModelDecision", true)!;
        var converter = Activator.CreateInstance(convertService, paths, gameData)!;
        var store = new JsonModLibraryStore(paths, allowLegacyMigration: false);
        var folders = new ObjectTreeImporter(new PatchFileNameParser());
        var importer = new ModLibraryImporter(paths, folders, new ArchiveObjectTreeImporter(folders), store);
        var reports = new List<object>();
        for (var i = 5; i < args.Length; i += 2)
        {
            var vpk = Path.GetFullPath(args[i]);
            var scale = double.Parse(args[i + 1], System.Globalization.CultureInfo.InvariantCulture);
            var stem = Path.GetFileNameWithoutExtension(vpk);
            var testRoot = Path.Combine(output, stem); Directory.CreateDirectory(testRoot);
            var originalHash = Hash(vpk);
            var prepareTask = (Task)convertService.GetMethod("TryPrepareAsync")!.Invoke(converter,
                [vpk, CancellationToken.None, (Action<string>)(text => Console.WriteLine(text))])!;
            await prepareTask;
            var source = prepareTask.GetType().GetProperty("Result")!.GetValue(prepareTask)!;
            using var sourceCleanup = new InvocationCleanup(source);
            var convertMethod = convertService.GetMethod("ConvertAsync")!;
            var callbackType = convertMethod.GetParameters()[5].ParameterType;
            var decision = CreateDecision(decisionType, !single, scale, single);
            var completed = typeof(Task).GetMethod("FromResult")!.MakeGenericMethod(decisionType);
            var callback = Expression.Lambda(callbackType,
                Expression.Call(completed, Expression.Constant(decision, decisionType)),
                Expression.Parameter(typeof(string)), Expression.Parameter(typeof(CancellationToken))).Compile();
            var task = (Task)convertMethod.Invoke(converter,
                [source, (Action<string>)(text => Console.WriteLine(text)), CancellationToken.None, null, null, callback])!;
            await task;
            var result = task.GetType().GetProperty("Result")!.GetValue(task)!;
            var conversionReport = result.GetType().GetField("Item1")!.GetValue(result)!;
            File.WriteAllText(Path.Combine(testRoot, "conversion.json"), JsonSerializer.Serialize(conversionReport));
            var packages = ((System.Collections.IEnumerable)result.GetType().GetField("Item2")!.GetValue(result)!).Cast<object>().ToArray();
            if (packages.Length != 1) throw new InvalidDataException("Expected one converted native model; see conversion.json.");
            var package = packages[0];
            var directory = (string)package.GetType().GetProperty("Directory")!.GetValue(package)!;
            if (package.GetType().GetProperty("NativeModelDirectory")!.GetValue(package) is null
                || !(bool)package.GetType().GetProperty("WantsNativeAnimation")!.GetValue(package)!)
                throw new InvalidDataException("Native model/animation decision was lost.");
            var markerName = single ? "single-skeleton.json" : "source-skeleton.json";
            var stagedManifest = Directory.GetFiles(directory, markerName, SearchOption.AllDirectories).Single();
            using (var doc = JsonDocument.Parse(File.ReadAllText(stagedManifest)))
                if (!doc.RootElement.TryGetProperty(single ? "configSha256" : "sourceAttachmentCalibration", out _))
                    throw new InvalidDataException("Model was not calibrated before import.");
            var imported = await importer.ImportFolderAsync(directory);
            var modelNode = imported.Snapshot.Nodes.Values.Single(node =>
                imported.ImportedNodeIds.Contains(node.Id) && Directory.GetFiles(Path.Combine(paths.ModsDirectory, node.RelativePath), markerName, SearchOption.AllDirectories).Length != 0);
            var model = Path.Combine(paths.ModsDirectory, modelNode.RelativePath);
            var manifest = Directory.GetFiles(model, markerName, SearchOption.AllDirectories).Single();
            if (targetArchive is not null)
            {
                var configuredPaths = (StoragePaths)settings.GetMethod("CreateStoragePaths")!.Invoke(null, null)!;
                if (!Path.GetFullPath(configuredPaths.ModsDirectory).Equals(Path.GetFullPath(paths.ModsDirectory), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Target simulation must use an isolated published settings.json pointing to this test library.");
                var rekey = assembly.GetType("HD2ModManager.Services.VpkRekeyService", true)!;
                var rekeyTask = (Task)rekey.GetMethod("RunAsync")!.Invoke(null,
                    [modelNode.Id.Value.ToString("N"), model, new[] { targetArchive }, null,
                     (Action<string>)(text => Console.WriteLine(text)), CancellationToken.None, false])!;
                await rekeyTask;
                var outcome = rekeyTask.GetType().GetProperty("Result")!.GetValue(rekeyTask)!;
                File.WriteAllText(Path.Combine(testRoot, "rekey-result.json"), JsonSerializer.Serialize(outcome));
                if (outcome.GetType().GetProperty("Ok")!.GetValue(outcome) is not true)
                    throw new InvalidDataException("Target rekey failed; see rekey-result.json");
            }
            // Diagnostic-only override AFTER the committed model snapshot. It
            // proves BuildSingle reads the current standard source, not cached
            // imported IK values. The real user library is never involved.
            var standardOverride = single ? Environment.GetEnvironmentVariable("HD2_SINGLE_STANDARD_TEST_CONFIG") : null;
            if (!string.IsNullOrWhiteSpace(standardOverride))
            {
                var targetConfig = Path.Combine(model, "config.toml");
                File.Copy(Path.GetFullPath(standardOverride), targetConfig);
                File.SetAttributes(targetConfig, File.GetAttributes(targetConfig) | FileAttributes.ReadOnly);
            }
            var tracked = Directory.GetFiles(model, "*", SearchOption.AllDirectories);
            if (tracked.Where(file => !Path.GetRelativePath(model, file).StartsWith("Overwrite" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                    && Path.GetFileName(file) != "wardrobe.json").Any(file => !File.GetAttributes(file).HasFlag(FileAttributes.ReadOnly)))
                throw new InvalidDataException("Real importer did not protect model files.");
            var before = tracked.ToDictionary(file => file, file => (Hash: Hash(file), Attributes: File.GetAttributes(file)));
            var handles = new List<FileStream>();
            string? lua = null;
            string runtime;
            try
            {
                // Windows sharing mode forbids writes/deletes while permitting the intended readers.
                foreach (var file in tracked) handles.Add(new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read));
                if (!single) lua = await (Task<string>)buildService.GetMethod("BuildAttachmentFixAsync", BindingFlags.NonPublic | BindingFlags.Static)!
                    .Invoke(null, [model, Path.Combine(testRoot, "attachment"), CancellationToken.None, null])!;
                var animationMethod = buildService.GetMethod(single ? "BuildSingleAsync" : "BuildAsync", BindingFlags.NonPublic | BindingFlags.Static)!;
                object?[] animationArguments = [model, Path.Combine(testRoot, "animations"), null, CancellationToken.None, (int?)samples];
                if (animationMethod.GetParameters().Length == 6) animationArguments = [.. animationArguments, 2];
                runtime = await (Task<string>)animationMethod.Invoke(null, animationArguments)!;
            }
            finally { foreach (var handle in handles) handle.Dispose(); }
            if (before.Any(pair => Hash(pair.Key) != pair.Value.Hash || File.GetAttributes(pair.Key) != pair.Value.Attributes))
                throw new InvalidDataException("Lua/animation build mutated a committed model.");
            if (Directory.GetFiles(model, "*.calibrated*", SearchOption.AllDirectories).Length != 0)
                throw new InvalidDataException("Temporary calibration files leaked into library.");
            if (!single)
            {
            var luaName = "[骨骼挂点修正]" + stem;
            var luaPackage = Path.Combine(testRoot, luaName);
            Directory.Move(Path.Combine(lua!, "patch版"), luaPackage);
            assembly.GetType("HD2ModManager.Services.ImportService", true)!.GetMethod("RewriteLuaPackageIdentity",
                BindingFlags.NonPublic | BindingFlags.Static)!.Invoke(null, [luaPackage, luaName]);
            await importer.ImportFolderAsync(luaPackage);
            }
            var animationName = (single ? "[单骨架动画](" : "[原比例混合动画](") + stem + ")";
            var animationPackage = Path.Combine(testRoot, animationName); Directory.CreateDirectory(animationPackage);
            foreach (var file in Directory.EnumerateFiles(runtime)) File.Copy(file, Path.Combine(animationPackage, Path.GetFileName(file)));
            var animations = await importer.ImportFolderAsync(animationPackage);
            var animationNode = animations.Snapshot.Nodes.Values.Single(node => node.Metadata.Name == animationName);
            var expectedDescription = single ? "[抽样动作文件：不可用于全量部署]" : "[全量动作文件]";
            if (animationNode.Metadata.Notes != expectedDescription) throw new InvalidDataException("Incorrect library animation description.");
            using var buildReport = JsonDocument.Parse(File.ReadAllText(Path.Combine(testRoot, "animations", "build-report.json")));
            if (buildReport.RootElement.GetProperty("animations").GetArrayLength() != samples)
                throw new InvalidDataException("Incorrect sampled animation count.");
            if (Hash(vpk) != originalHash) throw new InvalidDataException("Source VPK mutated.");
            var report = new { status = "PASS", vpk, model, scale, samples, singleHd2Skeleton = single, targetArchive, calibrationBeforeCommit = true,
                realGuiConvertService = true, realLibraryImporter = true, protectedModelUnchanged = true,
                exclusiveReadHandlesDuringBuild = tracked.Length, animationName, description = animationNode.Metadata.Notes,
                standardOverrideUsed = !string.IsNullOrWhiteSpace(standardOverride),
                singleProcessingProfile = single ? buildReport.RootElement.GetProperty("processingProfile").GetString() : null,
                standardIkChains = single ? buildReport.RootElement.GetProperty("ikChains").Clone() : (JsonElement?)null,
                actualIkEvaluations = single ? buildReport.RootElement.GetProperty("ikEvaluations").GetInt32() : 0,
                gameDeployed = false, gameTested = false };
            reports.Add(report);
            File.WriteAllText(Path.Combine(testRoot, "import-regression.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine("IMPORT REGRESSION PASS: " + stem);
        }
        File.WriteAllText(Path.Combine(output, "import-regression.json"), JsonSerializer.Serialize(reports, new JsonSerializerOptions { WriteIndented = true }));
    }
    internal static async Task VerifyReimportAsync(string[] args)
    {
        var published=Path.GetFullPath(args[1]);var output=Path.GetFullPath(args[2]);
        var game=Path.GetFullPath(args[3]);var vpk=Path.GetFullPath(args[4]);
        var scale=double.Parse(args[5],System.Globalization.CultureInfo.InvariantCulture);
        var paths=new StoragePaths(Path.Combine(output,"isolated-manager"),Path.Combine(output,"isolated-library"));
        var before=Directory.GetFiles(paths.ModsDirectory,"*",SearchOption.AllDirectories).ToDictionary(p=>p,Hash);
        AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY",published);
        AssemblyLoadContext.Default.Resolving+=(_,name)=>
        {
            var path=Path.Combine(published,name.Name+".dll");
            return File.Exists(path)?AssemblyLoadContext.Default.LoadFromAssemblyPath(path):null;
        };
        var assembly=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(published,"HD2ModManager.dll"));
        var service=assembly.GetType("HD2ModManager.Services.VpkImportService",true)!;
        var converter=Activator.CreateInstance(service,paths,game)!;
        var prepare=(Task)service.GetMethod("TryPrepareAsync")!.Invoke(converter,[vpk,CancellationToken.None,null])!;
        await prepare;var source=prepare.GetType().GetProperty("Result")!.GetValue(prepare)!;
        using var cleanup=new InvocationCleanup(source);
        var method=service.GetMethod("ConvertAsync")!;
        var decisionType=assembly.GetType("HD2ModManager.Services.VpkModelDecision",true)!;
        var decision=CreateDecision(decisionType,true,scale,false);
        var callback=Expression.Lambda(method.GetParameters()[5].ParameterType,
            Expression.Call(typeof(Task).GetMethod("FromResult")!.MakeGenericMethod(decisionType),Expression.Constant(decision,decisionType)),
            Expression.Parameter(typeof(string)),Expression.Parameter(typeof(CancellationToken))).Compile();
        var work=(Task)method.Invoke(converter,[source,(Action<string>)Console.WriteLine,CancellationToken.None,null,null,callback])!;
        await work;var result=work.GetType().GetProperty("Result")!.GetValue(work)!;
        var package=((System.Collections.IEnumerable)result.GetType().GetField("Item2")!.GetValue(result)!).Cast<object>().Single();
        object? Get(string key)=>package.GetType().GetProperty(key)!.GetValue(package);
        if(Get("UpdateTargetDirectory") is not string target || Get("NativeModelDirectory") is null || Get("WantsNativeAnimation") is not true)
            throw new InvalidDataException("Reimport lost its native model / animation update decision.");
        var staged=(string)Get("Directory")!;
        using var manifest=JsonDocument.Parse(File.ReadAllText(Path.Combine(staged,"source-skeleton.json")));
        if(!manifest.RootElement.TryGetProperty("weaponGripCalibration",out _))throw new InvalidDataException("Reimport staged model is not calibrated.");
        var oldKey=VpkCustomModelFile.TryReadKey(Path.Combine(target,ModNodePayloadLayout.VpkPatchDirectoryName));
        if(oldKey is null || oldKey!=VpkCustomModelFile.TryReadKey(staged))throw new InvalidDataException("Reimport changed model identity.");
        if(before.Any(pair=>Hash(pair.Key)!=pair.Value))throw new InvalidDataException("Staged update conversion mutated committed library files.");
        File.WriteAllText(Path.Combine(output,"reimport-regression.json"),JsonSerializer.Serialize(new {status="PASS",vpk,target,
            nativeDecisionPreserved=true,animationDecisionPreserved=true,modelKeyPreserved=true,calibrationBeforeSwap=true,
            liveLibraryUnchanged=true,gameDeployed=false,gameTested=false},new JsonSerializerOptions{WriteIndented=true}));
        Console.WriteLine("REIMPORT REGRESSION PASS: "+Path.GetFileName(vpk));
    }

    private static object CreateDecision(Type decisionType, bool dual, double scale, bool single)
    {
        object?[] arguments = [dual, scale, true, single];
        if (decisionType.GetConstructors().Any(c => c.GetParameters().Length == 5))
            arguments = [.. arguments, 2];
        return Activator.CreateInstance(decisionType, arguments)!;
    }

    private sealed class InvocationCleanup(object source) : IDisposable
    {
        public void Dispose() => source.GetType().GetMethod("Dispose")!.Invoke(source, null);
    }
    private static string Hash(string path)
    { using var input = File.OpenRead(path); return Convert.ToHexString(SHA256.HashData(input)); }
}


