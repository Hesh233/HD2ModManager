using System.Buffers.Binary;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

// Resource-only update: preserve method bodies, metadata identity, references,
// native directories and portable-PDB identity of EACH original installed backend.
if (args.Length != 4 || args[0] != "update")
    throw new ArgumentException("PhysicsResourceUpdate update original.dll formal-source-dir NEW-output-dir");
var original = Path.GetFullPath(args[1]);
var formal = Path.GetFullPath(args[2]);
var output = Path.GetFullPath(args[3]);
var workspace = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../"));
void Safe(string path) {
    if (!path.StartsWith(Path.TrimEndingDirectorySeparator(workspace) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        throw new IOException("Path outside tool workspace: " + path);
    for (var p = path; !string.IsNullOrEmpty(p); p = Path.GetDirectoryName(p))
        if ((File.Exists(p) || Directory.Exists(p)) && File.GetAttributes(p).HasFlag(FileAttributes.ReparsePoint))
            throw new IOException("Linked path refused: " + p);
}
Safe(original); Safe(formal); Safe(output);
if (Directory.Exists(output) || File.Exists(output)) throw new IOException("Use a new output directory");
var bytes = File.ReadAllBytes(original);
using var pe = new PEReader(new MemoryStream(bytes));
var headers = pe.PEHeaders;
var cor = headers.CorHeader ?? throw new InvalidDataException("No CLI header");
var ph = headers.PEHeader ?? throw new InvalidDataException("No PE header");
var md = pe.GetMetadataReader();
if (cor.Flags.HasFlag(CorFlags.StrongNameSigned) || ph.CertificateTableDirectory.Size != 0)
    throw new InvalidDataException("Signed images must be rebuilt/re-signed, not patched");
if (cor.ResourcesDirectory.Size == 0) throw new InvalidDataException("No managed resources");
var replacements = new Dictionary<string, byte[]> {
    ["HD2ModCore.PhysBone.physbone_compat.lua"] = File.ReadAllBytes(Path.Combine(formal, "physbone_compat.lua")),
    ["HD2ModCore.PhysBone.physbone_runtime.lua"] = File.ReadAllBytes(Path.Combine(formal, "physbone_runtime.lua"))
};
var resourceBlock = pe.GetSectionData(cor.ResourcesDirectory.RelativeVirtualAddress);
using var blob = new MemoryStream();
var rows = new List<(int TableOffset, int NewOffset)>();
var records = new List<object>();
var found = new HashSet<string>();
Span<byte> size = stackalloc byte[4];
foreach (var h in md.ManifestResources) {
    var r = md.GetManifestResource(h);
    if (!r.Implementation.IsNil) throw new InvalidDataException("Linked resource refused");
    var read = resourceBlock.GetReader(checked((int)r.Offset), resourceBlock.Length - checked((int)r.Offset));
    var old = read.ReadBytes(read.ReadInt32());
    var name = md.GetString(r.Name);
    var data = replacements.TryGetValue(name, out var replacement) ? replacement : old;
    if (replacement != null) found.Add(name);
    while ((blob.Length & 7) != 0) blob.WriteByte(0);
    int offset = checked((int)blob.Length);

    BinaryPrimitives.WriteInt32LittleEndian(size, data.Length);
    blob.Write(size); blob.Write(data);
    int table = headers.MetadataStartOffset + md.GetTableMetadataOffset(TableIndex.ManifestResource)
        + (MetadataTokens.GetRowNumber(h) - 1) * md.GetTableRowSize(TableIndex.ManifestResource);
    rows.Add((table, offset));
    records.Add(new { name, replaced = replacement != null, beforeSha256 = Convert.ToHexString(SHA256.HashData(old)), afterSha256 = Convert.ToHexString(SHA256.HashData(data)), size = data.Length });
}
if (!found.SetEquals(replacements.Keys)) throw new InvalidDataException("Missing physics resources");
int peAt = BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(0x3c));
int optional = peAt + 24;
int optionalSize = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(peAt + 20));
int sectionHeaders = optional + optionalSize;
int count = headers.CoffHeader.NumberOfSections;
var last = headers.SectionHeaders[count - 1];
if (headers.SectionHeaders.Any(s => s.VirtualAddress > last.VirtualAddress || s.PointerToRawData > last.PointerToRawData))
    throw new InvalidDataException("Unexpected PE section layout");
