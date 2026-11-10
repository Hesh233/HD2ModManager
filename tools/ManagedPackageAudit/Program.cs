using System.Collections.Immutable;
using System.Reflection.Emit;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

if (args.Length != 3) throw new ArgumentException("Usage: ManagedPackageAudit before.dll after.dll report.json");
var before = Capture(args[0]);
var after = Capture(args[1]);
var changed = before.Methods.Keys.Union(after.Methods.Keys).Where(k => before.Methods.GetValueOrDefault(k) != after.Methods.GetValueOrDefault(k)).ToArray();
var changedResources = before.Resources.Keys.Union(after.Resources.Keys).Where(k => before.Resources.GetValueOrDefault(k) != after.Resources.GetValueOrDefault(k)).ToArray();
var changedConstants = before.Constants.Keys.Union(after.Constants.Keys).Where(k => before.Constants.GetValueOrDefault(k) != after.Constants.GetValueOrDefault(k)).ToArray();
var changedReferences = before.References.Keys.Union(after.References.Keys).Where(k => before.References.GetValueOrDefault(k) != after.References.GetValueOrDefault(k)).ToArray();
var output = new { before = Path.GetFullPath(args[0]), after = Path.GetFullPath(args[1]),
    beforeSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))), afterSha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[1]))),
    identityUnchanged = before.Identity == after.Identity, methodsBefore = before.Methods.Count, methodsAfter = after.Methods.Count,
    changedMethods = changed, constantsBefore = before.Constants.Count, constantsAfter = after.Constants.Count,
    changedConstants, changedReferences, resourcesBefore = before.Resources.Count, resourcesAfter = after.Resources.Count, changedResources,
    comparison = "IL operands resolve metadata members and strings; no assembly execution or dependency loading" };
File.WriteAllText(args[2], JsonSerializer.Serialize(output, new JsonSerializerOptions { WriteIndented = true }));
Console.WriteLine(JsonSerializer.Serialize(new { output.identityUnchanged, output.methodsBefore, output.methodsAfter, changedMethodCount=changed.Length, changedMethods=changed.Take(12), changedConstants, changedReferences, changedResources }, new JsonSerializerOptions { WriteIndented = true }));

static Snapshot Capture(string path)
{
    using var stream = File.OpenRead(path);
    using var pe = new PEReader(stream);
    var r = pe.GetMetadataReader();
    var ad = r.GetAssemblyDefinition();
    var identity = r.GetString(ad.Name) + "|" + ad.Version + "|" + r.GetString(ad.Culture) + "|" + Convert.ToHexString(r.GetBlobBytes(ad.PublicKey));
    var methods = new Dictionary<string, string>();
    var constants = new Dictionary<string, string>();
    foreach (var th in r.TypeDefinitions)
    {
        var type = r.GetTypeDefinition(th);
        var typeName = Entity(r, th);
        foreach (var mh in type.GetMethods())
        {
            var m = r.GetMethodDefinition(mh);
            var key = typeName + "::" + r.GetString(m.Name) + "|" + SignatureNames.Format(m.DecodeSignature(new SignatureNames(), (object?)null));
            if (m.RelativeVirtualAddress == 0) { methods[key] = "none"; continue; }
            var body = pe.GetMethodBody(m.RelativeVirtualAddress);
            var canonical = $"attributes:{m.Attributes}:{m.ImplAttributes}|" + Normalize(r, body.GetILBytes()!);
            canonical += "|locals:" + (body.LocalSignature.IsNil ? "none" : string.Join(",", r.GetStandaloneSignature(body.LocalSignature).DecodeLocalSignature(new SignatureNames(), (object?)null)));
            foreach (var e in body.ExceptionRegions)
                canonical += $"|exception:{e.Kind}:{e.TryOffset}:{e.TryLength}:{e.HandlerOffset}:{e.HandlerLength}:{e.FilterOffset}:" + (e.CatchType.IsNil ? "none" : Entity(r, e.CatchType));
            methods[key] = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
        }
        foreach (var fh in type.GetFields())
        {
            var field = r.GetFieldDefinition(fh);
            if (!field.GetDefaultValue().IsNil)
            {
                var c = r.GetConstant(field.GetDefaultValue());
                constants[typeName + "::" + r.GetString(field.Name)] = c.TypeCode + ":" + Convert.ToHexString(r.GetBlobBytes(c.Value));
            }
        }
    }
    var resources = new Dictionary<string, string>();
    foreach (var handle in r.ManifestResources)
    {
        var resource = r.GetManifestResource(handle);
        if (!resource.Implementation.IsNil) throw new InvalidDataException("Expected embedded resources only");
        var section = pe.GetSectionData(pe.PEHeaders.CorHeader!.ResourcesDirectory.RelativeVirtualAddress);
        var reader = section.GetReader(checked((int)resource.Offset), section.Length - checked((int)resource.Offset));
        var data = reader.ReadBytes(reader.ReadInt32());
        resources[r.GetString(resource.Name)] = Convert.ToHexString(SHA256.HashData(data));
    }
    var references = r.AssemblyReferences.ToDictionary(h => r.GetString(r.GetAssemblyReference(h).Name), h => { var a=r.GetAssemblyReference(h); return a.Version + "|" + r.GetString(a.Culture) + "|" + Convert.ToHexString(r.GetBlobBytes(a.PublicKeyOrToken)); });
    return new(identity, methods, constants, resources, references);
}

