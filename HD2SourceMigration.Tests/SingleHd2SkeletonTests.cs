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

    [Fact]
    public void ArmSegmentsAndControlMarkersUseOriginalLocalAxes()
    {
        var (inputs, rig, _) = Fixture();
        var list = rig.Bones.ToList();
        foreach (var side in new[] { "l", "r" })
        {
            var shoulder = rig.Find(side + "_shoulder")!;
            var elbow = rig.Find(side + "_elbow")!;
            var hand = rig.Find(side + "_hand")!;
            list[elbow.Index] = elbow with { ParentIndex = shoulder.Index };
            list[hand.Index] = hand with { ParentIndex = elbow.Index };
        }
        var rightHand = rig.Find("r_hand")!;
        var mount = list.Count;
        list.Add(new(mount, "attach_hand_r", rightHand.Index,
            rightHand.WorldBind * TestRig.TranslationAt(.051, -.006, -.055)));
        list.Add(new(list.Count, "weapon_aim", mount,
            list[mount].WorldBind * TestRig.TranslationAt(0, 2, 0)));
        var extra = list.Count;
        var rightElbow = rig.Find("r_elbow")!;
        list.Add(new(extra, null, rightElbow.Index,
            rightElbow.WorldBind * TestRig.TranslationAt(.165, -.05, -.02)));
        rig = new Hd2Rig(list);
        var avatar = new UnitTransformInfo(0, 0, 0,
            list.Select(b =>
            {
                var p = b.ParentIndex;
                var local = p < 0 || p == b.Index || p >= list.Count
                    ? b.WorldOrigin : b.WorldOrigin - list[p].WorldOrigin;
                return new UnitLocalTransform([1,0,0,0,1,0,0,0,1],
                    [(float)local.X,(float)local.Y,(float)local.Z],[1,1,1],0);
            }).ToArray(),
            list.Select(b => new UnitTransformMatrix(TestRig.RowVectorAt(b.WorldOrigin.X,b.WorldOrigin.Y,b.WorldOrigin.Z))).ToArray(),
            list.Select(b => new UnitTransformEntry(1,(ushort)(b.ParentIndex<0 ? b.Index : b.ParentIndex))).ToArray(),
            list.Select(b => Hd2NameHash.Of(b.Name ?? "audit-unanimated")).ToArray());
        var armVertices = new[] { "R_UpperArm", "R_Forearm", "R_Hand" }.Select(name =>
        {
            var bone = inputs.Model.Bones.Single(b => b.Name!.EndsWith(name));
            return new SourceVertex(bone.WorldBind.Origin,new Vec3(0,0,1),0,0,
                new SourceVertexWeight(bone.Index,1),default,default);
        }).ToArray();
        var firstArmVertex = inputs.Geometry.Vertices.Count;
        inputs = inputs with { Geometry = inputs.Geometry with
            { Vertices = inputs.Geometry.Vertices.Concat(armVertices).ToArray() } };
        var conversion = SingleHd2Skeleton.Convert(inputs, rig, avatar);
        var result = conversion.Result;
        for (var i=0;i<armVertices.Length;i++)
        {
            var mapped=result.Resolved[armVertices[i].Weight0.BoneIndex];
            Assert.True((result.Output[firstArmVertex+i]-result.ShippedRest[mapped].Origin).Length<1e-8);
        }
        foreach (var side in new[] { "l", "r" })
        {
            var shoulder = rig.Find(side + "_shoulder")!;
            var elbow = rig.Find(side + "_elbow")!;
            var hand = rig.Find(side + "_hand")!;
            var actual = result.ShippedRest[elbow.Index].Origin-result.ShippedRest[shoulder.Index].Origin;
            var expected = elbow.WorldOrigin-shoulder.WorldOrigin;
            Assert.True(Vec3.Cross(actual,expected).Length/(actual.Length*expected.Length)<1e-8);
            actual = result.ShippedRest[hand.Index].Origin-result.ShippedRest[elbow.Index].Origin;
            expected = hand.WorldOrigin-elbow.WorldOrigin;
            Assert.True(Vec3.Cross(actual,expected).Length/(actual.Length*expected.Length)<1e-8);
        }
        foreach (var i in new[] { mount, mount+1, extra })
            for (var axis=0;axis<3;axis++)
                Assert.Equal(avatar.LocalTransforms[i].Position[axis],
                    result.SingleHd2Transforms!.LocalTransforms[i].Position[axis],precision:5);
        Assert.Equal("original-hd2-local-v1",conversion.Manifest.ControlMarkerPolicy);
        Assert.Equal("native-axis-source-length-v1",conversion.Manifest.ArmSegmentPolicy);
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
