using Mono.Cecil;
using Mono.Cecil.Cil;

try
{
if (args.Length != 3) throw new ArgumentException("before.dll source.dll output.dll");
using var resolver = new DefaultAssemblyResolver();
resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location)!);
using var target = ModuleDefinition.ReadModule(args[0], new ReaderParameters { AssemblyResolver = resolver });
using var donor = ModuleDefinition.ReadModule(args[1], new ReaderParameters { AssemblyResolver = resolver });
const string name = "HD2ModCore.Infrastructure.ChefArmorMappingTransport";
var donorRoot = donor.GetType(name) ?? throw new InvalidDataException(name);
var types = new Dictionary<TypeDefinition, TypeDefinition>();
var fields = new Dictionary<FieldDefinition, FieldDefinition>();
var methods = new Dictionary<MethodDefinition, MethodDefinition>();
var originalTypes = All(target.Types).ToDictionary(t => t.FullName);
var donorTypes = All([donorRoot]).ToArray();
foreach (var dt in donorTypes) {
    if (originalTypes.TryGetValue(dt.FullName, out var tt)) types.Add(dt, tt);
    else {
        tt = new TypeDefinition(dt.Namespace, dt.Name, dt.Attributes);
        if (dt.DeclaringType is null) target.Types.Add(tt); else types[(TypeDefinition)dt.DeclaringType].NestedTypes.Add(tt);
        types.Add(dt, tt);
        foreach (var gp in dt.GenericParameters) tt.GenericParameters.Add(new GenericParameter(gp.Name, tt) { Attributes = gp.Attributes });
    }
}
foreach (var dt in donorTypes) {
    var tt = types[dt];
    foreach (var df in dt.Fields) {
        var tf = tt.Fields.FirstOrDefault(f => f.Name == df.Name);
        if (tf is null) { tf = new FieldDefinition(df.Name, df.Attributes, target.TypeSystem.Object); tt.Fields.Add(tf); }
        fields.Add(df, tf);
    }
    foreach (var dm in dt.Methods) {
        var tm = tt.Methods.FirstOrDefault(m => m.FullName == dm.FullName);
        if (tm is null) {
            tm = new MethodDefinition(dm.Name, dm.Attributes, target.TypeSystem.Void); tt.Methods.Add(tm);
            foreach (var gp in dm.GenericParameters) tm.GenericParameters.Add(new GenericParameter(gp.Name, tm) { Attributes = gp.Attributes });
            foreach (var dp in dm.Parameters) tm.Parameters.Add(new ParameterDefinition(dp.Name, dp.Attributes, target.TypeSystem.Object));
        }
        methods.Add(dm, tm);
    }
}
var localTypes = All(target.Types).ToDictionary(t => t.FullName);
TypeReference Type(TypeReference t) {
    if (t is GenericParameter) return t; // signatures encode position and kind, not an owner token
    if (t is GenericInstanceType gi) { var r = new GenericInstanceType(Type(gi.ElementType)); foreach (var a in gi.GenericArguments) r.GenericArguments.Add(Type(a)); return r; }
    if (t is ArrayType array) return new ArrayType(Type(array.ElementType), array.Rank);
    if (t is ByReferenceType br) return new ByReferenceType(Type(br.ElementType));
    if (t is PointerType pt) return new PointerType(Type(pt.ElementType));
    if (t is PinnedType pin) return new PinnedType(Type(pin.ElementType));
    if (t is RequiredModifierType req) return new RequiredModifierType(Type(req.ModifierType), Type(req.ElementType));
    if (t is OptionalModifierType opt) return new OptionalModifierType(Type(opt.ModifierType), Type(opt.ElementType));
    if (t.Scope == donor || t.Scope is AssemblyNameReference an && an.Name == donor.Assembly.Name.Name) {
        if (!localTypes.TryGetValue(t.FullName, out var local)) throw new InvalidDataException("Missing installed type: " + t.FullName);
        return local;
    }
    return target.ImportReference(t);
}
foreach (var dt in donorTypes) {
    var tt = types[dt]; tt.BaseType = dt.BaseType is null ? null : Type(dt.BaseType);
    foreach (var df in dt.Fields) { var tf = fields[df]; tf.FieldType = Type(df.FieldType); if (df.HasConstant) tf.Constant = df.Constant; tf.InitialValue = df.InitialValue; }
    foreach (var dm in dt.Methods) {
        var tm = methods[dm]; tm.ReturnType = Type(dm.ReturnType); tm.ImplAttributes = dm.ImplAttributes;
        for (var i = 0; i < dm.Parameters.Count; i++) tm.Parameters[i].ParameterType = Type(dm.Parameters[i].ParameterType);
    }
}
MethodReference Method(MethodReference m) {
    if (m is GenericInstanceMethod gi) { var r = new GenericInstanceMethod(Method(gi.ElementMethod)); foreach (var a in gi.GenericArguments) r.GenericArguments.Add(Type(a)); return r; }
    if (m is MethodDefinition md && methods.TryGetValue(md, out var def)) return def;
    var declaring = Type(m.DeclaringType);
    if (declaring is TypeDefinition td) {
        var match = td.Methods.FirstOrDefault(x => x.FullName == m.FullName);
        if (match is null) throw new InvalidDataException("Missing installed method: " + m.FullName);
        return match;
    }
    var result = new MethodReference(m.Name, Type(m.ReturnType), declaring) { HasThis = m.HasThis, ExplicitThis = m.ExplicitThis, CallingConvention = m.CallingConvention };
    foreach (var gp in m.GenericParameters) result.GenericParameters.Add(new GenericParameter(gp.Name, result));
    foreach (var p in m.Parameters) result.Parameters.Add(new ParameterDefinition(Type(p.ParameterType)));
    return result;
}
FieldReference Field(FieldReference f) {
    if (f is FieldDefinition fd && fields.TryGetValue(fd, out var def)) return def;
    var declaring = Type(f.DeclaringType);
    if (declaring is TypeDefinition td) return td.Fields.Single(x => x.Name == f.Name);
    return new FieldReference(f.Name, Type(f.FieldType), declaring);
}
foreach (var pair in methods) {
    var dm = pair.Key; var tm = pair.Value;
    if (!dm.HasBody) continue;
    var body = new MethodBody(tm) { InitLocals = dm.Body.InitLocals, MaxStackSize = dm.Body.MaxStackSize };
    tm.Body = body;
    var variables = new Dictionary<VariableDefinition, VariableDefinition>();
    foreach (var v in dm.Body.Variables) { var nv = new VariableDefinition(Type(v.VariableType)); variables.Add(v, nv); body.Variables.Add(nv); }
    var instructions = new Dictionary<Instruction, Instruction>();
    foreach (var ins in dm.Body.Instructions) { var ni = Instruction.Create(OpCodes.Nop); ni.OpCode = ins.OpCode; body.Instructions.Add(ni); instructions.Add(ins, ni); }
    foreach (var ins in dm.Body.Instructions) instructions[ins].Operand = ins.Operand switch {
        null => null,
        Instruction x => instructions[x],
        Instruction[] xs => xs.Select(x => instructions[x]).ToArray(),
        VariableDefinition v => variables[v],
        ParameterDefinition p => tm.Parameters[p.Index],
        MethodReference m => Method(m),
        FieldReference f => Field(f),
        TypeReference t => Type(t),
        CallSite => throw new InvalidDataException("Unexpected calli"),
        var x => x
    };
    Instruction? Map(Instruction? i) => i is null ? null : instructions[i];
    foreach (var eh in dm.Body.ExceptionHandlers) body.ExceptionHandlers.Add(new ExceptionHandler(eh.HandlerType) {
        TryStart = Map(eh.TryStart), TryEnd = Map(eh.TryEnd), HandlerStart = Map(eh.HandlerStart), HandlerEnd = Map(eh.HandlerEnd), FilterStart = Map(eh.FilterStart), CatchType = eh.CatchType is null ? null : Type(eh.CatchType)
    });
}
// Patch the original normal-build state machines instead of importing newer
// ApplyAsync/physics behavior. Only the canonical writer and IO catch change.
var service = target.GetType("HD2ModCore.Infrastructure.RuntimeArmorRegistryService");
var writer = service.NestedTypes.Single(t => t.Name.StartsWith("<WriteAtomicTextAsync>"));
var move = writer.Methods.Single(m => m.Name == "MoveNext");
var fileMove = move.Body.Instructions.Single(i => i.OpCode == OpCodes.Call && i.Operand is MethodReference r && r.DeclaringType.FullName == "System.IO.File" && r.Name == "Move");
var transport = target.GetType(name);
var publish = transport.Methods.Single(m => m.Name == "PublishCanonical");
var il = move.Body.GetILProcessor(); var tail = fileMove;
foreach (var ins in new[] { Instruction.Create(OpCodes.Ldarg_0), Instruction.Create(OpCodes.Ldfld, writer.Fields.Single(f => f.Name == "path")), Instruction.Create(OpCodes.Ldarg_0), Instruction.Create(OpCodes.Ldfld, writer.Fields.Single(f => f.Name == "text")), Instruction.Create(OpCodes.Call, publish) }) { il.InsertAfter(tail, ins); tail = ins; }

