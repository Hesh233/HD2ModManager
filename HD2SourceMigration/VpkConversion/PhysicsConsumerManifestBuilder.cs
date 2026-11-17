using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;

namespace HD2SourceMigration.VpkConversion;

/// <summary>Read-only consumer facts. Does not rewrite a model, bind or library.
/// A plan is tied to the exact Unit and GPU/stream payload, not its filename.
/// The runtime must prove the winning deployed payload before using these facts.
/// Unsupported non-mesh components make a Unit ineligible, never silently empty.</summary>
public static class PhysicsConsumerManifestBuilder
{
    public const string Revision = "single-toc-palette-consumers-v2";
    public const string RecordName = "hd2_physics_consumers_v2.json";
    private static string Sha(ReadOnlySpan<byte> b) => Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();
    private static async Task<string> PreparedFingerprintAsync(string path,CancellationToken ct)
    {
        var suffix=path.EndsWith(".gpu_resources",StringComparison.Ordinal)?".gpu_resources":path.EndsWith(".stream",StringComparison.Ordinal)?".stream":null;
        if(suffix is null)return Sha(await File.ReadAllBytesAsync(path,ct));
        var toc=path[..^suffix.Length];var entries=await new PatchTocScanner().ScanEntriesAsync(toc,ct);var reader=new PatchEntryPayloadReader();
        using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        // Same contract as single_skeleton._model_files: sorted referenced assets,
        // not GPU padding or the separately appended PhysBone compatibility trailer.
        foreach(var entry in entries.OrderBy(e=>e.AssetKey.FileId).ThenBy(e=>e.AssetKey.TypeId))
        {
            var payload=await reader.ReadPayloadAsync(entry,ct);
            hash.AppendData(suffix==".gpu_resources"?payload.GpuResourceData:payload.StreamData);
        }
        return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();
    }
    private static uint U32(byte[] b, int at) => BinaryPrimitives.ReadUInt32LittleEndian(b.AsSpan(at,4));
    private static ulong U64(byte[] b, int at) => BinaryPrimitives.ReadUInt64LittleEndian(b.AsSpan(at,8));
    private static uint NameHash(string s) => HD2SourceMigration.Hd2NameHash.Of(s);
    private static string ReadName(byte[] b,int table,uint at)
    {
        var start=checked(table+(int)at); if(start<0||start>=b.Length)throw new InvalidDataException("Rig name outside table");
        var stop=Array.IndexOf(b,(byte)0,start);if(stop<start)throw new InvalidDataException("Unterminated rig name");
        return Encoding.UTF8.GetString(b,start,stop-start);
    }
    private static HashSet<string> RigNames(byte[] b,bool driver)
    {
        if(b.Length<32)throw new InvalidDataException("Rig too short");
        var names=new HashSet<string>(StringComparer.Ordinal);int count=checked((int)U32(b,12)),table=checked((int)U32(b,16)),size=checked((int)U32(b,24));
        if(count<0||count>4096||table<32||table>b.Length)throw new InvalidDataException("Rig range");
        if(!driver)
        {
            if(!b.AsSpan(0,8).SequenceEqual("HD2SRG01"u8)||size<148)throw new InvalidDataException("Unsupported spring rig");
            for(int i=0;i<count;i++){int at=32+i*size;names.Add(ReadName(b,table,U32(b,at+8)));names.Add(ReadName(b,table,U32(b,at+12)));}
        }
        else
        {
            if(!b.AsSpan(0,8).SequenceEqual("HD2DRV01"u8)||U32(b,8)!=3||size!=44)throw new InvalidDataException("Consumer plans are single-v3 only");
            int at=32;for(int i=0;i<count;i++){names.Add(ReadName(b,table,U32(b,at)));names.Add(ReadName(b,table,U32(b,at+4)));names.Add(ReadName(b,table,U32(b,at+8)));var rules=U32(b,at+12);if(rules<1||rules>64)throw new InvalidDataException("Driver rules");at=checked(at+size+(int)rules*48);if(at>table)throw new InvalidDataException("Driver record range");}
        }
        names.Remove("");return names;
    }
    private static HashSet<uint> PhysicalHashes(byte[] spring,byte[] driver)
    {
        var result=new HashSet<uint>();int count=(int)U32(spring,12),table=(int)U32(spring,16),stride=(int)U32(spring,24);
        for(int i=0;i<count;i++)result.Add(NameHash(ReadName(spring,table,U32(spring,32+i*stride+8))));
        int at=32;for(int i=0;i<(int)U32(driver,12);i++){result.Add(NameHash(ReadName(driver,(int)U32(driver,16),U32(driver,at))));at+=44+(int)U32(driver,at+12)*48;}
        return result;
    }
    public static async Task<byte[]> BuildAsync(string modelDirectory,CancellationToken ct=default)
    {
        var root=Path.GetFullPath(modelDirectory);var payload=Path.Combine(root,"sectional");
        var markerPath=Path.Combine(payload,"single-skeleton.json");var certPath=Path.Combine(payload,"single-hd2-bind.json");
        using var marker=JsonDocument.Parse(await File.ReadAllBytesAsync(markerPath,ct));using var cert=JsonDocument.Parse(await File.ReadAllBytesAsync(certPath,ct));
        var m=marker.RootElement;var c=cert.RootElement;
        if(m.GetProperty("sourceRigRetained").GetBoolean()||m.GetProperty("attachmentLua").GetBoolean()||m.GetProperty("attachmentSwap").GetBoolean()||c.GetProperty("policy").GetString()!="hd2-source-sized-shared-bind-v1"||c.GetProperty("meshOnlyPostprocessing").GetBoolean())throw new InvalidDataException("Not a certified single HD2 model");
        var effective=await File.ReadAllBytesAsync(Path.Combine(payload,"single-config.toml"),ct);var certBytes=await File.ReadAllBytesAsync(certPath,ct);
        if(Sha(certBytes)!=m.GetProperty("bindSha256").GetString()||Sha(effective)!=m.GetProperty("configSha256").GetString())throw new InvalidDataException("Stale bind/effective certificate");
        foreach(var file in m.GetProperty("modelFiles").EnumerateArray())
        {
            var name=file.GetProperty("name").GetString()??throw new InvalidDataException("Model fingerprint name");
            if(Path.IsPathRooted(name)||name.Contains("..")||Path.GetFileName(name)!=name)throw new InvalidDataException("Model fingerprint path");
            var actual=await PreparedFingerprintAsync(Path.Combine(payload,name),ct);
            if(actual!=file.GetProperty("sha256").GetString())throw new InvalidDataException("Prepared model fingerprint changed: "+name);
        }
        var native=c.GetProperty("driverHashes").EnumerateArray().Select(e=>e.GetUInt32()).ToHashSet();if(native.Count!=c.GetProperty("driverHashes").GetArrayLength()||native.Count==0)throw new InvalidDataException("Native node certificate");
        var nativeWorld=c.GetProperty("driverWorld").EnumerateArray().Select(x=>x.EnumerateArray().Select(v=>v.GetSingle()).ToArray()).ToArray();
        var nativeHashes=c.GetProperty("driverHashes").EnumerateArray().Select(x=>x.GetUInt32()).ToArray();
        if(nativeWorld.Length!=nativeHashes.Length||nativeWorld.Any(x=>x.Length!=16||x.Any(v=>!float.IsFinite(v))))throw new InvalidDataException("Invalid native world bind certificate");
        var spring=await File.ReadAllBytesAsync(Path.Combine(payload,"physbone-rig.bin"),ct);var driver=await File.ReadAllBytesAsync(Path.Combine(payload,"physbone-driver-rig.bin"),ct);
        var bindingNames=RigNames(spring,false);bindingNames.UnionWith(RigNames(driver,true));var physical=PhysicalHashes(spring,driver);
        var scanner=new PatchTocScanner();var reader=new PatchUnitMeshReader();var payloadReader=new PatchEntryPayloadReader();
        var units=new List<object>();var rejected=new List<object>();
        foreach(var domain in new[]{"sectional","Overwrite"})
        {
            var dir=Path.Combine(root,domain);if(!Directory.Exists(dir))continue;
            foreach(var patch in Directory.EnumerateFiles(dir,"*.patch_*").Where(p=>!p.EndsWith(".stream")&&!p.EndsWith(".gpu_resources")).Order(StringComparer.Ordinal))
            {
                var entries=await scanner.ScanEntriesAsync(patch,ct);
                foreach(var entry in entries.Where(e=>e.AssetKey.TypeId==PatchUnitMeshReader.UnitTypeId))
                {
                    try
                    {
                        var raw=await payloadReader.ReadPayloadAsync(entry,ct);var src=await reader.ReadCanonicalSourceAsync(entry,entries,cancellationToken:ct);var model=src.Model;var toc=raw.TocData;
                        if(model.Version!=10800438||model.CompositeRef!=0||model.TransformNameHashes.Distinct().Count()!=model.TransformNameHashes.Count||!native.IsSubsetOf(model.TransformNameHashes))throw new InvalidDataException("Unsupported/non-single Unit layout");
                        // Unknown actor/StateMachine/Wwise/connectors are not treated as no consumers.
                        foreach(int at in new[]{0x18,0x20})if(U64(toc,at)!=0)throw new InvalidDataException($"External Unit reference at {at:x}");
                        foreach(int at in new[]{0x40,0x44,0x48,0x50,0x68,0x6c,0x74,0x78,0x7c})if(U32(toc,at)!=0)throw new InvalidDataException($"Unsupported non-mesh header at {at:x}");
                        for(int ni=0;ni<nativeHashes.Length;ni++)
                        {
                            int index=model.TransformNameHashes.ToList().IndexOf(nativeHashes[ni]);
                            var world=model.TransformInfo.Matrices[index].Values;
                            if(world.Count!=16||world.Where((value,j)=>!float.IsFinite(value)||Math.Abs(value-nativeWorld[ni][j])>1e-4f).Any())throw new InvalidDataException("Native bind differs from this model certificate");
                        }
                        var nativeNodes=model.TransformNameHashes.Select((h,i)=>(h,i)).Where(p=>native.Contains(p.h)).Select(p=>p.i).ToHashSet();
                        var nonMesh=new HashSet<int>(nativeNodes);var weighted=new HashSet<int>();
                        // Preserve every non-deformation helper/socket, even if it has no triangles.
                        for(int i=0;i<model.TransformNameHashes.Count;i++)if(!physical.Contains(model.TransformNameHashes[i]))nonMesh.Add(i);
                        foreach(var mesh in model.Meshes){if(mesh.TransformIndex>=model.TransformNameHashes.Count)throw new InvalidDataException("Mesh origin node");nonMesh.Add((int)mesh.TransformIndex);}
                        var connecting=(int)U32(toc,0x54);
                        if(connecting>0)
                        {
                            int stop=(int)model.BoneInfoOffset;if(stop<=connecting||stop>toc.Length)throw new InvalidDataException("Connecting bone range");
                            int count=checked((int)U32(toc,connecting));if(count<1||count>256||4+count*12>stop-connecting)throw new InvalidDataException("Connecting bone count");
                            for(int i=0;i<count;i++){int at=connecting+4+i*12;uint hash=U32(toc,at);int node=model.TransformNameHashes.ToList().IndexOf(hash);if(node<0||U32(toc,at+4)!=0||U32(toc,at+8)>15)throw new InvalidDataException("Unsupported connecting bone record");nonMesh.Add(node);}
                            for(int at=connecting+4+count*12;at<stop;at++)if(toc[at]!=0)throw new InvalidDataException("Opaque connecting bone tail");
                        }
                        var lightAt=(int)U32(toc,0x38);var preLight=(int)U32(toc,0x3c);
                        if(lightAt>0){var lights=U32(toc,lightAt);if(lights>256||lightAt+16+(long)lights*112>toc.Length)throw new InvalidDataException("Light range");for(int i=0;i<lights;i++){var node=U32(toc,lightAt+16+i*112+4);if(node>=model.TransformNameHashes.Count)throw new InvalidDataException("Light bone node");nonMesh.Add((int)node);}}
                        if(preLight>0){if(lightAt<preLight||lightAt-preLight>256)throw new InvalidDataException("Opaque pre-light range");for(int at=preLight;at+4<=lightAt;at+=4){uint v=U32(toc,at);if(v<model.TransformNameHashes.Count)nonMesh.Add((int)v);if(v>0&&v-1<model.TransformNameHashes.Count)nonMesh.Add((int)v-1);}}
                        foreach(var mesh in model.RawMeshData)
                        {
                            if(mesh.LodIndex<0){if(mesh.Vertices.Any(v=>v.Components.Any(k=>k.TypeName=="bone_index")))throw new InvalidDataException("Unsupported skinned negative LOD");continue;}
                            var info=model.BoneInfos[mesh.LodIndex];
                            foreach(var section in mesh.Sections)
                            {
                                if(section.Triangles.Count==0)continue;var remap=info.Remaps.Single(r=>r.MaterialIndex==section.MaterialIndex);
                                foreach(var vertexId in section.Triangles.SelectMany(t=>new[]{t.A,t.B,t.C}).Distinct())
                                foreach(var index in mesh.Vertices[(int)vertexId].Components.Where(k=>k.TypeName=="bone_index"))
                                {
                                    var weights=mesh.Vertices[(int)vertexId].Components.SingleOrDefault(k=>k.TypeName=="bone_weight"&&k.Index==index.Index);
                                    for(int j=0;j<index.UIntValues.Length;j++){float weight=weights==null?(j==0?1:0):weights.FloatValues[j];if(!float.IsFinite(weight)||weight<0)throw new InvalidDataException("Invalid skin weight");if(weight<=0)continue;int node=checked((int)info.RealIndices[(int)remap.FakeIndices[(int)index.UIntValues[j]]]);if(node<0||node>=model.TransformNameHashes.Count)throw new InvalidDataException("Skin palette node");weighted.Add(node);}
                                }
                            }
                        }
                        // Safe GPU-independent upper bound: every legal skin index maps
                        // through these TOC palettes. Never reuse a positive-weight v1 mask
                        // without its GPU SHA; v2 preserves ALL possible palette consumers.
                        var palette=new HashSet<int>();
                        foreach(var info in model.BoneInfos)
                        {
                            foreach(var node in info.RealIndices){if(node>=model.TransformNameHashes.Count)throw new InvalidDataException("Palette node outside Unit");palette.Add(checked((int)node));}
                            foreach(var remap in info.Remaps)foreach(var fake in remap.FakeIndices)if(fake>=info.RealIndices.Count)throw new InvalidDataException("Palette remap outside RealIndices");
                        }
                        if(!weighted.IsSubsetOf(palette))throw new InvalidDataException("Actual GPU weights are not covered by the complete TOC palette");
                        var bindings=new Dictionary<string,object>(StringComparer.Ordinal);
                        foreach(var name in bindingNames){uint hash=NameHash(name);int node=model.TransformNameHashes.ToList().IndexOf(hash);if(node<0)continue;var t=model.TransformInfo.LocalTransforms[node];bindings[name]=new{node=node+1,native=native.Contains(hash),p=t.Position,q=t.Rotation,s=t.Scale};}
                        var parents=model.TransformInfo.Entries.Select((e,i)=>e.ParentIndex==ushort.MaxValue||e.ParentIndex==i?-1:(int)e.ParentIndex).ToArray();if(parents.Any(p=>p>=model.TransformNameHashes.Count))throw new InvalidDataException("Parent outside nodes");
                        units.Add(new{resource=entry.AssetKey.FileId.ToString("x16"),domain,nodeCount=model.TransformNameHashes.Count,nodeHashes=model.TransformNameHashes,parents,weightedNodes=weighted.Order().ToArray(),skinPaletteNodes=palette.Order().ToArray(),palettePolicy="all-toc-RealIndices-v1",proofMode="toc-exact-palette-v2",tocExactBase64=Convert.ToBase64String(raw.TocData),nativeNodes=nativeNodes.Order().ToArray(),nonMeshNodes=nonMesh.Order().ToArray(),bindings,tocBytes=raw.TocData.Length,tocSha256=Sha(raw.TocData),gpuBytes=raw.GpuResourceData.Length,gpuSha256=Sha(raw.GpuResourceData),streamBytes=raw.StreamData.Length,streamSha256=Sha(raw.StreamData),modelBindSha256=Sha(certBytes),effectiveConfigSha256=Sha(effective),nonMeshPolicy="native-and-all-nondeformation-helpers+mesh-origins+lights+conservative-prelight+typed-connecting-bone-v1",sourcePatch=patch});
                    }
                    catch(Exception ex) when(ex is InvalidDataException or ArgumentException or IndexOutOfRangeException){rejected.Add(new{resource=entry.AssetKey.FileId.ToString("x16"),domain,reason=ex.Message});}
                }
            }
        }
        return JsonSerializer.SerializeToUtf8Bytes(new{schema="hd2-physics-consumers/2",revision=Revision,modelName=Path.GetFileName(root),rigExactBase64=Convert.ToBase64String(spring),driverExactBase64=Convert.ToBase64String(driver),rigSha256=Sha(spring),driverRigSha256=Sha(driver),configSha256=Sha(effective),bindSha256=Sha(certBytes),units,rejected},new JsonSerializerOptions{WriteIndented=true});
    }
}
