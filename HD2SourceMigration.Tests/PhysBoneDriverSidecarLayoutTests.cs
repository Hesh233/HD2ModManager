using System.Buffers.Binary;
using System.Text;
using HD2ModAdaptation.PatchReconstruction;
using HD2SourceMigration.VpkConversion;
using HD2SourceModel;

namespace HD2SourceMigration.Tests;

public sealed class PhysBoneDriverSidecarLayoutTests
{
    [Theory]
    [InlineData("")]
    [InlineData("sectional")]
    [InlineData("vpk2patch")]
    [InlineData("Overwrite")]
    public void Locate_FollowsTheSpringSidecarLayout(string layer)
    {
        var directory = Directory.CreateTempSubdirectory("hd2-driver-layout-");
        try
        {
            Assert.Null(PhysBoneDriverRigSidecar.Locate(directory.FullName));
            var converted = Directory.CreateDirectory(Path.Combine(directory.FullName, layer));
            var expected = Path.Combine(converted.FullName, PhysBoneDriverRigSidecar.FileName);
            File.WriteAllBytes(expected, DriverRig());
            File.WriteAllBytes(Path.Combine(converted.FullName, PhysBoneRigSidecar.FileName), SpringRig());
            Assert.Equal(expected, PhysBoneDriverRigSidecar.Locate(directory.FullName));
            Assert.Equal(converted.FullName, Path.GetDirectoryName(PhysBoneRigSidecar.Locate(directory.FullName)));
        }
        finally { DeleteTemporaryDirectory(directory); }
    }

    [Theory]
    [InlineData("", "sectional")]
    [InlineData("sectional", "vpk2patch")]
    [InlineData("sectional", "Overwrite")]
    [InlineData("vpk2patch", "Overwrite")]
    public void Locate_PreservesSpringSidecarSearchPriority(string preferred, string fallback)
    {
        var directory = Directory.CreateTempSubdirectory("hd2-driver-priority-");
        try
        {
            foreach (var layer in new[] { fallback, preferred })
            {
                var converted = Directory.CreateDirectory(Path.Combine(directory.FullName, layer));
                File.WriteAllBytes(Path.Combine(converted.FullName, PhysBoneDriverRigSidecar.FileName), DriverRig());
                File.WriteAllBytes(Path.Combine(converted.FullName, PhysBoneRigSidecar.FileName), SpringRig());
            }
            Assert.Equal(Path.Combine(directory.FullName, preferred, PhysBoneDriverRigSidecar.FileName),
                PhysBoneDriverRigSidecar.Locate(directory.FullName));
        }
        finally { DeleteTemporaryDirectory(directory); }
    }

    [Theory]
    [InlineData("")]
    [InlineData("sectional")]
    [InlineData("vpk2patch")]
    [InlineData("Overwrite")]
    public async Task Embed_ConvertedDriverSurvivesContainerAssemblyAndRepeatImport(string layer)
    {
        var directory = Directory.CreateTempSubdirectory("hd2-driver-embed-");
        try
        {
            var converted = Directory.CreateDirectory(Path.Combine(directory.FullName, layer));
            var patch = Path.Combine(converted.FullName, "9ba626afa44a3aa3.patch_0");
            var toc = UnitPatch();
            byte[] payload = [1, 2, 3, 4];
            File.WriteAllBytes(patch, toc);
            File.WriteAllBytes(patch + ".gpu_resources", payload);
            var spring = SpringRig();
            var driver = DriverRig();
            File.WriteAllBytes(Path.Combine(converted.FullName, PhysBoneRigSidecar.FileName), spring);
            File.WriteAllBytes(Path.Combine(converted.FullName, PhysBoneDriverRigSidecar.FileName), driver);

            var result = await PhysBoneContainerEmbedder.EmbedAsync(null, directory.FullName);
            Assert.True(result.Embedded, result.Reason);
            Assert.Equal(1, result.DriverBoneCount);
            var carrier = File.ReadAllBytes(patch + ".gpu_resources");
            Assert.Equal(toc, File.ReadAllBytes(patch));
            Assert.Equal(payload, PhysBoneCarrier.Strip(carrier));
            Assert.Equal(spring, ReadRecord(carrier, PhysBoneContainerEmbedder.RigRecordName));
            Assert.Equal(driver, ReadRecord(carrier, PhysBoneContainerEmbedder.DriverRecordName));
            Assert.Equal(3u, BinaryPrimitives.ReadUInt32LittleEndian(driver.AsSpan(8)));
            Assert.Equal(0, (await PhysBoneContainerEmbedder.EmbedAsync(null, directory.FullName)).PatchCount);
            Assert.Equal(carrier, File.ReadAllBytes(patch + ".gpu_resources"));
        }
        finally { DeleteTemporaryDirectory(directory); }
    }