var applyHandlers = service.NestedTypes.Where(t => t.Name.StartsWith("<ApplyAsync>"))
    .SelectMany(t => t.Methods.Where(m => m.Name == "MoveNext").SelectMany(m => m.Body.ExceptionHandlers
        .Where(e => e.HandlerType == ExceptionHandlerType.Filter && e.HandlerStart.OpCode == OpCodes.Pop)
        .Select(e => (State: t, Method: m, Handler: e)))).ToArray();
if (applyHandlers.Length != 1) {
 foreach (var st in service.NestedTypes.Where(t => t.Name.StartsWith("<ApplyAsync>"))) foreach (var m in st.Methods.Where(m => m.Name=="MoveNext")) foreach(var e in m.Body.ExceptionHandlers) {
  Console.WriteLine(st.FullName+" "+e.HandlerType+" "+e.HandlerStart);
  for(var i=e.HandlerStart; i!=null && i.Offset<e.HandlerStart.Offset+24;i=i.Next) Console.WriteLine(i);
 }
}
if (applyHandlers.Length != 1) throw new InvalidDataException("Expected one legacy links IO handler, found " + applyHandlers.Length);
var entry = applyHandlers[0]; var api = entry.Method.Body.GetILProcessor();
var first = entry.Handler.HandlerStart;
var dup = Instruction.Create(OpCodes.Dup); api.InsertBefore(first, dup);
api.InsertAfter(dup, Instruction.Create(OpCodes.Call, transport.Methods.Single(m => m.Name == "RethrowIfMirrorFailure")));
entry.Handler.HandlerStart = dup;

