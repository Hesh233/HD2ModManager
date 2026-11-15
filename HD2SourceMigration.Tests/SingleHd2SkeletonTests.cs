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
        // Model the real HD2 phalanx hierarchy, rather than three self-parented
        // roots. The new axis gate must reject that impossible old fixture.
        var native = hd2.Bones.ToList();
        foreach (var side in new[] { "l", "r" })
        foreach (var stem in new[] { "thumb", "index", "middle", "ring", "pinky" })
        for (var k = 1; k <= 3; k++)
        {
            var b = native.Single(x => x.Name == $"{side}_{stem}_finger{k}");
            var parent = native.Single(x => x.Name == (k == 1 ? side + "_hand" : $"{side}_{stem}_finger{k - 1}"));
            native[b.Index] = b with { ParentIndex = parent.Index };
        }
        hd2 = new Hd2Rig(native);
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
                [(float)(b.WorldOrigin.X-(b.ParentIndex==b.Index ? 0 : hd2.Bones[b.ParentIndex].WorldOrigin.X)),0,(float)(b.WorldOrigin.Z-(b.ParentIndex==b.Index ? 0 : hd2.Bones[b.ParentIndex].WorldOrigin.Z))], [1,1,1],0)).ToArray(),
            hd2.Bones.Select(b => new UnitTransformMatrix(TestRig.RowVectorAt(b.WorldOrigin.X,0,b.WorldOrigin.Z))).ToArray(),
            hd2.Bones.Select(b => new UnitTransformEntry(1,(ushort)b.ParentIndex)).ToArray(),
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
        Assert.Equal("native-axis-source-length-hand-follow-v2",conversion.Manifest.ArmSegmentPolicy);
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
    [Theory]
    [InlineData("l")][InlineData("r")]
    public void NormalizeArmCarriesPalmFingersTwistAndWeightedGeometryTogether(string side)
    {
        var (inputs, rig, _) = Fixture();
        var baseline = SourceRetargetPipeline.Run(inputs,rig,options:SingleHd2Skeleton.Options());
        var list=rig.Bones.ToList();
        var sh=rig.Find(side+"_shoulder")!.Index;
        var el=rig.Find(side+"_elbow")!.Index;
        var ha=rig.Find(side+"_hand")!.Index;
        var f1=rig.Find(side+"_middle_finger1")!.Index;
        var f2=rig.Find(side+"_middle_finger2")!.Index;
        list[sh]=list[sh] with {WorldBind=TestRig.TranslationAt(0,0,1)};
        list[el]=list[el] with {ParentIndex=sh,WorldBind=TestRig.TranslationAt(.3,0,1)};
        list[ha]=list[ha] with {ParentIndex=el,WorldBind=TestRig.TranslationAt(.3,.3,1)};
        list[f1]=list[f1] with {ParentIndex=ha};list[f2]=list[f2] with {ParentIndex=f1};
        var tw=list.Count;list.Add(new(tw,side+"_hand_twist",el,list[ha].WorldBind));
        rig=new Hd2Rig(list);
        var worlds=baseline.ShippedRest.ToDictionary(x=>x.Key,x=>x.Value);
        worlds[sh]=TestRig.TranslationAt(0,0,1);worlds[el]=TestRig.TranslationAt(.3,0,1);
        worlds[ha]=TestRig.TranslationAt(.5,.2,1);worlds[tw]=worlds[ha];
        worlds[f1]=TestRig.TranslationAt(.55,.25,1);worlds[f2]=TestRig.TranslationAt(.58,.28,1);
        var frames=worlds.ToDictionary(x=>x.Key,_=>Mat4.Identity);
        int Source(int target)=>baseline.Resolved.First(p=>p.Value==target).Key;
        var points=new[]{worlds[ha].Origin,worlds[f1].Origin,new Vec3(.51,.22,1.01)};
        var vertices=new[]{
            new SourceVertex(points[0],new(0,0,1),0,0,new(Source(ha),1),default,default),
            new SourceVertex(points[1],new(0,0,1),0,0,new(Source(f1),1),default,default),
            new SourceVertex(points[2],new(0,0,1),0,0,new(Source(ha),.6f),new(Source(el),.4f),default)};
        inputs=inputs with {Geometry=inputs.Geometry with {Vertices=vertices}};
        var helper=new RetargetExtraBone("wrist_test",Hd2NameHash.Of("wrist_test"),el,new Vec3(.49,.19,1),el);
        var before=baseline with {ShippedRest=worlds,Deform=frames,Aligned=points,Output=points,ExtraBones=new[]{helper}};
        var after=SingleHd2Skeleton.NormalizeArmSegments(inputs,before,rig);
        var oldAxis=worlds[ha].Origin-worlds[el].Origin;
        var newAxis=after.ShippedRest[ha].Origin-after.ShippedRest[el].Origin;
        var rotate=RetargetMath.MinArcRotation(oldAxis,newAxis).ToMat4();
        Vec3 Expected(Vec3 p)=>after.ShippedRest[el].Origin+rotate.TransformPoint(p-worlds[el].Origin);
        foreach(var i in new[]{ha,tw,f1,f2}) {
            Assert.True((after.ShippedRest[i].Origin-Expected(worlds[i].Origin)).Length<1e-9);
            Assert.Equal(worlds[i].M11,after.ShippedRest[i].M11);
            Assert.Equal(worlds[i].M22,after.ShippedRest[i].M22);
            Assert.Equal(worlds[i].M33,after.ShippedRest[i].M33);
        }
        for(var i=0;i<points.Length;i++)Assert.True((after.Output[i]-Expected(points[i])).Length<1e-8);
        Assert.True((after.ExtraBones[0].WorldOrigin-Expected(helper.WorldOrigin)).Length<1e-9);
        Assert.True(Vec3.Cross(after.ShippedRest[f1].Origin-after.ShippedRest[ha].Origin,newAxis).Length<1e-9);
        Assert.Equal((worlds[f2].Origin-worlds[f1].Origin).Length,
            (after.ShippedRest[f2].Origin-after.ShippedRest[f1].Origin).Length,precision:10);
    }

    [Theory]
    [InlineData("l", "thumb")][InlineData("r", "thumb")]
    [InlineData("l", "index")][InlineData("r", "index")]
    [InlineData("l", "middle")][InlineData("r", "middle")]
    [InlineData("l", "ring")][InlineData("r", "ring")]
    [InlineData("l", "pinky")][InlineData("r", "pinky")]
    public void FingerNormalizationSharesJointAndMeshFramesPreservesRootsLengthsAndAxes(string side, string stem)
    {
        var (inputs, rig, _) = Fixture();
        var baseline = SourceRetargetPipeline.Run(inputs, rig, options: SingleHd2Skeleton.Options());
        var indices = Enumerable.Range(1,3).Select(k=>rig.Find($"{side}_{stem}_finger{k}")!.Index).ToArray();
        var worlds = baseline.ShippedRest.ToDictionary(x=>x.Key,x=>x.Value);
        var points = new[]{new Vec3(.6,.3,1.1),new Vec3(.62,.33,1.11),new Vec3(.61,.35,1.13)};
        for(var k=0;k<3;k++) worlds[indices[k]]=TestRig.TranslationAt(points[k].X,points[k].Y,points[k].Z);
        var leaf=points[2]+RetargetMath.SafeNormalize(points[2]-points[1])*.018;
        var palm=rig.Find(side+"_hand")!.Index;
        var geometry=new[]{points[0],points[1],points[2],leaf,new Vec3(.61,.32,1.12),worlds[palm].Origin};
        int Source(int node)=>baseline.Resolved.First(x=>x.Value==node).Key;
        var vertices=geometry.Select((v,k)=>new SourceVertex(v,new(0,0,1),0,0,
            new(Source(k==5 ? palm : indices[Math.Min(k,2)]),k==4 ? .3f : 1),
            k==4 ? new SourceVertexWeight(Source(indices[0]),.7f) : default,default)).ToArray();
        inputs=inputs with {Geometry=inputs.Geometry with {Vertices=vertices}};
        var helper=new RetargetExtraBone("finger_helper",Hd2NameHash.Of("finger_helper"),indices[1],points[1],indices[1]);
        var before=baseline with {ShippedRest=worlds,Deform=worlds.ToDictionary(x=>x.Key,_=>Mat4.Identity),
            Aligned=geometry,Output=geometry,ExtraBones=new[]{helper}};
        var after=SingleHd2Skeleton.NormalizeFingerSegments(inputs,before,rig);
        Assert.True((after.ShippedRest[indices[0]].Origin-points[0]).Length<1e-10);
        for(var k=1;k<3;k++) {
            var a=after.ShippedRest[indices[k]].Origin-after.ShippedRest[indices[k-1]].Origin;
            var b=rig.Bones[indices[k]].WorldOrigin-rig.Bones[indices[k-1]].WorldOrigin;
            Assert.True(Vec3.Cross(a,b).Length/(a.Length*b.Length)<1e-10);
            Assert.True(Vec3.Dot(a,b)>0);
            Assert.Equal((points[k]-points[k-1]).Length,a.Length,precision:10);
        }
        for(var k=0;k<3;k++) {
            Assert.True((after.Output[k]-after.ShippedRest[indices[k]].Origin).Length<1e-10);
            var matrix=after.ShippedRest[indices[k]];
            Assert.Equal(worlds[indices[k]].M11,matrix.M11);
            Assert.Equal(worlds[indices[k]].M22,matrix.M22);
            Assert.Equal(worlds[indices[k]].M33,matrix.M33);
        }
        var leafDirection=after.Output[3]-after.ShippedRest[indices[2]].Origin;
        var last=rig.Bones[indices[2]].WorldBind;
        var target=new Vec3(last.M11,last.M21,last.M31);
        Assert.True(Vec3.Cross(leafDirection,target).Length<1e-10);
        Assert.Equal(.018,leafDirection.Length,precision:10);
        var mixed=(after.Deform[indices[2]].TransformPoint(geometry[4])*.3f
            +after.Deform[indices[0]].TransformPoint(geometry[4])*.7f)/(.3f+.7f);
        Assert.True((after.Output[4]-mixed).Length<1e-10);
        Assert.Equal(geometry[5],after.Output[5]);
        Assert.Equal(worlds[palm],after.ShippedRest[palm]);
        Assert.True((after.ExtraBones[0].WorldOrigin-after.ShippedRest[indices[1]].Origin).Length<1e-10);
    }

    [Fact]
    public void FingerNormalizationRejectsDegenerateChainWithoutMeshOnlyFallback()
    {
        var (inputs,rig,_) = Fixture();
        var baseline=SourceRetargetPipeline.Run(inputs,rig,options:SingleHd2Skeleton.Options());
        var a=rig.Find("r_thumb_finger1")!.Index;var b=rig.Find("r_thumb_finger2")!.Index;
        var worlds=baseline.ShippedRest.ToDictionary(x=>x.Key,x=>x.Value);worlds[b]=worlds[a];
        Assert.Throws<InvalidDataException>(()=>SingleHd2Skeleton.NormalizeFingerSegments(inputs,baseline with {ShippedRest=worlds},rig));
    }

}
