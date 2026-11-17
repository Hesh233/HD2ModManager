using HD2ModCore.Infrastructure;

namespace HD2ModCore.Tests;

public sealed class LuaTriviaCompactorTests
{
    [Theory]
    [InlineData("return 1 -- trailing", "return 1")]
    [InlineData("a--comment\r\n=b", "a =b")]
    [InlineData("return - -- comment\n -x", "return - -x")]
    [InlineData("return 1 .. 2", "return 1 .. 2")]
    [InlineData("a--[==[ignored ]=] -- text]==]b", "a b")]
    [InlineData("local s='-- not a comment'; return s", "local s='-- not a comment'; return s")]
    [InlineData("return [==[\n -- literal \r\n]==]", "return [==[\n -- literal \r\n]==]")]
    [InlineData("return \"a\\\"--b\" -- comment", "return \"a\\\"--b\"")]
    public void OnlyTriviaChanges(string source, string expected) => Assert.Equal(expected, LuaTriviaCompactor.Compact(source));

    [Theory]
    [InlineData("return 'unterminated")]
    [InlineData("return [==[unterminated")]
    [InlineData("--[=[unterminated")]
    public void MalformedLiteralRefused(string source) => Assert.Throws<InvalidDataException>(() => LuaTriviaCompactor.Compact(source));

    [Fact]
    public void RealDirectSourcesShrinkAndRemainIdempotent()
    {
        foreach (var raw in new[] { PhysBoneLuaSource.LoadDirectCompat(), PhysBoneLuaSource.LoadDirectRuntime() })
        {
            var compact = LuaTriviaCompactor.Compact(raw);
            Assert.True(compact.Length < raw.Length * 0.7);
            Assert.Equal(compact, LuaTriviaCompactor.Compact(compact));
        }
    }
}