static string Normalize(MetadataReader r, byte[] il)
{
    var ops = typeof(OpCodes).GetFields(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)
        .Select(f => (OpCode)f.GetValue(null)!).ToDictionary(o => unchecked((ushort)o.Value));
    var b = new StringBuilder();
    for (var at = 0; at < il.Length;)
    {
        ushort value = il[at++];
        if (value == 0xfe) value = (ushort)(0xfe00 | il[at++]);
        var op = ops[value];
        b.Append(op.Name).Append(':');
        if (op.OperandType == OperandType.InlineSwitch)
        {
            var count = BitConverter.ToInt32(il, at); var bytes = 4 + count * 4;
            b.Append(Convert.ToHexString(il.AsSpan(at, bytes))); at += bytes;
        }
        else if (op.OperandType == OperandType.InlineString)
        {
            b.Append(JsonSerializer.Serialize(r.GetUserString(MetadataTokens.UserStringHandle(BitConverter.ToInt32(il, at) & 0xffffff)))); at += 4;
        }
        else if (op.OperandType is OperandType.InlineMethod or OperandType.InlineType or OperandType.InlineField or OperandType.InlineTok)
        {
            b.Append(Entity(r, MetadataTokens.EntityHandle(BitConverter.ToInt32(il, at)))); at += 4;
        }
        else
        {
            var bytes = op.OperandType switch
            {
                OperandType.InlineNone => 0,
                OperandType.ShortInlineBrTarget or OperandType.ShortInlineI or OperandType.ShortInlineVar => 1,
                OperandType.InlineVar => 2,
                OperandType.InlineI8 or OperandType.InlineR => 8,
                _ => 4
            };
            b.Append(Convert.ToHexString(il.AsSpan(at, bytes))); at += bytes;
        }
        b.Append(';');
    }
    return b.ToString();
}

