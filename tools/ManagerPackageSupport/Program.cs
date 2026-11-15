using System.Buffers.Binary;
using System.IO.Compression;
using System.Reflection;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

try
{
if (args.Length < 2) throw new ArgumentException("Usage: ManagerPackageSupport audit <install> <report> | physics-check <install> | physics <install> <new-output-dir> | companion-import-check <install> <base-zip> <panel-zip> <new-import-dir> | companion-check <install> | companion-export <install> <calibration> <new-output-dir> <model-name>");
var root = Path.GetFullPath(args[1]);
var options = new JsonSerializerOptions { WriteIndented = true };
if (args[0] == "audit" && args.Length == 3)
{
    var core = Inspect(Path.Combine(root, "HD2ModCore.dll"));
    var gui = Inspect(Path.Combine(root, "HD2ModManager.dll"));
    File.WriteAllText(args[2], JsonSerializer.Serialize(new { scope = "Offline PE metadata/IL/resources only; no managed assembly execution", core, gui }, options));
    Console.WriteLine("Static PE/IL/resource audit written.");
    return;
}
if (args[0] == "companion-export" && args.Length == 5)
{
    var ctx = new AssemblyLoadContext("production-companion-export", isCollectible: true);
    ctx.Resolving += (c, n) => { var f = Path.Combine(root, Path.GetFileName(n.Name) + ".dll"); return File.Exists(f) ? c.LoadFromAssemblyPath(f) : null; };
    var coreAssembly = ctx.LoadFromAssemblyPath(Path.Combine(root, "HD2ModCore.dll"));
    var type = coreAssembly.GetType("HD2ModCore.Infrastructure.NativeRuntimeCompanionPackageExport", true)!;
    var result = type.GetMethod("Export")!.Invoke(null, [args[3], args[2], args[4], CancellationToken.None])!;
    Console.WriteLine(JsonSerializer.Serialize(result, options));
    return;
}
if (args[0] == "companion-import-check" && args.Length == 5)
{
    var work = Path.GetFullPath(args[4]);
    if (Directory.Exists(work) || File.Exists(work)) throw new IOException("Choose a new isolated import directory.");
    Directory.CreateDirectory(work);
    var importContext = new AssemblyLoadContext("production-companion-import", isCollectible: true);
    importContext.Resolving += (c, n) => { var f = Path.Combine(root, Path.GetFileName(n.Name) + ".dll"); return File.Exists(f) ? c.LoadFromAssemblyPath(f) : null; };
    var importCore = importContext.LoadFromAssemblyPath(Path.Combine(root, "HD2ModCore.dll"));
    object New(string name, params object[] supplied)
    {
        var t = importCore.GetType("HD2ModCore.Infrastructure." + name, true)!;
        var ctor = t.GetConstructors().Single(c => c.GetParameters().Length >= supplied.Length
            && c.GetParameters().Skip(supplied.Length).All(p => p.HasDefaultValue));
        var values = supplied.Concat(ctor.GetParameters().Skip(supplied.Length).Select(p => p.DefaultValue)).ToArray();
        return ctor.Invoke(values);
    }
    // The importer resolves the bundled 7-Zip relative to the application, not the diagnostic helper.
    AppContext.SetData("APP_CONTEXT_BASE_DIRECTORY", Path.TrimEndingDirectorySeparator(root) + Path.DirectorySeparatorChar);
    if (!string.Equals(Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory), Path.TrimEndingDirectorySeparator(root), StringComparison.OrdinalIgnoreCase))
        throw new InvalidOperationException("Unable to select the validated installation dependency directory.");
    var storage = New("StoragePaths", work);
    var folder = New("ObjectTreeImporter", New("PatchFileNameParser"));
    var importer = New("ModLibraryImporter", storage, folder, New("ArchiveObjectTreeImporter", folder), New("JsonModLibraryStore", storage));
    async Task<object> Import(string zip)
    {
        var value = importer.GetType().GetMethod("ImportArchiveAsync")!.Invoke(importer, [zip, CancellationToken.None])!;
        var task = (Task)value.GetType().GetMethod("AsTask")!.Invoke(value, null)!;
        await task;
        return task.GetType().GetProperty("Result")!.GetValue(task)!;
    }
    await Import(Path.GetFullPath(args[2]));
    var result = await Import(Path.GetFullPath(args[3]));
    object Property(object value, string key) => value.GetType().GetProperty(key)!.GetValue(value)!;
    var snapshot = Property(result, "Snapshot");
    var nodes = ((System.Collections.IEnumerable)Property(snapshot, "Nodes")).Cast<object>().Select(v => Property(v, "Value")).ToArray();
    var standards = nodes.Where(n => Property(Property(n, "Metadata"), "Kind").ToString() == "Standard").ToArray();
    var choices = nodes.Where(n => Property(Property(n, "Metadata"), "Kind").ToString() == "Option").ToArray();
    using var zipPanel = ZipFile.OpenRead(args[3]);
    using var panelManifest = JsonDocument.Parse(zipPanel.GetEntry("manifest.json")!.Open());
    var expectedOptions = panelManifest.RootElement.GetProperty("Options");
    if (standards.Length != 2 || choices.Length != expectedOptions.GetArrayLength())
        throw new InvalidDataException("ZIP pair did not import as two independent roots with all options.");
    var fpLabel = expectedOptions[0].GetProperty("Name").GetString();
    var fpChoice = choices.Single(n => Property(Property(n, "Metadata"), "Name").ToString() == fpLabel);
    var fpFile = zipPanel.Entries.Single(e => e.FullName.StartsWith("options/00-fp-arms/", StringComparison.Ordinal)
        && Regex.IsMatch(e.FullName, @"\.patch_6$"));
    using var fpStream = fpFile.Open();
    var fpHash = Convert.ToHexString(SHA256.HashData(fpStream)).ToLowerInvariant();
    var mods = (string)Property(storage, "ModsDirectory");
    var fpCopies = Directory.EnumerateFiles(mods, "*.patch_*", SearchOption.AllDirectories)
        .Where(f => Regex.IsMatch(f, @"\.patch_\d+$") && Hash(File.ReadAllBytes(f)) == fpHash).ToArray();
    var fpDirectory = Path.Combine(mods, (string)Property(fpChoice, "RelativePath"));
    if (fpCopies.Length != 1 || Path.GetDirectoryName(fpCopies[0]) != fpDirectory)
        throw new InvalidDataException("FP graph leaked into the base/panel root or a TP-only option.");
    int Groups(object n) => ((System.Collections.IEnumerable)Property(n, "PatchGroups")).Cast<object>().Count();
    if (Groups(fpChoice) != 2 || choices.Any(n => n != fpChoice && Groups(n) != 1))
        throw new InvalidDataException("FP option must own marker+FP graph; each TP option must own only its marker.");
    var proof = new { status = "complete", coreSha256 = Hash(File.ReadAllBytes(Path.Combine(root, "HD2ModCore.dll"))),
        baseZip = Path.GetFullPath(args[2]), panelZip = Path.GetFullPath(args[3]), isolatedLibrary = mods,
        importedStandardCount = standards.Length, importedOptionCount = choices.Length, fpGraphOnlyInFpOption = true,
        fpOptionPatchGroups = Groups(fpChoice), tpOptionsMarkerOnly = true, gameDeployed = false };
    File.WriteAllText(Path.Combine(work, "companion-import-validation.json"), JsonSerializer.Serialize(proof, options));
    Console.WriteLine(JsonSerializer.Serialize(proof, options));
    return;
}
if (args[0] == "companion-check" && args.Length == 2)
{
    var ctx = new AssemblyLoadContext("production-companion-check", isCollectible: true);
    ctx.Resolving += (c, n) => { var f = Path.Combine(root, Path.GetFileName(n.Name) + ".dll"); return File.Exists(f) ? c.LoadFromAssemblyPath(f) : null; };
    var b3Assembly = ctx.LoadFromAssemblyPath(Path.Combine(root, "HD2ModCore.dll"));
    var exporter = b3Assembly.GetType("HD2ModCore.Infrastructure.NativeRuntimeCompanionPackageExport", true)!;
    string Constant(string name) => (string)exporter.GetField(name)!.GetRawConstantValue()!;
    if (Constant("RuntimeVersion") != "1.0.19" || Constant("FirstPersonSourceVersion") != "1.0.1"
        || Constant("Schema") != "hd2-grip-switches-v1" || exporter.GetMethod("Export")!.GetParameters().Length != 4)
        throw new InvalidDataException("Missing production B3 export contract.");
    var composer = b3Assembly.GetType("HD2ModCore.Infrastructure.PhysBoneLuaSource", true)!.GetMethod("ComposeB3AttachmentFixPackage")!;
    var b3Source = (string)composer.Invoke(null, ["return {runtimeCompanionVersion='1.0.19'}"] )!;
    if (!b3Source.StartsWith("-- HD2-Addon: mods/hd2modmanager/attachment_fix\n", StringComparison.Ordinal)
        || b3Source.Contains("-- INSERT ", StringComparison.Ordinal) || b3Source.Contains("1.0.18-test", StringComparison.Ordinal)
        || !b3Source.Contains("local FirstPersonSource=", StringComparison.Ordinal) || !b3Source.Contains("local OptionSwitches=", StringComparison.Ordinal))
        throw new InvalidDataException("Incomplete production B3 resources.");
    var resources = b3Assembly.GetManifestResourceNames().Where(n => n.Contains(".PhysBone.Production.", StringComparison.Ordinal)).Order().Select(name =>
    {
        using var stream = b3Assembly.GetManifestResourceStream(name)!;
        return new { name, sha256 = Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant() };
    }).ToArray();
    if (resources.Length != 8) throw new InvalidDataException("Unexpected production B3 resource set.");
    using var info = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "anim_batch_mod", "build-info.json")));
    if (info.RootElement.GetProperty("runtimeCompanionVersion").GetString() != Constant("RuntimeVersion")
        || info.RootElement.GetProperty("firstPersonSourceVersion").GetString() != Constant("FirstPersonSourceVersion"))
        throw new InvalidDataException("Bundled Python and Core B3 versions do not match.");
    var contract = b3Assembly.GetType("HD2ModCore.Infrastructure.AttachmentRepairProfileContract", true)!;
    var policyBytes = (byte[])contract.GetMethod("SharedPolicyBytes")!.Invoke(null, null)!;
    var policyHash = Hash(policyBytes);
    var shippedPolicy = Path.Combine(root, "anim_batch_mod", "attachment_repair_policy.json");
    if (!policyBytes.SequenceEqual(File.ReadAllBytes(shippedPolicy))
        || info.RootElement.GetProperty("attachmentRepairPolicyVersion").GetString() != Constant("RuntimeVersion")
        || info.RootElement.GetProperty("attachmentRepairPolicySha256").GetString() != policyHash)
        throw new InvalidDataException("Core/shipped production profile policy hash mismatch.");
    foreach (var row in info.RootElement.GetProperty("files").EnumerateArray())
    {
        var name = row.GetProperty("name").GetString()!;
        var file = Path.GetFullPath(Path.Combine(root, "anim_batch_mod", name));
        if (!file.StartsWith(Path.GetFullPath(Path.Combine(root, "anim_batch_mod")) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            || !Hash(File.ReadAllBytes(file)).Equals(row.GetProperty("sha256").GetString(), StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Bundled runtime/profile file hash mismatch: " + name);
    }
    foreach (var row in info.RootElement.GetProperty("presetFiles").EnumerateArray())
    {
        var file = Path.Combine(root, "anim_batch_mod", row.GetProperty("name").GetString()!);
        if (!Hash(File.ReadAllBytes(file)).Equals(row.GetProperty("sha256").GetString(), StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Skeleton preset hash mismatch: " + file);
    }
    var userConfig = File.ReadAllBytes(Path.Combine(root, "config.toml"));
    if (!userConfig.SequenceEqual(File.ReadAllBytes(Path.Combine(root, "anim_batch_mod", "config.toml"))))
        throw new InvalidDataException("Root/bundled user animation config mismatch; synchronize without replacing user customizations.");
    var boneConfig = File.ReadAllBytes(Path.Combine(root, "config", "attachment-fix.json"));
    if (Hash(boneConfig) != info.RootElement.GetProperty("attachmentFixConfigSha256").GetString())
        throw new InvalidDataException("Active attachment bone configuration hash mismatch.");
    using var boneDocument = JsonDocument.Parse(boneConfig); var bc = boneDocument.RootElement;
    var canonicalBones = new HashSet<string>(new[] { "attach_hand_r", "attach_hand_l", "attach_weapon", "attach_samplepouch", "attach_intelpad", "target_designator", "attach_knife", "sling", "backpack", "support_mg", "support", "cape1", "cape2", "cape3", "cape4", "cape5", "cape6", "cape7", "cape8", "hellpad_socket", "pistol" }, StringComparer.Ordinal);
    var activeBones = bc.GetProperty("bones").EnumerateArray().Select(x => x.GetString()!).ToArray();
    if (bc.GetProperty("version").GetInt32() != 1 || !bc.GetProperty("excludeHeadDescendants").GetBoolean()
        || activeBones.Distinct().Count() != activeBones.Length || activeBones.Any(b => !canonicalBones.Contains(b)))
        throw new InvalidDataException("Invalid active attachment bone configuration.");
    var managerVersion = AssemblyName.GetAssemblyName(Path.Combine(root, "HD2ModManager.dll")).Version!;
    if (info.RootElement.GetProperty("managerVersion").GetString() != $"{managerVersion.Major}.{managerVersion.Minor}.{managerVersion.Build}")
        throw new InvalidDataException("Manager assembly and build-info version mismatch.");
    var python = Path.Combine(root, "anim_batch_mod", "runtime_companions.py");
    if (!File.Exists(python)) throw new FileNotFoundException("Missing production B3 Python compiler.", python);
    Console.WriteLine(JsonSerializer.Serialize(new { status = "ready", runtimeVersion = Constant("RuntimeVersion"),
        firstPersonSourceVersion = Constant("FirstPersonSourceVersion"), schema = Constant("Schema"),
        coreSha256 = Hash(File.ReadAllBytes(Path.Combine(root, "HD2ModCore.dll"))),
        compilerSha256 = Hash(File.ReadAllBytes(python)), attachmentRepairPolicyVersion = Constant("RuntimeVersion"),
        attachmentRepairPolicySha256 = policyHash, attachmentFixConfigSha256 = Hash(boneConfig),
        managerVersion = $"{managerVersion.Major}.{managerVersion.Minor}.{managerVersion.Build}", skeletonPresetHashesValidated = true, resources }, options));
    return;
}
if (args[0] is not ("physics" or "physics-check")) throw new ArgumentException("Unknown command");
if (args[0] == "physics" && args.Length != 3) throw new ArgumentException("physics requires a new output directory");
var inputNames = new[] { "HD2ModCore.dll", "HD2GameItemAssets.dll" };
var inputs = inputNames.ToDictionary(n => n, n => Hash(File.ReadAllBytes(Path.Combine(root, n))));
var context = new AssemblyLoadContext("installed-production-physics", isCollectible: true);
context.Resolving += (ctx, name) => {
    var path = Path.Combine(root, Path.GetFileName(name.Name) + ".dll");
    return File.Exists(path) ? ctx.LoadFromAssemblyPath(path) : null;
};
var assembly = context.LoadFromAssemblyPath(Path.Combine(root, "HD2ModCore.dll"));
var catalog = assembly.GetType("HD2ModCore.Infrastructure.LuaAddonCatalog", true)!;
var feature = catalog.GetMethod("Physics", BindingFlags.Public | BindingFlags.Static)!.Invoke(null, null)!;
string Value(string key) => (string)feature.GetType().GetProperty(key)!.GetValue(feature)!;
var source = Value("Source").Replace("\r\n", "\n", StringComparison.Ordinal);
var owner = Value("AddonId");
var guid = Value("ModGuid");
if (owner != "mods/hd2modmanager/physbone" || guid != "7c1e2b90-5f3a-4d68-9a11-2b7c4e5f6a01") throw new InvalidDataException("Not the production physics feature");
if (!source.StartsWith("-- HD2-Addon: " + owner + "\n", StringComparison.Ordinal)) throw new InvalidDataException("Invalid production owner/BOM");
string Version(string method) {
    var text = (string)assembly.GetType("HD2ModCore.Infrastructure.PhysBoneLuaSource", true)!.GetMethod(method)!.Invoke(null, null)!;
    var match = Regex.Match(text, @"(?i)\bversion\s*=\s*['""]([^'""\s]+)['""]");
    if (!match.Success) throw new InvalidDataException("Missing version: " + method);
    var version = match.Groups[1].Value;
    if (!Regex.IsMatch(version, @"^\d+\.\d+\.\d+$")) throw new InvalidDataException("Test/preview physics version refused: " + version);
    return version;
}
var runtimeVersion = Version("LoadRuntime");
var compatVersion = Version("LoadCompat");
if (args[0] == "physics-check") {
    foreach (var pair in inputs) if (Hash(File.ReadAllBytes(Path.Combine(root, pair.Key))) != pair.Value) throw new IOException("Installed input changed");
    Console.WriteLine(JsonSerializer.Serialize(new { owner, guid, runtimeVersion, compatVersion, sourceSha256 = Hash(Encoding.UTF8.GetBytes(source)), inputs }, options));
    return;
}
var output = Path.GetFullPath(args[2]);
if (Directory.Exists(output) || File.Exists(output)) throw new IOException("Output must not exist");
Directory.CreateDirectory(output);
var export = Path.Combine(output, "export");
assembly.GetType("HD2ModCore.Infrastructure.PhysBoneLuaPackageExport", true)!.GetMethod("Export")!.Invoke(null, [export]);
var patch = "9ba626afa44a3aa3.patch_0";
var names = new[] { "manifest.json", patch, patch + ".stream", patch + ".gpu_resources" };
using (var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(export, "manifest.json")))) {
    if (manifest.RootElement.GetProperty("Guid").GetString() != guid || manifest.RootElement.GetProperty("Name").GetString() != Value("Title")) throw new InvalidDataException("Production manifest mismatch");
}
var bytes = File.ReadAllBytes(Path.Combine(export, patch));
if (bytes.Length < 200 || BinaryPrimitives.ReadUInt32LittleEndian(bytes) != 0xf0000011
    || BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(4)) != 1 || BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(8)) != 1
    || BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(112)) != 0xa14e8dfa2cd117e2) throw new InvalidDataException("Invalid one-resource Lua patch");
