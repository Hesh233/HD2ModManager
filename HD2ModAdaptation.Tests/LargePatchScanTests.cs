using System.Buffers.Binary;
using HD2ModAdaptation.PatchReconstruction;
using Xunit;

namespace HD2ModAdaptation.Tests;

public sealed class LargePatchScanTests
{
    [Fact]
    public async Task ScansAndRewritesPayloadPastFourGiBWithoutReadingEntirePatch()
    {
        var root = Directory.CreateTempSubdirectory("HD2-large-patch-").FullName;
        var path = Path.Combine(root, "large.patch_2");
        var output = Path.Combine(root, "output");
        try
        {
            const long offset = (1L << 32) + 256;
            var header = new byte[184]; // 72 + 32 + 80
            BinaryPrimitives.WriteUInt32LittleEndian(header, 0xf0000011);
            BinaryPrimitives.WriteUInt32LittleEndian(header.AsSpan(4), 1);
            BinaryPrimitives.WriteUInt32LittleEndian(header.AsSpan(8), 1);
            BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(80), 7);
            BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(88), 1);
            BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(104), 42);
            BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(112), 7);
            BinaryPrimitives.WriteUInt64LittleEndian(header.AsSpan(120), offset);
            BinaryPrimitives.WriteUInt32LittleEndian(header.AsSpan(160), 3);
            await using (var stream = File.Create(path))
            {
                await stream.WriteAsync(header);
                stream.Position = offset;
                await stream.WriteAsync(new byte[] { 4, 5, 6 });
            }
            var entry = Assert.Single(await new PatchTocScanner().ScanEntriesAsync(path));
            Assert.Equal((ulong)offset, entry.TocDataOffset);
            Assert.Equal(new byte[] { 4, 5, 6 }, (await new PatchEntryPayloadReader().ReadPayloadAsync(entry)).TocData);
            var result = await new PatchArchiveWriter().WriteAsync(path, output, []);
            var rewritten = Assert.Single(await new PatchTocScanner().ScanEntriesAsync(result.TocFilePath));
            Assert.Equal(new byte[] { 4, 5, 6 }, (await new PatchEntryPayloadReader().ReadPayloadAsync(rewritten)).TocData);
        }
        finally
        {
            File.Delete(path);
            if (Directory.Exists(output))
            {
                foreach (var file in Directory.EnumerateFiles(output)) File.Delete(file);
                Directory.Delete(output);
            }
            Directory.Delete(root);
        }
    }
}
