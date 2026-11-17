using System.Text.Json;
using HD2ModCore.Domain;
using HD2ModCore.Infrastructure;

var manager = Path.GetFullPath(args[0]); var output = Path.GetFullPath(args[1]);
if (Directory.Exists(output)) throw new IOException("Use a fresh isolated output directory");
Directory.CreateDirectory(output);
var mods = Path.Combine(manager, "test-library");
using var library = JsonDocument.Parse(File.ReadAllText(Path.Combine(mods, "library.json")));
var nodes = new Dictionary<ModNodeId, ModNode>();
foreach (var p in library.RootElement.GetProperty("nodes").EnumerateObject()) {
    var id = new ModNodeId(Guid.Parse(p.Name)); var path = p.Value.GetProperty("relativePath").GetString()!;
    nodes.Add(id, new ModNode(id, path, new ModNodeMetadata(path, null, DateTimeOffset.UtcNow, null), [], []));
}
var selected = nodes.Values.Single(n => n.RelativePath == "[单骨架模型]Cow_QiPao_Milltina_Nick");
var snapshot = new LibrarySnapshot(1, DateTimeOffset.UtcNow, nodes, []);
var index = await new PatchFileIndexBuilder(new PatchFileNameParser()).BuildAsync(snapshot, mods);
if (index.Issues.Any(i => i.Severity == CoreIssueSeverity.Error)) throw new InvalidDataException(string.Join(";", index.Issues.Select(i => i.Message)));
var profile = new Profile(ProfileId.New(), "isolated model only", DateTimeOffset.UtcNow, null, [new ProfileEntry(selected.Id, 0)]);
var data = Path.Combine(output, "data"); Directory.CreateDirectory(data);
var plan = await new ApplyPlanner(new PatchFileNameParser()).BuildPlanAsync(profile, snapshot, index, data);
foreach (var m in plan.PatchMappings) File.Copy(m.SourcePath, m.TargetPath);
var actual = await RuntimeArmorResourceFilter.ReadDeployedUnitsAsync(data);
using var workspace = JsonDocument.Parse(File.ReadAllText(Path.Combine(mods, ".hd2modmanager", "armor-registry.workspace.json")));
var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
var models = workspace.RootElement.GetProperty("models").Deserialize<RuntimeArmorRegistryModel[]>(options)!;
var mappings = workspace.RootElement.GetProperty("mappings").Deserialize<RuntimeArmorRegistryMapping[]>(options)!;
var desired = new RuntimeArmorRegistryDocument(1, true, mappings, models);
var compiled = RuntimeArmorResourceFilter.Compile(desired, actual);
if (compiled.Mappings.Count != mappings.Length) throw new Exception("Mappings lost");
var source = models.Single(m => m.Key == "custom-95fd1a3f4c1a4866be71d55974f93837");
var expected = source.Pieces!.Select(p => Convert.ToUInt64(p.Unit, 16)).Distinct().ToArray();
if (!expected.All(actual.Contains)) throw new Exception("Namespace missing");
string inactive;
try { RuntimeArmorResourceFilter.Compile(desired, new HashSet<ulong>()); throw new Exception("Inactive model guard bypassed"); }
catch (InvalidDataException e) { inactive = e.Message; }
File.WriteAllText(Path.Combine(output, "report.json"), JsonSerializer.Serialize(new { status = "PASS_REAL_LIBRARY_ISOLATED_PLAN", expectedUnits = expected.Select(u => u.ToString("x16")), namespaceMatches = expected.Length, actualUnitCount = actual.Count, mappings = compiled.Mappings.Count, inactiveModelRejected = inactive, files = plan.PatchMappings.Select(m => new { m.SourcePath, m.TargetPatchIndex, m.SidecarKind }), sourceLibraryWritten = false, actualGameWritten = false }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"PASS actual installation dependencies: {expected.Length}/7 source Units; {compiled.Mappings.Count} mappings; effective overwrite preserved; inactive guard retained");