    [Fact]
    public async Task Embed_OriginalFormatWithoutDriverStillHasOnlySpringRecord()
    {
        var directory = Directory.CreateTempSubdirectory("hd2-original-no-driver-");
        try
        {
            var converted = Directory.CreateDirectory(Path.Combine(directory.FullName, "sectional"));
            var patch = Path.Combine(converted.FullName, "9ba626afa44a3aa3.patch_0");
            File.WriteAllBytes(patch, UnitPatch());
            File.WriteAllBytes(patch + ".gpu_resources", [1, 2, 3, 4]);
            var spring = SpringRig();
            File.WriteAllBytes(Path.Combine(converted.FullName, PhysBoneRigSidecar.FileName), spring);
            var result = await PhysBoneContainerEmbedder.EmbedAsync(null, directory.FullName);
            Assert.True(result.Embedded, result.Reason);
            Assert.Null(result.DriverBoneCount);
            var carrier = File.ReadAllBytes(patch + ".gpu_resources");
            Assert.Equal(spring, ReadRecord(carrier, PhysBoneContainerEmbedder.RigRecordName));
            Assert.Null(ReadRecord(carrier, PhysBoneContainerEmbedder.DriverRecordName));
        }
        finally { DeleteTemporaryDirectory(directory); }
    }

    [Theory]
    [InlineData(false, "direct-v1")]
    [InlineData(true, "skeleton-v1")]
    public async Task Embed_ExplicitRouteIsVerifiedCarriedForwardAndIdempotent(bool skeleton, string route)
    {
        var directory = Directory.CreateTempSubdirectory("hd2-route-container-");
        try
        {
            var patch = Path.Combine(directory.FullName, "9ba626afa44a3aa3.patch_0");
            File.WriteAllBytes(patch, UnitPatch());
            byte[] payload = [1, 2, 3, 4];
            File.WriteAllBytes(patch + ".gpu_resources", payload);
            File.WriteAllBytes(Path.Combine(directory.FullName, PhysBoneRigSidecar.FileName), SpringRig());
            PhysBoneRouteSidecar.Write(directory.FullName, skeleton);
            var result = await PhysBoneContainerEmbedder.EmbedAsync(null, directory.FullName);
            Assert.True(result.Embedded, result.Reason);
            var carrier = File.ReadAllBytes(patch + ".gpu_resources");
            Assert.Equal(route, Encoding.UTF8.GetString(ReadRecord(carrier, PhysBoneRouteSidecar.RecordName)!));
            Assert.Equal(payload, PhysBoneCarrier.Strip(carrier));
            Assert.Equal(0, (await PhysBoneContainerEmbedder.EmbedAsync(null, directory.FullName)).PatchCount);
            Assert.Equal(carrier, File.ReadAllBytes(patch + ".gpu_resources"));
            var target = Directory.CreateDirectory(Path.Combine(directory.FullName, "carried"));
            var targetPatch = Path.Combine(target.FullName, "9ba626afa44a3aa3.patch_1");
            File.WriteAllBytes(targetPatch, UnitPatch());
            File.WriteAllBytes(targetPatch + ".gpu_resources", payload);
            var carried = await PhysBoneCarrier.CarryForwardAsync(patch, target.FullName);
            Assert.True(carried.Applied, carried.Note);
            var copied = File.ReadAllBytes(targetPatch + ".gpu_resources");
            Assert.Equal(route, Encoding.UTF8.GetString(ReadRecord(copied, PhysBoneRouteSidecar.RecordName)!));
            Assert.Equal(PhysBoneCarrier.ExtractContainer(carrier), PhysBoneCarrier.ExtractContainer(copied));
        }
        finally { DeleteTemporaryDirectory(directory); }
    }

