using System.Text;

namespace HD2ModCore.Infrastructure;

/// <summary>Reads the opt-in model conversion setting without altering the animation config.
/// Supported form: [vpk_conversion] merge_wrist_weights = true|false (also root dotted key).
/// Unrelated tables and string/comment contents are ignored; malformed/duplicate settings fail closed.</summary>
public static class VpkConversionConfig
{
    public const string Section = "vpk_conversion";
    public const string Key = "merge_wrist_weights";
    public static string ResolvePath(string managerRoot)
    {
        var root = Path.GetFullPath(managerRoot);
        var primary = Path.Combine(root, "config.toml");
        return File.Exists(primary) ? primary : Path.Combine(root, "anim_batch_mod", "config.toml");
    }
    public static bool Load(string managerRoot)
    {
        var path = ResolvePath(managerRoot);
        return File.Exists(path) && LoadFile(path);
    }
    public static bool LoadFile(string path)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("找不到 VPK 转换 config.toml。", path);
        if (new FileInfo(path).Length > 4 * 1024 * 1024)
            throw new InvalidDataException($"转换配置过大：{path}");
        return Parse(File.ReadAllText(path));
    }
    public static bool Parse(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var table = ""; string? multiline = null; bool? result = null;
        var sawTable = false; var lineNumber = 0;
        foreach (var raw in text.TrimStart('\uFEFF').Split('\n'))
        {
            lineNumber++;
            var line = CodeOnly(raw, ref multiline).Trim();
            if (line.Length == 0) continue;
            if (line.StartsWith('['))
            {
                table = line.Trim('[', ']', ' ', '\t', '\r').Trim('"', '\'');
                if (table == Section)
                {
                    if (line.StartsWith("[[")) throw Invalid(lineNumber, "不能使用数组配置节");
                    if (sawTable || result.HasValue) throw Invalid(lineNumber, "重复配置节");
                    sawTable = true;
                }
                continue;
            }
            var eq = line.IndexOf('=');
            if (eq < 0) continue;
            var key = line[..eq].Trim().Trim('"', '\'');
            var matches = table == Section && key == Key;
            if (table == "" && key == Section + "." + Key) matches = true;
            if (table == "" && key == Section)
                throw Invalid(lineNumber, "请使用 [vpk_conversion] 配置节，不使用内联表");
            if (!matches) continue;
            if (result.HasValue) throw Invalid(lineNumber, "重复开关");
            result = line[(eq + 1)..].Trim() switch
            {
                "true" => true,
                "false" => false,
                _ => throw Invalid(lineNumber, "值必须是 TOML 布尔量 true 或 false（不能加引号）")
            };
        }
        return result ?? false;
    }
    private static InvalidDataException Invalid(int line, string detail) =>
        new($"config.toml 第 {line} 行 [vpk_conversion].merge_wrist_weights：{detail}。");

    // Do not mistake a comment or a multiline TOML string for an active key/table.
    private static string CodeOnly(string raw, ref string? multiline)
    {
        var output = new StringBuilder(); char quote = '\0';
        for (var i = 0; i < raw.Length; i++)
        {
            if (multiline is not null)
            {
                if (raw.AsSpan(i).StartsWith(multiline) && (multiline == "'''" || i == 0 || raw[i-1] != '\\'))
                { i += 2; multiline = null; }
                continue;
            }
            var c = raw[i];
            if (quote != '\0')
            {
                output.Append(c);
                if (quote == '"' && c == '\\' && i + 1 < raw.Length) { output.Append(raw[++i]); continue; }
                if (c == quote) quote = '\0';
                continue;
            }
            if (c == '#') break;
            if (c is '"' or '\'')
            {
                var triple = new string(c, 3);
                if (raw.AsSpan(i).StartsWith(triple)) { multiline = triple; i += 2; continue; }
                quote = c;
            }
            output.Append(c);
        }
        return output.ToString();
    }
}