var hashType = context.LoadFromAssemblyPath(Path.Combine(root, "HD2GameItemAssets.dll")).GetType("HD2GameItemAssets.StingrayHash", true)!;
var resourceId = (ulong)hashType.GetMethod("Murmur64A", [typeof(string)])!.Invoke(null, [owner])!;
if (BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(104)) != resourceId) throw new InvalidDataException("Lua resource owner hash mismatch");
var offset = checked((int)BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(120)));
var size = checked((int)BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(160)));
if (offset < 184 || size < 8 || offset > bytes.Length - size || BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(offset + 4)) != 2
    || BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(offset)) != size - 8) throw new InvalidDataException("Invalid Lua resource payload");
var body = Encoding.UTF8.GetString(bytes, offset + 8, size - 8).Replace("\r\n", "\n", StringComparison.Ordinal);
if (body != source) throw new InvalidDataException("Exported patch differs from installed production source");
foreach (var name in names.Skip(2)) if (new FileInfo(Path.Combine(export, name)).Length != 0) throw new InvalidDataException("Unexpected external patch data");
var zipPath = Path.Combine(output, "physics-runtime.zip");
using (var zip = ZipFile.Open(zipPath, ZipArchiveMode.Create)) foreach (var name in names) zip.CreateEntryFromFile(Path.Combine(export, name), name, CompressionLevel.Optimal);
using (var zip = ZipFile.OpenRead(zipPath)) {
    if (zip.Entries.Count != names.Length) throw new InvalidDataException("Physics ZIP entry count mismatch");
    foreach (var name in names) {
        using var stream = zip.GetEntry(name)!.Open();
        using var memory = new MemoryStream(); stream.CopyTo(memory);
        if (!memory.ToArray().AsSpan().SequenceEqual(File.ReadAllBytes(Path.Combine(export, name)))) throw new InvalidDataException("Physics ZIP readback mismatch");
    }
}
foreach (var pair in inputs) if (Hash(File.ReadAllBytes(Path.Combine(root, pair.Key))) != pair.Value) throw new IOException("Installed input changed while exporting");
var report = new { kind = "production-physics-runtime", owner, guid, runtimeVersion, compatVersion, inputs,
    producer = "Installed HD2ModCore.PhysBoneLuaPackageExport.Export (no source rebuild, no test ZIP reuse)",
    sourceSha256 = Hash(Encoding.UTF8.GetBytes(source)), zipSha256 = Hash(File.ReadAllBytes(zipPath)),
    entries = names.Select(n => new { path = n, bytes = new FileInfo(Path.Combine(export, n)).Length, sha256 = Hash(File.ReadAllBytes(Path.Combine(export, n))) }).ToArray() };