    private static void DeleteTemporaryDirectory(DirectoryInfo directory)
    {
        var temporaryRoot = new DirectoryInfo(Path.GetFullPath(Path.GetTempPath())).FullName.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        Assert.Equal(temporaryRoot, directory.Parent?.FullName);
        Assert.StartsWith("hd2-", directory.Name);
        directory.Delete(recursive: true);
    }

    private static byte[] UnitPatch()
    {
        var toc = new byte[141];
        BinaryPrimitives.WriteUInt32LittleEndian(toc, 0xf0000011);
        BinaryPrimitives.WriteUInt32LittleEndian(toc.AsSpan(8), 1);
        BinaryPrimitives.WriteUInt64LittleEndian(toc.AsSpan(60), 1);
        BinaryPrimitives.WriteUInt64LittleEndian(toc.AsSpan(68), 0xe0a48d0be9a7453f);
        BinaryPrimitives.WriteUInt64LittleEndian(toc.AsSpan(76), 140);
        BinaryPrimitives.WriteUInt32LittleEndian(toc.AsSpan(116), 1);
        return toc;
    }

    private static byte[] DriverRig() => PhysBoneDriverRig.Serialize(
        [new SourceQuatInterpDriverFact(1, "driver", "hips", "l_thigh", Vec3.Zero,
            [new SourceQuatInterpTrigger(1f, Quat.Identity, [0, 0, 0], Quat.Identity)],
            Quat.Identity, Quat.Identity, Quat.Identity)], PhysBoneDriverRig.SingleVersion);

    private static byte[] SpringRig()
    {
        var parameters = new SourceJiggleBone(Flags: 0x31, Length: 30, TipMass: 200,
            YawStiffness: 50, YawDamping: 7, PitchStiffness: 50, PitchDamping: 7,
            AlongStiffness: 0, AlongDamping: 0, AngleLimit: 0.611f,
            MinYaw: 0, MaxYaw: 0, YawFriction: 0, YawBounce: 0,
            MinPitch: 0, MaxPitch: 0, PitchFriction: 0, PitchBounce: 0,
            BaseMass: 0, BaseStiffness: 0, BaseDamping: 0,
            BaseMinLeft: 0, BaseMaxLeft: 0, BaseLeftFriction: 0,
            BaseMinUp: 0, BaseMaxUp: 0, BaseUpFriction: 0,
            BaseMinForward: 0, BaseMaxForward: 0, BaseForwardFriction: 0);
        return PhysBoneSpringRig.Serialize(
            [new SourceJiggleBoneFact(72, "hair", 71, "head", 0x31, ["flexible"], new Vec3(0, 0, 1), parameters)]);
    }

    private static byte[]? ReadRecord(byte[] carrier, string recordName)
    {
        var container = PhysBoneCarrier.ExtractContainer(carrier);
        Assert.NotNull(container);
        var count = BinaryPrimitives.ReadUInt32LittleEndian(container.AsSpan(0x28));
        var cursor = (int)BinaryPrimitives.ReadUInt64LittleEndian(container.AsSpan(0x18));
        for (var i = 0; i < count; i++)
        {
            var nameLength = BinaryPrimitives.ReadUInt16LittleEndian(container.AsSpan(cursor));
            var offset = (int)BinaryPrimitives.ReadUInt64LittleEndian(container.AsSpan(cursor + 4));
            var length = (int)BinaryPrimitives.ReadUInt64LittleEndian(container.AsSpan(cursor + 12));
            var name = Encoding.UTF8.GetString(container.AsSpan(cursor + 56, nameLength));
            if (name == recordName) return container.AsSpan(offset, length).ToArray();
            cursor += 56 + nameLength;
        }
        return null;
    }
}
