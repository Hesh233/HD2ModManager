namespace HD2SourceModel.Tests;

public sealed class SourceWristWeightMergerTests
{
    private static SourceModelDocument Model()
    {
        SourceBone B(int i, string n, int p, int? control = null) => new(i,n,p,Mat4.Identity,Mat4.Identity,null,
            QuatInterp: control is { } c ? new(c, Array.Empty<SourceQuatInterpTrigger>()) : null);
        return new(49,"fixture",1,new[] {
            B(0,"ValveBiped.Bip01_L_Forearm",-1), B(1,"ValveBiped.Bip01_L_Hand",0), B(2,"wrist_L",0,1),
            B(3,"ValveBiped.Bip01_R_Forearm",-1), B(4,"ValveBiped.Bip01_R_Hand",3), B(5,"wrist_R",3,4),
            B(6,"ValveBiped.Bip01_L_Finger1",1), B(7,"wrong_side",0,4), B(8,"cloth",3,6)
        },Array.Empty<SourceBodyPart>(),Array.Empty<string>(),Array.Empty<SourceModelDiagnostic>());
    }
    private static SourceVertex V(params SourceVertexWeight[] weights) => new(new(1,2,3),new(0,0,1),.2f,.3f,
        weights.ElementAtOrDefault(0),weights.ElementAtOrDefault(1),weights.ElementAtOrDefault(2));
    private static SourceGeometry G(params SourceVertex[] vertices) => new(vertices,Array.Empty<SourceTriangle>(),Array.Empty<SourceGeometryPart>());

    [Fact] public void TransfersOnlyProceduralWristsAndKeepsAllBonesAndRules()
    {
        var model=Model();var geometry=G(V(new SourceVertexWeight(2,.4f),new(0,.3f),new(1,.3f)),V(new SourceVertexWeight(5,1)),V(new SourceVertexWeight(6,1)),V(new SourceVertexWeight(7,1)));
        var before=model.Bones.ToArray();var result=SourceWristWeightMerger.Merge(model,geometry);
        Assert.Equal(2,result.Summary.Bones.Count);Assert.Equal(2,result.Summary.ChangedVertices);
        Assert.Equal(0,result.Geometry.Vertices[0].Weight0.BoneIndex);
        Assert.InRange(Math.Abs(result.Geometry.Vertices[0].Weight0.Weight-.7f),0,1e-6);
        Assert.Equal(new SourceVertexWeight(1,.3f),result.Geometry.Vertices[0].Weight1);
        Assert.Equal(3,result.Geometry.Vertices[1].Weight0.BoneIndex);
        Assert.Equal(geometry.Vertices[2],result.Geometry.Vertices[2]);Assert.Equal(geometry.Vertices[3],result.Geometry.Vertices[3]);
        Assert.Equal(before,model.Bones);Assert.NotNull(model.Bones[2].QuatInterp);Assert.NotNull(model.Bones[5].QuatInterp);
        Assert.Equal(2,geometry.Vertices[0].Weight0.BoneIndex);
        Assert.Same(geometry.Triangles,result.Geometry.Triangles);Assert.Same(geometry.Parts,result.Geometry.Parts);
        for(var i=0;i<geometry.Vertices.Count;i++) {
            Assert.Equal(geometry.Vertices[i].Position,result.Geometry.Vertices[i].Position);
            Assert.Equal(geometry.Vertices[i].Normal,result.Geometry.Vertices[i].Normal);
            Assert.Equal(geometry.Vertices[i].U,result.Geometry.Vertices[i].U);Assert.Equal(geometry.Vertices[i].V,result.Geometry.Vertices[i].V);
            Assert.InRange(Math.Abs(geometry.Vertices[i].Influences().Sum(w=>w.Weight)-result.Geometry.Vertices[i].Influences().Sum(w=>w.Weight)),0,1e-6);
        }
    }
    [Fact] public void NoMatchingHelpersIsAnExactNoOp()
    {
        var m=Model() with {Bones=Model().Bones.Where(b=>b.QuatInterp is null).ToArray()};var g=G(V(new SourceVertexWeight(1,1)));
        var r=SourceWristWeightMerger.Merge(m,g);Assert.Same(g,r.Geometry);Assert.Empty(r.Summary.Bones);Assert.Equal(0,r.Summary.ChangedVertices);
    }
    [Fact] public void RealHandsAndFingersAreNeverTransferred()
    {
        var m=Model();var bones=m.Bones.ToArray();bones[1]=bones[1] with {QuatInterp=new(1,Array.Empty<SourceQuatInterpTrigger>())};
        var g=G(V(new SourceVertexWeight(1,.8f),new(6,.2f)));var r=SourceWristWeightMerger.Merge(m with {Bones=bones},g);
        Assert.Equal(g.Vertices[0],r.Geometry.Vertices[0]);Assert.Equal(0,r.Summary.ChangedVertices);
    }
    [Fact] public void DuplicateTargetWeightsCoalesceWithinThreeSlots()
    {
        var r=SourceWristWeightMerger.Merge(Model(),G(V(new SourceVertexWeight(2,.5f),new(0,.5f))));
        Assert.Equal(new SourceVertexWeight(0,1),r.Geometry.Vertices[0].Weight0);Assert.Equal(0,r.Geometry.Vertices[0].Weight1.Weight);
    }
}
