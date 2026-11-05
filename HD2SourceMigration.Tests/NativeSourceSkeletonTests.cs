using System.Text.Json;
using HD2ModAdaptation.PatchReconstruction.UnitMesh;
using HD2SourceMigration.Retarget;
using HD2SourceMigration.Segmentation;
using HD2SourceMigration.VpkConversion;
using HD2SourceModel;

namespace HD2SourceMigration.Tests;

public sealed class NativeSourceSkeletonTests
{
    private static (RetargetInputs Inputs, Hd2Rig Rig, UnitTransformInfo Avatar) Fixture()
    {
        var root = TestRig.SourceBone(1, "Pelvis", z: 40);
        var child = TestRig.SourceBone(0, "Helper", x: 10, z: 40) with { ParentIndex = 1 };
        var model = TestRig.SourceModel([child, root]);
        var geometry = new SourceGeometry([new SourceVertex(new Vec3(4,5,6),new Vec3(0,0,1),.2f,.3f,
            new SourceVertexWeight(0,.75f),new SourceVertexWeight(1,.25f),default)],[],[]);
        var avatar = new UnitTransformInfo(0,0,0,
            [new UnitLocalTransform([1,0,0,0,1,0,0,0,1],[0,0,0],[1,1,1],0)],
            [new UnitTransformMatrix(TestRig.RowVectorAt(0,0,0))],
            [new UnitTransformEntry(1,0)], [Hd2NameHash.Of("hips")]);
        var rig = new Hd2Rig([TestRig.Hd2Bone(0,"hips")]);
        return (new RetargetInputs("test.vpk","test","test.mdl",model,geometry,rig),rig,avatar);
    }

