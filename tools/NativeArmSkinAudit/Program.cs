using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;

// Read the delivered GPU vertex weights through the production mesh decoder.
// A name in TransformInfo alone does not prove that rendered triangles use it.
if (args.Length != 2) throw new ArgumentException("patch-path output-json");
var entries = await new PatchTocScanner().ScanEntriesAsync(Path.GetFullPath(args[0]));
var reader = new PatchUnitMeshReader();
var rows = new List<object>();
foreach (var entry in entries.Where(e => e.AssetKey.TypeId == PatchUnitMeshReader.UnitTypeId))
{
    var unit = await reader.ReadCanonicalSourceAsync(entry, entries);
    var model = unit.Model;
    var counts = new Dictionary<uint, HashSet<(int Mesh, uint Vertex)>>();
    var meshes = new List<object>();
    foreach (var mesh in model.RawMeshData)
    {
        if (mesh.LodIndex < 0) continue;
        var info = model.BoneInfos[mesh.LodIndex];
        var used = new HashSet<uint>();
        foreach (var section in mesh.Sections)
        {
            if (section.Triangles.Count == 0) continue;
            var remap = info.Remaps.Single(r => r.MaterialIndex == section.MaterialIndex);
            foreach (var vertexId in section.Triangles.SelectMany(t => new[] { t.A, t.B, t.C }).Distinct())
            {
                var vertex = mesh.Vertices[checked((int)vertexId)];
                foreach (var component in vertex.Components.Where(c => c.TypeName == "bone_index"))
                {
                    var weight = vertex.Components.SingleOrDefault(c => c.TypeName == "bone_weight" && c.Index == component.Index);
                    for (var i = 0; i < component.UIntValues.Length; i++)
                    {
                        var value = weight == null ? (i == 0 ? 1f : 0f) : weight.FloatValues[i];
                        if (!float.IsFinite(value) || value < 0) throw new InvalidDataException("Invalid vertex weight");
                        if (value <= 0) continue;
                        var node = info.RealIndices[checked((int)remap.FakeIndices[checked((int)component.UIntValues[i])])];
                        if (node >= model.TransformNameHashes.Count) throw new InvalidDataException("Skin node outside TransformInfo");
                        if (!counts.TryGetValue(node, out var vertices)) counts[node] = vertices = new();
                        vertices.Add((mesh.MeshInfoIndex, vertexId));
                        used.Add(node);
                    }
                }
            }
        }
        meshes.Add(new { mesh.MeshInfoIndex, mesh.LodIndex, nodes = used.Order().ToArray() });
    }
    rows.Add(new {
        resource = entry.AssetKey.FileId.ToString("x16"),
        nodeCount = model.TransformNameHashes.Count,
        weightedNodes = counts.OrderBy(r => r.Key).Select(r => new {
            index = r.Key, hash = model.TransformNameHashes[(int)r.Key], weightedVertices = r.Value.Count }).ToArray(),
        meshes
    });
}
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
await File.WriteAllTextAsync(args[1], JsonSerializer.Serialize(new { status = "PASS", gameTested = false, rows }, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"Decoded drawn-triangle skin weights for {rows.Count} model Units.");