static string Entity(MetadataReader r, EntityHandle h) => h.Kind switch
{
    HandleKind.TypeDefinition => TypeDef(r, (TypeDefinitionHandle)h),
    HandleKind.TypeReference => TypeRef(r, (TypeReferenceHandle)h),
    HandleKind.TypeSpecification => r.GetTypeSpecification((TypeSpecificationHandle)h).DecodeSignature(new SignatureNames(), (object?)null),
    HandleKind.MethodDefinition => Method(r, (MethodDefinitionHandle)h),
    HandleKind.FieldDefinition => Field(r, (FieldDefinitionHandle)h),
    HandleKind.MemberReference => Member(r, (MemberReferenceHandle)h),
    HandleKind.MethodSpecification => "methodspec:" + Entity(r, r.GetMethodSpecification((MethodSpecificationHandle)h).Method) + "|" + string.Join(",", r.GetMethodSpecification((MethodSpecificationHandle)h).DecodeSignature(new SignatureNames(), (object?)null)),
    HandleKind.AssemblyReference => "assembly:" + r.GetString(r.GetAssemblyReference((AssemblyReferenceHandle)h).Name),
    _ => h.Kind + ":" + MetadataTokens.GetToken(h)
};
static string TypeDef(MetadataReader r, TypeDefinitionHandle h)
{
    var t = r.GetTypeDefinition(h); var p = t.GetDeclaringType();
    return (p.IsNil ? r.GetString(t.Namespace) : TypeDef(r, p)) + "." + r.GetString(t.Name);
}
static string TypeRef(MetadataReader r, TypeReferenceHandle h)
{
    var t = r.GetTypeReference(h);
    return (t.ResolutionScope.Kind == HandleKind.AssemblyReference ? Entity(r,t.ResolutionScope) : t.ResolutionScope.Kind == HandleKind.TypeReference ? Entity(r,t.ResolutionScope) : "module") + ":" + r.GetString(t.Namespace) + "." + r.GetString(t.Name);
}
static string Method(MetadataReader r, MethodDefinitionHandle h)
{
    var m = r.GetMethodDefinition(h); return Entity(r, m.GetDeclaringType()) + "::" + r.GetString(m.Name) + "|" + SignatureNames.Format(m.DecodeSignature(new SignatureNames(), (object?)null));
}
static string Field(MetadataReader r, FieldDefinitionHandle h)
{
    var f = r.GetFieldDefinition(h); return Entity(r, f.GetDeclaringType()) + "::" + r.GetString(f.Name) + "|" + f.DecodeSignature(new SignatureNames(), (object?)null);
}
static string Member(MetadataReader r, MemberReferenceHandle h)
{
    var m = r.GetMemberReference(h); return Entity(r, m.Parent) + "::" + r.GetString(m.Name) + "|" + (m.GetKind()==MemberReferenceKind.Field ? m.DecodeFieldSignature(new SignatureNames(), (object?)null) : SignatureNames.Format(m.DecodeMethodSignature(new SignatureNames(), (object?)null)));
}
record Snapshot(string Identity, Dictionary<string,string> Methods, Dictionary<string,string> Constants, Dictionary<string,string> Resources, Dictionary<string,string> References);

sealed class SignatureNames : ISignatureTypeProvider<string,object?>
{
    public static string Format(MethodSignature<string> s) => $"{s.Header.RawValue}:g{s.GenericParameterCount}:req{s.RequiredParameterCount}:{s.ReturnType}({string.Join(",",s.ParameterTypes)})";
    public string GetArrayType(string e, ArrayShape s) => $"{e}[rank{s.Rank};{string.Join(",",s.Sizes)};{string.Join(",",s.LowerBounds)}]";
    public string GetByReferenceType(string e) => e+"&";
    public string GetFunctionPointerType(MethodSignature<string> s) => "fnptr:"+Format(s);
    public string GetGenericInstantiation(string g, ImmutableArray<string> a) => g+"<"+string.Join(",",a)+">";
    public string GetGenericMethodParameter(object? c,int i) => "!!"+i;
    public string GetGenericTypeParameter(object? c,int i) => "!"+i;
    public string GetModifiedType(string m,string u,bool req) => u+(req?" modreq(":" modopt(")+m+")";
    public string GetPinnedType(string e) => e+" pinned";
    public string GetPointerType(string e) => e+"*";
    public string GetPrimitiveType(PrimitiveTypeCode t) => t.ToString();
    public string GetSZArrayType(string e) => e+"[]";
    public string GetTypeFromDefinition(MetadataReader r,TypeDefinitionHandle h,byte k)
    { var t=r.GetTypeDefinition(h);var p=t.GetDeclaringType();return (p.IsNil?r.GetString(t.Namespace):GetTypeFromDefinition(r,p,k))+"."+r.GetString(t.Name); }
    public string GetTypeFromReference(MetadataReader r,TypeReferenceHandle h,byte k)
    { var t=r.GetTypeReference(h);var scope=t.ResolutionScope.Kind==HandleKind.AssemblyReference?"assembly:"+r.GetString(r.GetAssemblyReference((AssemblyReferenceHandle)t.ResolutionScope).Name):t.ResolutionScope.Kind==HandleKind.TypeReference?GetTypeFromReference(r,(TypeReferenceHandle)t.ResolutionScope,k):"module";return scope+":"+r.GetString(t.Namespace)+"."+r.GetString(t.Name); }
    public string GetTypeFromSpecification(MetadataReader r,object? c,TypeSpecificationHandle h,byte k) => r.GetTypeSpecification(h).DecodeSignature(this,c);
}
