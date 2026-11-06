using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceMigration.Retarget;
using HD2SourceMigration.VpkConversion;
using HD2SourceModel;

namespace HD2SourceMigration.Tests;

public sealed class SingleHd2SkeletonTests
{
    private static (RetargetInputs Inputs, Hd2Rig Rig, UnitTransformInfo Avatar) Fixture()
    {
        var (source, hd2) = TestRig.MatchingRigs();
        var bones = source.Bones.Select(b =>
        {
            var z = b.Name!.EndsWith("Head1") ? 70 : 35;
            var world = TestRig.TranslationAt(b.Index * .3, 0, z);
            return b with { WorldBind = world, PoseToBone = world.Inverse() };
        }).ToArray();
        source = source with { Bones = bones };
        hd2 = new Hd2Rig(hd2.Bones.Select(b => b with
        { WorldBind = TestRig.TranslationAt(b.Index * .01, 0, b.Name == "head" ? 1.7 : .8) }).ToArray());
        var head = Array.FindIndex(bones, b => b.Name!.EndsWith("Head1"));
        var pelvis = Array.FindIndex(bones, b => b.Name!.EndsWith("Pelvis"));
        SourceVertex Vertex(Vec3 position, int bone) => new(position, new Vec3(0,0,1), 0, 0,
            new SourceVertexWeight(bone, 1), default, default);
        var geometry = new SourceGeometry([
            Vertex(bones[head].WorldBind.Origin, head),
            Vertex(bones[pelvis].WorldBind.Origin, pelvis),
            Vertex(Vec3.Zero, pelvis)], [], []);
        var avatar = new UnitTransformInfo(0,0,0,
            hd2.Bones.Select(b => new UnitLocalTransform([1,0,0,0,1,0,0,0,1],
                [(float)b.WorldOrigin.X,0,(float)b.WorldOrigin.Z], [1,1,1],0)).ToArray(),
            hd2.Bones.Select(b => new UnitTransformMatrix(TestRig.RowVectorAt(b.WorldOrigin.X,0,b.WorldOrigin.Z))).ToArray(),
            hd2.Bones.Select(b => new UnitTransformEntry(1,(ushort)b.Index)).ToArray(),
            hd2.Bones.Select(b => Hd2NameHash.Of(b.Name!)).ToArray());
        return (new RetargetInputs("test.vpk","test","test.mdl",source,geometry,hd2),hd2,avatar);
    }

    [Fact]
    public void SharedBindPlacesWeightedJointVerticesOnTheShippedBones()
    {
        var (inputs,rig,avatar) = Fixture();
        var result = SingleHd2Skeleton.Convert(inputs,rig,avatar).Result;
        Assert.Null(result.SourceNativeTransforms);
        Assert.NotNull(result.SingleHd2Transforms);
        Assert.Equal(avatar.NameHashes, result.SingleHd2Transforms!.NameHashes);
        for (var i = 0; i < 2; i++)
        {
            var mapped = result.Resolved[inputs.Geometry.Vertices[i].Weight0.BoneIndex];
            Assert.True((result.Output[i] - result.ShippedRest[mapped].Origin).Length < 1e-9);
        }
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(result.SingleHd2Transforms, tolerance: 2e-5f);
        Assert.NotEqual(avatar.Matrices[0],result.SingleHd2Transforms.Matrices[0]);
    }

    [Fact]
    public void ModelMultiplierChangesMeshAndJointDistancesExactlyOnce()
    {
        var (inputs,rig,avatar) = Fixture();
        var a = SingleHd2Skeleton.Convert(inputs,rig,avatar).Result;
        var b = SingleHd2Skeleton.Convert(inputs,rig,avatar,1.2).Result;
        Assert.Equal(1,a.Metrics.Scale);Assert.Equal(1.2,b.Metrics.Scale);
        var anchor = rig.Find("head")!.Index;
        var ap = a.ShippedRest[anchor].Origin;
        var bp = b.ShippedRest[anchor].Origin;
        for (var i=0;i<a.Output.Count;i++)
            Assert.True(((a.Output[i]-ap)*1.2-(b.Output[i]-bp)).Length<1e-9);
        for (var i=0;i<rig.Bones.Count;i++)
            Assert.True(((a.ShippedRest[i].Origin-ap)*1.2-(b.ShippedRest[i].Origin-bp)).Length<1e-9);
    }

    [Fact]
    public void SinglePolicyDoesNotInheritMeshOnlyFitOrResize()
    {
        var o=SingleHd2Skeleton.Options();
        Assert.Equal(RetargetSkeleton.Snap,o.Skeleton);
        Assert.Equal(1,o.Scale);Assert.True(o.AnchorAtGround);Assert.False(o.SnapHeadTip);
        Assert.Equal(Vec3.Zero,o.MeshShift);
        Assert.Equal(1,o.HeadScale);Assert.Equal(1,o.UpperScale);
        Assert.False(o.FingerPose);Assert.False(o.ArmScratch);
        Assert.Equal(0,o.ArmFit);Assert.Equal(HandReorientMode.Off,o.HandReorient);
        Assert.Equal(0,o.GroundLift);
    }

    [Theory]
    [InlineData(0)][InlineData(-1)][InlineData(11)][InlineData(double.NaN)]
    public void InvalidScaleIsRejected(double scale)
    {
        var (inputs,rig,avatar)=Fixture();
        Assert.Throws<ArgumentOutOfRangeException>(()=>SingleHd2Skeleton.Convert(inputs,rig,avatar,scale));
    }

    [Fact]
    public void MissingHeadIsRejectedInsteadOfProducingAnEnormousModel()
    {
        var (inputs,rig,avatar)=Fixture();
        var model=inputs.Model with { Bones=inputs.Model.Bones.Where(b=>!b.Name!.EndsWith("Head1")).ToArray() };
        Assert.Throws<InvalidDataException>(()=>SingleHd2Skeleton.Convert(inputs with { Model=model },rig,avatar));
    }
}