// Explicit clear/disable publishes an empty projection even in the normal
// baseline's old zero-link early-out. The source workspace is not rewritten.
var leaveCatch = first.Next;
while (leaveCatch.OpCode == OpCodes.Nop) leaveCatch = leaveCatch.Next;
if (leaveCatch.OpCode != OpCodes.Leave && leaveCatch.OpCode != OpCodes.Leave_S) throw new InvalidDataException("Unexpected links handler exit");
var afterCatch = (Instruction)leaveCatch.Operand;
var beginStop = Instruction.Create(OpCodes.Ldarg_0);
api.InsertBefore(afterCatch, beginStop);
api.InsertBefore(afterCatch, Instruction.Create(OpCodes.Ldfld, entry.State.Fields.Single(f => f.Name == "<>4__this")));
api.InsertBefore(afterCatch, Instruction.Create(OpCodes.Ldfld, service.Fields.Single(f => f.Name == "registryRoot")));
api.InsertBefore(afterCatch, Instruction.Create(OpCodes.Ldarg_0));
api.InsertBefore(afterCatch, Instruction.Create(OpCodes.Ldfld, entry.State.Fields.Single(f => f.Name.Contains("compiled") && f.FieldType.FullName == "HD2ModCore.Domain.RuntimeArmorRegistryDocument")));
api.InsertBefore(afterCatch, Instruction.Create(OpCodes.Call, transport.Methods.Single(m => m.Name == "PublishStopIfNeeded")));
foreach (var instruction in entry.Method.Body.Instructions) {
    if (ReferenceEquals(instruction.Operand, afterCatch)) instruction.Operand = beginStop;
    else if (instruction.Operand is Instruction[] targets) instruction.Operand = targets.Select(t => ReferenceEquals(t, afterCatch) ? beginStop : t).ToArray();
}
foreach (var eh in entry.Method.Body.ExceptionHandlers) {
    if (ReferenceEquals(eh.HandlerEnd, afterCatch)) eh.HandlerEnd = beginStop;
    if (ReferenceEquals(eh.TryEnd, afterCatch)) eh.TryEnd = beginStop;
}

var resource = target.Resources.OfType<EmbeddedResource>().Single(r => r.Name.EndsWith(".armor_override_runtime.lua"));
var replacement = donor.Resources.OfType<EmbeddedResource>().Single(r => r.Name == resource.Name);
var resourceIndex = target.Resources.IndexOf(resource);
target.Resources[resourceIndex] = new EmbeddedResource(resource.Name, resource.Attributes, replacement.GetResourceData());
var description = target.GetType("HD2ModCore.Domain.ArmorMappingModes").Methods.Single(m => m.Name == "Description");
var sourceDescription = donor.GetType("HD2ModCore.Domain.ArmorMappingModes").Methods.Single(m => m.Name == "Description");
var chefText = sourceDescription.Body.Instructions.Single(i => i.OpCode == OpCodes.Ldstr && ((string)i.Operand).Contains("Chef Shared Loader")).Operand;
var oldDescription = description.Body.Instructions.Single(i => i.OpCode == OpCodes.Ldstr && ((string)i.Operand).Contains("外置 Lua 加载器"));
oldDescription.Operand = chefText;
if (target.AssemblyReferences.Any(r => r.Name == target.Assembly.Name.Name)) throw new InvalidDataException("Self assembly reference refused");
if (File.Exists(args[2])) throw new IOException("Output already exists");
target.Write(args[2]);
Console.WriteLine($"Updated Chef helper + original writer/apply hooks + mode description + one armor Lua: {methods.Count} donor methods; total resources={target.Resources.Count}; MVID={target.Mvid}");
static IEnumerable<TypeDefinition> All(IEnumerable<TypeDefinition> ts) { foreach (var t in ts) { yield return t; foreach (var n in All(t.NestedTypes)) yield return n; } }

}
catch (Exception exception) { Console.Error.WriteLine(exception); return 1; }
return 0;