File.WriteAllText(Path.Combine(output, "physics-provenance.json"), JsonSerializer.Serialize(report, options));
Console.WriteLine(JsonSerializer.Serialize(report, options));

}
catch (Exception error)
{
    Console.Error.WriteLine(error.GetBaseException().Message);
    Environment.ExitCode = 1;
}

static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
static object Inspect(string path) {
    using var pe = new PEReader(File.OpenRead(path)); var r = pe.GetMetadataReader();
    var resources = new List<object>();
    foreach (var h in r.ManifestResources) {
        var resource = r.GetManifestResource(h); if (!resource.Implementation.IsNil) continue;
        var section = pe.GetSectionData(pe.PEHeaders.CorHeader!.ResourcesDirectory.RelativeVirtualAddress);
        var reader = section.GetReader(checked((int)resource.Offset), section.Length - checked((int)resource.Offset));
        var data = reader.ReadBytes(reader.ReadInt32()); var text = Encoding.UTF8.GetString(data);
        resources.Add(new { name = r.GetString(resource.Name), bytes = data.Length, sha256 = Hash(data),
            versions = Regex.Matches(text, @"(?i)\bversion\s*=\s*['""]([^'""\s]+)['""]").Select(m => m.Groups[1].Value).Distinct().ToArray(),
            hasB3OptionModule = text.Contains("INSERT OPTION SWITCH MODULE", StringComparison.Ordinal) || text.Contains("local OptionSwitches=", StringComparison.Ordinal),
            hasFirstPersonSourceModule = text.Contains("INSERT FIRST PERSON SOURCE MODULE", StringComparison.Ordinal) || text.Contains("FirstPersonSource.new", StringComparison.Ordinal) });
    }
    var methods = new List<object>();
    foreach (var h in r.MethodDefinitions) {
        var m = r.GetMethodDefinition(h); var owner = TypeName(r, m.GetDeclaringType()); var name = r.GetString(m.Name);
        if (!(owner.Contains("NativeSkeletonProjectService", StringComparison.Ordinal)
            || owner.Contains("BuildAttachmentFixAsync", StringComparison.Ordinal) || owner.Contains("ImportVpkSourceAsync", StringComparison.Ordinal)
            || owner.EndsWith("PhysBoneLuaSource", StringComparison.Ordinal) && (name == "ComposeAttachmentFixPackage" || name == "ComposeB3AttachmentFixPackage")
            || owner.EndsWith("LuaAddonCatalog", StringComparison.Ordinal) && name == "AttachmentFix") || m.RelativeVirtualAddress == 0) continue;
        var il = pe.GetMethodBody(m.RelativeVirtualAddress).GetILBytes()!;
        var strings = new List<string>(); var calls = new List<string>();
        var ops = typeof(OpCodes).GetFields(BindingFlags.Public | BindingFlags.Static).Select(f => (OpCode)f.GetValue(null)!).ToDictionary(o => unchecked((ushort)o.Value));
        for (var at = 0; at < il.Length;) {
            ushort value = il[at++]; if (value == 0xfe) value = (ushort)(0xfe00 | il[at++]); var op = ops[value];
            if (op.OperandType == OperandType.InlineString) strings.Add(r.GetUserString(MetadataTokens.UserStringHandle(BitConverter.ToInt32(il, at) & 0xffffff)));
            if (op.OperandType == OperandType.InlineMethod) calls.Add(EntityName(r, MetadataTokens.EntityHandle(BitConverter.ToInt32(il, at))));
            at += op.OperandType switch {
                OperandType.InlineSwitch => 4 + 4 * BitConverter.ToInt32(il, at),
                OperandType.InlineNone => 0,
                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                OperandType.InlineVar => 2, OperandType.InlineI8 or OperandType.InlineR => 8, _ => 4 };
        }
        methods.Add(new { type = owner, name, ilSha256 = Hash(il), strings = strings.Distinct().ToArray(), calls = calls.Distinct().ToArray() });
    }
    return new { path = Path.GetFullPath(path), sha256 = Hash(File.ReadAllBytes(path)), resources, methods };
}
static string TypeName(MetadataReader r, TypeDefinitionHandle h) {
    var t = r.GetTypeDefinition(h); return (t.GetDeclaringType().IsNil ? r.GetString(t.Namespace) : TypeName(r, t.GetDeclaringType())) + "." + r.GetString(t.Name);
}
static string EntityName(MetadataReader r, EntityHandle h) => h.Kind switch {
    HandleKind.MethodDefinition => TypeName(r, r.GetMethodDefinition((MethodDefinitionHandle)h).GetDeclaringType()) + "::" + r.GetString(r.GetMethodDefinition((MethodDefinitionHandle)h).Name),
    HandleKind.MemberReference => EntityName(r, r.GetMemberReference((MemberReferenceHandle)h).Parent) + "::" + r.GetString(r.GetMemberReference((MemberReferenceHandle)h).Name),
    HandleKind.TypeReference => r.GetString(r.GetTypeReference((TypeReferenceHandle)h).Namespace) + "." + r.GetString(r.GetTypeReference((TypeReferenceHandle)h).Name),
    HandleKind.TypeDefinition => TypeName(r, (TypeDefinitionHandle)h),
    HandleKind.MethodSpecification => EntityName(r, r.GetMethodSpecification((MethodSpecificationHandle)h).Method), _ => h.Kind.ToString() };
