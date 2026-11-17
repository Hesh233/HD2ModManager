using System.Text;

namespace HD2ModCore.Infrastructure;

/// <summary>Remove Lua comments/whitespace without touching tokens, quoted strings or long strings.</summary>
internal static class LuaTriviaCompactor
{
    public static string Compact(string source)
    {
        ArgumentNullException.ThrowIfNull(source);
        var result = new StringBuilder(source.Length);
        void Space() { if (result.Length == 0 || result[^1] != ' ') result.Append(' '); }
        for (var i = 0; i < source.Length;)
        {
            var ch = source[i];
            if (ch is '\'' or '"')
            {
                var start = i++;
                var closed = false;
                while (i < source.Length)
                {
                    if (source[i] == '\\') { i += 2; continue; }
                    if (source[i++] == ch) { closed = true; break; }
                }
                if (!closed || i > source.Length) throw new InvalidDataException("Unterminated Lua quoted string");
                result.Append(source, start, i - start);
            }
            else if (ch == '-' && i + 1 < source.Length && source[i + 1] == '-')
            {
                i += 2;
                if (LongBracket(source, i, out var content, out var close))
                {
                    var end = source.IndexOf(close, content, StringComparison.Ordinal);
                    if (end < 0) throw new InvalidDataException("Unterminated Lua long comment");
                    i = end + close.Length;
                }
                else { while (i < source.Length && source[i] is not ('\r' or '\n')) i++; }
                Space(); // Never join identifiers or create '--' from separate minus tokens.
            }
            else if (LongBracket(source, i, out var content, out var close))
            {
                var end = source.IndexOf(close, content, StringComparison.Ordinal);
                if (end < 0) throw new InvalidDataException("Unterminated Lua long string");
                end += close.Length;
                result.Append(source, i, end - i);
                i = end;
            }
            else if (ch is ' ' or '\t' or '\r' or '\n' or '\v' or '\f')
            {
                do { i++; } while (i < source.Length && source[i] is ' ' or '\t' or '\r' or '\n' or '\v' or '\f');
                Space();
            }
            else { result.Append(ch); i++; }
        }
        return result.ToString().Trim();
    }

    private static bool LongBracket(string source, int at, out int content, out string close)
    {
        content = 0; close = string.Empty;
        if (at >= source.Length || source[at] != '[') return false;
        var next = at + 1;
        while (next < source.Length && source[next] == '=') next++;
        if (next >= source.Length || source[next] != '[') return false;
        content = next + 1;
        close = "]" + new string('=', next - at - 1) + "]";
        return true;
    }
}
