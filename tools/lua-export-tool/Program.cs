using HD2ModCore.Infrastructure;
// 用法: lua-export-tool <root> <featureKey...>   featureKey: physbone | attachment-fix | wardrobe
var root = args[0];
foreach (var key in args.Skip(1))
{
    var feature = key switch
    {
        "physbone" => LuaAddonCatalog.Physics(),
        "attachment-fix" => LuaAddonCatalog.AttachmentFix(),
        "wardrobe" => LuaAddonCatalog.Wardrobe(),
        _ => throw new ArgumentException($"unknown feature: {key}"),
    };
    var folder = LuaAddonPackageExport.Export(root, feature);
    Console.WriteLine($"exported: {folder}");
}
