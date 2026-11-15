using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace HD2ModCore.Infrastructure;

/// <summary>Fail closed on an old/partial repair profile even when the Lua version is current.</summary>
public static class AttachmentRepairProfileContract
{
    public const string Schema = "hd2-attachment-repair-policy-v1";
    public const string Revision = "accepted-tp-profile-r1-20261112";
    public static byte[] SharedPolicyBytes()
    {
        var a = typeof(AttachmentRepairProfileContract).Assembly;
        using var s = a.GetManifestResourceStream("HD2ModCore.PhysBone.Production.attachment_repair_policy.json")
            ?? throw new InvalidDataException("Missing production attachment repair policy resource.");
        using var m = new MemoryStream(); s.CopyTo(m); return m.ToArray();
    }
    public static string SharedPolicySha256 => Convert.ToHexString(SHA256.HashData(SharedPolicyBytes())).ToLowerInvariant();
    private static bool Equal(JsonElement a, JsonElement b) => JsonNode.DeepEquals(JsonNode.Parse(a.GetRawText()), JsonNode.Parse(b.GetRawText()));
    private static byte[] Canonical(JsonElement v)
    {
        using var m = new MemoryStream();
        using (var w = new Utf8JsonWriter(m)) Write(v, w);
        return m.ToArray();
        static void Write(JsonElement e, Utf8JsonWriter w)
        {
            if (e.ValueKind == JsonValueKind.Object) { w.WriteStartObject(); foreach (var p in e.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal)) { w.WritePropertyName(p.Name); Write(p.Value, w); } w.WriteEndObject(); }
            else if (e.ValueKind == JsonValueKind.Array) { w.WriteStartArray(); foreach (var x in e.EnumerateArray()) Write(x, w); w.WriteEndArray(); }
            else e.WriteTo(w);
        }
    }
    public static string ProfileToLua(JsonElement value)
    {
        static string Lua(JsonElement e) => e.ValueKind switch
        {
            JsonValueKind.Null => "nil", JsonValueKind.True => "true", JsonValueKind.False => "false",
            JsonValueKind.Number => e.GetRawText(),
            JsonValueKind.String => JsonSerializer.Serialize(e.GetString(), new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }),
            JsonValueKind.Array => "{" + string.Join(",", e.EnumerateArray().Select(Lua)) + "}",
            JsonValueKind.Object => "{" + string.Join(",", e.EnumerateObject().Select(p => "[" + JsonSerializer.Serialize(p.Name, new JsonSerializerOptions { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) + "]=" + Lua(p.Value))) + "}",
            _ => throw new InvalidDataException("Unsupported production profile value.")
        };
        return "return " + Lua(value) + "\n";
    }
    public static void ValidateProfile(JsonElement profile)
    {
        try
        {
            using var document = JsonDocument.Parse(SharedPolicyBytes()); var shared = document.RootElement;
            var repair = profile.GetProperty("repairPolicy");
            if (profile.TryGetProperty("testRepairs", out _) || repair.GetProperty("schema").GetString() != Schema
                || repair.GetProperty("version").GetString() != NativeRuntimeCompanionPackageExport.RuntimeVersion
                || shared.GetProperty("version").GetString() != NativeRuntimeCompanionPackageExport.RuntimeVersion
                || repair.GetProperty("revision").GetString() != Revision
                || repair.GetProperty("sharedPolicySha256").GetString() != SharedPolicySha256
                || !repair.GetProperty("enabled").GetBoolean()) throw new InvalidDataException("Production repair policy version/hash mismatch.");
            foreach (var p in shared.GetProperty("settings").EnumerateObject())
                if (!repair.TryGetProperty(p.Name, out var actual) || !Equal(p.Value, actual))
                    throw new InvalidDataException("Missing/changed production repair setting: " + p.Name);
            var consumers = profile.GetProperty("consumers"); var allowed = profile.GetProperty("allowedConsumers");
            foreach (var p in shared.GetProperty("fixedConsumers").EnumerateObject())
                if (!consumers.TryGetProperty(p.Name, out var actual) || !Equal(p.Value, actual))
                    throw new InvalidDataException("Missing/changed exact production consumer: " + p.Name);
            foreach (var p in shared.GetProperty("allowedConsumers").EnumerateObject())
                if (!allowed.TryGetProperty(p.Name, out var actual) || !actual.GetBoolean())
                    throw new InvalidDataException("Missing production allowed consumer: " + p.Name);
            var weapon = shared.GetProperty("weaponPolicies"); var targets = profile.GetProperty("leftGrip").GetProperty("weaponTargets");
            foreach (var p in weapon.GetProperty("leftPolicies").EnumerateObject())
                if (targets.TryGetProperty(p.Name, out var target) && target.GetProperty("leftPolicy").GetString() != p.Value.GetString()) throw new InvalidDataException("Missing stock/JAR grip policy.");
            foreach (var p in weapon.GetProperty("sidearms").EnumerateObject())
                if (!profile.GetProperty("gripFixes").GetProperty("sidearms").TryGetProperty(p.Name, out var value) || !value.GetBoolean()) throw new InvalidDataException("Missing C4/native-right policy.");
            foreach (var p in weapon.GetProperty("intentWeaponThresholds").EnumerateObject())
                if (!Equal(profile.GetProperty("leftGrip").GetProperty("intent").GetProperty("weaponThresholds").GetProperty(p.Name), p.Value)) throw new InvalidDataException("Missing JAR native-intent threshold.");
            foreach (var p in weapon.GetProperty("nativeRightTargets").EnumerateObject())
            {
                var target = targets.GetProperty(p.Name);
                foreach (var spec in p.Value.EnumerateObject()) if (!Equal(spec.Value, target.GetProperty(spec.Name))) throw new InvalidDataException("Invalid C4 native target policy.");
                if (target.GetProperty("rootToIKRight").GetArrayLength() != 12) throw new InvalidDataException("Missing current native C4 bind target.");
            }
            var calibration = repair.GetProperty("calibration"); var ns = calibration.GetProperty("namespace").GetString()!;
            if (!calibration.GetProperty("modelSpecific").GetBoolean() || string.IsNullOrWhiteSpace(ns)
                || !profile.GetProperty("variant").GetString()!.StartsWith(ns + "-production-b3-", StringComparison.Ordinal))
                throw new InvalidDataException("Repair calibration does not belong to this model namespace.");
            foreach (var key in new[] { "nativeBindSha256", "sourceBindsSha256", "contactsSha256", "avatarBindSha256" })
                if (!Regex.IsMatch(calibration.GetProperty(key).GetString()!, "^[a-f0-9]{64}$")) throw new InvalidDataException("Missing model bind proof: " + key);
            var contacts = repair.GetProperty("contacts");
            if (Convert.ToHexString(SHA256.HashData(Canonical(contacts))).ToLowerInvariant() != calibration.GetProperty("contactsSha256").GetString())
                throw new InvalidDataException("Contact calibration hash mismatch.");
            foreach (var side in new[] { "left", "right" }) foreach (var role in new[] { "native", "source" })
            {
                var a = contacts.GetProperty(side).GetProperty(role).EnumerateArray().Select(v => v.GetDouble()).ToArray();
                if (a.Length != 3 || a.Any(v => !double.IsFinite(v)) || Math.Sqrt(a.Sum(v => v * v)) is <= .001 or >= .3)
                    throw new InvalidDataException("Invalid model hand contact.");
            }
            var fk = repair.GetProperty("sourceFkRefresh"); var seen = new HashSet<int>();
            if (!fk.GetProperty("enabled").GetBoolean()) throw new InvalidDataException("Missing Source entry FK repair.");
            foreach (var level in fk.GetProperty("levels").EnumerateArray()) foreach (var node in level.EnumerateArray())
            {
                var index = node.GetProperty("index").GetInt32();
                if (!seen.Add(index) || index < 0 || index >= profile.GetProperty("avatar").GetProperty("count").GetInt32()
                    || !node.GetProperty("name").GetString()!.StartsWith(ns + "_", StringComparison.Ordinal))
                    throw new InvalidDataException("Source FK nodes do not belong to this model graph.");
            }
            if (seen.Count != 3) throw new InvalidDataException("Incomplete model Source FK entry set.");
        }
        catch (Exception e) when (e is KeyNotFoundException or InvalidOperationException or FormatException)
        { throw new InvalidDataException("Missing or malformed production repair profile.", e); }
    }
}