int Align(int n, int alignment) => checked((n + alignment - 1) / alignment * alignment);
int append = Align(bytes.Length, ph.FileAlignment);
int newEnd = checked(append + (int)blob.Length);
int newRaw = Align(newEnd - last.PointerToRawData, ph.FileAlignment);
int newVirtual = newEnd - last.PointerToRawData;
int newRva = checked(last.VirtualAddress + append - last.PointerToRawData);
var candidate = new byte[last.PointerToRawData + newRaw];
bytes.CopyTo(candidate, 0); blob.ToArray().CopyTo(candidate, append);
void Write(int at, int value) => BinaryPrimitives.WriteInt32LittleEndian(candidate.AsSpan(at), value);
foreach (var row in rows) Write(row.TableOffset, row.NewOffset);
Write(headers.CorHeaderStartOffset + 24, newRva);
Write(headers.CorHeaderStartOffset + 28, checked((int)blob.Length));
int sh = sectionHeaders + (count - 1) * 40;
Write(sh + 8, newVirtual); Write(sh + 16, newRaw);
// The existing relocation bytes remain in place. Its enlarged section must not
// be discardable because CLR resources now live after them, in read-only data.
uint flags = BinaryPrimitives.ReadUInt32LittleEndian(candidate.AsSpan(sh + 36));
flags = (flags & ~0x02000000u) | 0x40000040u;
BinaryPrimitives.WriteUInt32LittleEndian(candidate.AsSpan(sh + 36), flags);
Write(optional + 8, checked(ph.SizeOfInitializedData + newRaw - last.SizeOfRawData));
Write(optional + 56, Align(last.VirtualAddress + newVirtual, ph.SectionAlignment));
Write(optional + 64, 0); // unsigned managed image: checksum is unused; never forge a signature
using (var verify = new PEReader(new MemoryStream(candidate))) {
    var vm = verify.GetMetadataReader();
    if (vm.GetGuid(vm.GetModuleDefinition().Mvid) != md.GetGuid(md.GetModuleDefinition().Mvid))
        throw new InvalidDataException("MVID changed");
    var block = verify.GetSectionData(verify.PEHeaders.CorHeader!.ResourcesDirectory.RelativeVirtualAddress);
    foreach (var h in vm.ManifestResources) {
        var r = vm.GetManifestResource(h); var rd = block.GetReader((int)r.Offset, block.Length - (int)r.Offset);
        var actual = rd.ReadBytes(rd.ReadInt32()); var name = vm.GetString(r.Name);
        if (replacements.TryGetValue(name, out var expected) && !actual.AsSpan().SequenceEqual(expected))
            throw new InvalidDataException("Resource readback failed: " + name);
    }
}
if (!File.ReadAllBytes(original).AsSpan().SequenceEqual(bytes)) throw new IOException("Original changed while updating");
Directory.CreateDirectory(output);
File.WriteAllBytes(Path.Combine(output, "HD2ModCore.dll"), candidate);
var report = new { status = "CANDIDATE_RESOURCE_ONLY", original, output, originalSha256 = Convert.ToHexString(SHA256.HashData(bytes)), candidateSha256 = Convert.ToHexString(SHA256.HashData(candidate)), unchangedMvid = md.GetGuid(md.GetModuleDefinition().Mvid), resources = records };
File.WriteAllText(Path.Combine(output, "resource-update.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine($"Generated resource-only candidate; {records.Count} resources; exactly {found.Count} physics replacements. Original untouched.");