    [Fact]
    public void KeepsAllSourceNodesAndBindWithParentsReordered()
    {
        var (inputs,rig,avatar) = Fixture();
        var converted = NativeSourceSkeleton.Convert(inputs,rig,avatar);
        Assert.Equal(new[]{1,0},converted.Manifest.Bones.Select(b => b.SourceIndex));
        Assert.Null(converted.Manifest.Bones[0].Parent);
        Assert.Equal(0,converted.Manifest.Bones[1].Parent);
        Assert.Equal(3,converted.Transforms.NameHashes.Count);
        Assert.Null(converted.Manifest.MotionLayers);
        Assert.DoesNotContain("motionLayers", JsonSerializer.Serialize(converted.Manifest,
            new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase }));
        Assert.Equal(avatar.LocalTransforms[0], converted.Transforms.LocalTransforms[0]);
        Assert.Equal(.254f,converted.Transforms.LocalTransforms[2].Position[0],5);
        Assert.Equal(new Vec3(-4*.0254,-5*.0254,6*.0254),converted.Result.Output[0]);
        Assert.Equal("source", converted.Manifest.ScaleOrigin);
        Assert.Equal(6*.0254,converted.Manifest.SourceGroundMetres,9);
        Assert.StartsWith("hd2n_",converted.Manifest.Bones[0].Name);
        Assert.Equal(2,converted.Result.JiggleWeightTargets[0]);
        Assert.Equal(1,converted.Result.JiggleWeightTargets[1]);
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(converted.Transforms,1);
    }

    [Fact]
    public void ModelScaleScalesMeshAndSourceBindTogetherWithoutScalingDrivers()
    {
        var (inputs,rig,avatar) = Fixture();
        var baseline=NativeSourceSkeleton.Convert(inputs,rig,avatar);
        var scaled=NativeSourceSkeleton.Convert(inputs,rig,avatar,1.2);
        Assert.Equal(1.2,scaled.Manifest.ModelScale);
        Assert.Equal(baseline.Transforms.Matrices[0],scaled.Transforms.Matrices[0]);
        for(var i=0;i<baseline.Manifest.Bones.Count;i++)
            for(var j=12;j<15;j++)
                Assert.Equal(baseline.Manifest.Bones[i].World[j]*1.2,scaled.Manifest.Bones[i].World[j],5);
        Assert.True((scaled.Result.Output[0]-baseline.Result.Output[0]*1.2).Length<1e-12);
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(scaled.Transforms,1);
        foreach(var invalid in new[]{0.0,-1,11,double.NaN,double.PositiveInfinity})
            Assert.Throws<ArgumentOutOfRangeException>(()=>NativeSourceSkeleton.Convert(inputs,rig,avatar,invalid));
    }

    [Fact]
    public void PhysicsBranchIsMarkedWithoutChangingModelSkinHashes()
    {
        var (inputs,rig,avatar) = Fixture();
        var parameters = new SourceJiggleBone(0x31,10,1,50,7,50,7,0,0,.6f,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);
        var child = inputs.Model.Bones[0] with { Jiggle=parameters };
        var descendant = TestRig.SourceBone(2,"HelperEnd",x:12,z:40) with { ParentIndex=0 };
        inputs = inputs with { Model=inputs.Model with { Bones=[child,inputs.Model.Bones[1],descendant] } };
        var converted=NativeSourceSkeleton.Convert(inputs,rig,avatar);
        Assert.Equal(new[]{false,true,true},converted.Manifest.Bones.Select(b=>b.Physics));
        Assert.Equal(Hd2NameHash.Of(converted.Manifest.Bones[1].Name),converted.Transforms.NameHashes[2]);
        Assert.Equal(child.DisplayName,converted.Manifest.Bones[1].SourceName);
        Assert.Contains("_phys_",converted.Manifest.Bones[2].Name);
    }

    [Fact]
    public void RejectsCyclicSourceHierarchy()
    {
        var (inputs,rig,avatar) = Fixture();
        var invalid = inputs with { Model=inputs.Model with { Bones=[inputs.Model.Bones[0],inputs.Model.Bones[1] with { ParentIndex=0 }] } };
        Assert.Throws<InvalidDataException>(() => NativeSourceSkeleton.Convert(invalid,rig,avatar));
    }

    [Fact]
    public void RejectsReflectionAndInvalidWeights()
    {
        var (inputs,rig,avatar) = Fixture();
        var reflected = new Mat4(-1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1);
        var invalid = inputs with { Model=inputs.Model with { Bones=[inputs.Model.Bones[0] with { WorldBind=reflected },inputs.Model.Bones[1]] } };
        Assert.Throws<InvalidDataException>(() => NativeSourceSkeleton.Convert(invalid,rig,avatar));
        invalid = inputs with { Geometry=inputs.Geometry with { Vertices=[inputs.Geometry.Vertices[0] with { Weight0=new SourceVertexWeight(999,.75f) }] } };
        Assert.Throws<InvalidDataException>(() => NativeSourceSkeleton.Convert(invalid,rig,avatar));
    }

    [Fact]
    public void MotionLayersPreserveBindIndicesAndSourceMetadataWithForwardParents()
    {
        var (minimal, _, _) = Fixture();
        var source = new[] { TestRig.SourceBone(0, "Pelvis", z: 40),
            TestRig.SourceBone(1, "Spine", z: 44) with { ParentIndex = 0 },
            TestRig.SourceBone(2, "Helper", z: 46) with { ParentIndex = 1 } };
        var bossWorld = new Mat4(0,-1,0,.3, 1,0,0,.4, 0,0,1,.5, 0,0,0,1);
        var rig = new Hd2Rig([
            TestRig.Hd2Bone(0, "entity"),
            TestRig.Hd2Bone(1, "root", x:.1, y:.2) with { ParentIndex=0 },
            new Hd2RigBone(2,"boss",1,bossWorld),
            TestRig.Hd2Bone(3,"hips",z:1) with { ParentIndex=2 },
            TestRig.Hd2Bone(4,"spine1",z:1.1) with { ParentIndex=2 }]);
        var avatar = new UnitTransformInfo(7,8,9,
            rig.Bones.Select(b => NativeSourceSkeleton.ToLocal(b.Index == 0 ? b.WorldBind
                : rig.Bones[b.ParentIndex].WorldBind.Inverse()*b.WorldBind)).ToArray(),
            rig.Bones.Select(b => new UnitTransformMatrix(NativeSourceSkeleton.ToRow(b.WorldBind))).ToArray(),
            rig.Bones.Select(b => new UnitTransformEntry((ushort)(b.Index==0 ? 0 : 1), (ushort)b.ParentIndex)).ToArray(),
            rig.Bones.Select(b => Hd2NameHash.Of(b.Name!)).ToArray());
        var inputs = minimal with { Model=minimal.Model with { Bones=source } };
        var noRoot = new Hd2Rig(rig.Bones.Select(b => b.Name == "root" ? b with { Name=null } : b).ToArray());
        var baseline = NativeSourceSkeleton.Convert(inputs,noRoot,avatar,1.08);
        var converted = NativeSourceSkeleton.Convert(inputs,rig,avatar,1.08);
        var manifest = converted.Manifest;
        var transforms = converted.Transforms;
        Assert.Equal(10,transforms.NameHashes.Count);
        Assert.Equal("native-root-boss-layers-v7",manifest.RetargetHierarchy);
        Assert.Equal(new[]{"root","boss"},manifest.MotionLayers!.Select(l=>l.Driver));
        Assert.Equal(new[]{0,1},manifest.MotionParentOverrides!.Keys);
        Assert.All(manifest.MotionParentOverrides!.Values, layer=>Assert.Equal(1,layer));
        Assert.Equal(avatar.NameHashes[0],manifest.MotionLayers![0].ParentHash);
        Assert.Equal(manifest.MotionLayers[0].Hash,manifest.MotionLayers[1].ParentHash);
        for(var i=0;i<8;i++)
        {
            Assert.Equal(baseline.Transforms.NameHashes[i],transforms.NameHashes[i]);
            Assert.Equal(baseline.Transforms.Matrices[i].Values,transforms.Matrices[i].Values);
            if(i is 5 or 6) { Assert.Equal(9,transforms.Entries[i].ParentIndex); continue; }
            Assert.Equal(baseline.Transforms.Entries[i],transforms.Entries[i]);
            Assert.Equal(baseline.Transforms.LocalTransforms[i].Rotation,transforms.LocalTransforms[i].Rotation);
            Assert.Equal(baseline.Transforms.LocalTransforms[i].Position,transforms.LocalTransforms[i].Position);
        }
        for(var i=0;i<3;i++)
        {
            Assert.Equal(baseline.Manifest.Bones[i].Parent,manifest.Bones[i].Parent);
            Assert.Equal(baseline.Manifest.Bones[i].Local.Position,manifest.Bones[i].Local.Position);
            Assert.Equal(baseline.Manifest.Bones[i].Local.Rotation,manifest.Bones[i].Local.Rotation);
        }
        Assert.Equal(avatar.Entries[0],transforms.Entries[0]);
        Assert.Equal(0,transforms.Entries[8].ParentIndex);
        Assert.Equal(8,transforms.Entries[9].ParentIndex);
        Assert.Equal(avatar.Matrices[1].Values,transforms.Matrices[8].Values);
        Assert.Equal(avatar.Matrices[2].Values,transforms.Matrices[9].Values);
        Assert.Equal(baseline.Result.Output,converted.Result.Output);
        Assert.Equal(baseline.Result.JiggleWeightTargets,converted.Result.JiggleWeightTargets);
        UnitTransformInfoAppender.AssertLocalAndWorldAgree(transforms);
        var json=JsonSerializer.Serialize(manifest,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase});
        Assert.Contains("\"motionParentOverrides\":{\"0\":1,\"1\":1}",json);
        Assert.DoesNotContain("animationChannel",json);
        Assert.DoesNotContain("maskChannel",json);
        var cyclic=transforms with { Entries=transforms.Entries.Select((e,i)=>i==9 ? e with { ParentIndex=5 } : e).ToArray() };
        Assert.Throws<InvalidOperationException>(()=>UnitTransformInfoAppender.AssertLocalAndWorldAgree(cyclic));
    }

    [Fact]
    public void RealSourceBindAndWeightAudit()
    {
        var vpk = Environment.GetEnvironmentVariable("HD2_NATIVE_TEST_VPK");
        if (vpk is null) return; // Opt-in real fixture, synthetic cases always run.
        var toc = Environment.GetEnvironmentVariable("HD2_NATIVE_TEST_AVATAR")!;
        var hashes = Environment.GetEnvironmentVariable("HD2_NATIVE_TEST_BONEHASH")!;
        var auditPath = Environment.GetEnvironmentVariable("HD2_NATIVE_TEST_AUDIT")!;
        var inputs = SourceRetargetPipeline.LoadSource(vpk,null);
        var avatar = UnitMeshReader.ReadTransformInfoFromUnitToc(File.ReadAllBytes(toc));
        var rig = SourceRetargetPipeline.LoadRigFromTransformInfo(avatar,hashes);
        const double modelScale = 1.08;
        var native = NativeSourceSkeleton.Convert(inputs,rig,avatar,modelScale);
        Assert.Equal(inputs.Model.Bones.Count,native.Manifest.Bones.Count);
        double maxBindError=0, maxWeightError=0;
        foreach (var node in native.Manifest.Bones)
        {
            var source=inputs.Model.Bones.Single(b => b.Index==node.SourceIndex);
            Assert.Equal(source.DisplayName,node.SourceName);
            Assert.Equal(source.ParentIndex, node.Parent is null ? -1 : native.Manifest.Bones[node.Parent.Value].SourceIndex);
            var p=source.WorldBind.TransformPoint(new Vec3(0,0,0));
            var expected=new[]{-p.X*.0254*modelScale,-p.Y*.0254*modelScale,p.Z*.0254*modelScale};
            maxBindError=Math.Max(maxBindError,Enumerable.Range(0,3).Max(i=>Math.Abs(expected[i]-node.World[12+i])));
        }
        var split=SourceSegmentation.Split(inputs.Model,inputs.Geometry,new BodyRegionResolver(rig),native.Result.Resolved);
        var vertexCount=0;
        foreach(var group in split.Groups)
        {
            var mesh=RetargetedMeshBuilder.Build(group,inputs.Geometry,native.Result,native.Transforms);
            for(var i=0;i<mesh.Vertices.Count;i++)
            {
                var src=inputs.Geometry.Vertices[group.VertexIndices[i]];
                var original=new[]{src.Weight0,src.Weight1,src.Weight2}.Where(w=>w.Weight>0)
                    .GroupBy(w=>native.Manifest.Bones.Single(n=>n.SourceIndex==w.BoneIndex).Hash)
                    .ToDictionary(g=>g.Key,g=>g.Sum(w=>(double)w.Weight));
                var total=original.Values.Sum();
                var actual=mesh.Vertices[i].Influences.ToDictionary(w=>w.BoneHash,w=>w.Weight);
                foreach(var pair in original)
                    maxWeightError=Math.Max(maxWeightError,Math.Abs(pair.Value/total-actual.GetValueOrDefault(pair.Key)));
                Assert.All(actual.Keys,h=>Assert.Contains(h,original.Keys));
                vertexCount++;
            }
        }
        Assert.InRange(maxBindError,0,1e-5);
        Assert.InRange(maxWeightError,0,1.0/1024);
        File.WriteAllText(auditPath,JsonSerializer.Serialize(new { sourceBones=inputs.Model.Bones.Count,
            driverNodes=avatar.NameHashes.Count, combinedNodes=native.Transforms.NameHashes.Count,
            mappedSourceBones=native.Manifest.Bones.Count(b=>b.Driver!=null), verticesChecked=vertexCount,
            maxBindPositionErrorMetres=maxBindError, maxWeightQuantizationError=maxWeightError,
            sourceHierarchyMetadataPreserved=true, sourceBoneNamesMapped=true, modelScale=native.Manifest.ModelScale,
            motionLayers=native.Manifest.MotionLayers?.Count ?? 0, retargetHierarchy=native.Manifest.RetargetHierarchy,
            motionParentOverrides=native.Manifest.MotionParentOverrides,
            minMeshZ=native.Result.Output.Min(p=>p.Z),gameTested=false },new JsonSerializerOptions{WriteIndented=true}));
        File.WriteAllText(Path.ChangeExtension(auditPath,"manifest.json"),JsonSerializer.Serialize(native.Manifest,
            new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.CamelCase,WriteIndented=true}));
    }
}
